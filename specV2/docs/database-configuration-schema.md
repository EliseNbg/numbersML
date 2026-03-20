# Database Configuration Schema

## Overview

**Principle**: All configuration stored in database, only DB connection string in `.env`

**Benefits**:
- ✅ Single source of truth
- ✅ Dynamic configuration (no restart needed)
- ✅ Audit trail of all changes
- ✅ Easy backup/restore
- ✅ Consistent across all services

---

## Configuration Tables

### 1. system_config - Global Settings

```sql
-- System-wide configuration
CREATE TABLE system_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    is_sensitive BOOLEAN NOT NULL DEFAULT false,
    is_editable BOOLEAN NOT NULL DEFAULT true,
    validation_schema JSONB,  -- JSON Schema for validation
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by TEXT,
    version INTEGER NOT NULL DEFAULT 1
);

-- Index for lookups
CREATE INDEX idx_system_config_key ON system_config(key);

-- Comments
COMMENT ON TABLE system_config IS 'Global system configuration (all services)';
COMMENT ON COLUMN system_config.value IS 'Configuration value as JSON';
COMMENT ON COLUMN system_config.validation_schema IS 'JSON Schema for validating value';
```

**Initial Data**:

```sql
-- Application settings
INSERT INTO system_config (key, value, description) VALUES
('app.name', '{"value": "Crypto Trading System", "env": "production"}'::jsonb, 'Application name'),
('app.version', '{"value": "1.0.0"}'::jsonb, 'Application version'),
('app.environment', '{"value": "production", "allowed": ["development", "staging", "production"]}'::jsonb, 'Environment'),
('app.timezone', '{"value": "UTC"}'::jsonb, 'System timezone');

-- Database settings
('database.pool.min_size', '{"value": 5, "min": 1, "max": 20}'::jsonb, 'Minimum DB pool size'),
('database.pool.max_size', '{"value": 20, "min": 1, "max": 100}'::jsonb, 'Maximum DB pool size'),
('database.pool.timeout', '{"value": 60, "min": 10, "max": 300}'::jsonb, 'Connection timeout (seconds)'),

-- Data collection settings
('data_collection.enabled', '{"value": true}'::jsonb, 'Enable/disable data collection'),
('data_collection.batch_size', '{"value": 500, "min": 100, "max": 5000}'::jsonb, 'Batch size for inserts'),
('data_collection.batch_interval_ms', '{"value": 500, "min": 100, "max": 5000}'::jsonb, 'Batch interval (milliseconds)'),
('data_collection.max_reconnect_attempts', '{"value": 10, "min": 1, "max": 100}'::jsonb, 'Max reconnection attempts'),
('data_collection.reconnect_delay_sec', '{"value": 5, "min": 1, "max": 60}'::jsonb, 'Reconnection delay (seconds)'),

-- Data quality settings
('data_quality.enabled', '{"value": true}'::jsonb, 'Enable data quality validation'),
('data_quality.max_price_move_pct', '{"value": 10.0, "min": 1.0, "max": 50.0}'::jsonb, 'Max price move % per second'),
('data_quality.max_gap_seconds', '{"value": 5, "min": 1, "max": 60}'::jsonb, 'Max gap before alert'),
('data_quality.auto_reject_invalid', '{"value": true}'::jsonb, 'Auto-reject invalid ticks'),

-- Enrichment settings
('enrichment.enabled', '{"value": true}'::jsonb, 'Enable indicator enrichment'),
('enrichment.window_size', '{"value": 1000, "min": 100, "max": 10000}'::jsonb, 'Window size for indicator calculation'),
('enrichment.batch_size', '{"value": 100, "min": 10, "max": 1000}'::jsonb, 'Batch size for enrichment'),
('enrichment.max_latency_ms', '{"value": 100, "min": 10, "max": 1000}'::jsonb, 'Max latency (milliseconds)'),
('enrichment.indicators', '{"value": ["rsi_14", "macd", "sma_20", "ema_20", "bollinger"]}'::jsonb, 'Active indicators'),

-- Storage settings
('storage.enable_compression', '{"value": true}'::jsonb, 'Enable data compression'),
('storage.compression_age_days', '{"value": 30, "min": 7, "max": 365}'::jsonb, 'Compress data older than N days'),
('storage.enable_partitioning', '{"value": true}'::jsonb, 'Enable table partitioning'),
('storage.partition_interval', '{"value": "1 month", "allowed": ["1 week", "1 month", "3 months"]}'::jsonb, 'Partition interval'),

-- Monitoring settings
('monitoring.enabled', '{"value": true}'::jsonb, 'Enable monitoring'),
('monitoring.health_check_interval_sec', '{"value": 30, "min": 10, "max": 300}'::jsonb, 'Health check interval'),
('monitoring.metrics_enabled', '{"value": true}'::jsonb, 'Enable metrics collection'),
('monitoring.log_level', '{"value": "INFO", "allowed": ["DEBUG", "INFO", "WARNING", "ERROR"]}'::jsonb, 'Log level'),
('monitoring.alert_webhook', '{"value": null}'::jsonb, 'Webhook URL for alerts'),

-- Redis settings
('redis.enabled', '{"value": true}'::jsonb, 'Enable Redis pub/sub'),
('redis.channel_prefix', '{"value": "crypto"}'::jsonb, 'Redis channel prefix'),
('redis.publish_enriched_ticks', '{"value": true}'::jsonb, 'Publish enriched ticks to Redis');

-- Sensitive settings (not shown in logs)
INSERT INTO system_config (key, value, description, is_sensitive) VALUES
('credentials.binance.api_key', '{"value": null}'::jsonb, 'Binance API key', true),
('credentials.binance.api_secret', '{"value": null}'::jsonb, 'Binance API secret', true);
```

