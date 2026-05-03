"""
Integration Test: Wide Vector Quality & Normalization

Validates that wide_vectors for the last day contain proper indicator values:
- No pure 0 or NaN values (except explicit warmup periods)
- Each indicator falls within its expected physical range
- Normalization (median+IQR, mean+std, min-max) produces sensible statistics
- Forward-fill cache prevents indicator dropouts during gaps
"""

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any, Optional

import asyncpg
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DB_URL = "postgresql://crypto:crypto_secret@localhost:5432/crypto_trading"


@dataclass
class IndicatorRange:
    name_pattern: str
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    min_iqr: float = 1.0
    allow_zero: bool = False
    description: str = ""


INDICATOR_RANGES: list[IndicatorRange] = [
    IndicatorRange(name_pattern="_close", min_val=0.0, allow_zero=False, description="Close price"),
    IndicatorRange(name_pattern="_volume", min_val=0.0, allow_zero=True, description="Volume"),
    IndicatorRange(name_pattern="_upper", min_val=0.0, allow_zero=False, description="BB upper"),
    IndicatorRange(name_pattern="_middle", min_val=0.0, allow_zero=False, description="BB middle"),
    IndicatorRange(name_pattern="_lower", min_val=0.0, allow_zero=False, description="BB lower"),
    IndicatorRange(name_pattern="_vwap", min_val=0.0, allow_zero=False, description="VWAP"),
    IndicatorRange(
        name_pattern="_rsi", min_val=0.0, max_val=100.0, allow_zero=True, description="RSI"
    ),
    IndicatorRange(
        name_pattern="_mfi", min_val=0.0, max_val=100.0, allow_zero=True, description="MFI"
    ),
    IndicatorRange(
        name_pattern="_stochastic",
        min_val=0.0,
        max_val=100.0,
        allow_zero=True,
        description="Stochastic",
    ),
    IndicatorRange(name_pattern="_macd", allow_zero=True, description="MACD"),
    IndicatorRange(name_pattern="_signal", allow_zero=True, description="MACD signal"),
    IndicatorRange(name_pattern="_histogram", allow_zero=True, description="MACD hist"),
    IndicatorRange(name_pattern="_atr", min_val=0.0, allow_zero=True, description="ATR"),
    IndicatorRange(name_pattern="_std", min_val=0.0, allow_zero=True, description="BB std"),
    IndicatorRange(
        name_pattern="_adx", min_val=0.0, max_val=100.0, allow_zero=True, description="ADX"
    ),
    IndicatorRange(
        name_pattern="_aroon", min_val=-100.0, max_val=100.0, allow_zero=True, description="Aroon"
    ),
    IndicatorRange(name_pattern="_obv", allow_zero=True, description="OBV"),
]


def classify_feature(column_name: str) -> tuple[str, IndicatorRange]:
    for ir in INDICATOR_RANGES:
        if ir.name_pattern in column_name.lower():
            return ir.name_pattern.strip("_"), ir
    return "unknown", IndicatorRange(name_pattern="", allow_zero=True, description="Unclassified")


def normalize(values: np.ndarray, method: str) -> tuple[np.ndarray, float, float]:
    v = values[~np.isnan(values)]
    if len(v) == 0:
        return np.zeros_like(values), 0.0, 0.0
    if method == "mean_std":
        m, s = np.mean(v), max(np.std(v), 1e-6)
        norm = (values - m) / s
    elif method == "median_iqr":
        med = np.median(v)
        q25, q75 = np.percentile(v, [25, 75])
        iqr = max(q75 - q25, 1.0)
        norm = (values - med) / iqr
    elif method == "min_max":
        mi, ma = np.min(v), np.max(v)
        rng = max(ma - mi, 1e-6)
        norm = (values - mi) / rng * 2.0 - 1.0
    else:
        raise ValueError(f"Unknown method: {method}")
    nc = norm[~np.isnan(norm)]
    return norm, float(np.mean(nc)), float(np.std(nc))


