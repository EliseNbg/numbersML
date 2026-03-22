# Step 016: Binance Asset Sync Service

## Context

**Phase**: 2 - Data Infrastructure  
**Effort**: 6 hours  
**Dependencies**: Step 002 (Database Schema), Step 004 (Data Collection) completed

---

## Goal

Implement a service to synchronize Binance asset metadata daily, ensuring our symbol information stays up-to-date with:
- Asset names and codes
- Trading status (trading/delisted)
- Logo URLs and tags
- Fee information
- Market type (MAINWEB, DEX, ETF)

**API Endpoint**: `https://www.binance.com/bapi/asset/v2/public/asset/asset/get-all-asset`

---

## Domain Model

### Entities Updated

```python
# Symbol entity extended (from Step 003, now with metadata)

class Symbol(Entity):
    # ... existing fields from Step 003 ...
    
    # Binance metadata (NEW)
    binance_asset_code: str
    binance_asset_name: str
    binance_id: int
    logo_url: str
    tags: List[str]
    is_trading: bool
    is_delisted: bool
    plate_type: str
    etf: bool
    commission_rate: Decimal
    free_audit_withdraw_amt: Decimal
    asset_digit: int
    fee_digit: int
    last_synced_at: datetime
```

### Domain Events (NEW)

```python
class AssetSyncCompletedEvent(DomainEvent):
    """Raised when asset sync completes."""
    assets_created: int
    assets_updated: int
    assets_delisted: int
    total_assets: int

class SymbolMetadataChangedEvent(DomainEvent):
    """Raised when symbol metadata changes significantly."""
    symbol_id: int
    symbol: str
    changes: Dict[str, Any]  # e.g., {'is_trading': (True, False)}
```

---

## Implementation Tasks

### Task 16.1: Binance Asset Sync Service

**File**: `src/infrastructure/exchanges/binance_asset_sync.py`

