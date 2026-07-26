"""Tests for backtest harness and evaluation metrics."""

import pytest
from datetime import date

from helios_scoring.backtest import BacktestReport, BacktestCaseResult

pytestmark = pytest.mark.unit

def test_backtest_report_metrics():
    """Test calculation of precision, recall, lead time, and power estimation."""
    cases = [
        # True Positive, lead time 100 days
        BacktestCaseResult(
            project_code="SITE-1",
            as_of=date(2023, 1, 1),
            expected_min_stage=8,
            expected_max_stage=8,
            predicted_stage=8,
            confidence=80.0,
            passed=True,
            is_true_positive=True,
            is_false_positive=False,
            is_false_negative=False,
            lead_time_days=100,
            estimated_power_mw=20.0,
            detail="",
        ),
        # False Positive (Predicted as DC, but expected max is 0)
        BacktestCaseResult(
            project_code="SITE-2",
            as_of=date(2023, 1, 1),
            expected_min_stage=0,
            expected_max_stage=0,
            predicted_stage=4,
            confidence=60.0,
            passed=False,
            is_true_positive=False,
            is_false_positive=True,
            is_false_negative=False,
            lead_time_days=None,
            estimated_power_mw=10.0,
            detail="",
        ),
        # False Negative (Not predicted as DC, but expected is 8)
        BacktestCaseResult(
            project_code="SITE-3",
            as_of=date(2023, 1, 1),
            expected_min_stage=8,
            expected_max_stage=8,
            predicted_stage=0,
            confidence=20.0,
            passed=False,
            is_true_positive=False,
            is_false_positive=False,
            is_false_negative=True,
            lead_time_days=None,
            estimated_power_mw=None,
            detail="",
        ),
        # True Negative (Not predicted, expected 0) -> not tracked explicitly in these metrics, but doesn't add to TP/FP/FN
        BacktestCaseResult(
            project_code="SITE-4",
            as_of=date(2023, 1, 1),
            expected_min_stage=0,
            expected_max_stage=0,
            predicted_stage=0,
            confidence=10.0,
            passed=True,
            is_true_positive=False,
            is_false_positive=False,
            is_false_negative=False,
            lead_time_days=None,
            estimated_power_mw=None,
            detail="",
        ),
    ]
    
    report = BacktestReport(cases=cases)
    
    # 1 TP, 1 FP -> Precision = 1 / 2 = 0.5
    assert report.precision == 0.5
    
    # 1 TP, 1 FN -> Recall = 1 / 2 = 0.5
    assert report.recall == 0.5
    
    # 2 passed, 4 total -> Accuracy = 0.5
    assert report.accuracy == 0.5
    
    # Only SITE-1 has lead time of 100
    assert report.avg_lead_time_days == 100.0

def test_generate_research_report():
    """Test generating the markdown research report."""
    cases = [
        BacktestCaseResult(
            project_code="SITE-1",
            as_of=date(2023, 1, 1),
            expected_min_stage=8,
            expected_max_stage=8,
            predicted_stage=8,
            confidence=80.0,
            passed=True,
            is_true_positive=True,
            is_false_positive=False,
            is_false_negative=False,
            lead_time_days=100,
            estimated_power_mw=20.0,
            detail="",
        )
    ]
    report = BacktestReport(cases=cases)
    markdown = report.generate_research_report()
    
    assert "**Identity Precision**: 100.0%" in markdown
    assert "**Identity Recall**: 100.0%" in markdown
    assert "**Average Lead Time**: 100.0 days" in markdown
    assert "| SITE-1 |" in markdown
