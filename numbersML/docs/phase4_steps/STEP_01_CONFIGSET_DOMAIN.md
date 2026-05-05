# Step 1: ConfigurationSet Domain Model

## Objective
Create the `ConfigurationSet` domain entity following DDD principles. This entity separates algorithm logic from runtime parameters and enables reusable parameter sets.

## Context
- Phase 3 completed algorithm domain models in `src/domain/algorithms/`
- Need a new entity that encapsulates runtime configuration (symbols, thresholds, risk parameters)
- Must follow existing DDD patterns in the project (see `src/domain/models/base.py` for Entity base class)

## DDD Architecture Decision (ADR)

**Decision**: ConfigurationSet is a Domain Entity (not Value Object) because:
- It has identity (UUID)
- It has lifecycle (created, updated, deactivated)
- Multiple algorithms can reference the same ConfigurationSet

**Configuration Structure**:
```python
config: dict = {
    "symbols": ["BTC/USDT", "ETH/USDT"],
    "thresholds": {
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "macd_signal": 9
    },
    "risk": {
        "max_position_size_pct": 10,
        "max_daily_loss_pct": 5,
        "stop_loss_pct": 2,
        "take_profit_pct": 4
    },
    "execution": {
        "order_type": "market",
        "slippage_bps": 10,
        "fee_bps": 10
    },
    "initial_balance": 10000.0
}
```

## TDD Approach

1. **Red**: Write failing tests first
2. **Green**: Implement minimal code to pass tests
3. **Refactor**: Apply DDD patterns, add docstrings

## Implementation Files

### 1. `src/domain/algorithms/config_set.py`