---

### 2. collection_config - Per-Symbol Settings

```sql
-- Per-symbol collection configuration
CREATE TABLE collection_config (
    symbol_id INTEGER PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
    
    -- Data collection flags
    collect_ticks BOOLEAN NOT NULL DEFAULT false,
    collect_24hr_ticker BOOLEAN NOT NULL DEFAULT true,
    collect_orderbook BOOLEAN NOT NULL DEFAULT false,
    collect_candles BOOLEAN NOT NULL DEFAULT true,
    
    -- Collection frequency (seconds)
    tick_snapshot_interval_sec INTEGER NOT NULL DEFAULT 1,
    ticker_snapshot_interval_sec INTEGER NOT NULL DEFAULT 1,
    orderbook_snapshot_interval_sec INTEGER DEFAULT 1,
    candle_intervals TEXT[] NOT NULL DEFAULT '{"1m", "5m", "15m", "1h"}',
    
    -- Order book configuration (future)
    orderbook_levels INTEGER DEFAULT 10,
    orderbook_storage_mode TEXT DEFAULT 'arrays',
    
    -- Retention policies (days)
    tick_retention_days INTEGER NOT NULL DEFAULT 30,
    ticker_retention_days INTEGER NOT NULL DEFAULT 180,
    orderbook_retention_days INTEGER DEFAULT 30,
    candle_retention_days INTEGER NOT NULL DEFAULT 365,
    
    -- Quality thresholds
    max_price_move_pct NUMERIC(10,4) DEFAULT 10.0,
    max_quantity_move_pct NUMERIC(10,4) DEFAULT 50.0,
    max_gap_seconds INTEGER DEFAULT 5,
    
    -- Status
    is_collecting BOOLEAN NOT NULL DEFAULT false,
    last_config_change TIMESTAMP NOT NULL DEFAULT NOW(),
    config_version INTEGER NOT NULL DEFAULT 1,
    
    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT chk_tick_interval CHECK (tick_snapshot_interval_sec >= 1),
    CONSTRAINT chk_ticker_interval CHECK (ticker_snapshot_interval_sec >= 1),
    CONSTRAINT chk_orderbook_levels CHECK (orderbook_levels >= 5 AND orderbook_levels <= 20),
    CONSTRAINT chk_retention_days CHECK (tick_retention_days >= 0)
);

-- Index for active collection
CREATE INDEX idx_collection_config_collecting 
    ON collection_config(is_collecting) 
    WHERE is_collecting = true;

-- Index for ticker collection
CREATE INDEX idx_collection_config_ticker 
    ON collection_config(collect_24hr_ticker) 
    WHERE collect_24hr_ticker = true;

-- Trigger to update timestamp
CREATE TRIGGER collection_config_update_timestamp
    BEFORE UPDATE ON collection_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Comments
COMMENT ON TABLE collection_config IS 'Per-symbol data collection configuration';
COMMENT ON COLUMN collection_config.collect_ticks IS 'Collect individual trades (high storage)';
COMMENT ON COLUMN collection_config.collect_24hr_ticker IS 'Collect 24hr ticker stats (low storage)';
COMMENT ON COLUMN collection_config.collect_orderbook IS 'Collect order book snapshots (future)';
```

