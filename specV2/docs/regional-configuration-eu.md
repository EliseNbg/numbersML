# Regional Configuration - EU Compliance

## Overview

**Problem**: Not all cryptocurrencies/stablecoins are available in all regions (e.g., USDT restricted in EU)

**Solution**: Configurable allowed/restricted assets in database

---

## Configuration Variables

### Add to `system_config` table

```sql
-- Regional/Regulatory settings
INSERT INTO system_config (key, value, description) VALUES

-- Allowed quote assets (EU compliance)
('region.allowed_quote_assets', 
 '{"value": ["USDC", "BTC", "ETH"], "description": "Allowed quote assets for EU region"}'::jsonb, 
 'Allowed quote assets (USDT not allowed in EU)'),

-- Allowed base assets (empty = all allowed)
('region.allowed_base_assets', 
 '{"value": [], "description": "Restricted base assets (empty = all allowed)"}'::jsonb, 
 'Allowed base assets'),

-- Restricted symbols (specific exclusions)
('region.restricted_symbols', 
 '{"value": [], "description": "Specific symbols to exclude"}'::jsonb, 
 'Restricted symbols (e.g. leverage tokens)'),

-- Enable/disable auto-filtering
('region.enable_auto_filter', 
 '{"value": true, "description": "Auto-filter symbols based on region"}'::jsonb, 
 'Enable automatic symbol filtering'),

-- Region code
('app.region', 
 '{"value": "EU", "allowed": ["US", "EU", "UK", "GLOBAL"]}'::jsonb, 
 'Operating region');
```

---

## Helper Functions

```sql
-- Function: Check if quote asset is allowed
CREATE OR REPLACE FUNCTION is_quote_asset_allowed(p_asset TEXT)
RETURNS BOOLEAN AS $$
DECLARE
    v_allowed_assets TEXT[];
BEGIN
    -- Get allowed quote assets from config
    SELECT (value->'value')::TEXT[] INTO v_allowed_assets
    FROM system_config
    WHERE key = 'region.allowed_quote_assets';
    
    -- If no allowed assets defined, allow all
    IF v_allowed_assets IS NULL OR array_length(v_allowed_assets, 1) IS NULL THEN
        RETURN TRUE;
    END IF;
    
    -- Check if asset is in allowed list
    RETURN p_asset = ANY(v_allowed_assets);
END;
$$ LANGUAGE plpgsql STABLE;

-- Function: Check if base asset is allowed
CREATE OR REPLACE FUNCTION is_base_asset_allowed(p_asset TEXT)
RETURNS BOOLEAN AS $$
DECLARE
    v_allowed_assets TEXT[];
BEGIN
    -- Get allowed base assets from config
    SELECT (value->'value')::TEXT[] INTO v_allowed_assets
    FROM system_config
    WHERE key = 'region.allowed_base_assets';
    
    -- If no allowed assets defined, allow all
    IF v_allowed_assets IS NULL OR array_length(v_allowed_assets, 1) IS NULL THEN
        RETURN TRUE;
    END IF;
    
    -- Check if asset is in allowed list
    RETURN p_asset = ANY(v_allowed_assets);
END;
$$ LANGUAGE plpgsql STABLE;

-- Function: Check if symbol is allowed
CREATE OR REPLACE FUNCTION is_symbol_allowed(p_symbol TEXT)
RETURNS BOOLEAN AS $$
DECLARE
    v_base_asset TEXT;
    v_quote_asset TEXT;
    v_restricted_symbols TEXT[];
BEGIN
    -- Parse symbol (e.g., "BTC/USDC" → base="BTC", quote="USDC")
    v_base_asset := split_part(p_symbol, '/', 1);
    v_quote_asset := split_part(p_symbol, '/', 2);
    
    -- Check if quote asset is allowed
    IF NOT is_quote_asset_allowed(v_quote_asset) THEN
        RETURN FALSE;
    END IF;
    
    -- Check if base asset is allowed
    IF NOT is_base_asset_allowed(v_base_asset) THEN
        RETURN FALSE;
    END IF;
    
    -- Check if symbol is in restricted list
    SELECT (value->'value')::TEXT[] INTO v_restricted_symbols
    FROM system_config
    WHERE key = 'region.restricted_symbols';
    
    IF v_restricted_symbols IS NOT NULL AND p_symbol = ANY(v_restricted_symbols) THEN
        RETURN FALSE;
    END IF;
    
    -- Check if auto-filter is enabled
    IF NOT (SELECT (value->>'value')::BOOLEAN 
            FROM system_config 
            WHERE key = 'region.enable_auto_filter') THEN
        RETURN TRUE;
    END IF;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql STABLE;

-- Function: Get allowed symbols from Binance
CREATE OR REPLACE FUNCTION get_allowed_symbols(p_exchange TEXT DEFAULT 'binance')
RETURNS TABLE (
    symbol TEXT,
    base_asset TEXT,
    quote_asset TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        s.symbol,
        s.base_asset,
        s.quote_asset
    FROM symbols s
    WHERE s.exchange = p_exchange
      AND s.is_active = true
      AND is_symbol_allowed(s.symbol);
END;
$$ LANGUAGE plpgsql STABLE;
```

