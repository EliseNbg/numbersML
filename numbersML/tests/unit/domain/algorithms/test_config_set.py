"""
Unit tests for ConfigurationSet domain entity.

Follows TDD approach: tests first, then implementation.
"""

from datetime import datetime
from uuid import UUID, uuid4

import pytest

from src.domain.algorithms.config_set import ConfigurationSet, ConfigurationSnapshot


class TestConfigurationSnapshot:
    """Tests for ConfigurationSnapshot value object."""

    def test_create_snapshot(self):
        """Test creating a configuration snapshot."""
        config = {"symbols": ["BTC/USDT"], "risk": {"max_position_size_pct": 10}}
        snapshot = ConfigurationSnapshot(config=config, captured_by="test_user")

        assert snapshot.config == config
        assert snapshot.captured_by == "test_user"
        assert isinstance(snapshot.captured_at, datetime)

    def test_snapshot_immutability(self):
        """Test that snapshot is immutable (frozen dataclass)."""
        config = {"test": 1}
        snapshot = ConfigurationSnapshot(config=config)

        with pytest.raises(AttributeError):
            snapshot.config = {"new": 2}


class TestConfigurationSetCreation:
    """Tests for ConfigurationSet creation."""

    def test_create_valid_config_set(self):
        """Test creating a valid ConfigurationSet."""
        config = {
            "symbols": ["BTC/USDT"],
            "thresholds": {"rsi_oversold": 30},
            "risk": {"max_position_size_pct": 10},
        }
        config_set = ConfigurationSet(
            name="Test Config",
            config=config,
            description="Test description",
            created_by="test",
        )

        assert isinstance(config_set.id, UUID)
        assert config_set.name == "Test Config"
        assert config_set.description == "Test description"
        assert config_set.is_active is True
        assert config_set.config == config
        assert config_set.version == 1
        assert config_set.created_by == "test"

    def test_create_minimal_config_set(self):
        """Test creating with minimal required fields."""
        config_set = ConfigurationSet(
            name="Minimal",
            config={"symbols": []},
        )

        assert config_set.name == "Minimal"
        assert config_set.description is None
        assert config_set.is_active is True

    def test_create_with_custom_id(self):
        """Test creating with custom UUID."""
        custom_id = uuid4()
        config_set = ConfigurationSet(
            name="Custom ID",
            config={"symbols": []},
            id=custom_id,
        )

        assert config_set.id == custom_id

    def test_create_empty_name_raises_error(self):
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            ConfigurationSet(name="", config={"symbols": []})

    def test_create_whitespace_name_raises_error(self):
        """Test that whitespace-only name raises ValueError."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            ConfigurationSet(name="   ", config={"symbols": []})

    def test_create_empty_config_raises_error(self):
        """Test that empty config raises ValueError."""
        with pytest.raises(ValueError, match="config cannot be empty"):
            ConfigurationSet(name="Test", config={})


class TestConfigurationSetUpdate:
    """Tests for configuration update with audit trail."""

    def test_update_config_creates_snapshot(self):
        """Test that updating config creates a snapshot."""
        config_set = ConfigurationSet(
            name="Test",
            config={"version": 1},
        )
        original_config = config_set.config.copy()

        new_config = {"version": 2, "updated": True}
        config_set.update_config(new_config, updated_by="admin")

        assert config_set.config == new_config
        assert config_set.version == 2
        assert len(config_set.get_snapshots()) == 1

        snapshot = config_set.get_snapshots()[0]
        assert snapshot.config == original_config
        assert snapshot.captured_by == "admin"

    def test_multiple_updates_track_history(self):
        """Test that multiple updates track full history."""
        config_set = ConfigurationSet(name="Test", config={"v": 1})

        config_set.update_config({"v": 2})
        config_set.update_config({"v": 3})
        config_set.update_config({"v": 4})

        assert config_set.version == 4
        snapshots = config_set.get_snapshots()
        assert len(snapshots) == 3
        assert snapshots[0].config == {"v": 1}
        assert snapshots[2].config == {"v": 3}

    def test_update_empty_config_raises_error(self):
        """Test that updating with empty config raises error."""
        config_set = ConfigurationSet(name="Test", config={"v": 1})

        with pytest.raises(ValueError, match="cannot be empty"):
            config_set.update_config({})


class TestConfigurationSetGetters:
    """Tests for convenience getter methods."""

    def test_get_symbols(self):
        """Test getting symbols from config."""
        config = {"symbols": ["BTC/USDT", "ETH/USDT"]}
        config_set = ConfigurationSet(name="Test", config=config)

        assert config_set.get_symbols() == ["BTC/USDT", "ETH/USDT"]

    def test_get_symbols_empty(self):
        """Test getting symbols when not configured."""
        config_set = ConfigurationSet(name="Test", config={"symbols": []})

        assert config_set.get_symbols() == []

    def test_get_risk_param(self):
        """Test getting risk parameter."""
        config = {"risk": {"max_position_size_pct": 10, "stop_loss_pct": 2}}
        config_set = ConfigurationSet(name="Test", config=config)

        assert config_set.get_risk_param("max_position_size_pct") == 10
        assert config_set.get_risk_param("stop_loss_pct") == 2
        assert config_set.get_risk_param("nonexistent", 99) == 99

    def test_get_threshold(self):
        """Test getting indicator threshold."""
        config = {"thresholds": {"rsi_oversold": 30, "rsi_overbought": 70}}
        config_set = ConfigurationSet(name="Test", config=config)

        assert config_set.get_threshold("rsi_oversold") == 30
        assert config_set.get_threshold("rsi_overbought") == 70
        assert config_set.get_threshold("macd_signal", 9) == 9


class TestConfigurationSetActivation:
    """Tests for activation/deactivation."""

    def test_deactivate(self):
        """Test deactivating a config set."""
        config_set = ConfigurationSet(name="Test", config={"symbols": []})
        assert config_set.is_active is True

        config_set.deactivate()
        assert config_set.is_active is False

    def test_activate(self):
        """Test reactivating a config set."""
        config_set = ConfigurationSet(name="Test", config={"symbols": []})
        config_set.deactivate()
        assert config_set.is_active is False

        config_set.activate()
        assert config_set.is_active is True


class TestConfigurationSetSerialization:
    """Tests for to_dict serialization."""

    def test_to_dict(self):
        """Test converting to dictionary."""
        config_set = ConfigurationSet(
            name="Serializable",
            config={"key": "value"},
            description="Test desc",
            created_by="serializer",
        )

        result = config_set.to_dict()

        assert result["name"] == "Serializable"
        assert result["config"] == {"key": "value"}
        assert result["description"] == "Test desc"
        assert isinstance(result["id"], str)
        assert isinstance(result["created_at"], str)

    def test_to_dict_returns_config_copy(self):
        """Test that to_dict returns a copy of config, not reference."""
        config = {"mutable": True}
        config_set = ConfigurationSet(name="Test", config=config)

        result = config_set.to_dict()
        result["config"]["mutable"] = False

        assert config_set.config["mutable"] is True