**Initial Data**:

```sql
-- Default configuration for all symbols
INSERT INTO collection_config (symbol_id, collect_ticks, collect_24hr_ticker, collect_orderbook)
SELECT id, false, true, false
FROM symbols
WHERE is_active = true
ON CONFLICT (symbol_id) DO NOTHING;

-- Override for key symbols (BTC, ETH)
UPDATE collection_config 
SET 
    collect_ticks = true,
    tick_retention_days = 30
WHERE symbol_id IN (
    SELECT id FROM symbols 
    WHERE symbol IN ('BTC/USDT', 'ETH/USDT')
);
```

---

### 3. config_change_log - Audit Trail

```sql
-- Audit trail for all configuration changes
CREATE TABLE config_change_log (
    id BIGSERIAL PRIMARY KEY,
    config_type TEXT NOT NULL,  -- 'system', 'symbol', 'user'
    config_key TEXT NOT NULL,   -- config key or symbol_id
    old_value JSONB,
    new_value JSONB NOT NULL,
    changed_by TEXT NOT NULL DEFAULT 'system',
    changed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    applied_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'applied',  -- pending, applied, failed
    reason TEXT,
    rollback_value JSONB
);

-- Indexes for querying
CREATE INDEX idx_config_change_log_type_key 
    ON config_change_log(config_type, config_key);
CREATE INDEX idx_config_change_log_status 
    ON config_change_log(status) 
    WHERE status = 'pending';
CREATE INDEX idx_config_change_log_changed_at 
    ON config_change_log(changed_at DESC);
CREATE INDEX idx_config_change_log_changed_by 
    ON config_change_log(changed_by);

-- Comments
COMMENT ON TABLE config_change_log IS 'Audit trail for all configuration changes';
COMMENT ON COLUMN config_change_log.status IS 'pending=awaiting apply, applied=success, failed=error';
```

---

### 4. service_status - Service State

```sql
-- Track status of all services
CREATE TABLE service_status (
    service_name TEXT PRIMARY KEY,
    status TEXT NOT NULL,  -- 'running', 'stopped', 'error', 'starting', 'stopping'
    pid INTEGER,
    host TEXT,
    port INTEGER,
    
    -- Health metrics
    is_healthy BOOLEAN NOT NULL DEFAULT false,
    last_health_check TIMESTAMP,
    health_check_error TEXT,
    
    -- Statistics
    uptime_seconds BIGINT DEFAULT 0,
    records_processed BIGINT DEFAULT 0,
    errors_last_hour INTEGER DEFAULT 0,
    last_error TEXT,
    last_error_at TIMESTAMP,
    
    -- Configuration
    config_version INTEGER DEFAULT 1,
    started_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Index for status queries
CREATE INDEX idx_service_status_status 
    ON service_status(status);
CREATE INDEX idx_service_status_healthy 
    ON service_status(is_healthy) 
    WHERE is_healthy = false;

-- Trigger to update timestamp
CREATE TRIGGER service_status_update_timestamp
    BEFORE UPDATE ON service_status
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Comments
COMMENT ON TABLE service_status IS 'Real-time status of all services';
```

