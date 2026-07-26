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
    is_true_positive: bool = False
    is_false_positive: bool = False
    is_false_negative: bool = False
    lead_time_days: int | None = None
    estimated_power_mw: float | None = None


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

    @property
    def precision(self) -> float:
        """Identity precision (TP / (TP + FP))."""
        tp = sum(1 for c in self.cases if c.is_true_positive)
        fp = sum(1 for c in self.cases if c.is_false_positive)
        return tp / (tp + fp) if (tp + fp) > 0 else 0.0

    @property
    def recall(self) -> float:
        """Identity recall (TP / (TP + FN))."""
        tp = sum(1 for c in self.cases if c.is_true_positive)
        fn = sum(1 for c in self.cases if c.is_false_negative)
        return tp / (tp + fn) if (tp + fn) > 0 else 0.0

    @property
    def avg_lead_time_days(self) -> float | None:
        """Average lead time for true positive operational cases."""
        times = [c.lead_time_days for c in self.cases if c.lead_time_days is not None]
        return (sum(times) / len(times)) if times else None

    def generate_research_report(self) -> str:
        """Generate a markdown report of the backtest evaluation."""
        lines = [
            "# Helios Phase 4: Backtesting & Research Evaluation",
            "",
            "## Aggregate Metrics",
            f"- **Total Cases Evaluated**: {self.total}",
            f"- **Stage Accuracy**: {self.accuracy:.1%}",
            f"- **Identity Precision**: {self.precision:.1%}",
            f"- **Identity Recall**: {self.recall:.1%}",
        ]
        
        if self.avg_lead_time_days is not None:
            lines.append(f"- **Average Lead Time**: {self.avg_lead_time_days:.1f} days")
        else:
            lines.append("- **Average Lead Time**: N/A (no operational cases identified)")
            
        lines.append("")
        lines.append("## Case Details")
        lines.append("| Project | As Of | Expected | Predicted | Lead Time (days) | Est. Power (MW) | OK |")
        lines.append("|---|---|---|---|---|---|---|")
        
        for case in self.cases:
            pred = str(case.predicted_stage) if case.predicted_stage is not None else "None"
            lt = str(case.lead_time_days) if case.lead_time_days is not None else "N/A"
            power = f"{case.estimated_power_mw:.1f}" if case.estimated_power_mw is not None else "N/A"
            ok = "✅" if case.passed else "❌"
            lines.append(f"| {case.project_code} | {case.as_of} | {case.expected_min_stage}-{case.expected_max_stage} | {pred} | {lt} | {power} | {ok} |")

        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        """Serialise for CLI / API output."""
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.total - self.passed,
            "accuracy": round(self.accuracy, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "avg_lead_time_days": self.avg_lead_time_days,
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
        predicted = int(outcome.stage_score.implied_stage)
        passed = case.expected_min_stage <= predicted <= case.expected_max_stage
        
        identity_confidence = outcome.identity_score.confidence
        identified_as_dc = identity_confidence >= 50.0
        expected_as_dc = case.expected_max_stage > 0
        
        is_true_positive = identified_as_dc and expected_as_dc
        is_false_positive = identified_as_dc and not expected_as_dc
        is_false_negative = not identified_as_dc and expected_as_dc
        
        lead_time_days = None
        if expected_as_dc and predicted >= 7 and site.first_signal_date:
            lead_time_days = (case.as_of - site.first_signal_date).days
            
        estimated_power_mw = None
        if site.total_acres:
            estimated_power_mw = float(site.total_acres) * 2.0

        report.cases.append(
            BacktestCaseResult(
                project_code=case.project_code,
                as_of=case.as_of,
                expected_min_stage=case.expected_min_stage,
                expected_max_stage=case.expected_max_stage,
                predicted_stage=predicted,
                confidence=identity_confidence,
                passed=passed,
                is_true_positive=is_true_positive,
                is_false_positive=is_false_positive,
                is_false_negative=is_false_negative,
                lead_time_days=lead_time_days,
                estimated_power_mw=estimated_power_mw,
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


def run_time_sliced_backtest(
    session: Session,
    cases: list[BacktestCase] | None = None,
    *,
    cases_path: Path | None = None,
) -> BacktestReport:
    """Evaluate historical stage expectations in quarterly time slices."""
    from dateutil.relativedelta import relativedelta
    
    selected = cases if cases is not None else load_cases(cases_path)
    sliced_cases: list[BacktestCase] = []
    
    for case in selected:
        current_date = date(2020, 1, 1)
        if current_date > case.as_of:
            sliced_cases.append(case)
            continue
            
        while current_date < case.as_of:
            sliced_cases.append(
                BacktestCase(
                    project_code=case.project_code,
                    as_of=current_date,
                    expected_min_stage=0,  # Relax min bounds for intermediate history
                    expected_max_stage=case.expected_max_stage,
                    notes=f"Time-slice for {case.project_code}",
                )
            )
            current_date += relativedelta(months=3)
            
        sliced_cases.append(case)

    return run_backtest(session, sliced_cases)


__all__ = [
    "DEFAULT_CASES_PATH",
    "BacktestCase",
    "BacktestCaseResult",
    "BacktestReport",
    "load_cases",
    "run_backtest",
    "run_time_sliced_backtest",
]
