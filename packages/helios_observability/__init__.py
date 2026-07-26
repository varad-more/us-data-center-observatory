"""Observability helpers for Helios.

This package is intentionally thin in the first sprint. Connector-run telemetry
lives on ``ConnectorRun`` rows and structured logs; a dedicated metrics/export
layer is deferred until there is a measured need beyond Compose logs.
"""

from helios_connectors.registry import registry_coverage_summary

__all__ = ["registry_coverage_summary"]
