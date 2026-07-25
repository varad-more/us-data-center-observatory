"""Immutable, content-addressed storage for fetched source documents.

Design
------
Raw bytes are stored under a key derived entirely from their SHA-256 digest::

    <prefix>/<source_slug>/<aa>/<bb>/<full-sha256><ext>

Content addressing gives three properties Helios depends on:

1. **Immutability by construction.** A key cannot be reused for different
   content, because the key *is* the content's digest. There is no code path
   that overwrites a stored document; :meth:`EvidenceStore.put` short-circuits
   when the key already exists.
2. **Free deduplication.** A permit PDF that appears unchanged in fifty nightly
   crawls is stored once.
3. **Verifiability.** :meth:`EvidenceStore.verify` re-hashes stored bytes, so
   silent corruption or tampering is detectable.

Two backends are provided behind one protocol: a local filesystem store for
development and tests, and an S3-compatible store that works against both AWS
and MinIO.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from helios_common.config import Settings, get_settings
from helios_common.hashing import content_sha256
from helios_common.logging import get_logger
from helios_common.time import utcnow

if TYPE_CHECKING:
    from datetime import datetime

logger = get_logger(__name__)

_MIME_EXTENSIONS: dict[str, str] = {
    "application/json": ".json",
    "application/geo+json": ".geojson",
    "application/pdf": ".pdf",
    "application/xml": ".xml",
    "application/zip": ".zip",
    "text/html": ".html",
    "text/csv": ".csv",
    "text/plain": ".txt",
    "text/xml": ".xml",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


def extension_for_mime(mime_type: str) -> str:
    """Return a conventional file extension for a MIME type.

    Args:
        mime_type: A MIME type, possibly with parameters (``; charset=utf-8``).

    Returns:
        A dot-prefixed extension, or ``.bin`` when unrecognised.
    """
    base = mime_type.split(";", 1)[0].strip().lower()
    return _MIME_EXTENSIONS.get(base, ".bin")


class EvidenceStoreError(RuntimeError):
    """Raised when the evidence store cannot satisfy a request."""


class ImmutabilityViolationError(EvidenceStoreError):
    """Raised when a write would change the bytes behind an existing key.

    Reaching this exception means a caller tried to do something the data model
    forbids, so it is deliberately loud rather than silently tolerated.
    """


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Metadata describing a successfully stored payload."""

    key: str
    sha256: str
    size_bytes: int
    mime_type: str
    backend: str
    stored_at: datetime
    already_existed: bool
    """True when identical content was already present, so nothing was written."""

    metadata: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class EvidenceStore(Protocol):
    """Protocol implemented by every evidence-store backend."""

    backend_name: str

    def build_key(self, source_slug: str, sha256: str, mime_type: str) -> str:
        """Compute the storage key for a payload."""
        ...

    def put(
        self,
        source_slug: str,
        payload: bytes,
        mime_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        """Store a payload, returning its metadata. Never overwrites."""
        ...

    def get(self, key: str) -> bytes:
        """Retrieve raw bytes by key."""
        ...

    def exists(self, key: str) -> bool:
        """Return whether a key is present."""
        ...

    def verify(self, key: str, expected_sha256: str) -> bool:
        """Re-hash stored content and compare against the expected digest."""
        ...


class _BaseEvidenceStore:
    """Shared key derivation for the concrete backends."""

    backend_name = "base"

    def build_key(self, source_slug: str, sha256: str, mime_type: str) -> str:
        """Derive a content-addressed key.

        The two-level ``aa/bb`` fan-out keeps directory listings manageable on
        filesystem backends and spreads S3 key prefixes, which matters once a
        source has produced hundreds of thousands of documents.

        Args:
            source_slug: Registry slug of the owning source.
            sha256: Hex digest of the payload.
            mime_type: MIME type, used only to pick a readable extension.

        Returns:
            A relative storage key.
        """
        safe_slug = source_slug.strip().lower().replace("/", "-") or "unknown-source"
        return f"{safe_slug}/{sha256[:2]}/{sha256[2:4]}/{sha256}{extension_for_mime(mime_type)}"


class FilesystemEvidenceStore(_BaseEvidenceStore):
    """Local-filesystem evidence store for development and tests.

    Each payload is written alongside a ``.meta.json`` sidecar recording the
    MIME type, size, and store time, so the archive remains interpretable
    without the database.
    """

    backend_name = "filesystem"

    def __init__(self, root: Path) -> None:
        """Initialise the store.

        Args:
            root: Directory that will contain the archive. Created if absent.
        """
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        # Defends against a crafted source slug escaping the archive root.
        if not candidate.is_relative_to(self.root):
            raise EvidenceStoreError(f"Storage key escapes archive root: {key!r}")
        return candidate

    def put(
        self,
        source_slug: str,
        payload: bytes,
        mime_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        """Store a payload if not already present.

        Args:
            source_slug: Registry slug of the owning source.
            payload: Raw bytes exactly as received.
            mime_type: MIME type reported by the source.
            metadata: Optional extra key/value pairs for the sidecar.

        Returns:
            Metadata for the stored (or pre-existing) object.

        Raises:
            ImmutabilityViolationError: If existing content at the key does not
                match the payload digest, which would indicate corruption.
        """
        digest = content_sha256(payload)
        key = self.build_key(source_slug, digest, mime_type)
        path = self._path_for(key)
        now = utcnow()

        if path.exists():
            existing = path.read_bytes()
            if content_sha256(existing) != digest:
                raise ImmutabilityViolationError(
                    f"Existing object at {key!r} does not match its content hash"
                )
            logger.debug("evidence_store.deduplicated", key=key, sha256=digest)
            return StoredObject(
                key=key,
                sha256=digest,
                size_bytes=len(payload),
                mime_type=mime_type,
                backend=self.backend_name,
                stored_at=now,
                already_existed=True,
                metadata=metadata or {},
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temporary sibling then rename, so a crashed process cannot
        # leave a truncated file that would later fail hash verification.
        tmp_path = path.with_suffix(path.suffix + ".partial")
        tmp_path.write_bytes(payload)
        tmp_path.replace(path)

        sidecar = {
            "sha256": digest,
            "mime_type": mime_type,
            "size_bytes": len(payload),
            "stored_at": now.isoformat(),
            "source_slug": source_slug,
            **(metadata or {}),
        }
        path.with_suffix(path.suffix + ".meta.json").write_text(
            json.dumps(sidecar, indent=2, sort_keys=True), encoding="utf-8"
        )

        logger.info(
            "evidence_store.stored",
            key=key,
            sha256=digest,
            size_bytes=len(payload),
            mime_type=mime_type,
        )
        return StoredObject(
            key=key,
            sha256=digest,
            size_bytes=len(payload),
            mime_type=mime_type,
            backend=self.backend_name,
            stored_at=now,
            already_existed=False,
            metadata=metadata or {},
        )

    def get(self, key: str) -> bytes:
        """Read stored bytes.

        Args:
            key: Storage key returned by :meth:`put`.

        Returns:
            The stored payload.

        Raises:
            EvidenceStoreError: If the key is absent.
        """
        path = self._path_for(key)
        if not path.exists():
            raise EvidenceStoreError(f"No stored object for key {key!r}")
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        """Return whether a key is present."""
        return self._path_for(key).exists()

    def verify(self, key: str, expected_sha256: str) -> bool:
        """Re-hash the stored payload and compare with the expected digest."""
        try:
            return content_sha256(self.get(key)) == expected_sha256
        except EvidenceStoreError:
            return False

    def clear(self) -> None:
        """Delete the entire archive.

        Test-support only. Production archives are append-only, and this method
        is never invoked by application code.
        """
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)


class S3EvidenceStore(_BaseEvidenceStore):
    """S3-compatible evidence store, usable against AWS S3 or MinIO.

    Object-lock or a bucket policy denying ``s3:DeleteObject`` should be applied
    in production; this class enforces immutability at the application layer by
    never issuing a put for an existing key.
    """

    backend_name = "s3"

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        region_name: str = "us-west-2",
        client: Any | None = None,
    ) -> None:
        """Initialise the store.

        Args:
            bucket: Target bucket name.
            endpoint_url: Override for MinIO or another S3-compatible service.
            region_name: AWS region.
            client: Pre-built boto3 client, primarily for tests.
        """
        self.bucket = bucket
        if client is not None:
            self._client = client
        else:
            import boto3  # imported lazily so filesystem-only runs skip the dependency

            self._client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region_name)

    def put(
        self,
        source_slug: str,
        payload: bytes,
        mime_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        """Store a payload if not already present."""
        digest = content_sha256(payload)
        key = self.build_key(source_slug, digest, mime_type)
        now = utcnow()

        if self.exists(key):
            logger.debug("evidence_store.deduplicated", key=key, sha256=digest, backend="s3")
            return StoredObject(
                key=key,
                sha256=digest,
                size_bytes=len(payload),
                mime_type=mime_type,
                backend=self.backend_name,
                stored_at=now,
                already_existed=True,
                metadata=metadata or {},
            )

        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=payload,
            ContentType=mime_type,
            ChecksumSHA256=None if metadata is None else metadata.get("checksum_sha256"),
            Metadata={
                "sha256": digest,
                "source-slug": source_slug,
                "stored-at": now.isoformat(),
                **{k.replace("_", "-"): v for k, v in (metadata or {}).items()},
            },
        )
        logger.info("evidence_store.stored", key=key, sha256=digest, backend="s3")
        return StoredObject(
            key=key,
            sha256=digest,
            size_bytes=len(payload),
            mime_type=mime_type,
            backend=self.backend_name,
            stored_at=now,
            already_existed=False,
            metadata=metadata or {},
        )

    def get(self, key: str) -> bytes:
        """Read stored bytes.

        Raises:
            EvidenceStoreError: If the object is missing or unreadable.
        """
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:  # boto3 raises client-specific errors
            raise EvidenceStoreError(f"No stored object for key {key!r}") from exc
        body: bytes = response["Body"].read()
        return body

    def exists(self, key: str) -> bool:
        """Return whether a key is present."""
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
        except Exception:
            return False
        return True

    def verify(self, key: str, expected_sha256: str) -> bool:
        """Re-hash the stored payload and compare with the expected digest."""
        try:
            return content_sha256(self.get(key)) == expected_sha256
        except EvidenceStoreError:
            return False


def build_evidence_store(settings: Settings | None = None) -> EvidenceStore:
    """Construct the configured evidence store backend.

    Args:
        settings: Configuration to use; defaults to process settings.

    Returns:
        A ready-to-use store.
    """
    cfg = settings or get_settings()
    if cfg.evidence_backend == "s3":
        return S3EvidenceStore(
            cfg.evidence_bucket,
            endpoint_url=cfg.s3_endpoint_url,
            region_name=cfg.s3_region,
        )
    return FilesystemEvidenceStore(cfg.evidence_root)


__all__ = [
    "EvidenceStore",
    "EvidenceStoreError",
    "FilesystemEvidenceStore",
    "ImmutabilityViolationError",
    "S3EvidenceStore",
    "StoredObject",
    "build_evidence_store",
    "extension_for_mime",
]
