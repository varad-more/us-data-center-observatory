"""The ``helios`` command-line interface.

Every operational task is exposed here so that local development, CI, and the
Docker Compose entrypoint all drive the same code paths the API does.
"""

from __future__ import annotations

import json
from datetime import date
from functools import partial
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select

from helios_common.config import get_settings
from helios_common.evidence_store import build_evidence_store
from helios_common.logging import configure_logging
from helios_common.vocabulary import ConnectorStatus
from helios_connectors.area_totals import (
    EiaStateElectricityConnector,
    EiaStateGenerationCapacityConnector,
    UsgsCountyWaterConnector,
)
from helios_connectors.azcc_edocket import AzccEdocketConnector
from helios_connectors.epa_echo import HOSTING_NAICS_QUERY, EpaEchoAirConnector
from helios_connectors.maricopa_assessor import MaricopaAssessorConnector
from helios_connectors.mesa_permits import MesaBuildingPermitsConnector
from helios_connectors.osm_power import OsmPowerConnector
from helios_connectors.pipeline import IngestionPipeline
from helios_connectors.registry import SOURCE_REGISTRY, registry_coverage_summary
from helios_connectors.replay import (
    FIXTURE_INGEST_ORDER,
    FixtureNotFoundError,
    build_fixture_connector,
)
from helios_connectors.sync import sync_registry
from helios_domain.models import (
    EvidenceRecord,
    Parcel,
    Site,
    Source,
    SourceDocument,
    Substation,
)
from helios_domain.ontology import DevelopmentStage
from helios_domain.regions import DEFAULT_REGION_SLUG, get_region
from helios_domain.session import session_scope
from helios_geospatial.site_builder import build_sites
from helios_scoring.backtest import run_backtest
from helios_scoring.service import recalculate_site

