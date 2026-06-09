"""Tests for Data Quality Guard"""

from datetime import UTC, datetime

import pytest

from src.domain.services.data_quality import DataIssue, DataQualityGuard, QualityReport


@pytest.fixture
def guard():
    return DataQualityGuard()


@pytest.fixture
def valid_values():
    return {
        "atr_499": 45.12,
        "atr_999": 6.38,
        "ema_800": 534.44,
        "ema_2000": 584.83,
        "rsi_299": 65.3,
        "sma_2000": 600.03,
        "sma_6000": 600.03,
        "bb_990_2_std": 137.66,
        "bb_990_2_lower": 324.71,
        "bb_990_2_upper": 875.34,
        "bb_990_2_middle": 600.03,
        "macd_280_590_29_macd": -50.38,
        "macd_280_590_29_signal": -10.08,
        "macd_280_590_29_histogram": -40.30,
        "macd_8590_13800_195_macd": -50.38,
        "macd_8590_13800_195_signal": -10.08,
        "macd_8590_13800_195_histogram": -40.30,
        "macd_980_1960_100_macd": -50.38,
        "macd_980_1960_100_signal": -10.08,
        "macd_980_1960_100_histogram": -40.30,
    }


@pytest.fixture
def sample_time():
    return datetime(2026, 4, 25, 0, 4, 36, tzinfo=UTC)


class TestDataIssue:
    def test_dataclass_fields(self, sample_time):
        issue = DataIssue(
            symbol_id=57,
            symbol="BTC/USDC",
            time=sample_time,
            indicator="rsi_14",
            issue_type="null",
            value=None,
            severity="error",
            message="test",
        )
        assert issue.symbol_id == 57
        assert issue.indicator == "rsi_14"
        assert issue.severity == "error"


class TestQualityReport:
    def test_empty_report(self, sample_time):
        report = QualityReport(
            symbol_id=57, symbol="BTC/USDC", time=sample_time, total_indicators=10
        )
        assert report.quality_score == 100.0
        assert report.issue_count == 0
        assert not report.has_issues
        assert not report.is_critical


class TestDataQualityGuard:
    def test_validate_valid_values(self, guard, valid_values, sample_time):
        report = guard.validate_indicator_values(
            symbol_id=57, symbol="BTC/USDC", time=sample_time, values=valid_values
        )
        assert report.quality_score == 100.0
        assert not report.has_issues
        assert report.total_indicators == len(valid_values)

    def test_validate_null_value(self, guard, valid_values, sample_time):
        values = valid_values.copy()
        values["rsi_299"] = None
        report = guard.validate_indicator_values(
            symbol_id=57, symbol="BTC/USDC", time=sample_time, values=values
        )
        assert report.has_issues
        assert report.is_critical
        assert any(i.issue_type == "null" for i in report.issues)
        assert report.quality_score < 100

    def test_validate_null_optional(self, guard, valid_values, sample_time):
        values = valid_values.copy()
        values["some_optional_indicator"] = None
        report = guard.validate_indicator_values(
            symbol_id=57, symbol="BTC/USDC", time=sample_time, values=values
        )
        assert report.has_issues
        assert not report.is_critical
        assert any(i.indicator == "some_optional_indicator" for i in report.issues)

    def test_validate_nan(self, guard, valid_values, sample_time):
        values = valid_values.copy()
        values["rsi_299"] = float("nan")
        report = guard.validate_indicator_values(
            symbol_id=57, symbol="BTC/USDC", time=sample_time, values=values
        )
        assert report.has_issues
        assert any(i.issue_type == "nan" for i in report.issues)

    def test_validate_inf(self, guard, valid_values, sample_time):
        values = valid_values.copy()
        values["rsi_299"] = float("inf")
        report = guard.validate_indicator_values(
            symbol_id=57, symbol="BTC/USDC", time=sample_time, values=values
        )
        assert report.has_issues
        assert any(i.issue_type == "inf" for i in report.issues)

    def test_validate_out_of_range(self, guard, valid_values, sample_time):
        values = valid_values.copy()
        values["rsi_299"] = 150
        report = guard.validate_indicator_values(
            symbol_id=57, symbol="BTC/USDC", time=sample_time, values=values
        )
        assert report.has_issues
        assert any(i.issue_type == "out_of_range" for i in report.issues)

    def test_validate_missing_critical(self, guard, sample_time):
        report = guard.validate_indicator_values(
            symbol_id=57, symbol="BTC/USDC", time=sample_time, values={}
        )
        assert report.has_issues
        assert report.is_critical
        assert report.quality_score == 0
        assert any(i.issue_type == "missing" for i in report.issues)

    def test_validate_empty_values(self, guard, sample_time):
        report = guard.validate_indicator_values(
            symbol_id=57, symbol="BTC/USDC", time=sample_time, values={}
        )
        assert report.total_indicators == 0
        assert report.quality_score == 0

    def test_get_issue_summary(self, guard, valid_values, sample_time):
        reports = []
        for i in range(5):
            values = valid_values.copy()
            if i == 0:
                values["rsi_299"] = None
            if i == 1:
                values["rsi_299"] = float("nan")
            reports.append(
                guard.validate_indicator_values(
                    symbol_id=57, symbol="BTC/USDC", time=sample_time, values=values
                )
            )

        summary = guard.get_issue_summary(reports)
        assert summary["total_reports"] == 5
        assert summary["reports_with_issues"] == 2
        assert summary["total_issues"] > 0
        assert summary["avg_quality_score"] < 100

    def test_validate_batch(self, guard, valid_values, sample_time):
        pairs = [
            (sample_time, valid_values),
            (sample_time, valid_values),
        ]
        reports = guard.validate_batch(57, "BTC/USDC", pairs)
        assert len(reports) == 2
        for r in reports:
            assert r.quality_score == 100.0

    def test_zero_generates_warning(self, guard, valid_values, sample_time):
        values = valid_values.copy()
        values["custom_indicator"] = 0.0
        report = guard.validate_indicator_values(
            symbol_id=57, symbol="BTC/USDC", time=sample_time, values=values
        )
        assert any(i.indicator == "custom_indicator" for i in report.issues)
        assert any(i.severity == "warning" for i in report.issues)

    def test_negative_macd(self, guard, valid_values, sample_time):
        values = valid_values.copy()
        values["macd_280_590_29_macd"] = -50.0
        report = guard.validate_indicator_values(
            symbol_id=57, symbol="BTC/USDC", time=sample_time, values=values
        )
        assert not any(i.indicator == "macd_280_590_29_macd" for i in report.issues)

    def test_scoring_critical(self, guard, valid_values, sample_time):
        values = valid_values.copy()
        values["rsi_299"] = None
        values["ema_800"] = None
        report = guard.validate_indicator_values(
            symbol_id=57, symbol="BTC/USDC", time=sample_time, values=values
        )
        assert report.quality_score < 80

    def test_scoring_perfect(self, guard, valid_values, sample_time):
        report = guard.validate_indicator_values(
            symbol_id=57, symbol="BTC/USDC", time=sample_time, values=valid_values
        )
        assert report.quality_score == 100.0
