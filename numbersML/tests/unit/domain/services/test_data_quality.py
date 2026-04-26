"""Tests for Data Quality Guard"""

import pytest
from datetime import datetime, timezone
from src.domain.services.data_quality import (
    DataQualityGuard,
    QualityReport,
    DataIssue
)


@pytest.fixture
def guard():
    return DataQualityGuard()


@pytest.fixture
def valid_values():
    return {
        'atr_14': 45.12,
        'atr_99': 6.38,
        'ema_12': 534.44,
        'ema_26': 584.83,
        'rsi_14': 65.3,
        'rsi_54': 60.5,
        'sma_20': 600.03,
        'bb_20_2_std': 137.66,
        'bb_20_2_lower': 324.71,
        'bb_20_2_upper': 875.34,
        'bb_20_2_middle': 600.03,
        'macd_12_26_9_macd': -50.38,
        'macd_12_26_9_signal': -10.08,
        'macd_12_26_9_histogram': -40.30,
    }


@pytest.fixture
def sample_time():
    return datetime(2026, 4, 25, 0, 4, 36, tzinfo=timezone.utc)


class TestDataIssue:
    def test_dataclass_fields(self, sample_time):
        issue = DataIssue(
            symbol_id=57,
            symbol='BTC/USDC',
            time=sample_time,
            indicator='rsi_14',
            issue_type='null',
            value=None,
            severity='error',
            message='test'
        )
        assert issue.symbol_id == 57
        assert issue.indicator == 'rsi_14'
        assert issue.severity == 'error'


class TestQualityReport:
    def test_empty_report(self, sample_time):
        report = QualityReport(
            symbol_id=57,
            symbol='BTC/USDC',
            time=sample_time,
            total_indicators=10
        )
        assert report.quality_score == 100.0
        assert report.issue_count == 0
        assert not report.has_issues
        assert not report.is_critical


class TestDataQualityGuard:
    def test_validate_valid_values(self, guard, valid_values, sample_time):
        report = guard.validate_indicator_values(
            symbol_id=57,
            symbol='BTC/USDC',
            time=sample_time,
            values=valid_values
        )
        assert report.quality_score == 100.0
        assert not report.has_issues
        assert report.total_indicators == len(valid_values)

    def test_validate_null_value(self, guard, valid_values, sample_time):
        values = valid_values.copy()
        values['rsi_14'] = None
        report = guard.validate_indicator_values(
            symbol_id=57,
            symbol='BTC/USDC',
            time=sample_time,
            values=values
        )
        assert report.has_issues
        assert report.is_critical
        assert any(i.issue_type == 'null' for i in report.issues)
        assert report.quality_score < 100

    def test_validate_null_optional(self, guard, valid_values, sample_time):
        values = valid_values.copy()
        values['atr_999'] = None
        report = guard.validate_indicator_values(
            symbol_id=57,
            symbol='BTC/USDC',
            time=sample_time,
            values=values
        )
        assert report.has_issues
        assert not report.is_critical
        assert any(i.indicator == 'atr_999' for i in report.issues)

    def test_validate_nan(self, guard, valid_values, sample_time):
        values = valid_values.copy()
        values['rsi_14'] = float('nan')
        report = guard.validate_indicator_values(
            symbol_id=57,
            symbol='BTC/USDC',
            time=sample_time,
            values=values
        )
        assert report.has_issues
        assert any(i.issue_type == 'nan' for i in report.issues)

    def test_validate_inf(self, guard, valid_values, sample_time):
        values = valid_values.copy()
        values['rsi_14'] = float('inf')
        report = guard.validate_indicator_values(
            symbol_id=57,
            symbol='BTC/USDC',
            time=sample_time,
            values=values
        )
        assert report.has_issues
        assert any(i.issue_type == 'inf' for i in report.issues)

    def test_validate_out_of_range(self, guard, valid_values, sample_time):
        values = valid_values.copy()
        values['rsi_14'] = 150
        report = guard.validate_indicator_values(
            symbol_id=57,
            symbol='BTC/USDC',
            time=sample_time,
            values=values
        )
        assert report.has_issues
        assert any(i.issue_type == 'out_of_range' for i in report.issues)

    def test_validate_missing_critical(self, guard, sample_time):
        report = guard.validate_indicator_values(
            symbol_id=57,
            symbol='BTC/USDC',
            time=sample_time,
            values={}
        )
        assert report.has_issues
        assert report.is_critical
        assert report.quality_score == 0
        assert any(i.issue_type == 'missing' for i in report.issues)

    def test_validate_empty_values(self, guard, sample_time):
        report = guard.validate_indicator_values(
            symbol_id=57,
            symbol='BTC/USDC',
            time=sample_time,
            values={}
        )
        assert report.total_indicators == 0
        assert report.quality_score == 0

    def test_get_issue_summary(self, guard, valid_values, sample_time):
        reports = []
        for i in range(5):
            values = valid_values.copy()
            if i == 0:
                values['rsi_14'] = None
            if i == 1:
                values['rsi_14'] = float('nan')
            reports.append(guard.validate_indicator_values(
                symbol_id=57, symbol='BTC/USDC',
                time=sample_time, values=values
            ))

        summary = guard.get_issue_summary(reports)
        assert summary['total_reports'] == 5
        assert summary['reports_with_issues'] == 2
        assert summary['total_issues'] > 0
        assert summary['avg_quality_score'] < 100

    def test_validate_batch(self, guard, valid_values, sample_time):
        pairs = [
            (sample_time, valid_values),
            (sample_time, valid_values),
        ]
        reports = guard.validate_batch(57, 'BTC/USDC', pairs)
        assert len(reports) == 2
        for r in reports:
            assert r.quality_score == 100.0

    def test_zero_optional_indicator(self, guard, valid_values, sample_time):
        values = valid_values.copy()
        values['ema_450'] = 0.0
        report = guard.validate_indicator_values(
            symbol_id=57,
            symbol='BTC/USDC',
            time=sample_time,
            values=values
        )
        assert not any(i.indicator == 'ema_450' for i in report.issues)

    def test_negative_macd(self, guard, valid_values, sample_time):
        values = valid_values.copy()
        values['macd_12_26_9_macd'] = -50.0
        report = guard.validate_indicator_values(
            symbol_id=57,
            symbol='BTC/USDC',
            time=sample_time,
            values=values
        )
        assert not any(i.indicator == 'macd_12_26_9_macd' for i in report.issues)

    def test_scoring_critical(self, guard, valid_values, sample_time):
        values = valid_values.copy()
        values['rsi_14'] = None
        values['ema_12'] = None
        report = guard.validate_indicator_values(
            symbol_id=57,
            symbol='BTC/USDC',
            time=sample_time,
            values=values
        )
        assert report.quality_score < 50

    def test_scoring_perfect(self, guard, valid_values, sample_time):
        report = guard.validate_indicator_values(
            symbol_id=57,
            symbol='BTC/USDC',
            time=sample_time,
            values=valid_values
        )
        assert report.quality_score == 100.0
