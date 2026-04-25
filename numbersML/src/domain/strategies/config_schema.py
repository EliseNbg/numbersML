"""Strategy config schema loading and validation helpers."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class ValidationIssue:
    """Validation issue returned by schema and business rule checks."""

    path: str
    message: str


def _schema_path() -> Path:
    return Path(__file__).parent / "schemas" / "strategy_config_v1.json"


def load_strategy_schema() -> dict[str, Any]:
    """Load Strategy Config V1 JSON schema from disk."""
    return json.loads(_schema_path().read_text(encoding="utf-8"))


def validate_strategy_config(config: dict[str, Any]) -> tuple[bool, list[ValidationIssue]]:
    """Validate strategy config against schema and business rules."""
    validator = Draft202012Validator(load_strategy_schema())
    issues = [
        ValidationIssue(
            path=".".join([str(part) for part in error.path]) or "$",
            message=error.message,
        )
        for error in sorted(validator.iter_errors(config), key=str)
    ]

    risk = config.get("risk", {})
    stop_loss = risk.get("stop_loss_pct")
    take_profit = risk.get("take_profit_pct")
    if stop_loss is not None and take_profit is not None and stop_loss >= take_profit:
        issues.append(
            ValidationIssue(
                path="risk",
                message="stop_loss_pct must be lower than take_profit_pct.",
            )
        )

    issues.extend(_validate_signal_params(config.get("signal", {})))

    return len(issues) == 0, issues


def _validate_signal_params(signal: dict[str, Any]) -> list[ValidationIssue]:
    """Apply signal-specific parameter constraints."""
    signal_type = signal.get("type")
    params = signal.get("params", {})
    if not isinstance(params, dict):
        return [ValidationIssue(path="signal.params", message="params must be an object.")]

    issues: list[ValidationIssue] = []
    if signal_type == "rsi":
        issues.extend(_validate_rsi_params(params))
    elif signal_type == "macd":
        issues.extend(_validate_macd_params(params))
    elif signal_type == "sma_cross":
        issues.extend(_validate_sma_cross_params(params))
    elif signal_type == "bollinger":
        issues.extend(_validate_bollinger_params(params))
    elif signal_type == "composite":
        rules = params.get("rules")
        if not isinstance(rules, list) or len(rules) == 0:
            issues.append(
                ValidationIssue(
                    path="signal.params.rules",
                    message="composite strategies require non-empty rules list.",
                )
            )
    return issues


def _validate_rsi_params(params: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    required_keys = ("period", "oversold", "overbought")
    for key in required_keys:
        if key not in params:
            issues.append(
                ValidationIssue(
                    path=f"signal.params.{key}",
                    message=f"{key} is required for rsi strategy.",
                )
            )

    period = params.get("period")
    oversold = params.get("oversold")
    overbought = params.get("overbought")
    if not isinstance(period, int) or period < 2:
        issues.append(ValidationIssue(path="signal.params.period", message="period must be int >= 2."))
    if not isinstance(oversold, (int, float)) or not 0 <= oversold <= 100:
        issues.append(
            ValidationIssue(path="signal.params.oversold", message="oversold must be number in [0, 100].")
        )
    if not isinstance(overbought, (int, float)) or not 0 <= overbought <= 100:
        issues.append(
            ValidationIssue(
                path="signal.params.overbought",
                message="overbought must be number in [0, 100].",
            )
        )
    if (
        isinstance(oversold, (int, float))
        and isinstance(overbought, (int, float))
        and oversold >= overbought
    ):
        issues.append(
            ValidationIssue(
                path="signal.params",
                message="oversold must be lower than overbought.",
            )
        )
    return issues


def _validate_macd_params(params: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    required_keys = ("fast", "slow", "signal")
    for key in required_keys:
        if key not in params:
            issues.append(
                ValidationIssue(
                    path=f"signal.params.{key}",
                    message=f"{key} is required for macd strategy.",
                )
            )

    fast = params.get("fast")
    slow = params.get("slow")
    signal = params.get("signal")
    if not isinstance(fast, int) or fast < 1:
        issues.append(ValidationIssue(path="signal.params.fast", message="fast must be int >= 1."))
    if not isinstance(slow, int) or slow < 2:
        issues.append(ValidationIssue(path="signal.params.slow", message="slow must be int >= 2."))
    if not isinstance(signal, int) or signal < 1:
        issues.append(ValidationIssue(path="signal.params.signal", message="signal must be int >= 1."))
    if isinstance(fast, int) and isinstance(slow, int) and fast >= slow:
        issues.append(ValidationIssue(path="signal.params", message="fast must be lower than slow."))
    return issues


def _validate_sma_cross_params(params: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    required_keys = ("fast", "slow")
    for key in required_keys:
        if key not in params:
            issues.append(
                ValidationIssue(
                    path=f"signal.params.{key}",
                    message=f"{key} is required for sma_cross strategy.",
                )
            )

    fast = params.get("fast")
    slow = params.get("slow")
    if not isinstance(fast, int) or fast < 1:
        issues.append(ValidationIssue(path="signal.params.fast", message="fast must be int >= 1."))
    if not isinstance(slow, int) or slow < 2:
        issues.append(ValidationIssue(path="signal.params.slow", message="slow must be int >= 2."))
    if isinstance(fast, int) and isinstance(slow, int) and fast >= slow:
        issues.append(ValidationIssue(path="signal.params", message="fast must be lower than slow."))
    return issues


def _validate_bollinger_params(params: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    required_keys = ("period", "std_dev")
    for key in required_keys:
        if key not in params:
            issues.append(
                ValidationIssue(
                    path=f"signal.params.{key}",
                    message=f"{key} is required for bollinger strategy.",
                )
            )

    period = params.get("period")
    std_dev = params.get("std_dev")
    if not isinstance(period, int) or period < 2:
        issues.append(ValidationIssue(path="signal.params.period", message="period must be int >= 2."))
    if not isinstance(std_dev, (int, float)) or std_dev <= 0:
        issues.append(
            ValidationIssue(path="signal.params.std_dev", message="std_dev must be positive number.")
        )
    return issues
