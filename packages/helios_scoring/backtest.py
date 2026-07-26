"""Historical replay harness for the rule-based scoring model.

Backtests never mutate live site stage. Each case scores a site at an
``as_of`` cutoff with ``is_backtest=True`` and compares the implied stage to an
expected band. Cases are deliberately sparse until a labelled corpus exists;
the harness exists so calibration work has a place to land.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from helios_common.logging import get_logger
from helios_common.time import utcnow
from helios_domain.models import Site
from helios_domain.ontology import DevelopmentStage
from helios_scoring.service import recalculate_site

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_logger(__name__)

DEFAULT_CASES_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "backtest"
    / "east_valley_cases.json"
)


@dataclass(frozen=True, slots=True)
class BacktestCase:
    """One labelled historical expectation for a site."""

    project_code: str
    as_of: date
    expected_min_stage: int
    expected_max_stage: int
    notes: str = ""


@dataclass(slots=True)
class BacktestCaseResult:
    """Outcome of evaluating one case."""

    project_code: str
    as_of: date
    expected_min_stage: int
    expected_max_stage: int
    predicted_stage: int | None
    confidence: float | None
    passed: bool
    detail: str


@dataclass(slots=True)
class BacktestReport:
    """Aggregate backtest metrics."""

    cases: list[BacktestCaseResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Number of cases evaluated."""
        return len(self.cases)

    @property
    def passed(self) -> int:
        """Number of cases within the expected stage band."""
        return sum(1 for case in self.cases if case.passed)

    @property
    def accuracy(self) -> float:
        """Share of cases that passed."""
        return (self.passed / self.total) if self.total else 0.0

    def as_dict(self) -> dict[str, Any]:
        """Serialise for CLI / API output."""
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.total - self.passed,
            "accuracy": round(self.accuracy, 4),
            "cases": [asdict(case) for case in self.cases],
        }


def load_cases(path: Path | None = None) -> list[BacktestCase]:
    """Load backtest cases from a JSON file.

    Args:
        path: Path to the cases file; defaults to the East Valley fixture.

    Returns:
        Parsed cases.
    """
    cases_path = path or DEFAULT_CASES_PATH
    payload = json.loads(cases_path.read_text(encoding="utf-8"))
    cases: list[BacktestCase] = []
    for row in payload.get("cases", []):
        cases.append(
            BacktestCase(
                project_code=str(row["project_code"]),
                as_of=_parse_as_of(row["as_of"]),
                expected_min_stage=int(row["expected_min_stage"]),
                expected_max_stage=int(row["expected_max_stage"]),
                notes=str(row.get("notes") or ""),
            )
        )
    return cases


def _parse_as_of(value: object) -> date:
    """Parse an ISO date or the literal ``today`` (UTC calendar date)."""
    text = str(value).strip().lower()
    if text == "today":
        return utcnow().date()
    return date.fromisoformat(str(value)[:10])


def run_backtest(
    session: Session,
    cases: list[BacktestCase] | None = None,
    *,
    cases_path: Path | None = None,
) -> BacktestReport:
    """Evaluate historical stage expectations without mutating live site state.

    Args:
        session: Open database session.
        cases: Explicit cases; otherwise loaded from ``cases_path``.
        cases_path: Optional override for the cases JSON file.

    Returns:
        Aggregate report.
    """
    selected = cases if cases is not None else load_cases(cases_path)
    report = BacktestReport()

    for case in selected:
        site = session.scalar(select(Site).where(Site.project_code == case.project_code))
        if site is None:
            report.cases.append(
                BacktestCaseResult(
                    project_code=case.project_code,
                    as_of=case.as_of,
                    expected_min_stage=case.expected_min_stage,
                    expected_max_stage=case.expected_max_stage,
                    predicted_stage=None,
                    confidence=None,
                    passed=False,
                    detail="site not found",
                )
            )
            continue

        outcome = recalculate_site(session, site, as_of=case.as_of, is_backtest=True)
        predicted = int(outcome.score.implied_stage)
        passed = case.expected_min_stage <= predicted <= case.expected_max_stage
        report.cases.append(
            BacktestCaseResult(
                project_code=case.project_code,
                as_of=case.as_of,
                expected_min_stage=case.expected_min_stage,
                expected_max_stage=case.expected_max_stage,
                predicted_stage=predicted,
                confidence=outcome.score.confidence,
                passed=passed,
                detail=(
                    f"{DevelopmentStage(predicted).label}; "
                    f"expected {case.expected_min_stage}-{case.expected_max_stage}"
                    + (f"; {case.notes}" if case.notes else "")
                ),
            )
        )
        logger.info(
            "backtest.case",
            project_code=case.project_code,
            as_of=case.as_of.isoformat(),
            predicted=predicted,
            passed=passed,
        )

    return report


__all__ = [
    "DEFAULT_CASES_PATH",
    "BacktestCase",
    "BacktestCaseResult",
    "BacktestReport",
    "load_cases",
    "run_backtest",
]