```python
"""
ConfigurationSet domain entity.

Represents a reusable set of configuration parameters that can be
linked to multiple algorithms. Follows DDD Entity pattern.

Architecture: Domain Layer (pure Python, no external dependencies)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from src.domain.models.base import Entity


@dataclass(frozen=True)
class ConfigurationSnapshot:
    """
    Immutable snapshot of configuration at a point in time.
    
    Used for audit trail and backtesting reproducibility.
    """
    config: Dict[str, Any]
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    captured_by: str = "system"


class ConfigurationSet(Entity):
    """
    Domain entity for algorithm configuration sets.
    
    Encapsulates all runtime parameters needed by a algorithm:
    - Trading symbols
    - Indicator thresholds
    - Risk parameters
    - Execution parameters
    
    Lifecycle:
        Created → Active → (optionally) Archived
        
    Example:
        >>> config_set = ConfigurationSet(
        ...     name="Conservative BTC",
        ...     config={"symbols": ["BTC/USDT"], "risk": {"max_position_size_pct": 5}}
        ... )
        >>> config_set.is_active
        True
    """
    
    def __init__(
        self,
        name: str,
        config: Dict[str, Any],
        description: Optional[str] = None,
        id: UUID = None,
        is_active: bool = True,
        created_by: str = "system",
    ) -> None:
        """
        Initialize ConfigurationSet.
        
        Args:
            name: Human-readable name
            config: Configuration dictionary (validated on set)
            description: Optional description
            id: UUID (auto-generated if None)
            is_active: Whether this config set is available for use
            created_by: User or system identifier
            
        Raises:
            ValueError: If name is empty or config is invalid
        """
        super().__init__(id or uuid4())
        
        if not name or not name.strip():
            raise ValueError("ConfigurationSet name cannot be empty")
        if not config:
            raise ValueError("ConfigurationSet config cannot be empty")
        
        self._name = name
        self._description = description
        self._config = config
        self._is_active = is_active
        self._created_by = created_by
        self._created_at = datetime.now(timezone.utc)
        self._updated_at = self._created_at
        self._version = 1
        self._snapshots: List[ConfigurationSnapshot] = []
    
    @property
    def name(self) -> str:
        """Get configuration set name."""
        return self._name
    
    @property
    def description(self) -> Optional[str]:
        """Get description."""
        return self._description
    
    @property
    def config(self) -> Dict[str, Any]:
        """Get configuration (defensive copy)."""
        return self._config.copy()
    
    @property
    def is_active(self) -> bool:
        """Check if configuration set is active."""
        return self._is_active
    
    @property
    def created_by(self) -> str:
        """Get creator identifier."""
        return self._created_by
    
    @property
    def created_at(self) -> datetime:
        """Get creation timestamp."""
        return self._created_at
    
    @property
    def updated_at(self) -> datetime:
        """Get last update timestamp."""
        return self._updated_at
    
    @property
    def version(self) -> int:
        """Get config version (increments on update)."""
        return self._version
    
    def update_config(self, new_config: Dict[str, Any], updated_by: str = "system") -> None:
        """
        Update configuration, creating a snapshot for audit trail.
        
        Args:
            new_config: New configuration dictionary
            updated_by: User making the change
            
        Raises:
            ValueError: If new_config is empty or invalid
        """
        if not new_config:
            raise ValueError("New configuration cannot be empty")
        
        # Create snapshot of old config
        snapshot = ConfigurationSnapshot(
            config=self._config.copy(),
            captured_by=updated_by
        )
        self._snapshots.append(snapshot)
        
        # Apply new config
        self._config = new_config
        self._updated_at = datetime.now(timezone.utc)
        self._version += 1
    
    def get_symbols(self) -> List[str]:
        """
        Get list of trading symbols from config.
        
        Returns:
            List of symbol strings, empty list if not configured
        """
        return self._config.get("symbols", [])
    
    def get_risk_param(self, key: str, default: Any = None) -> Any:
        """
        Get risk parameter by key.
        
        Args:
            key: Parameter key
            default: Default value if not found
            
        Returns:
            Parameter value or default
        """
        risk_config = self._config.get("risk", {})
        return risk_config.get(key, default)
    
    def get_threshold(self, indicator: str, default: Any = None) -> Any:
        """
        Get indicator threshold by indicator name.
        
        Args:
            indicator: Indicator name (e.g., 'rsi_oversold')
            default: Default value if not found
            
        Returns:
            Threshold value or default
        """
        thresholds = self._config.get("thresholds", {})
        return thresholds.get(indicator, default)
    
    def deactivate(self) -> None:
        """Deactivate this configuration set (soft delete)."""
        self._is_active = False
        self._updated_at = datetime.now(timezone.utc)
    
    def activate(self) -> None:
        """Activate this configuration set."""
        self._is_active = True
        self._updated_at = datetime.now(timezone.utc)
    
    def get_snapshots(self) -> List[ConfigurationSnapshot]:
        """Get audit trail of configuration changes."""
        return self._snapshots.copy()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.
        
        Returns:
            Dictionary representation
        """
        return {
            "id": str(self.id),
            "name": self._name,
            "description": self._description,
            "config": self._config.copy(),
            "is_active": self._is_active,
            "created_by": self._created_by,
            "created_at": self._created_at.isoformat(),
            "updated_at": self._updated_at.isoformat(),
            "version": self._version,
        }
```

### 2. `tests/unit/domain/algorithms/test_config_set.py`

```python
"""
Unit tests for ConfigurationSet domain entity.

Follows TDD approach: tests first, then implementation.
"""

import pytest
from datetime import datetime, timezone
from uuid import UUID, uuid4

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
            created_by="test"
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
            config={"symbols": []}
        )
        
        assert config_set.name == "Minimal"
        assert config_set.description is None
        assert config_set.is_active is True
    
    def test_create_with_custom_id(self):
        """Test creating with custom UUID."""
        custom_id = uuid4()
        config_set = ConfigurationSet(
            name="Custom ID",
            config={},
            id=custom_id
        )
        
        assert config_set.id == custom_id
    
    def test_create_empty_name_raises_error(self):
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            ConfigurationSet(name="", config={})
    
    def test_create_whitespace_name_raises_error(self):
        """Test that whitespace-only name raises ValueError."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            ConfigurationSet(name="   ", config={})
    
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
            config={"version": 1}
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
        config_set = ConfigurationSet(name="Test", config={})
        
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
        config_set = ConfigurationSet(name="Test", config={})
        assert config_set.is_active is True
        
        config_set.deactivate()
        assert config_set.is_active is False
    
    def test_activate(self):
        """Test reactivating a config set."""
        config_set = ConfigurationSet(name="Test", config={})
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
            created_by="serializer"
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
        
        assert config_set.config["mutable"] is True  # Original unchanged
```

