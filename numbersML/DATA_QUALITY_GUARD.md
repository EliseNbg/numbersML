# Data Quality Guard

## Overview

The Data Quality Guard is a validation system that detects and reports issues in indicator data that could affect ML model performance.

## Problem Statement

Indicator data often contains issues that negatively impact ML models:

1. **Null values** - Missing indicator values (especially critical indicators)
2. **NaN/Inf** - Invalid numeric values from calculations
3. **Zero values** - Indicators with zero where they shouldn't be
4. **Out-of-range values** - RSI=150, negative prices, etc.
5. **Missing critical keys** - Essential indicators absent from data

These issues cause:
- LLM prediction failures
- Broken feature scaling
- NaN gradients during training
- Poor model accuracy

## Solution Architecture

### Multi-Layer Defense

```

 Layer 4: Data Quality API  
   - Expose quality scores      
   - List problem symbols       
   - Historical trends          


         ↓

 Layer 3: Post-Calculation      
   - Validate stored values     
   - Check ranges & types       
   - Flag anomalies             

         ↓

 Layer 2: Calculation Guard     
   - Pre-validate lookback      
   - Catch NaN/Inf              
   - Track failures             

         ↓

 Layer 1: Input Validation      
   - Validate OHLCV ranges      
   - Detect duplicates          
   - Reject outliers            

```

## Implementation

### DataQualityGuard Class

**Location**: `src/domain/services/data_quality.py`

#### Core Methods

```python
from src.domain.services.data_quality import DataQualityGuard

guard = DataQualityGuard()

# Validate indicator values for a specific timestamp
report = guard.validate_indicator_values(
    symbol_id=57,
    symbol='BTC/USDC',
    time=datetime.now(timezone.utc),
    values={
        'atr_14': 45.12,
        'rsi_14': 65.3,
        'sma_20': 600.03,
        # ... more indicators
    }
)

print(f"Quality Score: {report.quality_score}")  # 0-100
print(f"Has Issues: {report.has_issues}")
print(f"Issue Count: {report.issue_count}")

for issue in report.issues:
    print(f"  - {issue.indicator}: {issue.message}")
```

#### Quality Report

```python
@dataclass
class QualityReport:
    symbol_id: int
    symbol: str
    time: datetime
    total_indicators: int
    issues: List[DataIssue]
    quality_score: float  # 0-100
    
    @property
    def issue_count(self) -> int
    @property
    def has_issues(self) -> bool
    @property
    def is_critical(self) -> bool
```

#### Data Issue

```python
@dataclass
class DataIssue:
    symbol_id: int
    symbol: str
    time: datetime
    indicator: str
    issue_type: str  # null, zero, nan, out_of_range, missing, negative, inf
    value: Any
    severity: str    # info, warning, error, critical
    message: str
```

### Validation Rules

#### Critical Indicators (Must Never Be Null)

These indicators form the backbone of the feature set:

```python
CRITICAL_INDICATORS = {
    'atr_14', 'atr_99',           # Volatility
    'ema_12', 'ema_26',           # Short-term trends
    'rsi_14',                     # Momentum
    'sma_20',                     # Medium trend
    'bb_20_2_std',                # Volatility bands
    'bb_20_2_lower', 'bb_20_2_upper', 'bb_20_2_middle',
    'macd_12_26_9_macd',          # Trend & momentum
    'macd_12_26_9_signal',
    'macd_12_26_9_histogram',
}
```

#### Optional Indicators (Can Be Null)

Calculated with longer lookback periods - may be null for recent data:

```python
OPTIONAL_INDICATORS = {
    'atr_999',                    # Long-term volatility
    'ema_450', 'ema_2000',        # Very long trends
    'sma_450', 'sma_2000',
    'macd_120_260_29_*',          # Long-term MACD
    'macd_400_860_300_*',         # Very long MACD
    'bb_900_2_*',                 # Long-term Bollinger Bands
}
```

#### Indicator Ranges

Values outside these ranges indicate calculation errors:

