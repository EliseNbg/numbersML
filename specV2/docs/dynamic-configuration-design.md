# Dynamic Configuration Design

## Overview

**Goal**: All data collection parameters must be configurable **at runtime** without restarting services.

**Key Configuration Areas**:
1. Active symbols (which symbols to collect)
2. Data types per symbol (ticks, order book, candles)
3. Collection frequency (1s, 5s, 1m)
4. Retention policies (how long to keep data)
5. Quality thresholds (validation rules)

---

## Configuration Architecture

```
┌────────────────────────────────────────────────────────────┐
│                 CONFIGURATION LAYERS                        │
│                                                             │
│  Layer 1: Database (Source of Truth)                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  PostgreSQL Tables                                    │  │
│  │  - symbols (is_active, metadata)                     │  │
│  │  - collection_config (per-symbol config)             │  │
│  │  - system_config (global settings)                   │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ▲                                  │
│                          │ LISTEN/NOTIFY                    │
│  Layer 2: Application Cache                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  In-Memory Config (per service)                      │  │
│  │  - Reloads on NOTIFY                                  │  │
│  │  - Validates changes                                  │  │
│  │  - Applies without restart                            │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ▲                                  │
│                          │                                  │
│  Layer 3: CLI / API                                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Management Interface                                 │  │
│  │  - crypto config set symbol BTC/USDT ...             │  │
│  │  - crypto config get symbol BTC/USDT                 │  │
│  │  - crypto config reload                               │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### 1. Collection Configuration Table

```sql
-- Per-symbol collection configuration
CREATE TABLE collection_config (
    symbol_id INTEGER PRIMARY KEY REFERENCES symbols(id),
    
    -- Data collection flags
    collect_ticks BOOLEAN NOT NULL DEFAULT true,
    collect_orderbook BOOLEAN NOT NULL DEFAULT false,
    collect_candles BOOLEAN NOT NULL DEFAULT true,
    
    -- Collection frequency (in seconds)
    tick_snapshot_interval_sec INTEGER NOT NULL DEFAULT 1,
    orderbook_snapshot_interval_sec INTEGER DEFAULT 1,
    candle_intervals TEXT[] NOT NULL DEFAULT '{"1m", "5m", "15m", "1h"}',
    
    -- Order book configuration (for future implementation)
    orderbook_levels INTEGER DEFAULT 10,  -- 10, 20, or full depth
    orderbook_storage_mode TEXT DEFAULT 'arrays',  -- 'arrays', 'normalized', 'deltas'
    
    -- Retention policies (in days)
    tick_retention_days INTEGER NOT NULL DEFAULT 180,
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
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Index for active collection
CREATE INDEX idx_collection_config_collecting 
    ON collection_config(is_collecting) 
    WHERE is_collecting = true;

-- Trigger to update timestamp
CREATE TRIGGER collection_config_update_timestamp
    BEFORE UPDATE ON collection_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

### 2. System Configuration Table

```sql
-- Global system configuration
CREATE TABLE system_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    is_sensitive BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by TEXT
);

-- Insert default configuration
INSERT INTO system_config (key, value, description) VALUES
('data_collection', '{
    "enabled": true,
    "batch_size": 500,
    "batch_interval_ms": 500,
    "max_reconnect_attempts": 10,
    "reconnect_delay_sec": 5
}'::jsonb, 'Global data collection settings'),

('data_quality', '{
    "enable_validation": true,
    "max_price_move_pct": 10.0,
    "max_gap_seconds": 5,
    "auto_reject_invalid": true
}'::jsonb, 'Data quality validation settings'),

('enrichment', '{
    "enabled": true,
    "window_size": 1000,
    "batch_size": 100,
    "max_latency_ms": 100,
    "indicators": ["rsi_14", "macd", "sma_20", "ema_20", "bollinger"]
}'::jsonb, 'Indicator enrichment settings'),

('storage', '{
    "enable_compression": true,
    "compression_age_days": 30,
    "enable_partitioning": true,
    "partition_interval": "1 month"
}'::jsonb, 'Storage optimization settings'),

('monitoring', '{
    "health_check_interval_sec": 30,
    "metrics_enabled": true,
    "alert_webhook": null,
    "log_level": "INFO"
}'::jsonb, 'Monitoring and alerting settings');
```

### 3. Configuration Change Log

```sql
-- Audit trail for configuration changes
CREATE TABLE config_change_log (
    id BIGSERIAL PRIMARY KEY,
    config_type TEXT NOT NULL,  -- 'symbol', 'system'
    config_key TEXT NOT NULL,   -- symbol_id or config key
    old_value JSONB,
    new_value JSONB NOT NULL,
    changed_by TEXT NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    applied_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'pending'  -- pending, applied, failed
);

CREATE INDEX idx_config_change_log_type_key 
    ON config_change_log(config_type, config_key);
CREATE INDEX idx_config_change_log_status 
    ON config_change_log(status) 
    WHERE status = 'pending';
```

---

## Configuration Management Service

**File**: `src/application/services/config_manager.py`

```python
"""Dynamic configuration management."""

import asyncio
import asyncpg
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class SymbolConfig:
    """Configuration for a single symbol."""
    
    symbol_id: int
    symbol: str
    
    # Data collection
    collect_ticks: bool = True
    collect_orderbook: bool = False  # For future implementation
    collect_candles: bool = True
    
    # Frequency
    tick_snapshot_interval_sec: int = 1
    orderbook_snapshot_interval_sec: int = 1
    candle_intervals: List[str] = None
    
    # Order book (future)
    orderbook_levels: int = 10
    orderbook_storage_mode: str = 'arrays'
    
    # Retention
    tick_retention_days: int = 180
    orderbook_retention_days: int = 30
    candle_retention_days: int = 365
    
    # Quality
    max_price_move_pct: float = 10.0
    max_quantity_move_pct: float = 50.0
    max_gap_seconds: int = 5
    
    # Status
    is_collecting: bool = False
    config_version: int = 1
    
    def __post_init__(self):
        if self.candle_intervals is None:
            self.candle_intervals = ['1m', '5m', '15m', '1h']


class ConfigManager:
    """
    Manages dynamic configuration.
    
    Features:
    - Load configuration from database
    - Listen for configuration changes (PostgreSQL NOTIFY)
    - Update configuration at runtime
    - Validate configuration changes
    - Audit trail of changes
    """
    
    def __init__(self, db_pool: asyncpg.Pool, service_name: str):
        self.db_pool = db_pool
        self.service_name = service_name
        
        # In-memory cache
        self._symbol_configs: Dict[int, SymbolConfig] = {}
        self._system_configs: Dict[str, Any] = {}
        
        # Change listeners
        self._change_callbacks: List[callable] = []
    
    async def initialize(self):
        """Load initial configuration."""
        logger.info(f"{self.service_name}: Loading configuration...")
        
        await self._load_symbol_configs()
        await self._load_system_configs()
        
        logger.info(
            f"{self.service_name}: Loaded {len(self._symbol_configs)} symbol configs"
        )
    
    async def start_listening(self):
        """Start listening for configuration changes."""
        logger.info(f"{self.service_name}: Starting config change listener...")
        
        async with self.db_pool.acquire() as conn:
            await conn.listen('config_changed')
            
            async for notification in conn.notifications():
                try:
                    data = json.loads(notification.payload)
                    await self._handle_config_change(data)
                except Exception as e:
                    logger.error(f"Error handling config change: {e}")
    
    async def _load_symbol_configs(self):
        """Load all symbol configurations."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    cc.*,
                    s.symbol,
                    s.is_active
                FROM collection_config cc
                JOIN symbols s ON s.id = cc.symbol_id
                WHERE s.is_active = true OR cc.is_collecting = true
            """)
            
            for row in rows:
                self._symbol_configs[row['symbol_id']] = SymbolConfig(
                    symbol_id=row['symbol_id'],
                    symbol=row['symbol'],
                    collect_ticks=row['collect_ticks'],
                    collect_orderbook=row['collect_orderbook'],
                    collect_candles=row['collect_candles'],
                    tick_snapshot_interval_sec=row['tick_snapshot_interval_sec'],
                    orderbook_snapshot_interval_sec=row['orderbook_snapshot_interval_sec'],
                    candle_intervals=row['candle_intervals'],
                    orderbook_levels=row['orderbook_levels'],
                    orderbook_storage_mode=row['orderbook_storage_mode'],
                    tick_retention_days=row['tick_retention_days'],
                    orderbook_retention_days=row['orderbook_retention_days'],
                    candle_retention_days=row['candle_retention_days'],
                    max_price_move_pct=float(row['max_price_move_pct']),
                    max_quantity_move_pct=float(row['max_quantity_move_pct']),
                    max_gap_seconds=row['max_gap_seconds'],
                    is_collecting=row['is_collecting'],
                    config_version=row['config_version'],
                )
    
    async def _load_system_configs(self):
        """Load all system configurations."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT key, value FROM system_config"
            )
            
            for row in rows:
                self._system_configs[row['key']] = row['value']
    
    async def _handle_config_change(self, data: dict):
        """Handle configuration change notification."""
        config_type = data.get('type')
        config_key = data.get('key')
        
        logger.info(
            f"{self.service_name}: Configuration change detected: "
            f"{config_type}.{config_key}"
        )
        
        # Reload configuration
        if config_type == 'symbol':
            await self._reload_symbol_config(int(config_key))
        elif config_type == 'system':
            await self._reload_system_config(config_key)
        
        # Notify callbacks
        for callback in self._change_callbacks:
            try:
                await callback(config_type, config_key, data)
            except Exception as e:
                logger.error(f"Config change callback error: {e}")
    
    async def _reload_symbol_config(self, symbol_id: int):
        """Reload configuration for a single symbol."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT cc.*, s.symbol
                FROM collection_config cc
                JOIN symbols s ON s.id = cc.symbol_id
                WHERE cc.symbol_id = $1
            """, symbol_id)
            
            if row:
                self._symbol_configs[symbol_id] = SymbolConfig(
                    symbol_id=row['symbol_id'],
                    symbol=row['symbol'],
                    collect_ticks=row['collect_ticks'],
                    collect_orderbook=row['collect_orderbook'],
                    collect_candles=row['collect_candles'],
                    tick_snapshot_interval_sec=row['tick_snapshot_interval_sec'],
                    orderbook_snapshot_interval_sec=row['orderbook_snapshot_interval_sec'],
                    candle_intervals=row['candle_intervals'],
                    orderbook_levels=row['orderbook_levels'],
                    orderbook_storage_mode=row['orderbook_storage_mode'],
                    tick_retention_days=row['tick_retention_days'],
                    orderbook_retention_days=row['orderbook_retention_days'],
                    candle_retention_days=row['candle_retention_days'],
                    max_price_move_pct=float(row['max_price_move_pct']),
                    max_quantity_move_pct=float(row['max_quantity_move_pct']),
                    max_gap_seconds=row['max_gap_seconds'],
                    is_collecting=row['is_collecting'],
                    config_version=row['config_version'],
                )
                logger.info(f"Reloaded config for {row['symbol']}")
    
    async def _reload_system_config(self, key: str):
        """Reload a single system configuration."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM system_config WHERE key = $1", key
            )
            
            if row:
                self._system_configs[key] = row['value']
                logger.info(f"Reloaded system config: {key}")
    
    def get_symbol_config(self, symbol_id: int) -> Optional[SymbolConfig]:
        """Get configuration for a symbol."""
        return self._symbol_configs.get(symbol_id)
    
    def get_all_symbol_configs(self) -> List[SymbolConfig]:
        """Get all symbol configurations."""
        return list(self._symbol_configs.values())
    
    def get_active_symbols(self) -> List[SymbolConfig]:
        """Get configurations for actively collected symbols."""
        return [
            config for config in self._symbol_configs.values()
            if config.is_collecting
        ]
    
    def get_system_config(self, key: str, default: Any = None) -> Any:
        """Get system configuration value."""
        return self._system_configs.get(key, default)
    
    def register_change_callback(self, callback: callable):
        """Register callback for configuration changes."""
        self._change_callbacks.append(callback)
    
    async def update_symbol_config(
        self,
        symbol_id: int,
        updates: Dict[str, Any],
        changed_by: str = 'system'
    ) -> bool:
        """
        Update symbol configuration.
        
        Returns True if update was applied.
        """
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                # Build update query
                set_clauses = []
                values = [symbol_id]
                
                for key, value in updates.items():
                    set_clauses.append(f"{key} = ${len(values) + 1}")
                    values.append(value)
                
                set_clauses.append("last_config_change = NOW()")
                set_clauses.append("config_version = config_version + 1")
                
                query = f"""
                    UPDATE collection_config
                    SET {', '.join(set_clauses)},
                        updated_at = NOW()
                    WHERE symbol_id = $1
                    RETURNING symbol_id
                """
                
                result = await conn.fetchval(query, *values)
                
                if result:
                    # Log change
                    await conn.execute(
                        """
                        INSERT INTO config_change_log 
                        (config_type, config_key, new_value, changed_by, changed_at)
                        VALUES ($1, $2, $3, $4, NOW())
                        """,
                        'symbol',
                        symbol_id,
                        json.dumps(updates),
                        changed_by,
                    )
                    
                    # Notify change
                    await conn.execute(
                        """
                        SELECT pg_notify('config_changed', $1)
                        """,
                        json.dumps({
                            'type': 'symbol',
                            'key': str(symbol_id),
                            'changes': updates,
                        })
                    )
                    
                    logger.info(f"Updated config for symbol {symbol_id}")
                    return True
                
                return False
    
    async def update_system_config(
        self,
        key: str,
        value: Any,
        changed_by: str = 'system'
    ) -> bool:
        """Update system configuration."""
        async with self.db_pool.acquire() as conn:
            result = await conn.execute(
                """
                INSERT INTO system_config (key, value, updated_at, updated_by)
                VALUES ($1, $2, NOW(), $3)
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = NOW(),
                    updated_by = EXCLUDED.updated_by
                """,
                key, value, changed_by
            )
            
            # Log change
            await conn.execute(
                """
                INSERT INTO config_change_log 
                (config_type, config_key, new_value, changed_by, changed_at)
                VALUES ($1, $2, $3, $4, NOW())
                """,
                'system',
                key,
                json.dumps({'value': value}),
                changed_by,
            )
            
            # Notify change
            await conn.execute(
                """
                SELECT pg_notify('config_changed', $1)
                """,
                json.dumps({
                    'type': 'system',
                    'key': key,
                    'changes': {'value': value},
                })
            )
            
            logger.info(f"Updated system config: {key}")
            return True
```

---

## CLI Commands

**File**: `src/cli/commands/config.py`

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
async def list_symbols(db_dsn):
    """List all symbol configurations."""
    pool = await asyncpg.create_pool(db_dsn)
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    s.symbol,
                    cc.is_collecting,
                    cc.collect_ticks,
                    cc.collect_orderbook,
                    cc.tick_snapshot_interval_sec AS tick_interval,
                    cc.orderbook_levels AS ob_levels,
                    cc.tick_retention_days AS retention,
                    cc.config_version AS version
                FROM symbols s
                LEFT JOIN collection_config cc ON cc.symbol_id = s.id
                ORDER BY s.symbol
            """)
            
            click.echo("\nSymbol Configurations:")
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
@click.argument('symbol')
@click.argument('key')
@click.argument('value')
async def set_symbol(db_dsn, symbol, key, value):
    """
    Set symbol configuration value.
    
    Examples:
    
    \b
    # Enable order book collection
    crypto config set-symbol BTC/USDT collect_orderbook true
    
    \b
    # Change tick snapshot interval
    crypto config set-symbol BTC/USDT tick_snapshot_interval_sec 5
    
    \b
    # Change retention
    crypto config set-symbol BTC/USDT tick_retention_days 90
    """
    pool = await asyncpg.create_pool(db_dsn)
    
    try:
        async with pool.acquire() as conn:
            # Get symbol_id
            symbol_id = await conn.fetchval(
                "SELECT id FROM symbols WHERE symbol = $1", symbol
            )
            
            if not symbol_id:
                click.echo(f"Error: Symbol {symbol} not found")
                return
            
            # Validate key
            valid_keys = [
                'collect_ticks', 'collect_orderbook', 'collect_candles',
                'tick_snapshot_interval_sec', 'orderbook_snapshot_interval_sec',
                'orderbook_levels', 'orderbook_storage_mode',
                'tick_retention_days', 'orderbook_retention_days', 'candle_retention_days',
                'max_price_move_pct', 'max_quantity_move_pct', 'max_gap_seconds',
                'is_collecting'
            ]
            
            if key not in valid_keys:
                click.echo(f"Error: Invalid key '{key}'")
                click.echo(f"Valid keys: {', '.join(valid_keys)}")
                return
            
            # Convert value type
            if key in ['collect_ticks', 'collect_orderbook', 'collect_candles', 'is_collecting']:
                value = value.lower() == 'true'
            elif key in ['tick_snapshot_interval_sec', 'orderbook_snapshot_interval_sec', 
                        'orderbook_levels', 'tick_retention_days', 'orderbook_retention_days',
                        'candle_retention_days', 'max_gap_seconds']:
                value = int(value)
            elif key in ['max_price_move_pct', 'max_quantity_move_pct']:
                value = float(value)
            
            # Update
            await conn.execute(
                f"""
                INSERT INTO collection_config (symbol_id, {key})
                VALUES ($1, $2)
                ON CONFLICT (symbol_id) DO UPDATE SET
                    {key} = EXCLUDED.{key},
                    last_config_change = NOW(),
                    config_version = collection_config.config_version + 1
                """,
                symbol_id, value
            )
            
            # Notify change
            await conn.execute(
                """
                SELECT pg_notify('config_changed', $1)
                """,
                json.dumps({
                    'type': 'symbol',
                    'key': str(symbol_id),
                    'changes': {key: value},
                })
            )
            
            click.echo(f"✓ Updated {symbol}.{key} = {value}")
    
    finally:
        await pool.close()


@config.command()
@click.option('--db-dsn', envvar='DATABASE_URL', required=True)
@click.argument('symbol')
async def get_symbol(db_dsn, symbol):
    """Get symbol configuration."""
    pool = await asyncpg.create_pool(db_dsn)
    
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT 
                    s.symbol,
                    cc.*,
                    s.is_active
                FROM symbols s
                LEFT JOIN collection_config cc ON cc.symbol_id = s.id
                WHERE s.symbol = $1
            """, symbol)
            
            if not row:
                click.echo(f"Error: Symbol {symbol} not found")
                return
            
            click.echo(f"\nConfiguration for {symbol}:")
            click.echo("=" * 50)
            
            # Data collection
            click.echo("\nData Collection:")
            click.echo(f"  Active: {row['is_active']}")
            click.echo(f"  Collecting: {row['is_collecting']}")
            click.echo(f"  Ticks: {row['collect_ticks']}")
            click.echo(f"  Order Book: {row['collect_orderbook']}")
            click.echo(f"  Candles: {row['collect_candles']}")
            
            # Frequency
            click.echo("\nFrequency:")
            click.echo(f"  Tick Interval: {row['tick_snapshot_interval_sec']}s")
            click.echo(f"  Order Book Interval: {row['orderbook_snapshot_interval_sec']}s")
            click.echo(f"  Candle Intervals: {', '.join(row['candle_intervals'])}")
            
            # Order book
            click.echo("\nOrder Book (Future):")
            click.echo(f"  Levels: {row['orderbook_levels']}")
            click.echo(f"  Storage Mode: {row['orderbook_storage_mode']}")
            
            # Retention
            click.echo("\nRetention:")
            click.echo(f"  Ticks: {row['tick_retention_days']} days")
            click.echo(f"  Order Book: {row['orderbook_retention_days']} days")
            click.echo(f"  Candles: {row['candle_retention_days']} days")
            
            # Quality
            click.echo("\nQuality Thresholds:")
            click.echo(f"  Max Price Move: {row['max_price_move_pct']}%")
            click.echo(f"  Max Quantity Move: {row['max_quantity_move_pct']}%")
            click.echo(f"  Max Gap: {row['max_gap_seconds']}s")
            
            # Version
            click.echo(f"\nConfig Version: {row['config_version']}")
            click.echo(f"  Last Change: {row['last_config_change']}")
    
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
                SELECT key, value, description, updated_at
                FROM system_config
                ORDER BY key
            """)
            
            click.echo("\nSystem Configurations:")
            click.echo("=" * 100)
            
            for row in rows:
                click.echo(f"\n{row['key']}:")
                click.echo(f"  Value: {json.dumps(row['value'], indent=2)}")
                click.echo(f"  Description: {row['description']}")
                click.echo(f"  Updated: {row['updated_at']}")
    
    finally:
        await pool.close()


@config.command()
@click.option('--db-dsn', envvar='DATABASE_URL', required=True)
@click.argument('key')
@click.argument('value')
async def set_system(db_dsn, key, value):
    """
    Set system configuration value.
    
    Examples:
    
    \b
    # Change log level
    crypto config set-system monitoring '{"log_level": "DEBUG"}'
    
    \b
    # Enable/disable data collection
    crypto config set-system data_collection '{"enabled": false}'
    """
    pool = await asyncpg.create_pool(db_dsn)
    
    try:
        # Parse JSON value
        try:
            value_json = json.loads(value)
        except json.JSONDecodeError:
            click.echo(f"Error: Value must be valid JSON")
            return
        
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO system_config (key, value, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = NOW()
                """,
                key, value_json
            )
            
            # Notify change
            await conn.execute(
                """
                SELECT pg_notify('config_changed', $1)
                """,
                json.dumps({
                    'type': 'system',
                    'key': key,
                    'changes': {'value': value_json},
                })
            )
            
            click.echo(f"✓ Updated system config: {key}")
    
    finally:
        await pool.close()