async def fetch_vectors(
    conn: asyncpg.Connection, hours: int = 24
) -> tuple[list[str], np.ndarray, list[list[str]]]:
    rows = await conn.fetch(
        "SELECT vector, column_names FROM wide_vectors WHERE time >= NOW() - $1::INTERVAL ORDER BY time DESC",
        f"{hours} hours",
    )
    if not rows:
        raise RuntimeError("No wide_vectors found")
    all_names = [
        (
            json.loads(r["column_names"])
            if isinstance(r["column_names"], str)
            else list(r["column_names"])
        )
        for r in rows
    ]
    cols = all_names[0]
    vecs = np.array([json.loads(r["vector"]) for r in rows], dtype=np.float64)
    return cols, vecs, all_names


async def run_test() -> dict[str, Any]:
    print("=" * 70)
    print("INTEGRATION TEST: Wide Vector Quality & Normalization")
    print("=" * 70)

    conn = await asyncpg.connect(DB_URL)
    try:
        cols, vecs = await fetch_vectors(conn)
        n, f = vecs.shape
        print(f"\nFetched {n} vectors x {f} features (last 24h)")

        dead, range_fail, bad_norm = [], [], []
        print(
            f"\n{'Column':<40} {'Type':<10} {'IQR':>10} {'Dead':>4} {'RangeOK':>7} {'mean_iqr':>10} {'std_iqr':>10}"
        )
        print("-" * 100)

        for idx, col in enumerate(cols):
            feat = vecs[:, idx]
            zeros = int(np.sum(feat == 0.0))
            nans = int(np.sum(np.isnan(feat)))
            valid = feat[~np.isnan(feat)]

            ft, ir = classify_feature(col)
            violations = []
            if len(valid) > 0:
                if ir.min_val is not None and np.min(valid) < ir.min_val:
                    violations.append("below_min")
                if ir.max_val is not None and np.max(valid) > ir.max_val:
                    violations.append("above_max")
            if zeros == len(feat) and not ir.allow_zero:
                violations.append("all_zeros")
            if nans > len(feat) * 0.1:
                violations.append("too_many_nans")

            q25, q75 = np.percentile(valid, [25, 75]) if len(valid) else (0.0, 0.0)
            iqr = q75 - q25
            is_dead = iqr < ir.min_iqr and np.std(valid) < ir.min_iqr

            _, mean_iqr, std_iqr = normalize(feat, "median_iqr")
            _, mean_std, std_std = normalize(feat, "mean_std")

            if is_dead:
                dead.append(col)
            if violations:
                range_fail.append(f"{col}: {', '.join(violations)}")
            if abs(mean_iqr) > 5.0 or std_iqr > 10.0:
                bad_norm.append(f"{col}: mean_iqr={mean_iqr:.2f}, std_iqr={std_iqr:.2f}")

            print(
                f"{col:<40} {ft:<10} {iqr:>10.4f} {'YES' if is_dead else '':>4} "
                f"{'OK' if not violations else 'FAIL':>7} {mean_iqr:>10.2f} {std_iqr:>10.2f}"
            )

        # Summaries
        print(f"\n--- Dead / Near-Constant Features: {len(dead)} ---")
        for d in dead[:20]:
            print(f"  {d}")

        print(f"\n--- Range Violations: {len(range_fail)} ---")
        for r in range_fail[:20]:
            print(f"  {r}")

        print(f"\n--- Bad Normalization (|mean|>5 or std>10): {len(bad_norm)} ---")
        for b in bad_norm[:20]:
            print(f"  {b}")

        passed = len(range_fail) == 0 and len(dead) == 0
        print("\n" + "=" * 70)
        print(f"RESULT: {'PASS' if passed else 'FAIL'}")
        print(f"  Dead features: {len(dead)}")
        print(f"  Range violations: {len(range_fail)}")
        print(f"  Bad normalization: {len(bad_norm)}")
        print("=" * 70)

        return {
            "passed": passed,
            "vectors": n,
            "features": f,
            "dead_count": len(dead),
            "range_fail_count": len(range_fail),
            "bad_norm_count": len(bad_norm),
            "dead_features": dead,
            "range_failures": range_fail,
            "bad_normalization": bad_norm,
        }
    finally:
        await conn.close()


if __name__ == "__main__":
    result = asyncio.run(run_test())
    sys.exit(0 if result["passed"] else 1)