```python
INDICATOR_RANGES = {
    'rsi': (0, 100),              # RSI must be 0-100
    'stochastic': (0, 100),       # Stochastic 0-100
    'adx': (0, 100),              # ADX 0-100
    'aroon': (0, 100),            # Aroon 0-100
    'mfi': (0, 100),              # MFI 0-100
}
```

### Scoring System

Quality score calculation:

```
Base Score: 100

Penalties:
  - Critical issue (error/critical): -25 points
  - Warning issue: -5 points
  - Ratio of affected indicators: -(affected/total) * 30

Final Score = max(0, min(100, base - penalties))
```

**Score Interpretation**:

| Score Range | Quality | Action |
|-------------|---------|--------|
| 90-100 | Excellent | ✅ Use for ML |
| 70-89 | Good | ✅ Use with caution |
| 50-69 | Fair | ⚠️ Investigate issues |
| 30-49 | Poor | ❌ Limited use |
| 0-29 | Critical | 🚫 Do not use |

### Batch Validation

```python
# Validate multiple timestamps
reports = guard.validate_batch(
    symbol_id=57,
    symbol='BTC/USDC',
    time_value_pairs=[
        (time1, values1),
        (time2, values2),
        (time3, values3),
    ]
)

# Get summary across all reports
summary = guard.get_issue_summary(reports)
print(summary)
```

**Summary Output**:

```python
{
    'total_reports': 5,
    'reports_with_issues': 2,
    'critical_reports': 1,
    'total_issues': 7,
    'avg_quality_score': 85.4,
    'issues_by_type': {
        'null': 3,
        'nan': 1,
        'out_of_range': 3
    },
    'issues_by_severity': {
        'error': 4,
        'warning': 3
    },
    'affected_indicators': {
        'rsi_14': 2,
        'ema_12': 1,
        'bb_20_2_std': 1
    }
}
```

## Usage Examples

### Example 1: Pre-ML Model Validation

```python
from src.domain.services.data_quality import DataQualityGuard

guard = DataQualityGuard()

def prepare_ml_features(indicator_data):
    """Validate data before feeding to ML model"""
    all_reports = []
    
    for row in indicator_data:
        report = guard.validate_indicator_values(
            symbol_id=row['symbol_id'],
            symbol=row['symbol'],
            time=row['time'],
            values=row['values']
        )
        all_reports.append(report)
        
        # Reject critical data
        if report.is_critical:
            logger.error(f"Critical issue for {row['symbol']} at {row['time']}")
            return None
    
    # Check overall quality
    summary = guard.get_issue_summary(all_reports)
    if summary['avg_quality_score'] < 70:
        logger.warning(f"Low quality data: {summary['avg_quality_score']}")
        return None
    
    return extract_features(indicator_data)
```

### Example 2: Data Pipeline Monitoring

```python
class DataQualityPipeline:
    def __init__(self):
        self.guard = DataQualityGuard()
        self.metrics = []
    
    async def process_indicators(self, symbol_id, symbol, time, values):
        # Step 1: Validate
        report = self.guard.validate_indicator_values(
            symbol_id, symbol, time, values
        )
        
        # Step 2: Log quality
        self.metrics.append({
            'symbol': symbol,
            'time': time,
            'quality_score': report.quality_score,
            'issue_count': report.issue_count
        })
        
        # Step 3: Alert on critical issues
        if report.is_critical:
            await self.alert_data_team(report)
        
        # Step 4: Store only if quality is acceptable
        if report.quality_score >= 50:
            await self.store_indicators(values)
        else:
            await self.store_quarantined(symbol, time, values, report)
```

### Example 3: Historical Data Audit