---

## Updated Collection Config

```sql
-- Add to collection_config table
ALTER TABLE collection_config ADD COLUMN 
    -- Regional filtering
    is_allowed BOOLEAN NOT NULL DEFAULT true,
    last_region_check TIMESTAMP DEFAULT NOW();

-- Trigger to update region check
CREATE OR REPLACE FUNCTION update_region_check()
RETURNS TRIGGER AS $$
BEGIN
    NEW.is_allowed := is_symbol_allowed(
        (SELECT symbol FROM symbols WHERE id = NEW.symbol_id)
    );
    NEW.last_region_check := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to collection_config
CREATE TRIGGER collection_config_region_check
    BEFORE INSERT OR UPDATE ON collection_config
    FOR EACH ROW
    EXECUTE FUNCTION update_region_check();
```

---

## Ticker Collector Integration

**Update ticker collector to filter by allowed symbols**:

```python
# src/infrastructure/exchanges/ticker_collector.py

class TickerStatsCollector:
    def __init__(self, db_pool: asyncpg.Pool, symbols: List[str] = None):
        self.db_pool = db_pool
        self.symbols = symbols  # Can be None (load from DB)
        self._symbol_ids: Dict[str, int] = {}
        self._running = False
    
    async def _init_symbols(self):
        """Initialize symbol mappings from database (filtered by region)."""
        async with self.db_pool.acquire() as conn:
            if self.symbols:
                # Specific symbols requested
                rows = await conn.fetch("""
                    SELECT id, symbol FROM symbols
                    WHERE symbol = ANY($1)
                      AND is_active = true
                      AND is_symbol_allowed(symbol)
                    """, self.symbols)
            else:
                # Load all allowed symbols
                rows = await conn.fetch("""
                    SELECT id, symbol FROM get_allowed_symbols('binance')
                """)
            
            for row in rows:
                self._symbol_ids[row['symbol']] = row['id']
        
        logger.info(
            f"Initialized {len(self._symbol_ids)} allowed symbols for ticker collection"
        )
```

---

## Usage Examples

### Configure Allowed Assets

```sql
-- Set allowed quote assets (EU compliance)
SELECT set_config(
    'region.allowed_quote_assets',
    '["USDC", "BTC", "ETH"]'::jsonb,
    'admin'
);

-- Add more allowed assets
SELECT set_config(
    'region.allowed_quote_assets',
    '["USDC", "BTC", "ETH", "EUR"]'::jsonb,
    'admin'
);

-- Set region
SELECT set_config('app.region', 'EU', 'admin');

-- Enable auto-filtering
SELECT set_config('region.enable_auto_filter', true, 'admin');
```

