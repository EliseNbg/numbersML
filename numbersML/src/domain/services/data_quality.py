"""
Data Quality Guard Service

Validates indicator data and detects issues that could affect ML models.
Tracks: nulls, zeros, NaNs, out-of-range values, missing keys.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DataIssue:
    """Single data quality issue"""

    symbol_id: int
    symbol: str
    time: datetime
    indicator: str
    issue_type: str  # null, zero, nan, out_of_range, missing, negative, inf
    value: Any
    severity: str  # info, warning, error, critical
    message: str


@dataclass
class QualityReport:
    """Data quality report for a set of indicator values"""

    symbol_id: int
    symbol: str
    time: datetime
    total_indicators: int
    issues: list[DataIssue] = field(default_factory=list)
    quality_score: float = 100.0  # 0-100

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def has_issues(self) -> bool:
        return len(self.issues) > 0

    @property
    def is_critical(self) -> bool:
        return any(i.severity in ("error", "critical") for i in self.issues)


class DataQualityGuard:
    """Validates indicator data quality"""

    # Expected ranges for common indicators
    INDICATOR_RANGES = {
        "rsi": (0, 100),
        "stochastic": (0, 100),
        "adx": (0, 100),
        "aroon": (0, 100),
        "mfi": (0, 100),
    }

    # Indicators that can be zero/null (acceptable - insufficient data)
    OPTIONAL_INDICATORS = {
        "atr_999",
        "ema_450",
        "sma_450",
        "ema_2000",
        "sma_2000",
        "macd_120_260_29_macd",
        "macd_120_260_29_signal",
        "macd_120_260_29_histogram",
        "macd_400_860_300_macd",
        "macd_400_860_300_signal",
        "macd_400_860_300_histogram",
        "bb_900_2_lower",
        "bb_900_2_upper",
        "bb_900_2_middle",
        "bb_20_2_std",
        "bb_20_2_lower",
        "bb_20_2_upper",
        "bb_20_2_middle",
        "bb_200_2_std",
        "bb_200_2_lower",
        "bb_200_2_upper",
        "bb_200_2_middle",
        "rsi_54",
    }

    # Indicators that should NEVER be null (critical indicator backbone)
    CRITICAL_INDICATORS = {
        "atr_14",
        "atr_99",
        "ema_12",
        "ema_26",
        "rsi_14",
        "sma_20",
        "bb_20_2_std",
        "bb_20_2_lower",
        "bb_20_2_upper",
        "bb_20_2_middle",
        "macd_12_26_9_macd",
        "macd_12_26_9_signal",
        "macd_12_26_9_histogram",
    }

    def __init__(self) -> None:
        self.issues: list[DataIssue] = []

    def validate_indicator_values(
        self, symbol_id: int, symbol: str, time: datetime, values: dict[str, Any]
    ) -> QualityReport:
        """Validate a set of indicator values and return quality report"""
        self.issues = []

        if not values:
            self.issues.append(
                DataIssue(
                    symbol_id=symbol_id,
                    symbol=symbol,
                    time=time,
                    indicator="ALL",
                    issue_type="missing",
                    value=None,
                    severity="critical",
                    message="No indicator values found",
                )
            )
            return self._build_report(symbol_id, symbol, time, values)

        for key, value in values.items():
            self._validate_indicator(symbol_id, symbol, time, key, value)

        self._check_critical_indicators(symbol_id, symbol, time, values)

        return self._build_report(symbol_id, symbol, time, values)

    def _validate_indicator(
        self, symbol_id: int, symbol: str, time: datetime, key: str, value: Any
    ) -> None:
        """Validate a single indicator value"""

        # Check for None/null
        if value is None:
            severity = "error" if key in self.CRITICAL_INDICATORS else "warning"
            self.issues.append(
                DataIssue(
                    symbol_id=symbol_id,
                    symbol=symbol,
                    time=time,
                    indicator=key,
                    issue_type="null",
                    value=value,
                    severity=severity,
                    message=f"{key} is null"
                    + (" (critical indicator)" if severity == "error" else ""),
                )
            )
            return

        # Check for numeric types
        if not isinstance(value, int | float):
            return  # Skip non-numeric (shouldn't happen)

        # Check for NaN
        if isinstance(value, float) and math.isnan(value):
            self.issues.append(
                DataIssue(
                    symbol_id=symbol_id,
                    symbol=symbol,
                    time=time,
                    indicator=key,
                    issue_type="nan",
                    value=value,
                    severity="error",
                    message=f"{key} is NaN",
                )
            )
            return

        # Check for Infinity
        if isinstance(value, float) and math.isinf(value):
            self.issues.append(
                DataIssue(
                    symbol_id=symbol_id,
                    symbol=symbol,
                    time=time,
                    indicator=key,
                    issue_type="inf",
                    value=value,
                    severity="critical",
                    message=f"{key} is infinite",
                )
            )
            return

        # Check for zero (warning if not in OPTIONAL_INDICATORS)
        if value == 0.0 and key not in self.OPTIONAL_INDICATORS:
            # For price/volume, zero might be valid (rare trades)
            if not any(p in key for p in ["price", "volume", "close", "open", "high", "low"]):
                self.issues.append(
                    DataIssue(
                        symbol_id=symbol_id,
                        symbol=symbol,
                        time=time,
                        indicator=key,
                        issue_type="zero",
                        value=value,
                        severity="warning",
                        message=f"{key} is zero (may indicate insufficient data)",
                    )
                )

        # Check for negative values (where not expected)
        if value < 0:
            # Allow negative for certain derived indicators
            negative_allowed = any(
                p in key.lower() for p in ["macd", "histogram", "change", "diff", "momentum"]
            )
            if not negative_allowed:
                self.issues.append(
                    DataIssue(
                        symbol_id=symbol_id,
                        symbol=symbol,
                        time=time,
                        indicator=key,
                        issue_type="negative",
                        value=value,
                        severity="warning",
                        message=f"{key} is negative ({value})",
                    )
                )

        # Check for out-of-range values
        for pattern, (min_val, max_val) in self.INDICATOR_RANGES.items():
            if pattern in key.lower():
                if value < min_val or value > max_val:
                    self.issues.append(
                        DataIssue(
                            symbol_id=symbol_id,
                            symbol=symbol,
                            time=time,
                            indicator=key,
                            issue_type="out_of_range",
                            value=value,
                            severity="error",
                            message=f"{key}={value} outside expected range [{min_val}, {max_val}]",
                        )
                    )
                break

    def _check_critical_indicators(
        self, symbol_id: int, symbol: str, time: datetime, values: dict[str, Any]
    ) -> None:
        """Check if critical indicators are missing"""
        missing_critical = self.CRITICAL_INDICATORS - set(values.keys())
        for indicator in missing_critical:
            self.issues.append(
                DataIssue(
                    symbol_id=symbol_id,
                    symbol=symbol,
                    time=time,
                    indicator=indicator,
                    issue_type="missing",
                    value=None,
                    severity="critical",
                    message=f"Critical indicator {indicator} is missing from values",
                )
            )

    def _build_report(
        self, symbol_id: int, symbol: str, time: datetime, values: dict[str, Any]
    ) -> QualityReport:
        """Build quality report with score"""
        total = len(values)
        issue_count = len(self.issues)

        if total == 0:
            score = 0.0
        else:
            # Count issues by severity
            critical_count = sum(1 for i in self.issues if i.severity in ("error", "critical"))
            warning_count = sum(1 for i in self.issues if i.severity == "warning")

            # Scoring: start at 100, apply penalties
            score = 100.0
            score -= critical_count * 25.0  # -25 per critical issue
            score -= warning_count * 5.0  # -5 per warning
            # Penalty for ratio of affected indicators
            score -= (issue_count / total) * 30.0
            score = max(0.0, min(100.0, score))

        report = QualityReport(
            symbol_id=symbol_id,
            symbol=symbol,
            time=time,
            total_indicators=total,
            issues=self.issues,
            quality_score=round(score, 2),
        )

        # Log critical issues
        if report.is_critical:
            logger.warning(
                f"CRITICAL quality issue for {symbol} at {time}: "
                f"{issue_count} issues, score={score}"
            )

        return report

    def get_issue_summary(self, reports: list[QualityReport]) -> dict:
        """Summarize issues across multiple reports"""
        if not reports:
            return {
                "total_reports": 0,
                "reports_with_issues": 0,
                "critical_reports": 0,
                "total_issues": 0,
                "avg_quality_score": 0,
                "issues_by_type": {},
                "issues_by_severity": {},
                "affected_indicators": {},
            }

        summary = {
            "total_reports": len(reports),
            "reports_with_issues": sum(1 for r in reports if r.has_issues),
            "critical_reports": sum(1 for r in reports if r.is_critical),
            "total_issues": sum(r.issue_count for r in reports),
            "avg_quality_score": round(sum(r.quality_score for r in reports) / len(reports), 2),
            "issues_by_type": {},
            "issues_by_severity": {},
            "affected_indicators": {},
        }

        for report in reports:
            for issue in report.issues:
                # By type
                key = issue.issue_type
                summary["issues_by_type"][key] = summary["issues_by_type"].get(key, 0) + 1

                # By severity
                key = issue.severity
                summary["issues_by_severity"][key] = summary["issues_by_severity"].get(key, 0) + 1

                # By indicator
                key = issue.indicator
                summary["affected_indicators"][key] = summary["affected_indicators"].get(key, 0) + 1

        return summary

    def validate_batch(
        self, symbol_id: int, symbol: str, time_value_pairs: list[tuple[datetime, dict[str, Any]]]
    ) -> list[QualityReport]:
        """Validate multiple time points"""
        reports = []
        for time, values in time_value_pairs:
            report = self.validate_indicator_values(symbol_id, symbol, time, values)
            reports.append(report)
        return reports