@config.command()
@click.option('--db-dsn', envvar='DATABASE_URL', required=True)
@click.option('--symbol', default=None, help='Filter by symbol')
async def history(db_dsn, symbol):
    """Show configuration change history."""
    pool = await asyncpg.create_pool(db_dsn)
    
    try:
        async with pool.acquire() as conn:
            if symbol:
                rows = await conn.fetch("""
                    SELECT 
                        ccl.*,
                        s.symbol
                    FROM config_change_log ccl
                    JOIN symbols s ON s.id = ccl.config_key::int
                    WHERE ccl.config_type = 'symbol'
                      AND s.symbol = $1
                    ORDER BY ccl.changed_at DESC
                    LIMIT 50
                """, symbol)
            else:
                rows = await conn.fetch("""
                    SELECT ccl.*, s.symbol
                    FROM config_change_log ccl
                    LEFT JOIN symbols s ON 
                        (ccl.config_type = 'symbol' AND s.id = ccl.config_key::int)
                    ORDER BY ccl.changed_at DESC
                    LIMIT 50
                """)
            
            click.echo("\nConfiguration Change History:")
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

## Usage Examples

### 1. Enable Order Book for Specific Symbols

```bash
# Enable order book collection for BTC/USDT (future use)
crypto config set-symbol BTC/USDT collect_orderbook true
crypto config set-symbol BTC/USDT orderbook_levels 20

# Keep ticks disabled for order book-only symbols
crypto config set-symbol BTC/USDT collect_ticks false

# View configuration
crypto config get-symbol BTC/USDT
```