**Initial Data**:

```sql
-- Register all services
INSERT INTO service_status (service_name, status, is_healthy) VALUES
('data-collector', 'stopped', false),
('ticker-collector', 'stopped', false),
('data-enricher', 'stopped', false),
('orderbook-collector', 'stopped', false),
('asset-sync', 'stopped', false),
('backfill', 'stopped', false),
('gap-filler', 'stopped', false),
('pruner', 'stopped', false);
```

---

### 5. Helper Functions

```sql
-- Function: Get configuration value
CREATE OR REPLACE FUNCTION get_config(p_key TEXT, p_default JSONB DEFAULT NULL)
RETURNS JSONB AS $$
    SELECT COALESCE(value->>'value', p_default::TEXT)::JSONB
    FROM system_config
    WHERE key = p_key;
$$ LANGUAGE SQL STABLE;

-- Function: Set configuration value
CREATE OR REPLACE FUNCTION set_config(
    p_key TEXT,
    p_value JSONB,
    p_changed_by TEXT DEFAULT 'system'
) RETURNS BOOLEAN AS $$
DECLARE
    v_old_value JSONB;
BEGIN
    -- Get old value
    SELECT value INTO v_old_value
    FROM system_config
    WHERE key = p_key;
    
    -- Update or insert
    INSERT INTO system_config (key, value, updated_at, updated_by)
    VALUES (p_key, jsonb_build_object('value', p_value), NOW(), p_changed_by)
    ON CONFLICT (key) DO UPDATE SET
        value = jsonb_build_object('value', p_value),
        updated_at = NOW(),
        updated_by = p_changed_by,
        version = system_config.version + 1;
    
    -- Log change
    INSERT INTO config_change_log (config_type, config_key, old_value, new_value, changed_by)
    VALUES ('system', p_key, v_old_value, jsonb_build_object('value', p_value), p_changed_by);
    
    -- Notify services
    PERFORM pg_notify('config_changed', json_build_object(
        'type', 'system',
        'key', p_key,
        'value', p_value
    )::text);
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Function: Get symbol configuration
CREATE OR REPLACE FUNCTION get_symbol_config(p_symbol_id INTEGER)
RETURNS collection_config AS $$
    SELECT * FROM collection_config WHERE symbol_id = p_symbol_id;
$$ LANGUAGE SQL STABLE;

-- Function: Update symbol configuration
CREATE OR REPLACE FUNCTION set_symbol_config(
    p_symbol_id INTEGER,
    p_key TEXT,
    p_value ANYELEMENT,
    p_changed_by TEXT DEFAULT 'system'
) RETURNS BOOLEAN AS $$
DECLARE
    v_old_value JSONB;
    v_query TEXT;
BEGIN
    -- Get old value
    EXECUTE format('SELECT %I FROM collection_config WHERE symbol_id = $1', p_key)
    INTO v_old_value
    USING p_symbol_id;
    
    -- Update
    EXECUTE format('UPDATE collection_config SET %I = $1, updated_at = NOW() WHERE symbol_id = $2', p_key)
    USING p_value, p_symbol_id;
    
    -- Log change
    INSERT INTO config_change_log (config_type, config_key, old_value, new_value, changed_by)
    VALUES ('symbol', p_symbol_id::TEXT, 
            jsonb_build_object(p_key, v_old_value),
            jsonb_build_object(p_key, p_value),
            p_changed_by);
    
    -- Notify services
    PERFORM pg_notify('config_changed', json_build_object(
        'type', 'symbol',
        'key', p_symbol_id::TEXT,
        'changes', jsonb_build_object(p_key, p_value)
    )::text);
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Function: Validate configuration value
CREATE OR REPLACE FUNCTION validate_config_value(p_key TEXT, p_value JSONB)
RETURNS BOOLEAN AS $$
DECLARE
    v_schema JSONB;
    v_result BOOLEAN;
BEGIN
    -- Get validation schema
    SELECT validation_schema INTO v_schema
    FROM system_config
    WHERE key = p_key;
    
    -- No schema = always valid
    IF v_schema IS NULL THEN
        RETURN TRUE;
    END IF;
    
    -- TODO: Implement JSON Schema validation
    -- For now, just check basic types
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Function: Get all active symbols with config
CREATE OR REPLACE FUNCTION get_active_symbols_config()
RETURNS TABLE (
    symbol_id INTEGER,
    symbol TEXT,
    collect_ticks BOOLEAN,
    collect_24hr_ticker BOOLEAN,
    collect_orderbook BOOLEAN,
    tick_snapshot_interval_sec INTEGER,
    ticker_snapshot_interval_sec INTEGER,
    is_collecting BOOLEAN
) AS $$
    SELECT 
        cc.symbol_id,
        s.symbol,
        cc.collect_ticks,
        cc.collect_24hr_ticker,
        cc.collect_orderbook,
        cc.tick_snapshot_interval_sec,
        cc.ticker_snapshot_interval_sec,
        cc.is_collecting
    FROM collection_config cc
    JOIN symbols s ON s.id = cc.symbol_id
    WHERE s.is_active = true OR cc.is_collecting = true;
$$ LANGUAGE SQL STABLE;
```

