"""
Base indicator class.

All indicators must inherit from this base class.
Provides common functionality for parameter validation,
code hashing, and result formatting.
"""

import hashlib
import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np


@dataclass
class IndicatorResult:
    """
    Result of indicator calculation.

    Attributes:
        name: Indicator name (e.g., 'rsi_14')
        values: Dictionary of calculated values
        metadata: Additional metadata about calculation
    """

    name: str
    values: dict[str, np.ndarray]
    metadata: dict[str, Any] = field(default_factory=dict)


class Indicator(ABC):
    """
    Base class for all indicators.

    Each indicator is a Python class that:
    - Defines its parameters with validation
    - Implements calculation logic
    - Can be serialized/deserialized for versioning
    """

    # Class-level metadata (override in subclasses)
    category: str = "custom"
    description: str = ""
    version: str = "1.0.0"

    def __init__(self, **params: Any) -> None:
        """
        Initialize indicator with parameters.

        Args:
            **params: Indicator parameters (e.g., period=14)
        """
        self.params: dict[str, Any] = params
        self._validate_params()

    @abstractmethod
    def calculate(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        highs: Optional[np.ndarray] = None,
        lows: Optional[np.ndarray] = None,
        opens: Optional[np.ndarray] = None,
    ) -> IndicatorResult:
        """
        Calculate indicator values.

        Args:
            prices: Array of prices (close prices, required)
            volumes: Array of volumes (required)
            highs: Array of highs (optional)
            lows: Array of lows (optional)
            opens: Array of opens (optional)

        Returns:
            IndicatorResult with calculated values
        """
        pass

    def _validate_params(self) -> None:
        """Validate parameters against schema."""
        schema = self.params_schema()

        # Check required parameters
        if "required" in schema:
            for param in schema["required"]:
                if param not in self.params:
                    raise ValueError(f"Missing required parameter: {param}")

        # Check parameter types and ranges
        if "properties" in schema:
            for param, spec in schema["properties"].items():
                if param in self.params:
                    value = self.params[param]

                    # Type checking
                    if "type" in spec:
                        expected_type = spec["type"]
                        if expected_type == "integer" and not isinstance(value, int):
                            raise ValueError(
                                f"Parameter {param} must be integer, got {type(value)}"
                            )
                        elif expected_type == "number" and not isinstance(value, (int, float)):
                            raise ValueError(f"Parameter {param} must be number, got {type(value)}")

                    # Range checking
                    if "minimum" in spec and value < spec["minimum"]:
                        raise ValueError(
                            f"Parameter {param} must be >= {spec['minimum']}, got {value}"
                        )
                    if "maximum" in spec and value > spec["maximum"]:
                        raise ValueError(
                            f"Parameter {param} must be <= {spec['maximum']}, got {value}"
                        )

    @classmethod
    @abstractmethod
    def params_schema(cls) -> dict[str, Any]:
        """
        Return JSON Schema for parameter validation.

        Returns:
            JSON Schema dictionary
        """
        pass

    def get_code_hash(self) -> str:
        """Calculate hash of indicator code."""
        source = inspect.getsource(self.__class__)
        return hashlib.sha256(source.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Serialize indicator definition to dictionary."""
        return {
            "name": self.name,
            "class_name": self.__class__.__name__,
            "module_path": self.__module__,
            "category": self.category,
            "params": self.params,
            "params_schema": self.params_schema(),
            "code_hash": self.get_code_hash(),
            "description": self.description,
        }

    def calculate_latest(
        self,
        prices: np.ndarray,
        volumes: np.ndarray,
        highs: Optional[np.ndarray] = None,
        lows: Optional[np.ndarray] = None,
        opens: Optional[np.ndarray] = None,
    ) -> dict[str, Optional[float]]:
        """
        Calculate only the latest (last) indicator value.

        This is an optimized version that only returns the most recent value,
        useful for real-time calculations where historical values aren't needed.

        Args:
            prices: Array of prices (close prices, required)
            volumes: Array of volumes (required)
            highs: Array of highs (optional)
            lows: Array of lows (optional)
            opens: Array of opens (optional)

        Returns:
            Dictionary with the same keys as calculate(), but only the latest value.
            NaN values are converted to None.
        """
        result = self.calculate(
            prices=prices,
            volumes=volumes,
            highs=highs,
            lows=lows,
            opens=opens,
        )

        latest: dict[str, Optional[float]] = {}
        for key, values in result.values.items():
            if len(values) > 0:
                val = float(values[-1])
                if np.isnan(val) or np.isinf(val):
                    latest[key] = None
                else:
                    latest[key] = val
            else:
                latest[key] = None

        return latest

    @property
    def name(self) -> str:
        """Generate unique name from class and parameters."""
        params_str = "_".join(f"{k}{v}" for k, v in sorted(self.params.items()))
        return f"{self.__class__.__name__.lower()}_{params_str}"