```python
async def audit_historical_data(db_pool, days=30):
    """Audit historical indicator data quality"""
    guard = DataQualityGuard()
    
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT symbol_id, time, values
            FROM candle_indicators
            WHERE time > NOW() - $1::interval
            ORDER BY time
            """,
            f'{days} days'
        )
    
    all_reports = []
    for row in rows:
        report = guard.validate_indicator_values(
            symbol_id=row['symbol_id'],
            symbol=str(row['symbol_id']),  # Get from symbols table
            time=row['time'],
            values=row['values']
        )
        all_reports.append(report)
    
    summary = guard.get_issue_summary(all_reports)
    
    print(f"Audit Results ({days} days):")
    print(f"  Total Records: {summary['total_reports']}")
    print(f"  Records with Issues: {summary['reports_with_issues']}")
    print(f"  Critical Records: {summary['critical_reports']}")
    print(f"  Avg Quality Score: {summary['avg_quality_score']}")
    print(f"\nTop Issues:")
    for issue_type, count in sorted(
        summary['issues_by_type'].items(),
        key=lambda x: x[1],
        reverse=True
    ):
        print(f"  {issue_type}: {count}")
    
    return summary
```

## Integration Points

### 1. Indicator Calculator

Add validation after calculation:

```python
# In indicator_calculator.py
from src.domain.services.data_quality import DataQualityGuard

class IndicatorCalculator:
    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.quality_guard = DataQualityGuard()
    
    async def _run_indicators(self, ...):
        # ... calculate indicators ...
        
        if results:
            # Validate before storing
            report = self.quality_guard.validate_indicator_values(
                symbol_id=symbol_id,
                symbol=symbol,
                time=latest_time,
                values=results
            )
            
            if report.is_critical:
                logger.error(f"Critical quality issue for {symbol}")
                # Optionally: don't store, or store with warning flag
            
            await self._write_results(...)
```

### 2. API Endpoint

Add quality information to API responses:

```python
# In routes/candles.py
from src.domain.services.data_quality import DataQualityGuard

@router.get("/candles/{symbol_id}/indicators")
async def get_indicators(symbol_id: int, limit: int = 100):
    guard = DataQualityGuard()
    
    rows = await fetch_indicators(symbol_id, limit)
    
    results = []
    for row in rows:
        report = guard.validate_indicator_values(
            symbol_id=row['symbol_id'],
            symbol=row['symbol'],
            time=row['time'],
            values=row['values']
        )
        
        results.append({
            'time': row['time'],
            'price': float(row['price']),
            'values': row['values'],
            'quality': {
                'score': report.quality_score,
                'has_issues': report.has_issues,
                'issue_count': report.issue_count
            }
        })
    
    return results
```

### 3. Scheduled Health Check

```python
# Run daily to check data quality
async def daily_quality_check():
    guard = DataQualityGuard()
    
    async with db_pool.acquire() as conn:
        # Check last 24 hours
        rows = await conn.fetch(
            """
            SELECT symbol_id, time, values
            FROM candle_indicators
            WHERE time > NOW() - INTERVAL '24 hours'
            """
        )
    
    reports = []
    for row in rows:
        report = guard.validate_indicator_values(
            symbol_id=row['symbol_id'],
            symbol=get_symbol(row['symbol_id']),
            time=row['time'],
            values=row['values']
        )
        reports.append(report)
    
    summary = guard.get_issue_summary(reports)
    
    if summary['critical_reports'] > 0:
        send_alert(
            f"Data Quality Alert: {summary['critical_reports']} "
            f"critical issues detected"
        )
```

## Testing

```bash
# Run data quality tests
pytest tests/unit/domain/services/test_data_quality.py -v

# Run all tests
pytest tests/unit/ -x
```

## Benefits

1. **Early Detection**: Catch data issues before they reach ML models
2. **Transparency**: Clear quality scores and issue tracking
3. **Actionable**: Specific issues with severity levels
4. **Scalable**: Batch validation for large datasets
5. **Flexible**: Custom validation rules per indicator
6. **Observable**: Historical quality trends

## Future Enhancements

- [ ] Real-time validation webhook
- [ ] Data quality dashboard
- [ ] Automated data correction suggestions
- [ ] ML model performance correlation
- [ ] Alert thresholds per symbol/indicator
- [ ] Quality trends over time
- [ ] Root cause analysis for anomalies

## See Also

- [Indicator Definitions](src/infrastructure/repositories/indicator_repo.py)
- [Indicator Calculator](src/pipeline/indicator_calculator.py)
- [API Routes](src/infrastructure/api/routes/)