---

### 6. Views for Easy Querying

```sql
-- View: Current configuration summary
CREATE VIEW config_summary AS
SELECT 
    'system' AS config_type,
    key AS config_key,
    value->>'value' AS current_value,
    description,
    is_sensitive,
    updated_at,
    version
FROM system_config
UNION ALL
SELECT 
    'symbol' AS config_type,
    s.symbol || '.' || cc.key AS config_key,
    CASE cc.key
        WHEN 'collect_ticks' THEN cc.collect_ticks::TEXT
        WHEN 'collect_24hr_ticker' THEN cc.collect_24hr_ticker::TEXT
        WHEN 'tick_snapshot_interval_sec' THEN cc.tick_snapshot_interval_sec::TEXT
        WHEN 'ticker_snapshot_interval_sec' THEN cc.ticker_snapshot_interval_sec::TEXT
        ELSE NULL
    END AS current_value,
    'Per-symbol configuration' AS description,
    false AS is_sensitive,
    cc.updated_at,
    cc.config_version AS version
FROM collection_config cc
JOIN symbols s ON s.id = cc.symbol_id;

-- View: Service health overview
CREATE VIEW service_health_overview AS
SELECT 
    service_name,
    status,
    is_healthy,
    CASE 
        WHEN is_healthy THEN '✓'
        WHEN status = 'error' THEN '✗ ERROR'
        WHEN status = 'stopped' THEN '○ STOPPED'
        ELSE '⚠ CHECK'
    END AS health_indicator,
    uptime_seconds,
    records_processed,
    errors_last_hour,
    last_health_check,
    config_version
FROM service_status
ORDER BY service_name;

-- View: Recent configuration changes
CREATE VIEW config_recent_changes AS
SELECT 
    config_type,
    config_key,
    old_value,
    new_value,
    changed_by,
    changed_at,
    status,
    reason
FROM config_change_log
ORDER BY changed_at DESC
LIMIT 100;

-- View: Active collection symbols
CREATE VIEW active_collection_symbols AS
SELECT 
    s.id AS symbol_id,
    s.symbol,
    s.is_active,
    cc.collect_ticks,
    cc.collect_24hr_ticker,
    cc.collect_orderbook,
    cc.tick_snapshot_interval_sec,
    cc.ticker_snapshot_interval_sec,
    cc.is_collecting,
    cc.config_version
FROM symbols s
JOIN collection_config cc ON cc.symbol_id = s.id
WHERE cc.is_collecting = true OR s.is_active = true
ORDER BY s.symbol;
```

