/**
 * The evidence timeline.
 *
 * Each entry shows what Helios observed, when, how certain it is, and - through
 * a quoted snippet and a link to the original document - exactly where the
 * claim came from. The "View original" link is the point of the whole system:
 * a reader who distrusts a conclusion can go and check it.
 */
import type { TimelineEntry } from "@/lib/types";
import { AssertionBadge, StatusPill } from "./AssertionBadge";

function formatDate(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

function humanizeKind(kind: string): string {
  return kind.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function Timeline({ entries }: { entries: TimelineEntry[] }) {
  if (entries.length === 0) {
    return (
      <p className="muted">
        No evidence has been recorded for this site yet. That means Helios has
        not found anything, not that nothing is happening.
      </p>
    );
  }

  return (
    <ol className="timeline">
      {entries.map((entry, index) => (
        <li
          key={`${entry.entry_type}-${entry.occurred_on}-${index}`}
          className={`timeline-item ${
            entry.entry_type === "stage_transition" ? "is-stage" : "is-evidence"
          }`}
        >
          <div className="timeline-date">{formatDate(entry.occurred_on)}</div>
          <div className="timeline-title">
            {entry.title}
            {entry.evidence && (
              <AssertionBadge assertion={entry.evidence.assertion_class} />
            )}
            {entry.evidence?.is_standing_condition && (
              <StatusPill title="A statement about the current state of the world rather than a dated event. Standing conditions do not decay with age.">
                Standing condition
              </StatusPill>
            )}
            {entry.stage_transition?.is_downgrade && (
              <StatusPill tone="negative">Downgrade</StatusPill>
            )}
          </div>

          <p className="timeline-detail">{entry.detail}</p>

          {entry.evidence && <EvidenceProvenance evidence={entry.evidence} />}
          {entry.stage_transition && (
            <StageTransitionDetail transition={entry.stage_transition} />
          )}
        </li>
      ))}
    </ol>
  );
}

/**
 * Whether an evidence URL is one that can never be opened.
 *
 * Fixture replay stamps `https://example.invalid/recorded` on evidence whose
 * real URL was not retained, and RFC 2606 reserves `.invalid` precisely so it
 * can never resolve. Offering "View original evidence" against one promises the
 * reader a document that does not exist — the same failure as a contact URL
 * pointing at a repository that is not there, and a worse one here, because
 * checkable provenance is the claim this project rests on. The sha256 beside it
 * still pins the exact bytes, which is what Helios can stand behind for a
 * fixture.
 */
function isUnreachable(url: string): boolean {
  return /^https?:\/\/[^/?#]*\.invalid\b/i.test(url);
}

function EvidenceProvenance({
  evidence,
}: {
  evidence: NonNullable<TimelineEntry["evidence"]>;
}) {
  return (
    <>
      {evidence.snippet && (
        <div className="snippet" aria-label="Verbatim source excerpt">
          {evidence.snippet}
        </div>
      )}
      <div className="provenance">
        <span>
          <span className="muted">Source:</span> {evidence.source.source_name}
        </span>
        {isUnreachable(evidence.source.source_url) ? (
          <span className="muted">
            Recorded fixture — no source URL retained
          </span>
        ) : (
          <a href={evidence.source.source_url} target="_blank" rel="noreferrer">
            View original evidence
          </a>
        )}
        <span className="muted">
          Retrieved{" "}
          {new Date(evidence.source.retrieved_at).toISOString().slice(0, 10)}
        </span>
        <span
          className="mono muted"
          title="SHA-256 of the exact bytes Helios retained"
        >
          sha256:{evidence.source.content_sha256.slice(0, 12)}
        </span>
        {evidence.snippet_locator && (
          <span
            className="mono muted"
            title="Location of this fact within the source document"
          >
            {evidence.snippet_locator.startsWith("http")
              ? "OSM element"
              : evidence.snippet_locator}
          </span>
        )}
        <span className="muted">
          Extraction confidence {(evidence.confidence * 100).toFixed(0)}%
        </span>
      </div>
    </>
  );
}

function StageTransitionDetail({
  transition,
}: {
  transition: NonNullable<TimelineEntry["stage_transition"]>;
}) {
  return (
    <div className="provenance">
      <span>
        {transition.from_stage_label ?? "Unclassified"} &rarr;{" "}
        {transition.to_stage_label}
      </span>
      {transition.detection_lag_days !== null &&
        transition.detection_lag_days > 0 && (
          <span
            className="muted"
            title="Days between when the transition took effect in the world and when Helios detected it. Large values mean the evidence predated ingestion."
          >
            Detected {transition.detection_lag_days} days after the fact
          </span>
        )}
      <span className="muted">
        Confidence at transition {transition.confidence.toFixed(0)}%
      </span>
    </div>
  );
}

export { humanizeKind };
