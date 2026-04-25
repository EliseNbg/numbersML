"""Unit tests for strategy config schema validation."""

from src.domain.strategies.config_schema import validate_strategy_config


class TestStrategyConfigSchema:
    """Test schema and business validation for strategy configs."""

    def test_valid_config_passes(self) -> None:
        config = {
            "meta": {"name": "RSI baseline", "schema_version": 1},
            "universe": {"symbols": ["BTC/USDC"], "timeframe": "1M"},
            "signal": {"type": "rsi", "params": {"period": 14, "oversold": 30, "overbought": 70}},
            "risk": {
                "max_position_size_pct": 5.0,
                "max_daily_loss_pct": 2.0,
                "stop_loss_pct": 1.0,
                "take_profit_pct": 3.0,
            },
            "execution": {"order_type": "market", "slippage_bps": 5, "fee_bps": 10},
            "mode": "paper",
            "status": "draft",
        }

        is_valid, issues = validate_strategy_config(config)

        assert is_valid is True
        assert issues == []

    def test_invalid_schema_version_fails(self) -> None:
        config = {
            "meta": {"name": "Broken schema", "schema_version": 2},
            "universe": {"symbols": ["BTC/USDC"], "timeframe": "1M"},
            "signal": {"type": "rsi", "params": {}},
            "risk": {"max_position_size_pct": 1.0, "max_daily_loss_pct": 1.0},
            "execution": {"order_type": "market"},
            "mode": "paper",
            "status": "draft",
        }

        is_valid, issues = validate_strategy_config(config)

        assert is_valid is False
        assert any("schema_version" in issue.path for issue in issues)

    def test_business_rule_stop_loss_must_be_less_than_take_profit(self) -> None:
        config = {
            "meta": {"name": "Bad risk model", "schema_version": 1},
            "universe": {"symbols": ["ETH/USDC"], "timeframe": "1M"},
            "signal": {"type": "sma_cross", "params": {"fast": 20, "slow": 50}},
            "risk": {
                "max_position_size_pct": 10.0,
                "max_daily_loss_pct": 4.0,
                "stop_loss_pct": 5.0,
                "take_profit_pct": 2.0,
            },
            "execution": {"order_type": "limit", "slippage_bps": 2, "fee_bps": 8},
            "mode": "paper",
            "status": "draft",
        }

        is_valid, issues = validate_strategy_config(config)

        assert is_valid is False
        assert any(issue.path == "risk" for issue in issues)

    def test_rsi_signal_specific_validation_fails(self) -> None:
        config = {
            "meta": {"name": "Invalid RSI", "schema_version": 1},
            "universe": {"symbols": ["BTC/USDC"], "timeframe": "1M"},
            "signal": {"type": "rsi", "params": {"period": 1, "oversold": 80, "overbought": 20}},
            "risk": {"max_position_size_pct": 1.0, "max_daily_loss_pct": 1.0},
            "execution": {"order_type": "market"},
            "mode": "paper",
            "status": "draft",
        }

        is_valid, issues = validate_strategy_config(config)

        assert is_valid is False
        assert any("signal.params.period" == issue.path for issue in issues)
        assert any("signal.params" == issue.path for issue in issues)

    def test_macd_signal_specific_validation_fails(self) -> None:
        config = {
            "meta": {"name": "Invalid MACD", "schema_version": 1},
            "universe": {"symbols": ["BTC/USDC"], "timeframe": "1M"},
            "signal": {"type": "macd", "params": {"fast": 26, "slow": 12, "signal": 0}},
            "risk": {"max_position_size_pct": 2.0, "max_daily_loss_pct": 1.0},
            "execution": {"order_type": "market"},
            "mode": "paper",
            "status": "draft",
        }

        is_valid, issues = validate_strategy_config(config)

        assert is_valid is False
        assert any(issue.path == "signal.params.signal" for issue in issues)
        assert any(issue.path == "signal.params" for issue in issues)

    def test_required_signal_params_missing_fails(self) -> None:
        config = {
            "meta": {"name": "Missing signal keys", "schema_version": 1},
            "universe": {"symbols": ["BTC/USDC"], "timeframe": "1M"},
            "signal": {"type": "bollinger", "params": {}},
            "risk": {"max_position_size_pct": 2.0, "max_daily_loss_pct": 1.0},
            "execution": {"order_type": "market"},
            "mode": "paper",
            "status": "draft",
        }

        is_valid, issues = validate_strategy_config(config)

        assert is_valid is False
        assert any(issue.path == "signal.params.period" for issue in issues)
        assert any(issue.path == "signal.params.std_dev" for issue in issues)