---

## Usage Examples

### Get/Set System Configuration

```sql
-- Get value
SELECT get_config('data_collection.batch_size');
-- Returns: 500

-- Set value
SELECT set_config('data_collection.batch_size', 1000, 'admin');
-- Returns: TRUE

-- Verify change
SELECT get_config('data_collection.batch_size');
-- Returns: 1000

-- Check audit log
SELECT * FROM config_recent_changes 
WHERE config_key = 'data_collection.batch_size';
```

### Get/Set Symbol Configuration

```sql
-- Enable ticker for symbol
SELECT set_symbol_config(1, 'collect_24hr_ticker', true, 'admin');

-- Change tick interval
SELECT set_symbol_config(1, 'tick_snapshot_interval_sec', 5, 'admin');

-- Get symbol config
SELECT * FROM get_symbol_config(1);

-- Get all active symbols
SELECT * FROM active_collection_symbols;
```

### Query Service Status

```sql
-- Check all services
SELECT * FROM service_health_overview;

-- Check specific service
SELECT * FROM service_status WHERE service_name = 'data-collector';
```

---

## Environment File (.env)

**Only DB connection string**:

```bash
# Database Connection
DATABASE_URL=postgresql://crypto:crypto_secret@localhost:5432/crypto_trading

# Optional: Override specific config (for development)
# APP_ENVIRONMENT=development
# LOG_LEVEL=DEBUG
```

**All other configuration comes from database!**

---

## Configuration Management CLI

**File**: `src/cli/commands/config.py` (updated)