app = typer.Typer(
    name="helios",
    help="Helios Open AI Infrastructure Observatory - operational CLI.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

STUDY_REGION = get_region(DEFAULT_REGION_SLUG)

EAST_VALLEY_CITY_SQL = "PropertyCity IN ({})".format(
    ",".join(f"'{city}'" for city in STUDY_REGION.cities_upper)
)
"""Assessor query fragment, derived so it cannot drift from the region."""

CONNECTORS: dict[str, Any] = {
    "maricopa-assessor-parcels": MaricopaAssessorConnector,
    "osm-power-infrastructure": OsmPowerConnector,
    "epa-echo-air-facilities": EpaEchoAirConnector,
    # The same connector asking the other question it can ask. City mode reads
    # the six pilot cities; this reads every state at once by hosting NAICS, and
    # is a separate recorded document rather than a wider version of the first.
    "epa-echo-air-facilities-national": partial(
        EpaEchoAirConnector, naics_codes=HOSTING_NAICS_QUERY, state=None
    ),
    "mesa-building-permits": MesaBuildingPermitsConnector,
    "azcc-edocket": AzccEdocketConnector,
    "usgs-county-water-use": UsgsCountyWaterConnector,
    "eia-state-electricity-sales": EiaStateElectricityConnector,
    "eia-state-generation-capacity": EiaStateGenerationCapacityConnector,
}

AREA_TOTAL_SCOPES: dict[str, dict[str, Any]] = {
    # Both files are national. Narrowing on ingest keeps the database to the
    # areas Helios can actually put a site in; --nationwide lifts it.
    "usgs-county-water-use": {"counties": STUDY_REGION.county_fips},
    "eia-state-electricity-sales": {"states": (STUDY_REGION.state_code,)},
    "eia-state-generation-capacity": {"states": (STUDY_REGION.state_code,)},
}


@app.callback()
def main(
    log_level: Annotated[str, typer.Option(help="Logging level")] = "INFO",
    log_format: Annotated[str, typer.Option(help="json or console")] = "console",
) -> None:
    """Configure logging before any subcommand runs."""
    configure_logging(log_level, log_format)


# ------------------------------------------------------------------ registry --


@app.command("registry-sync")
def registry_sync() -> None:
    """Load the declarative source registry into the database."""
    with session_scope() as session:
        result = sync_registry(session)
    console.print(
        f"[green]Synchronised[/green] {result['sources']} sources "
        f"and {result['connectors']} connectors."
    )


@app.command("registry-show")
def registry_show() -> None:
    """Print the source registry, including sources Helios cannot access."""
    table = Table(title="Helios Source Registry", show_lines=False)
    table.add_column("Slug", style="cyan", no_wrap=True)
    table.add_column("Category")
    table.add_column("Status")
    table.add_column("Licence")
    table.add_column("Limitation", max_width=48)

    for entry in SOURCE_REGISTRY:
        status_style = {
            "implemented": "green",
            "fixture_only": "yellow",
            "planned": "dim",
            "withdrawn": "red",
        }.get(str(entry.connector_status), "white")
        table.add_row(
            entry.slug,
            str(entry.category),
            f"[{status_style}]{entry.connector_status}[/{status_style}]",
            entry.license_name or "-",
            (entry.access_limitation or "")[:200],
        )

    console.print(table)
    console.print(f"Coverage: {registry_coverage_summary()}")


# ----------------------------------------------------------------- ingestion --


@app.command("ingest")
def ingest(
    connector_slug: Annotated[str, typer.Argument(help="Connector to run")],
    where: Annotated[str | None, typer.Option(help="Attribute filter, if supported")] = None,
    east_valley_data_centers: Annotated[
        bool,
        typer.Option(
            help=(
                "Shorthand for the assessor connector: East Valley parcels the county "
                "classifies as DATA CENTERS."
            )
        ),
    ] = False,
    nationwide: Annotated[
        bool,
        typer.Option(
            help=(
                "Drop the study-region narrowing. EPA ECHO queries every state by "
                "hosting NAICS code instead of enumerating cities; the area-total "
                "connectors keep every county or state in the published file."
            )
        ),
    ] = False,
    fixture: Annotated[
        bool,
        typer.Option(help="Replay recorded fixtures instead of reaching the live source"),
    ] = False,
) -> None:
    """Run one connector against its live source, or against recorded fixtures."""
    if connector_slug not in CONNECTORS:
        console.print(f"[red]Unknown connector[/red] {connector_slug!r}")
        console.print(f"Available: {', '.join(sorted(CONNECTORS))}")
        raise typer.Exit(code=1)

    settings = get_settings()
    kwargs: dict[str, Any] = {}

    if fixture:
        # Replay ignores live query narrowing: the recorded bytes already are
        # the response the query would have produced. The area-total scopes are
        # the exception -- they narrow during parsing, not during fetching, so
        # they must still be applied or a replay would load more than a live run.
        try:
            connector = build_fixture_connector(
                connector_slug, settings=settings, **AREA_TOTAL_SCOPES.get(connector_slug, {})
            )
        except (KeyError, FixtureNotFoundError) as exc:
            console.print(f"[red]No fixture available[/red] {exc}")
            raise typer.Exit(code=1) from exc
        mode = "fixture"
    else:
        if east_valley_data_centers:
            kwargs["where"] = f"PropertyUseDescription='DATA CENTERS' AND {EAST_VALLEY_CITY_SQL}"
        elif where:
            kwargs["where"] = where

        if connector_slug in AREA_TOTAL_SCOPES:
            kwargs = dict(AREA_TOTAL_SCOPES[connector_slug])

        if nationwide:
            if connector_slug.startswith("epa-echo-air-facilities"):
                # state=None drops the p_st narrowing, leaving the NAICS filter alone.
                kwargs = {"naics_codes": HOSTING_NAICS_QUERY, "state": None}
            elif connector_slug in AREA_TOTAL_SCOPES:
                # The file is downloaded whole either way; this only stops the
                # parser discarding the areas outside the study region.
                kwargs = {}
            else:
                console.print(f"[red]--nationwide does not apply to[/red] {connector_slug!r}")
                raise typer.Exit(code=1)

        # Fixture-only connectors never take constructor kwargs meant for live queries.
        if connector_slug == "azcc-edocket":
            kwargs = {}

        connector = CONNECTORS[connector_slug](settings=settings, **kwargs)
        mode = (
            "fixture" if connector.get_metadata().status == ConnectorStatus.FIXTURE_ONLY else "live"
        )
    try:
        with session_scope() as session:
            summary = IngestionPipeline(
                session,
                connector,
                build_evidence_store(settings),
                mode=mode,
                trigger="cli",
            ).run()
    finally:
        connector.close()

    console.print_json(json.dumps(summary.as_dict(), indent=2))
    if summary.status != "success":
        raise typer.Exit(code=1)


@app.command("health-check")
def health_check(
    connector_slug: Annotated[str, typer.Argument(help="Connector to probe")],
) -> None:
    """Probe a source's reachability without ingesting anything."""
    if connector_slug not in CONNECTORS:
        console.print(f"[red]Unknown connector[/red] {connector_slug!r}")
        raise typer.Exit(code=1)

    connector = CONNECTORS[connector_slug](settings=get_settings())
    try:
        result = connector.health_check()
    finally:
        connector.close()

    colour = "green" if result.healthy else "red"
    console.print(f"[{colour}]{'healthy' if result.healthy else 'unhealthy'}[/{colour}]")
    console.print(
        f"  status={result.http_status} latency={result.latency_ms}ms "
        f"message={result.message or '-'}"
    )
    console.print(f"  detail={result.detail}")
    if not result.healthy:
        raise typer.Exit(code=1)


# -------------------------------------------------------------------- sites --


@app.command("build-sites")
def build_sites_command() -> None:
    """Cluster parcels into sites and link infrastructure dependencies."""
    with session_scope() as session:
        result = build_sites(session, region=STUDY_REGION)
    console.print(
        f"[green]Sites[/green] created={result.sites_created} updated={result.sites_updated} "
        f"parcels_linked={result.parcels_linked} "
        f"dependencies={result.dependencies_created}"
    )


@app.command("score")
def score(
    project_code: Annotated[
        str | None, typer.Option(help="Score one site; omit to score all")
    ] = None,
) -> None:
    """Recalculate confidence scores and record any stage transitions."""
    with session_scope() as session:
        statement = select(Site)
        if project_code:
            statement = statement.where(Site.project_code == project_code)
        sites = session.scalars(statement).all()

        if not sites:
            console.print("[yellow]No sites to score.[/yellow]")
            return

        table = Table(title="Scoring results")
        table.add_column("Project", style="cyan")
        table.add_column("Stage")
        table.add_column("Confidence", justify="right")
        table.add_column("Evidence", justify="right")
        table.add_column("Kinds", justify="right")

        for site in sites:
            outcome = recalculate_site(session, site)
            table.add_row(
                site.project_code,
                f"{outcome.new_stage.value} {outcome.new_stage.label}",
                f"{outcome.identity_score.confidence:.1f}% / {outcome.stage_score.confidence:.1f}%",
                str(outcome.identity_score.evidence_considered),
                str(outcome.identity_score.distinct_kinds),
            )

    console.print(table)


@app.command("explain")
def explain(
    project_code: Annotated[str, typer.Argument(help="Site project code")],
    as_of: Annotated[str | None, typer.Option(help="Historical cutoff, YYYY-MM-DD")] = None,
) -> None:
    """Print why Helios reached its conclusion about a site."""
    from helios_scoring.rules import score_site
    from helios_scoring.service import load_evidence_inputs

    cutoff = date.fromisoformat(as_of) if as_of else None

    with session_scope() as session:
        site = session.scalar(select(Site).where(Site.project_code == project_code))
        if site is None:
            console.print(f"[red]No site[/red] with project code {project_code!r}")
            raise typer.Exit(code=1)

        evidence = load_evidence_inputs(session, site.id, as_of=cutoff)
        identity_result = score_site(evidence, as_of=cutoff or date.today(), target="identity")
        stage_result = score_site(evidence, as_of=cutoff or date.today(), target="stage")

        console.print(f"\n[bold cyan]{site.project_code}[/bold cyan] - {site.jurisdiction}")
        console.print(f"  {site.summary}\n")
        console.print(
            f"  Stage      : {stage_result.implied_stage.value} {stage_result.implied_stage.label}"
        )
        console.print(f"  Id. Conf.  : {identity_result.confidence:.1f}% ({identity_result.band})")
        console.print(f"  Stage Conf.: {stage_result.confidence:.1f}% ({stage_result.band})")
        console.print(f"  As of      : {identity_result.as_of.isoformat()}\n")

        table = Table(title="Identity Score Contributions")
        table.add_column("Weight", justify="right")
        table.add_column("Rule", style="cyan")
        table.add_column("Detail", max_width=70)

        for contribution in identity_result.contributions:
            colour = "green" if contribution.applied_weight > 0 else "red"
            table.add_row(
                f"[{colour}]{contribution.applied_weight:+.2f}[/{colour}]",
                contribution.label,
                contribution.detail,
            )
        console.print(table)

        stage_table = Table(title="Stage Score Contributions")
        stage_table.add_column("Weight", justify="right")
        stage_table.add_column("Rule", style="cyan")
        stage_table.add_column("Detail", max_width=70)

        for contribution in stage_result.contributions:
            colour = "green" if contribution.applied_weight > 0 else "red"
            stage_table.add_row(
                f"[{colour}]{contribution.applied_weight:+.2f}[/{colour}]",
                contribution.label,
                contribution.detail,
            )
        console.print(stage_table)

        for note in identity_result.notes:
            console.print(f"  [yellow]note (identity)[/yellow] {note}")
        for note in stage_result.notes:
            console.print(f"  [yellow]note (stage)[/yellow] {note}")


# -------------------------------------------------------------------- status --


@app.command("status")
def status() -> None:
    """Summarise what is currently in the database."""
    with session_scope() as session:
        counts = {
            "sources": session.scalar(select(func.count()).select_from(Source)),
            "documents": session.scalar(select(func.count()).select_from(SourceDocument)),
            "parcels": session.scalar(select(func.count()).select_from(Parcel)),
            "substations": session.scalar(select(func.count()).select_from(Substation)),
            "sites": session.scalar(select(func.count()).select_from(Site)),
            "evidence": session.scalar(select(func.count()).select_from(EvidenceRecord)),
        }

        table = Table(title="Helios database status")
        table.add_column("Entity", style="cyan")
        table.add_column("Count", justify="right")
        for key, value in counts.items():
            table.add_row(key, str(value))
        console.print(table)

        sites = session.scalars(
            select(Site).order_by(Site.current_confidence.desc().nullslast()).limit(10)
        ).all()
        if not sites:
            return

        site_table = Table(title="Top sites by confidence")
        site_table.add_column("Project", style="cyan")
        site_table.add_column("City")
        site_table.add_column("Stage")
        site_table.add_column("Confidence", justify="right")
        site_table.add_column("Acres", justify="right")
        site_table.add_column("Evidence", justify="right")

        for site in sites:
            site_table.add_row(
                site.project_code,
                site.jurisdiction or "-",
                DevelopmentStage(site.current_stage).label,
                f"{site.current_confidence:.1f}%",
                f"{float(site.total_acres):.1f}" if site.total_acres else "-",
                str(site.evidence_count),
            )
        console.print(site_table)


@app.command("backtest")
def backtest(
    cases: Annotated[
        str | None,
        typer.Option(help="Path to backtest cases JSON; defaults to East Valley fixture"),
    ] = None,
    time_sliced: Annotated[
        bool,
        typer.Option(help="Evaluate history in quarterly slices up to target date"),
    ] = False,
    report: Annotated[
        bool,
        typer.Option(help="Generate a markdown research report to research_report.md"),
    ] = False,
) -> None:
    """Replay historical cutoffs without mutating live site stage."""
    from pathlib import Path

    from helios_scoring.backtest import run_time_sliced_backtest

    with session_scope() as session:
        cases_path = Path(cases) if cases else None
        if time_sliced:
            report_data = run_time_sliced_backtest(session, cases_path=cases_path)
        else:
            report_data = run_backtest(session, cases_path=cases_path)

    table = Table(title="Backtest results")
    table.add_column("Project", style="cyan")
    table.add_column("As of")
    table.add_column("Predicted", justify="right")
    table.add_column("Expected")
    table.add_column("OK")
    for case in report_data.cases:
        table.add_row(
            case.project_code,
            case.as_of.isoformat(),
            "-" if case.predicted_stage is None else str(case.predicted_stage),
            f"{case.expected_min_stage}-{case.expected_max_stage}",
            "[green]pass[/green]" if case.passed else "[red]fail[/red]",
        )
    console.print(table)
    console.print(
        f"Accuracy: {report_data.passed}/{report_data.total} ({report_data.accuracy:.0%})"
    )
    console.print(f"Precision: {report_data.precision:.0%} | Recall: {report_data.recall:.0%}")

    if report:
        report_path = Path("research_report.md")
        report_path.write_text(report_data.generate_research_report(), encoding="utf-8")
        console.print(f"[green]Research report written to {report_path}[/green]")

    if report_data.passed < report_data.total and not time_sliced:
        raise typer.Exit(code=1)


@app.command("bootstrap")
def bootstrap(
    live: Annotated[
        bool, typer.Option(help="Fetch from live public sources rather than recorded fixtures")
    ] = False,
) -> None:
    """Run the full pipeline: registry, ingestion, site building, and scoring.

    This is the single command that takes an empty database to a browsable
    observatory.

    Fixtures are the default so that a fresh clone, a test run, and CI never
    put load on county servers, and so that the resulting database is
    reproducible. Pass ``--live`` to fetch current records instead.
    """
    console.rule("[bold]1/4 Source registry")
    registry_sync()

    console.rule("[bold]2/4 Ingestion")
    if live:
        _ingest_live()
    else:
        _ingest_fixtures()

    console.rule("[bold]3/4 Site construction")
    build_sites_command()

    console.rule("[bold]4/4 Scoring")
    score()

    console.rule("[bold]Done")
    status()


def _ingest_fixtures() -> None:
    """Replay every recorded source, in dependency order."""
    console.print("[cyan]Fixture mode[/cyan] - replaying recorded payloads, no network access.")
    for slug in FIXTURE_INGEST_ORDER:
        ingest(slug, fixture=True)


def _ingest_live() -> None:
    """Fetch from live public sources, tolerating the flaky ones."""
    console.print("[yellow]Live mode[/yellow] - fetching from public sources.")
    ingest("maricopa-assessor-parcels", east_valley_data_centers=True)
    ingest("osm-power-infrastructure")
    # EPA may 429 under load; failures are non-fatal for bootstrap so the
    # observatory still stands on assessor + OSM (+ ACC fixtures).
    for echo_slug in ("epa-echo-air-facilities", "epa-echo-air-facilities-national"):
        try:
            ingest(echo_slug)
        except typer.Exit:
            console.print(
                f"[yellow]{echo_slug} ingest failed (often rate-limit). "
                f"Continuing with remaining sources; re-run "
                f"`helios ingest {echo_slug}` later.[/yellow]"
            )
    # Mesa permits need assessor parcels already loaded for address matching.
    try:
        ingest("mesa-building-permits")
    except typer.Exit:
        console.print(
            "[yellow]Mesa permits ingest failed. Continuing; re-run "
            "`helios ingest mesa-building-permits` later.[/yellow]"
        )
    # Area totals are large annual publications on stable federal hosts. They
    # are independent of everything above, so a failure here costs the context
    # figures and nothing else.
    for slug in (
        "usgs-county-water-use",
        "eia-state-electricity-sales",
        "eia-state-generation-capacity",
    ):
        try:
            ingest(slug)
        except typer.Exit:
            console.print(
                f"[yellow]{slug} ingest failed. The observatory stands without it, "
                f"but per-site estimates will have no reported total to sit "
                f"against. Re-run `helios ingest {slug}` later.[/yellow]"
            )
    ingest("azcc-edocket")


if __name__ == "__main__":  # pragma: no cover
    app()