```python
"""Binance asset metadata synchronization."""

import aiohttp
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
import asyncpg
import logging

logger = logging.getLogger(__name__)


class BinanceAssetSync:
    """
    Synchronizes Binance asset metadata.
    
    Calls: https://www.binance.com/bapi/asset/v2/public/asset/asset/get-all-asset
    
    Run periodically (once per day) to keep symbol metadata up-to-date.
    """
    
    ASSET_INFO_URL = "https://www.binance.com/bapi/asset/v2/public/asset/asset/get-all-asset"
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if not self._session:
            self._session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                }
            )
        return self._session
    
    async def close(self):
        """Close HTTP session."""
        if self._session:
            await self._session.close()
    
    async def fetch_asset_info(self) -> List[Dict]:
        """Fetch all asset info from Binance."""
        session = await self._get_session()
        
        try:
            async with session.get(self.ASSET_INFO_URL) as response:
                response.raise_for_status()
                data = await response.json()
                
                # API returns: {"code":"000000","message":"success","data":[...]}
                if data.get('code') == '000000':
                    return data.get('data', [])
                else:
                    logger.error(f"Binance API error: {data}")
                    return []
        
        except Exception as e:
            logger.error(f"Failed to fetch asset info: {e}")
            raise
    
    async def sync_all_assets(self) -> Dict[str, int]:
        """
        Synchronize all assets from Binance.
        
        Returns:
            Dict with counts: {'created': X, 'updated': Y, 'unchanged': Z, 'delisted': W}
        """
        logger.info("Starting Binance asset sync...")
        
        # Fetch latest data from Binance
        asset_list = await self.fetch_asset_info()
        logger.info(f"Fetched {len(asset_list)} assets from Binance")
        
        stats = {'created': 0, 'updated': 0, 'unchanged': 0, 'delisted': 0}
        
        async with self.db_pool.acquire() as conn:
            for asset_info in asset_list:
                result = await self._sync_single_asset(conn, asset_info)
                stats[result] += 1
        
        logger.info(f"Asset sync complete: {stats}")
        return stats
    
    async def _sync_single_asset(
        self, 
        conn: asyncpg.Connection, 
        asset_info: Dict
    ) -> str:
        """
        Sync a single asset.
        
        Returns:
            'created', 'updated', 'unchanged', or 'delisted'
        """
        asset_code = asset_info.get('assetCode', '')
        is_delisted = asset_info.get('delisted', False)
        
        # Skip delisted assets (or mark them)
        if is_delisted:
            await self._mark_as_delisted(conn, asset_code)
            return 'delisted'
        
        # Check if asset exists
        existing = await conn.fetchrow(
            """
            SELECT id, binance_id, is_trading, last_synced_at
            FROM symbols
            WHERE base_asset = $1
            """,
            asset_code
        )
        
        if existing:
            # Update existing
            changed = await self._update_asset(conn, existing['id'], asset_info)
            return 'updated' if changed else 'unchanged'
        else:
            # Create new
            await self._create_asset(conn, asset_info)
            return 'created'
    
    async def _create_asset(self, conn: asyncpg.Connection, asset_info: Dict):
        """Create new asset record."""
        asset_code = asset_info.get('assetCode', '')
        
        await conn.execute(
            """
            INSERT INTO symbols (
                symbol, base_asset, quote_asset,
                binance_asset_code, binance_asset_name, binance_id,
                logo_url, tags, is_trading, is_delisted, plate_type, etf,
                commission_rate, free_audit_withdraw_amt, asset_digit, fee_digit,
                last_synced_at, sync_source, is_active
            ) VALUES (
                $1 || '/USDT', $1, 'USDT',  -- Assume USDT pair for now
                $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14,
                NOW(), 'binance_api', true
            )
            ON CONFLICT (symbol) DO UPDATE SET
                binance_asset_name = EXCLUDED.binance_asset_name,
                binance_id = EXCLUDED.binance_id,
                logo_url = EXCLUDED.logo_url,
                tags = EXCLUDED.tags,
                is_trading = EXCLUDED.is_trading,
                plate_type = EXCLUDED.plate_type,
                etf = EXCLUDED.etf,
                commission_rate = EXCLUDED.commission_rate,
                free_audit_withdraw_amt = EXCLUDED.free_audit_withdraw_amt,
                asset_digit = EXCLUDED.asset_digit,
                fee_digit = EXCLUDED.fee_digit,
                last_synced_at = NOW(),
                updated_at = NOW()
            """,
            asset_code,
            asset_info.get('assetCode'),
            asset_info.get('assetName'),
            int(asset_info.get('id', 0)) or None,
            asset_info.get('logoUrl'),
            asset_info.get('tags', []),
            asset_info.get('trading', True),
            asset_info.get('delisted', False),
            asset_info.get('plateType'),
            asset_info.get('etf', False),
            asset_info.get('commissionRate', 0),
            asset_info.get('freeAuditWithdrawAmt', 0),
            asset_info.get('assetDigit', 8),
            asset_info.get('feeDigit', 2),
        )
    
    async def _update_asset(
        self, 
        conn: asyncpg.Connection, 
        symbol_id: int, 
        asset_info: Dict
    ) -> bool:
        """
        Update existing asset.
        
        Returns True if any significant field changed.
        """
        # Get old values
        old = await conn.fetchrow(
            """
            SELECT is_trading, is_delisted, plate_type
            FROM symbols
            WHERE id = $1
            """,
            symbol_id
        )
        
        # Update
        await conn.execute(
            """
            UPDATE symbols SET
                binance_asset_name = $2,
                binance_id = $3,
                logo_url = $4,
                tags = $5,
                is_trading = $6,
                is_delisted = $7,
                plate_type = $8,
                etf = $9,
                commission_rate = $10,
                free_audit_withdraw_amt = $11,
                asset_digit = $12,
                fee_digit = $13,
                last_synced_at = NOW(),
                updated_at = NOW()
            WHERE id = $1
            """,
            symbol_id,
            asset_info.get('assetName'),
            int(asset_info.get('id', 0)) or None,
            asset_info.get('logoUrl'),
            asset_info.get('tags', []),
            asset_info.get('trading', True),
            asset_info.get('delisted', False),
            asset_info.get('plateType'),
            asset_info.get('etf', False),
            asset_info.get('commissionRate', 0),
            asset_info.get('freeAuditWithdrawAmt', 0),
            asset_info.get('assetDigit', 8),
            asset_info.get('feeDigit', 2),
        )
        
        # Check if anything significant changed
        new_trading = asset_info.get('trading', True)
        new_delisted = asset_info.get('delisted', False)
        new_plate = asset_info.get('plateType')
        
        return (
            old['is_trading'] != new_trading or
            old['is_delisted'] != new_delisted or
            old['plate_type'] != new_plate
        )
    
    async def _mark_as_delisted(self, conn: asyncpg.Connection, asset_code: str):
        """Mark asset as delisted."""
        await conn.execute(
            """
            UPDATE symbols SET
                is_delisted = true,
                is_trading = false,
                is_active = false,  -- Deactivate immediately
                last_synced_at = NOW(),
                updated_at = NOW()
            WHERE base_asset = $1
            """,
            asset_code
        )
    
    async def get_sync_status(self) -> Dict:
        """Get synchronization status."""
        async with self.db_pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT 
                    COUNT(*) FILTER (WHERE last_synced_at IS NULL) AS never_synced,
                    COUNT(*) FILTER (WHERE last_synced_at < NOW() - INTERVAL '24 hours') AS needs_sync,
                    COUNT(*) FILTER (WHERE is_delisted = true) AS delisted,
                    COUNT(*) FILTER (WHERE is_active = true) AS active,
                    MAX(last_synced_at) AS last_sync_time
                FROM symbols
            """)
```

