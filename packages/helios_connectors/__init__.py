"""Source connectors, the source registry, and the ingestion pipeline.

Connectors are imported from their own modules rather than re-exported here.
Eager re-exports would pull every connector's dependencies into scope on any
import of this package - including optional ones such as PyMuPDF - which makes
a default install unusable for anyone working only on the API or the frontend.
The registry refers to connectors by entry-point string for the same reason.
"""