### Check Symbol Allowance

```sql
-- Check if specific symbol is allowed
SELECT is_symbol_allowed('BTC/USDC');  -- TRUE
SELECT is_symbol_allowed('BTC/USDT');  -- FALSE (USDT not in allowed list)
SELECT is_symbol_allowed('ETH/BTC');   -- TRUE

-- Get all allowed symbols
SELECT * FROM get_allowed_symbols('binance');

-- Check if quote asset is allowed
SELECT is_quote_asset_allowed('USDC');  -- TRUE
SELECT is_quote_asset_allowed('USDT');  -- FALSE
```

### View Configuration

```sql
-- View regional settings
SELECT 
    key,
    value->'value' AS value,
    value->>'description' AS description
FROM system_config
WHERE key LIKE 'region.%';

-- View allowed symbols
SELECT 
    s.symbol,
    s.base_asset,
    s.quote_asset,
    cc.is_allowed,
    cc.last_region_check
FROM symbols s
JOIN collection_config cc ON cc.symbol_id = s.id
WHERE s.is_active = true
ORDER BY cc.is_allowed DESC, s.symbol;
```

### Update Restricted List

```sql
-- Add specific restricted symbols (e.g., leverage tokens)
SELECT set_config(
    'region.restricted_symbols',
    '["BTCUP/USDT", "BTCDOWN/USDT", "ETHUP/USDT", "ETHDOWN/USDT"]'::jsonb,
    'admin'
);

-- Remove all restricted symbols
SELECT set_config(
    'region.restricted_symbols',
    '[]'::jsonb,
    'admin'
);
```

---

## CLI Commands

```python
# src/cli/commands/region.py

@click.group()
def region():
    """Regional configuration management."""
    pass


@region.command()
@click.option('--db-dsn', envvar='DATABASE_URL', required=True)
async def allowed_assets(db_dsn):
    """Show allowed quote assets."""
    pool = await asyncpg.create_pool(db_dsn)
    
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value->'value' AS assets FROM system_config WHERE key = 'region.allowed_quote_assets'"
            )
            
            if row:
                click.echo("Allowed Quote Assets:")
                for asset in row['assets']:
                    click.echo(f"  ✓ {asset}")
    
    finally:
        await pool.close()


@region.command()
@click.option('--db-dsn', envvar='DATABASE_URL', required=True)
@click.argument('asset')
async def add_allowed_asset(db_dsn, asset):
    """Add allowed quote asset."""
    pool = await asyncpg.create_pool(db_dsn)
    
    try:
        async with pool.acquire() as conn:
            # Get current list
            row = await conn.fetchrow(
                "SELECT value->'value' AS assets FROM system_config WHERE key = 'region.allowed_quote_assets'"
            )
            
            assets = list(row['assets']) if row and row['assets'] else []
            
            if asset.upper() not in assets:
                assets.append(asset.upper())
                
                # Update config
                await conn.execute(
                    "SELECT set_config('region.allowed_quote_assets', $1, 'cli')",
                    json.dumps(assets)
                )
                
                click.echo(f"✓ Added {asset.upper()} to allowed assets")
            else:
                click.echo(f"{asset.upper()} is already in allowed list")
    
    finally:
        await pool.close()


@region.command()
@click.option('--db-dsn', envvar='DATABASE_URL', required=True)
async def check_symbols(db_dsn):
    """Check which symbols are allowed."""
    pool = await asyncpg.create_pool(db_dsn)
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    s.symbol,
                    s.base_asset,
                    s.quote_asset,
                    is_symbol_allowed(s.symbol) AS is_allowed,
                    cc.is_collecting
                FROM symbols s
                LEFT JOIN collection_config cc ON cc.symbol_id = s.id
                WHERE s.is_active = true
                ORDER BY is_allowed DESC, s.symbol
            """)
            
            allowed = [r for r in rows if r['is_allowed']]
            restricted = [r for r in rows if not r['is_allowed']]
            
            click.echo(f"\nAllowed Symbols ({len(allowed)}):")
            click.echo("=" * 60)
            click.echo(tabulate(
                [dict(r) for r in allowed],
                headers='keys',
                tablefmt='grid'
            ))
            
            if restricted:
                click.echo(f"\nRestricted Symbols ({len(restricted)}):")
                click.echo("=" * 60)
                click.echo(tabulate(
                    [dict(r) for r in restricted],
                    headers='keys',
                    tablefmt='grid'
                ))
    
    finally:
        await pool.close()
```