---

### Task 16.2: Asset Sync Scheduler

**File**: `src/application/services/asset_sync_scheduler.py`

```python
"""Scheduled asset synchronization."""

import asyncio
from datetime import timedelta
import asyncpg
from ..infrastructure.exchanges.binance_asset_sync import BinanceAssetSync
import logging

logger = logging.getLogger(__name__)


class AssetSyncScheduler:
    """
    Schedules periodic Binance asset sync.
    
    Runs once per day (e.g., at 00:00 UTC) to keep metadata fresh.
    """
    
    def __init__(
        self, 
        db_pool: asyncpg.Pool,
        sync_interval_hours: int = 24
    ):
        self.db_pool = db_pool
        self.sync_interval = timedelta(hours=sync_interval_hours)
        self._running = False
    
    async def start(self):
        """Start the sync scheduler."""
        logger.info(f"Starting asset sync scheduler (interval: {self.sync_interval})")
        self._running = True
        
        while self._running:
            try:
                await self._run_sync()
            except Exception as e:
                logger.error(f"Asset sync failed: {e}")
            
            # Wait until next sync
            await asyncio.sleep(self.sync_interval.total_seconds())
    
    async def stop(self):
        """Stop the scheduler."""
        self._running = False
    
    async def _run_sync(self):
        """Run a single sync operation."""
        sync = BinanceAssetSync(self.db_pool)
        
        try:
            stats = await sync.sync_all_assets()
            
            # Log results
            logger.info(f"Asset sync completed: {stats}")
            
            # Update service health
            await self._update_health(stats)
        
        finally:
            await sync.close()
    
    async def _update_health(self, stats: Dict):
        """Update service health after sync."""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO service_health 
                (service_name, status, last_heartbeat, records_processed, updated_at)
                VALUES ('asset_sync', 'healthy', NOW(), $1, NOW())
                ON CONFLICT (service_name) DO UPDATE SET
                    status = 'healthy',
                    last_heartbeat = NOW(),
                    records_processed = service_health.records_processed + $1,
                    updated_at = NOW()
                """,
                stats.get('created', 0) + stats.get('updated', 0)
            )
```

---

### Task 16.3: CLI Command

**File**: `src/cli/commands/sync_assets.py`

```python
"""CLI command for manual asset sync."""

import click
import asyncio
import asyncpg
from src.infrastructure.exchanges.binance_asset_sync import BinanceAssetSync


@click.command()
@click.option('--db-dsn', envvar='DATABASE_URL', required=True)
@click.option('--dry-run', is_flag=True, help='Show what would be synced')
def sync_assets(db_dsn, dry_run):
    """
    Synchronize Binance asset metadata.
    
    Examples:
    
    # Full sync
    crypto sync-assets
    
    # Dry run (no changes)
    crypto sync-assets --dry-run
    """
    asyncio.run(_run_sync(db_dsn, dry_run))


async def _run_sync(db_dsn: str, dry_run: bool):
    """Execute sync."""
    pool = await asyncpg.create_pool(db_dsn)
    
    try:
        sync = BinanceAssetSync(pool)
        
        if dry_run:
            # Just fetch and show what would change
            asset_list = await sync.fetch_asset_info()
            click.echo(f"Would sync {len(asset_list)} assets")
            
            # Show first few
            for asset in asset_list[:5]:
                click.echo(f"  - {asset.get('assetCode')}: {asset.get('assetName')}")
            
            if len(asset_list) > 5:
                click.echo(f"  ... and {len(asset_list) - 5} more")
        
        else:
            # Actually sync
            stats = await sync.sync_all_assets()
            
            click.echo("✓ Asset sync completed!")
            click.echo(f"  Created:   {stats['created']}")
            click.echo(f"  Updated:   {stats['updated']}")
            click.echo(f"  Unchanged: {stats['unchanged']}")
            click.echo(f"  Delisted:  {stats['delisted']}")
    
    finally:
        await pool.close()
```