```python
"""Configuration management CLI."""

import click
import asyncio
import asyncpg
import json
from tabulate import tabulate


@click.group()
def config():
    """Configuration management."""
    pass


@config.command()
@click.option('--db-dsn', envvar='DATABASE_URL', required=True)
@click.argument('key')
async def get(db_dsn, key):
    """Get system configuration value."""
    pool = await asyncpg.create_pool(db_dsn)
    
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value, description, updated_at FROM system_config WHERE key = $1",
                key
            )
            
            if row:
                click.echo(f"Key: {key}")
                click.echo(f"Value: {row['value']->'value'}")
                click.echo(f"Description: {row['description']}")
                click.echo(f"Updated: {row['updated_at']}")
            else:
                click.echo(f"Configuration key '{key}' not found")
    
    finally:
        await pool.close()


@config.command()
@click.option('--db-dsn', envvar='DATABASE_URL', required=True)
@click.argument('key')
@click.argument('value')
async def set(db_dsn, key, value):
    """Set system configuration value."""
    pool = await asyncpg.create_pool(db_dsn)
    
    try:
        async with pool.acquire() as conn:
            # Parse value
            try:
                value_json = json.loads(value)
            except json.JSONDecodeError:
                # Try to infer type
                if value.lower() == 'true':
                    value_json = True
                elif value.lower() == 'false':
                    value_json = False
                elif value.isdigit():
                    value_json = int(value)
                else:
                    value_json = value
            
            # Set config
            result = await conn.fetchval(
                "SELECT set_config($1, $2, 'cli')",
                key, value_json
            )
            
            if result:
                click.echo(f"✓ Updated {key} = {value_json}")
            else:
                click.echo("✗ Failed to update configuration")
    
    finally:
        await pool.close()


@config.command()
@click.option('--db-dsn', envvar='DATABASE_URL', required=True)
async def list_system(db_dsn):
    """List all system configurations."""
    pool = await asyncpg.create_pool(db_dsn)
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT key, value->>'value' AS value, description, updated_at
                FROM system_config
                WHERE is_sensitive = false
                ORDER BY key
            """)
            
            click.echo("\nSystem Configuration:")
            click.echo("=" * 80)
            click.echo(tabulate(
                [dict(row) for row in rows],
                headers=['Key', 'Value', 'Description', 'Updated'],
                tablefmt='grid',
                maxcolwidths=[30, 20, 30, 20]
            ))
    
    finally:
        await pool.close()


@config.command()
@click.option('--db-dsn', envvar='DATABASE_URL', required=True)
@click.option('--symbol', default=None)
async def list_symbols(db_dsn, symbol):
    """List symbol configurations."""
    pool = await asyncpg.create_pool(db_dsn)
    
    try:
        async with pool.acquire() as conn:
            if symbol:
                rows = await conn.fetch("""
                    SELECT 
                        s.symbol,
                        cc.collect_ticks,
                        cc.collect_24hr_ticker,
                        cc.collect_orderbook,
                        cc.tick_snapshot_interval_sec,
                        cc.ticker_snapshot_interval_sec,
                        cc.is_collecting,
                        cc.config_version
                    FROM collection_config cc
                    JOIN symbols s ON s.id = cc.symbol_id
                    WHERE s.symbol = $1
                """, symbol)
            else:
                rows = await conn.fetch("""
                    SELECT 
                        s.symbol,
                        cc.collect_ticks,
                        cc.collect_24hr_ticker,
                        cc.collect_orderbook,
                        cc.tick_snapshot_interval_sec,
                        cc.ticker_snapshot_interval_sec,
                        cc.is_collecting
                    FROM collection_config cc
                    JOIN symbols s ON s.id = cc.symbol_id
                    ORDER BY s.symbol
                """)
            
            click.echo("\nSymbol Configuration:")
            click.echo("=" * 100)
            click.echo(tabulate(
                [dict(row) for row in rows],
                headers='keys',
                tablefmt='grid'
            ))
    
    finally:
        await pool.close()


@config.command()
@click.option('--db-dsn', envvar='DATABASE_URL', required=True)
@click.option('--limit', default=20)
async def history(db_dsn, limit):
    """Show configuration change history."""
    pool = await asyncpg.create_pool(db_dsn)
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    config_type,
                    config_key,
                    old_value,
                    new_value,
                    changed_by,
                    changed_at,
                    status
                FROM config_change_log
                ORDER BY changed_at DESC
                LIMIT $1
            """, limit)
            
            click.echo("\nConfiguration Change History:")
            click.echo("=" * 120)
            click.echo(tabulate(
                [dict(row) for row in rows],
                headers='keys',
                tablefmt='grid'
            ))
    
    finally:
        await pool.close()


@config.command()
@click.option('--db-dsn', envvar='DATABASE_URL', required=True)
async def services(db_dsn):
    """Show service status."""
    pool = await asyncpg.create_pool(db_dsn)
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM service_health_overview")
            
            click.echo("\nService Status:")
            click.echo("=" * 100)
            click.echo(tabulate(
                [dict(row) for row in rows],
                headers='keys',
                tablefmt='grid'
            ))
    
    finally:
        await pool.close()
```

---

## Summary

### Configuration Tables

| Table | Purpose | Rows |
|-------|---------|------|
| **system_config** | Global settings | ~30 |
| **collection_config** | Per-symbol settings | #symbols |
| **config_change_log** | Audit trail | Unlimited |
| **service_status** | Service health | ~8 |

### Only in .env

```bash
DATABASE_URL=postgresql://...
```

### Everything Else in Database

- ✅ Application settings
- ✅ Data collection config
- ✅ Quality thresholds
- ✅ Enrichment settings
- ✅ Storage policies
- ✅ Monitoring config
- ✅ Per-symbol configuration
- ✅ Service status
- ✅ Audit trail

**Ready to implement!**