## LLM Implementation Prompt

```text
You are implementing Step 1 of Phase 4: ConfigurationSet Domain Model.

## Your Task

Create the ConfigurationSet domain entity following DDD (Domain-Driven Design) principles.

## Context

- This is for a Python 3.11 FastAPI/asyncpg crypto trading system
- Phase 3 is complete (algorithm domain models exist in src/domain/algorithms/)
- You must follow the project's DDD architecture (see AGENTS.md and existing domain models)
- Base entity class is in src/domain/models/base.py

## Requirements

1. Create `src/domain/algorithms/config_set.py` with:
   - `ConfigurationSnapshot` frozen dataclass (immutable audit trail)
   - `ConfigurationSet` entity class extending Entity base class
   - Full type annotations (mypy strict mode)
   - Google-style docstrings for all public methods
   - Properties: name, description, config, is_active, created_by, created_at, updated_at, version
   - Methods:
     * update_config(new_config, updated_by) -> creates snapshot, increments version
     * get_symbols() -> List[str]
     * get_risk_param(key, default) -> Any
     * get_threshold(indicator, default) -> Any
     * deactivate() / activate()
     * get_snapshots() -> List[ConfigurationSnapshot]
     * to_dict() -> Dict[str, Any]
   - Validation in __init__: non-empty name, non-empty config
   - Validation in update_config: non-empty new_config

2. Create `tests/unit/domain/algorithms/test_config_set.py` with TDD approach:
   - TestConfigurationSnapshot: creation, immutability
   - TestConfigurationSetCreation: valid/invalid creation, custom ID
   - TestConfigurationSetUpdate: snapshot creation, version increment, multiple updates
   - TestConfigurationSetGetters: get_symbols, get_risk_param, get_threshold
   - TestConfigurationSetActivation: deactivate/activate
   - TestConfigurationSetSerialization: to_dict, defensive copy

## Constraints

- Follow AGENTS.md coding standards exactly
- Use type hints on all public methods (mypy strict)
- Use Google-style docstrings
- No external dependencies in domain layer
- Use relative imports within package
- Line length max 100 characters
- Use logging.getLogger(__name__) for any logging needed

## Acceptance Criteria

1. `ConfigurationSet` can be created with valid name and config
2. Empty name or config raises ValueError
3. update_config() creates snapshot and increments version
4. Getters return correct values from nested config structure
5. deactivate()/activate() toggle is_active flag
6. to_dict() returns proper serialization with defensive copy
7. All unit tests pass
8. mypy passes with no errors
9. ruff check passes with no errors
10. black formatting applied

## Commands to Run

```bash
# Format and lint
black src/domain/algorithms/config_set.py tests/unit/domain/algorithms/test_config_set.py
ruff check src/domain/algorithms/config_set.py tests/unit/domain/algorithms/test_config_set.py
mypy src/domain/algorithms/config_set.py

# Run tests
.venv/bin/python -m pytest tests/unit/domain/algorithms/test_config_set.py -v
```

## Output

1. List of files created/modified
2. Test results (passed/failed count)
3. mypy/ruff output (no errors)
4. Any issues encountered and how resolved
```

## Success Criteria

- [ ] ConfigurationSet entity created with all specified methods
- [ ] ConfigurationSnapshot immutable dataclass created
- [ ] All unit tests pass (TDD approach)
- [ ] mypy strict mode passes
- [ ] ruff check passes (rules: E, W, F, I, N, UP, B, C4)
- [ ] black formatting applied
- [ ] Google-style docstrings on all public methods
- [ ] Follows DDD Entity pattern (extends base Entity class)