---

### Task 16.4: Update Domain Models

**File**: `src/domain/models/symbol.py` (update from Step 003)

```python
# Add these fields to the Symbol entity from Step 003

@dataclass
class Symbol(Entity):
    # ... existing fields ...
    
    # Binance metadata (NEW - Step 016)
    binance_asset_code: str = ""
    binance_asset_name: str = ""
    binance_id: Optional[int] = None
    logo_url: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    is_trading: bool = True
    is_delisted: bool = False
    plate_type: Optional[str] = None
    etf: bool = False
    commission_rate: Decimal = Decimal("0")
    free_audit_withdraw_amt: Decimal = Decimal("0")
    asset_digit: int = 8
    fee_digit: int = 2
    last_synced_at: Optional[datetime] = None
    sync_source: str = "binance_api"
    
    def update_from_binance_info(self, binance_info: dict) -> bool:
        """
        Update symbol from Binance asset info.
        
        Returns True if any field changed.
        """
        old_state = self._get_state_hash()
        
        # Map Binance API response to our fields
        self.binance_id = int(binance_info.get('id', 0)) or None
        self.binance_asset_code = binance_info.get('assetCode', '')
        self.binance_asset_name = binance_info.get('assetName', '')
        self.logo_url = binance_info.get('logoUrl')
        self.tags = binance_info.get('tags', [])
        self.is_trading = binance_info.get('trading', True)
        self.is_delisted = binance_info.get('delisted', False)
        self.plate_type = binance_info.get('plateType')
        self.etf = binance_info.get('etf', False)
        self.commission_rate = Decimal(str(binance_info.get('commissionRate', 0)))
        self.free_audit_withdraw_amt = Decimal(str(binance_info.get('freeAuditWithdrawAmt', 0)))
        self.asset_digit = int(binance_info.get('assetDigit', 8))
        self.fee_digit = int(binance_info.get('feeDigit', 2))
        
        # Auto-deactivate if delisted
        if self.is_delisted and self.is_active:
            self.deactivate()
        
        # Auto-activate if trading and main market
        if self.is_trading and not self.is_delisted and self.is_main_market:
            if not self.is_active:
                self.activate()
        
        self.last_synced_at = datetime.utcnow()
        
        return self._get_state_hash() != old_state
    
    @property
    def is_main_market(self) -> bool:
        """Check if this is a main market (not DEX, not ETF)."""
        return self.plate_type == "MAINWEB" and not self.etf
```

---

## Test Requirements

### Test Coverage Target: **80%**

### Unit Tests

**File**: `tests/unit/infrastructure/exchanges/test_binance_asset_sync.py`