### 2. Change Collection Frequency

```bash
# Change tick snapshot interval to 5 seconds (save storage)
crypto config set-symbol BTC/USDT tick_snapshot_interval_sec 5

# Change for all symbols (via SQL)
psql $DATABASE_URL -c "
UPDATE collection_config 
SET tick_snapshot_interval_sec = 5 
WHERE symbol_id IN (SELECT id FROM symbols WHERE is_active = true);
SELECT pg_notify('config_changed', '{\"type\":\"bulk_update\"}');
"
```

### 3. Adjust Retention Policies

```bash
# Reduce tick retention to 90 days
crypto config set-symbol BTC/USDT tick_retention_days 90

# Set order book retention (for future)
crypto config set-symbol ETH/USDT orderbook_retention_days 30
```

### 4. Configure Quality Thresholds

```bash
# Increase max price move threshold for volatile symbols
crypto config set-symbol DOGE/USDT max_price_move_pct 20.0

# Reduce max gap for critical symbols
crypto config set-symbol BTC/USDT max_gap_seconds 3
```

### 5. View Configuration

```bash
# List all symbol configurations
crypto config list-symbols

# Get specific symbol config
crypto config get-symbol BTC/USDT

# View change history
crypto config history --symbol BTC/USDT
```

---

## Integration with Services

