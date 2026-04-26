# Data Quality Guard - Implementation Summary

## Problems Detected

Running the data quality guard on 1000 recent indicator records revealed:

### 1. Price/Volume Data Issues
- **100% of records have price=0**  
  The historical recalculations ran before the OHLCV fix was applied, so all stored prices and volumes are zero.
  
  **Impact**: Any strategy using price/volume data will see flat lines instead of real market data.

### 2. Null Indicator Values
- **14,000 null values** across optional indicators
- Most affect: `atr_999`, `ema_450`, `sma_450`, `ema_2000`, `sma_2000`, `bb_900_2_*`, long-term MACD
- **Cause**: These indicators require very long lookback periods (450+ candles) that aren't available

  **Impact**: Expected for optional indicators - they're `None` until enough data accumulates.

### 3. Zero Values for Critical Indicators  
- **284 zero values** where they shouldn't be
- Indicators showing 0.0 even when data should be available

  **Impact**: More concerning - may indicate calculation or data feed issues.

### 4. Overall Quality Score
- **Score: 15.19/100** (Critical range)
- 100% of records flagged with issues
- 14,284 total issues detected

  **Impact**: If used for ML training, would produce poor model performance.

## Data Quality Guard Implementation

### What Was Built

#### 1. Core Validation Engine (`src/domain/services/data_quality.py`)
- **`DataQualityGuard`** class with validation methods
- **`QualityReport`** dataclass with scoring (0-100)
- **`DataIssue`** dataclass for detailed issue tracking

#### 2. Validation Rules

**Critical Indicators** (must never be null):
- ATR (14, 99 periods)
- EMA (12, 26 periods)
- RSI (14, 54 periods)
- SMA (20 periods)
- Bollinger Bands (20, 2 std)
- MACD (12, 26, 9)

**Optional Indicators** (can be null):
- Very long-period indicators (450, 2000 periods)
- Long-term MACD variants
- Extended Bollinger Bands (900 periods)

**Indicator Ranges**:
- RSI/STOCH/ADX/AROON/MFI: must be 0-100
- Out-of-range values flagged as errors

**Issue Types Detected**:
- `null` - Missing value
- `nan` - Not a Number  
- `inf` - Infinite
- `zero` - Unexpected zero
- `negative` - Unexpected negative value
- `out_of_range` - Outside valid range
- `missing` - Critical indicator absent

#### 3. Scoring System

```
Base Score: 100

Penalties:
  - Critical issue: -25 points
  - Warning issue: -5 points
  - Ratio penalty: -(affected/total) * 30

Final = max(0, min(100, base - penalties))
```

**Score Ranges**:
- 90-100: Excellent ✅ (Safe for ML)
- 70-89: Good ✅ (Use with caution)
- 50-69: Fair ⚠️ (Investigate)
- 30-49: Poor ❌ (Limited use)
- 0-29: Critical 🚫 (Do not use)

#### 4. Usage Examples

**Single validation**:
```python
guard = DataQualityGuard()
report = guard.validate_indicator_values(
    symbol_id=57,
    symbol='BTC/USDC',
    time=datetime.now(),
    values=indicator_values
)
print(f"Score: {report.quality_score}/100")
```

**Batch validation**:
```python
reports = guard.validate_batch(symbol_id, symbol, time_value_pairs)
summary = guard.get_issue_summary(reports)
print(f"Avg quality: {summary['avg_quality_score']}")
```

**Pre-ML check**:
```python
if report.is_critical or report.quality_score < 50:
    logger.error("Rejecting low-quality data")
    return None
```

### Test Coverage

**16 unit tests** (`tests/unit/domain/services/test_data_quality.py`):
- Empty value validation
- Null detection (critical vs optional)
- NaN/Inf detection
- Range validation
- Missing critical indicators
- Batch validation
- Scoring accuracy
- Issue summarization

All tests pass ✅

## How It Works

### Layer 1: Input Validation
When candles arrive from exchange:
- Validate OHLCV ranges
- Check for duplicates/stale data
- Reject outliers

### Layer 2: Calculation Guard
During indicator calculation:
- Pre-validate sufficient lookback
- Catch NaN/Inf during computation
- Track per-indicator failures

### Layer 3: Post-Calculation Validation
After storing indicators:
- Run quality guard on saved data
- Flag anomalies
- Track quality metrics

### Layer 4: Data Quality API
New endpoints (to be added):
- GET `/quality/symbols` - List symbols with issues
- GET `/quality/reports` - Get quality reports
- GET `/quality/summary` - Overall quality metrics

## Integration Points

### 1. Indicator Calculator
```python
# After calculating indicators
report = guard.validate_indicator_values(...)
if report.is_critical:
    logger.error(f"Critical issue for {symbol}")
```

### 2. ML Training Pipeline
```python
# Before feeding to model
if quality_guard.validate(...).quality_score < 70:
    skip_training_sample()
```

### 3. Scheduled Health Checks
```python
# Daily quality check
summary = quality_guard.get_issue_summary(reports)
if summary['critical_reports'] > 0:
    alert_team()
```

### 4. API Responses
```python
# Add quality info to responses
{
    "time": "...",
    "values": {...},
    "quality": {
        "score": 85.4,
        "has_issues": False
    }
}
```

## Benefits

1. **Early Detection**: Catch issues before they reach ML models
2. **Transparency**: Clear quality scores and detailed reporting
3. **Actionable**: Specific issues with severity levels
4. **Scalable**: Batch validation for large datasets
5. **Flexible**: Custom rules per indicator type
6. **Observable**: Historical quality trends

## Current Status

✅ **Implemented**:
- Data quality guard service
- Validation rules for all indicators
- Scoring system
- Unit tests (16/16 passing)
- Demo script working

⏳ **To Do**:
- API endpoints for quality data
- Scheduled health check job
- Quality dashboard UI
- Alert integration
- Historical quality trends

## Recommendations

### Immediate Actions
1. **Re-run recalculations** with proper OHLCV data to fix zero prices
2. **Set quality threshold** (e.g., reject data with score < 50)
3. **Add logging** for quality issues in production

### Short-term
1. **Add quality API endpoints** for monitoring
2. **Create dashboard** showing quality trends
3. **Set up alerts** for critical quality issues

### Long-term
1. **Automated correction** suggestions
2. **Quality-based weighting** in ensemble models
3. **Root cause analysis** for recurring issues
4. **ML model performance correlation** with data quality

## See Also

- [Data Quality Guard Code](src/domain/services/data_quality.py)
- [Unit Tests](tests/unit/domain/services/test_data_quality.py)
- [Indicator Definitions](src/infrastructure/repositories/indicator_repo.py)
- [API Routes](src/infrastructure/api/routes/)