---

## Default Configuration (EU)

```sql
-- EU-compliant default configuration
INSERT INTO system_config (key, value, description) VALUES

-- Allowed quote assets (USDT not allowed in EU)
('region.allowed_quote_assets', 
 '{"value": ["USDC", "BTC", "ETH"], "description": "EU allowed quote assets"}'::jsonb, 
 'Allowed quote assets for EU'),

-- No base asset restrictions
('region.allowed_base_assets', 
 '{"value": [], "description": "All base assets allowed"}'::jsonb, 
 'Allowed base assets'),

-- No specific symbol restrictions
('region.restricted_symbols', 
 '{"value": [], "description": "No restricted symbols"}'::jsonb, 
 'Restricted symbols'),

-- Enable auto-filtering
('region.enable_auto_filter', 
 '{"value": true, "description": "Auto-filter enabled"}'::jsonb, 
 'Enable auto-filtering'),

-- Set region
('app.region', 
 '{"value": "EU", "description": "Operating region"}'::jsonb, 
 'Region');
```

---

## Workload Management

### Filter Ticker@All Stream

```python
# When subscribing to ticker@all, filter by allowed symbols

async def _get_allowed_symbols(self):
    """Get list of allowed symbols from database."""
    async with self.db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT symbol FROM get_allowed_symbols('binance')
        """)
        return [row['symbol'] for row in rows]

async def _connect_websocket(self):
    """Connect with filtered symbol list."""
    # Get allowed symbols
    allowed_symbols = await self._get_allowed_symbols()
    
    # Build streams (only allowed symbols)
    streams = [
        f"{s.lower().replace('/', '')}@ticker"
        for s in allowed_symbols
    ]
    
    ws_url = f"wss://stream.binance.com:9443/ws/{'/'.join(streams)}"
    
    logger.info(
        f"Subscribing to {len(streams)} allowed ticker streams "
        f"(filtered from all available symbols)"
    )
```

### Reduce Workload

```sql
-- Only collect for allowed symbols
UPDATE collection_config 
SET is_collecting = true
WHERE symbol_id IN (
    SELECT id FROM symbols 
    WHERE is_symbol_allowed(symbol)
);

-- Disable collection for restricted symbols
UPDATE collection_config 
SET is_collecting = false
WHERE symbol_id IN (
    SELECT id FROM symbols 
    WHERE NOT is_symbol_allowed(symbol)
);
```

---

## Benefits

✅ **Regulatory Compliance**: Automatically filter restricted assets  
✅ **Configurable**: Change allowed assets without code changes  
✅ **Audit Trail**: Track when symbols are allowed/restricted  
✅ **Workload Reduction**: Only collect data for allowed symbols  
✅ **Region-Specific**: Different configs for EU, US, UK, etc.  
✅ **Dynamic**: Changes apply immediately (no restart)  

---

## Example: EU Configuration

```bash
# Show current allowed assets
crypto region allowed-assets

# Add EUR as allowed quote asset
crypto region add-allowed-asset EUR

# Check which symbols are allowed
crypto region check-symbols

# Result:
# ✓ BTC/USDC - Allowed
# ✓ ETH/USDC - Allowed
# ✓ BTC/EUR  - Allowed
# ✗ BTC/USDT - Restricted (USDT not allowed in EU)
```

---

**Ready to implement EU-compliant symbol filtering!** 🇪🇺