### Data Collector Integration

```python
# In DataCollectionService

class DataCollectionService:
    def __init__(self, ...):
        self.config_manager = ConfigManager(self.db_pool, "data-collector")
        self._collect_ticks: Dict[int, bool] = {}
        self._snapshot_intervals: Dict[int, int] = {}
    
    async def start(self):
        # Initialize configuration
        await self.config_manager.initialize()
        
        # Register for config changes
        self.config_manager.register_change_callback(self._on_config_change)
        
        # Start listening for config changes (background task)
        asyncio.create_task(self.config_manager.start_listening())
        
        # Apply initial configuration
        await self._apply_symbol_configs()
        
        # Start collection
        await self._start_collection()
    
    async def _on_config_change(self, config_type: str, key: str, data: dict):
        """Handle configuration changes."""
        if config_type == 'symbol':
            symbol_id = int(key)
            await self._reload_symbol_config(symbol_id)
    
    async def _reload_symbol_config(self, symbol_id: int):
        """Reload configuration for symbol and adjust collection."""
        config = self.config_manager.get_symbol_config(symbol_id)
        
        if config:
            self._collect_ticks[symbol_id] = config.collect_ticks
            self._snapshot_intervals[symbol_id] = config.tick_snapshot_interval_sec
            
            logger.info(
                f"Updated config for symbol {config.symbol}: "
                f"collect_ticks={config.collect_ticks}, "
                f"interval={config.tick_snapshot_interval_sec}s"
            )
```

---

## Summary

### What You Get

✅ **Dynamic Configuration**:
- Change collection parameters without restart
- Per-symbol configuration
- System-wide settings

✅ **Order Book Ready**:
- Configuration fields ready (collect_orderbook, orderbook_levels, etc.)
- Just enable when you implement it

✅ **Audit Trail**:
- All changes logged
- Version tracking
- Change history

✅ **CLI Management**:
- Easy command-line interface
- List, get, set configurations
- View history

✅ **Automatic Reload**:
- PostgreSQL NOTIFY/LISTEN
- Services reload config automatically
- No downtime

---

## Next Steps

1. **Create database tables** (collection_config, system_config, config_change_log)
2. **Implement ConfigManager** service
3. **Add CLI commands** (config.py)
4. **Integrate with DataCollector**
5. **Test dynamic changes** (change config, verify service adapts)

**Ready to implement?**