```python
"""Test Binance asset synchronization."""

import pytest
from src.infrastructure.exchanges.binance_asset_sync import BinanceAssetSync


class TestBinanceAssetSync:
    """Test BinanceAssetSync class."""
    
    @pytest.mark.asyncio
    async def test_fetch_asset_info_structure(self, mock_aiohttp):
        """Test fetching asset info from Binance."""
        # Mock API response
        mock_aiohttp.return_value.json.return_value = {
            "code": "000000",
            "message": "success",
            "data": [
                {
                    "id": "10",
                    "assetCode": "BNB",
                    "assetName": "BNB",
                    "trading": True,
                    "delisted": False,
                    "plateType": "MAINWEB",
                    "tags": ["Layer1_Layer2", "BSC"],
                }
            ]
        }
        
        sync = BinanceAssetSync(mock_pool)
        assets = await sync.fetch_asset_info()
        
        assert len(assets) == 1
        assert assets[0]['assetCode'] == 'BNB'
    
    @pytest.mark.asyncio
    async def test_sync_creates_new_asset(self, mock_db):
        """Test creating new asset from sync."""
        sync = BinanceAssetSync(mock_db.pool)
        
        asset_info = {
            "id": "374",
            "assetCode": "CHR",
            "assetName": "Chromia",
            "trading": True,
            "delisted": False,
        }
        
        result = await sync._sync_single_asset(mock_db.conn, asset_info)
        
        assert result == 'created'
        mock_db.conn.execute.assert_called()
    
    @pytest.mark.asyncio
    async def test_sync_marks_delisted_assets(self, mock_db):
        """Test that delisted assets are marked correctly."""
        sync = BinanceAssetSync(mock_db.pool)
        
        delisted_asset = {
            "assetCode": "OLD",
            "assetName": "Old Coin",
            "delisted": True,
            "trading": False,
        }
        
        result = await sync._sync_single_asset(mock_db.conn, delisted_asset)
        
        assert result == 'delisted'
        
        # Verify asset was marked as delisted
        call_args = mock_db.conn.execute.call_args[0][0]
        assert 'is_delisted = true' in call_args
        assert 'is_active = false' in call_args
    
    @pytest.mark.asyncio
    async def test_sync_detects_changes(self, mock_db):
        """Test change detection in asset sync."""
        sync = BinanceAssetSync(mock_db.pool)
        
        # Mock existing asset
        mock_db.conn.fetchrow.return_value = {
            'id': 1,
            'is_trading': True,
            'is_delisted': False,
            'plate_type': 'MAINWEB'
        }
        
        # Asset with changed status
        asset_info = {
            "assetCode": "TEST",
            "trading": False,  # Changed from True
            "delisted": False,
            "plateType": "MAINWEB",
        }
        
        result = await sync._sync_single_asset(mock_db.conn, asset_info)
        
        assert result == 'updated'  # Changed, so 'updated' not 'unchanged'
```

### Integration Tests

**File**: `tests/integration/exchanges/test_binance_asset_sync.py`

```python
"""Test Binance asset sync with real API."""

import pytest
import asyncpg
from testcontainers.postgres import PostgresContainer
from src.infrastructure.exchanges.binance_asset_sync import BinanceAssetSync


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_sync_workflow(postgres_container):
    """Test complete sync workflow."""
    dsn = postgres_container.get_connection_url()
    pool = await asyncpg.create_pool(dsn)
    
    try:
        # Run migrations first
        await pool.execute(migration_sql)
        
        sync = BinanceAssetSync(pool)
        
        # Fetch real data from Binance
        assets = await sync.fetch_asset_info()
        
        assert len(assets) > 0
        
        # Sync all
        stats = await sync.sync_all_assets()
        
        # Verify stats
        assert stats['created'] > 0 or stats['updated'] > 0
        
        # Verify data in database
        async with pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM symbols")
            assert count > 0
            
            # Check synced symbols have metadata
            symbol = await conn.fetchrow(
                "SELECT * FROM symbols WHERE binance_id IS NOT NULL LIMIT 1"
            )
            assert symbol is not None
            assert symbol['last_synced_at'] is not None
    
    finally:
        await pool.close()
```

---

## Acceptance Criteria

- [ ] BinanceAssetSync service implemented
- [ ] Fetches data from Binance API correctly
- [ ] Creates new assets from API response
- [ ] Updates existing assets
- [ ] Marks delisted assets correctly
- [ ] Auto-deactivates delisted symbols
- [ ] Scheduler runs daily sync
- [ ] CLI command works (dry-run and real)
- [ ] Unit tests pass (80%+ coverage)
- [ ] Integration test with real API works
- [ ] Domain models updated with metadata fields

---

## Verification Commands

```bash
# Run unit tests
pytest tests/unit/infrastructure/exchanges/test_binance_asset_sync.py -v --cov

# Run integration test (requires Docker)
pytest tests/integration/exchanges/test_binance_asset_sync.py -v --cov

# Manual sync (dry run)
crypto sync-assets --dry-run

# Full sync
crypto sync-assets

# Check sync status in database
psql postgresql://crypto:crypto@localhost/crypto_trading_dev
SELECT 
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE last_synced_at > NOW() - INTERVAL '24 hours') AS recently_synced,
    COUNT(*) FILTER (WHERE is_delisted = true) AS delisted
FROM symbols;
```

---

## Next Step

After completing this step, proceed to **[004-data-collection-service.md](004-data-collection-service.md)** (or continue with remaining steps in [004-to-015-summary.md](004-to-015-summary.md))
