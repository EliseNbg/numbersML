# Step 11: Market Service GUI & Order Execution

## Objective

Build a comprehensive order execution layer with Binance filter compliance, two operational modes (Market Service self-handling vs. direct Binance routing), a dashboard UI for order management, secure API key CRUD, and robust error handling with automatic filter retry logic.

## Scope

This step is split into **5 sub-steps** for manageable implementation:

- **11A**: Binance Filter Engine — price/quantity normalization with retry logic
- **11B**: Order Execution Router — Mode 1 (self-handled) vs Mode 2 (Binance direct)
- **11C**: API Key Management — secure CRUD with encryption
- **11D**: Order Dashboard UI — web interface for order management
- **11E**: Backtest Integration — test order support for backtesting strategies

---

## 11A: Binance Filter Engine

### Purpose

Ensure all orders comply with Binance exchange filters before submission. This is the **most critical** component — filter violations cause ~70% of order failures in production crypto trading systems.

### Binance Filters to Support

| Filter | Description | Fields |
|--------|-------------|--------|
| `PRICE_FILTER` | Price range and tick size | `minPrice`, `maxPrice`, `tickSize` |
| `LOT_SIZE` | Quantity range and step size | `minQty`, `maxQty`, `stepSize` |
| `MARKET_LOT_SIZE` | Quantity rules for MARKET orders | `minQty`, `maxQty`, `stepSize` |
| `MIN_NOTIONAL` | Minimum order value (price × qty) | `minNotional`, `applyToMarket`, `avgPriceMins` |
| `NOTIONAL` | Min/max notional range | `minNotional`, `maxNotional`, `applyMinToMarket`, `applyMaxToMarket` |
| `PERCENT_PRICE_BY_SIDE` | Price range relative to avg price | `bidMultiplierUp/Down`, `askMultiplierUp/Down` |
| `MAX_NUM_ORDERS` | Max open orders per symbol | `maxNumOrders` |
| `MAX_POSITION` | Max position size | `maxPosition` |

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `src/infrastructure/market/binance_filters.py` | **NEW** | `BinanceFilterEngine` class |
| `src/infrastructure/market/order_normalizer.py` | **NEW** | `OrderNormalizer` — applies filters to orders |
| `src/infrastructure/market/binance_exchange_client.py` | **MODIFY** | Add `get_exchange_info()`, `get_symbol_filters()` |
| `src/domain/market/order.py` | **MODIFY** | Add `SymbolFilters` dataclass |
| `tests/unit/market/test_binance_filters.py` | **NEW** | Comprehensive filter tests (30+ tests) |
| `tests/unit/market/test_order_normalizer.py` | **NEW** | Normalizer tests |

### `BinanceFilterEngine`

```python
class BinanceFilterEngine:
    """
    Validates and normalizes orders against Binance exchange filters.

    Responsibilities:
    - Fetch and cache exchange info (filters) per symbol
    - Normalize price to tick size (PRICE_FILTER)
    - Normalize quantity to step size (LOT_SIZE / MARKET_LOT_SIZE)
    - Validate min/max bounds
    - Validate notional value (MIN_NOTIONAL / NOTIONAL)
    - Retry with ±0.5% adjustment on filter violation
    """

    def __init__(self, exchange_client: BinanceExchangeClient):
        self._client = exchange_client
        self._filter_cache: dict[str, SymbolFilters] = {}
        self._cache_ttl = 300  # 5 minutes

    async def load_filters(self, symbol: str) -> SymbolFilters:
        """Fetch filters from /api/v3/exchangeInfo and cache."""

    def normalize_price(self, symbol: str, price: Decimal) -> Decimal:
        """Round price to tick_size, clamp to min/max."""

    def normalize_quantity(self, symbol: str, quantity: Decimal,
                          order_type: OrderType) -> Decimal:
        """Round quantity to step_size, clamp to min/max."""

    def validate_notional(self, symbol: str, price: Decimal,
                         quantity: Decimal, order_type: OrderType) -> bool:
        """Check price * quantity >= minNotional."""

    async def normalize_order(self, symbol: str, price: Decimal | None,
                             quantity: Decimal, order_type: OrderType,
                             side: OrderSide) -> NormalizedOrder:
        """Full normalization: price, quantity, notional."""
```

### Retry Logic with ±0.5% Adjustment

```python
class OrderNormalizer:
    """
    Applies filters and retries on failure with incremental adjustment.

    Retry strategy:
    1. Try exact normalized values
    2. On filter error, adjust price ±0.5% and re-normalize
    3. On filter error, adjust quantity ±0.5% and re-normalize
    4. Max 3 retries total
    5. If all fail, return error with details
    """

    MAX_RETRIES = 3
    ADJUSTMENT_PCT = Decimal("0.005")  # 0.5%

    async def place_with_retry(
        self,
        market_service: MarketService,
        request: OrderRequest,
    ) -> Order:
        """Place order with filter retry logic."""
        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                # Normalize before each attempt
                normalized = await self._normalize(request)
                return await market_service.place_order(normalized)

            except BinanceFilterError as e:
                last_error = e
                if attempt == 0:
                    # First retry: adjust price ±0.5%
                    request = self._adjust_price(request, e.filter_type)
                elif attempt == 1:
                    # Second retry: adjust quantity ±0.5%
                    request = self._adjust_quantity(request, e.filter_type)
                elif attempt == 2:
                    # Third retry: adjust both ±0.5%
                    request = self._adjust_both(request)

        raise OrderNormalizationError(
            f"Failed after {self.MAX_RETRIES} retries: {last_error}"
        )
```

### `SymbolFilters` Dataclass

```python
@dataclass(frozen=True)
class SymbolFilters:
    """Cached Binance exchange filters for a symbol."""
    symbol: str
    # PRICE_FILTER
    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal
    # LOT_SIZE
    min_qty: Decimal
    max_qty: Decimal
    step_size: Decimal
    # MARKET_LOT_SIZE (separate from LOT_SIZE)
    market_min_qty: Decimal
    market_max_qty: Decimal
    market_step_size: Decimal
    # NOTIONAL
    min_notional: Decimal
    max_notional: Decimal
    # PERCENT_PRICE_BY_SIDE
    bid_multiplier_up: Decimal
    bid_multiplier_down: Decimal
    ask_multiplier_up: Decimal
    ask_multiplier_down: Decimal
    # Other
    max_num_orders: int
    max_position: Decimal
```

### Database Schema Update: Symbol Filters

The `symbols` table already has `tick_size`, `step_size`, `min_price`, `max_price`, `min_quantity`, `max_quantity`, `min_notional`, `max_notional`. We need to add:

```sql
-- Migration: migrations/010_symbol_filters.sql
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS market_min_qty NUMERIC(20,10);
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS market_max_qty NUMERIC(20,10);
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS market_step_size NUMERIC(20,10);
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS bid_multiplier_up NUMERIC(10,6) DEFAULT 1.3;
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS bid_multiplier_down NUMERIC(10,6) DEFAULT 0.7;
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS ask_multiplier_up NUMERIC(10,6) DEFAULT 5.0;
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS ask_multiplier_down NUMERIC(10,6) DEFAULT 0.8;
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS max_num_orders INTEGER DEFAULT 200;
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS max_position NUMERIC(20,10);
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS filters_last_synced TIMESTAMPTZ;
```

### Tests for 11A (30+ tests)

| Test | Description |
|------|-------------|
| `test_normalize_price_to_tick_size` | Price rounded to tick_size |
| `test_normalize_price_clamp_min` | Price below min_price → clamped to min |
| `test_normalize_price_clamp_max` | Price above max_price → clamped to max |
| `test_normalize_quantity_to_step_size` | Quantity rounded to step_size |
| `test_normalize_quantity_clamp_min` | Quantity below min_qty → clamped |
| `test_normalize_quantity_clamp_max` | Quantity above max_qty → clamped |
| `test_market_lot_size_normalization` | MARKET orders use MARKET_LOT_SIZE |
| `test_min_notional_validation` | price * qty >= minNotional |
| `test_min_notional_market_order` | MIN_NOTIONAL applies to MARKET orders |
| `test_notional_max_validation` | price * qty <= maxNotional |
| `test_percent_price_buy_filter` | BUY price within bid multipliers |
| `test_percent_price_sell_filter` | SELL price within ask multipliers |
| `test_retry_adjusts_price_on_filter_error` | First retry adjusts price ±0.5% |
| `test_retry_adjusts_quantity_on_filter_error` | Second retry adjusts quantity ±0.5% |
| `test_retry_adjusts_both_on_third_attempt` | Third retry adjusts both |
| `test_retry_fails_after_max_attempts` | Raises after 3 retries |
| `test_filter_cache_respects_ttl` | Cache expires after 5 minutes |
| `test_filter_cache_hit_skips_api_call` | Cached filters used |
| `test_normalize_btc_usdc` | Real BTC/USDC filter values |
| `test_normalize_doge_usdc` | Real DOGE/USDC filter values (tiny price) |
| `test_normalize_shib_usdc` | Real SHIB/USDC filter values (very tiny price) |
| `test_filter_error_contains_details` | Error message includes filter type and values |
| `test_normalize_limit_order` | LIMIT order normalization |
| `test_normalize_market_order` | MARKET order normalization (no price) |
| `test_normalize_zero_quantity_rejected` | Zero quantity → error |
| `test_normalize_negative_price_rejected` | Negative price → error |
| `test_filter_engine_concurrent_load` | Concurrent filter loads don't duplicate API calls |
| `test_filters_loaded_from_db_fallback` | DB filters used when API unavailable |
| `test_sync_filters_updates_db` | Exchange info synced to symbols table |
| `test_filter_precision_for_tiny_prices` | Correct precision for prices like 0.000001 |

---

## 11B: Order Execution Router

### Purpose

Route orders through two modes:
- **Mode 1 (Self-Handled)**: Market Service handles orders internally (paper trading, internal matching)
- **Mode 2 (Binance Direct)**: Orders sent directly to Binance API (live or testnet)

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `src/infrastructure/market/order_router.py` | **NEW** | `OrderRouter` — mode-based routing |
| `src/infrastructure/market/binance_exchange_client.py` | **MODIFY** | Add `create_test_order()` for backtesting |
| `src/domain/market/order.py` | **MODIFY** | Add `ExecutionMode` enum |
| `src/infrastructure/market/market_service_factory.py` | **MODIFY** | Support execution mode in factory |
| `tests/unit/market/test_order_router.py` | **NEW** | Router tests |

### `ExecutionMode` Enum

```python
class ExecutionMode(str, Enum):
    """Order execution mode."""
    PAPER = "paper"           # Mode 1: Market Service self-handled
    LIVE = "live"             # Mode 2: Binance mainnet
    TESTNET = "testnet"       # Mode 2: Binance testnet
    BACKTEST = "backtest"     # Backtest mode (create_test_order)
```

### `OrderRouter`

```python
class OrderRouter:
    """
    Routes orders to the correct execution backend based on mode.

    Mode 1 (PAPER):
      - Order handled by PaperMarketService
      - Deterministic fills with configurable slippage/fees
      - No external API calls

    Mode 2 (LIVE/TESTNET):
      - Order sent to BinanceExchangeClient
      - Filter normalization applied first
      - Retry logic on filter violations
      - Idempotent via client_order_id

    Mode BACKTEST:
      - Uses create_test_order() endpoint
      - Simulated execution against historical data
    """

    def __init__(
        self,
        paper_service: PaperMarketService,
        live_service: LiveMarketService | None,
        testnet_service: LiveMarketService | None,
        filter_engine: BinanceFilterEngine,
        normalizer: OrderNormalizer,
    ):
        ...

    async def route(self, request: OrderRequest, mode: ExecutionMode) -> Order:
        """Route order to appropriate backend."""
        if mode == ExecutionMode.PAPER:
            return await self._paper_service.place_order(request)

        # Normalize for live/testnet/backtest
        normalized = await self._normalizer.normalize_order(
            symbol=request.symbol,
            price=request.limit_price,
            quantity=request.quantity,
            order_type=request.order_type,
            side=request.side,
        )

        if mode == ExecutionMode.BACKTEST:
            return await self._place_test_order(normalized)

        if mode == ExecutionMode.TESTNET:
            return await self._normalizer.place_with_retry(
                self._testnet_service, normalized
            )

        if mode == ExecutionMode.LIVE:
            return await self._normalizer.place_with_retry(
                self._live_service, normalized
            )
```

### Backtest Order Support

```python
class BinanceExchangeClient:
    async def create_test_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None,
        client_order_id: str,
    ) -> dict:
        """
        Create test order (Binance test endpoint).

        Uses /api/v3/order/test — validates order but does NOT execute.
        Returns what the order would look like if submitted.
        Perfect for backtesting without real execution.
        """
        # Same signing as create_order, but hits /api/v3/order/test
        return await self._request("POST", "/api/v3/order/test", params=signed, signed=True)
```

### Tests for 11B

| Test | Description |
|------|-------------|
| `test_route_paper_mode` | Paper mode uses PaperMarketService |
| `test_route_live_mode` | Live mode uses BinanceExchangeClient |
| `test_route_testnet_mode` | Testnet mode uses testnet client |
| `test_route_backtest_mode` | Backtest mode uses create_test_order |
| `test_live_mode_applies_filters` | Filters applied before live submission |
| `test_live_mode_retries_on_filter_error` | Retry logic triggered on filter error |
| `test_paper_mode_skips_filters` | Paper mode doesn't need filter normalization |
| `test_router_with_disabled_live` | Live disabled → RuntimeError |
| `test_idempotent_order_submission` | Duplicate client_order_id returns existing order |

---

## 11C: API Key Management

### Purpose

Secure CRUD for Binance API keys. Keys are **encrypted at rest** and **never logged or exposed in API responses**.

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `src/domain/market/api_key.py` | **NEW** | `ApiKey` domain model |
| `src/infrastructure/security/encryption.py` | **NEW** | AES-256-GCM encryption for secrets |
| `src/infrastructure/api/routes/api_keys.py` | **NEW** | CRUD endpoints for API keys |
| `src/application/services/api_key_service.py` | **NEW** | `ApiKeyService` application service |
| `migrations/011_api_keys.sql` | **NEW** | Database schema for API keys |
| `tests/unit/security/test_encryption.py` | **NEW** | Encryption tests |
| `tests/unit/services/test_api_key_service.py` | **NEW** | API key service tests |

### Database Schema: `api_keys` Table

```sql
CREATE TABLE api_keys (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name TEXT NOT NULL,
    environment TEXT NOT NULL CHECK (environment IN ('mainnet', 'testnet')),
    api_key_encrypted BYTEA NOT NULL,
    api_secret_encrypted BYTEA NOT NULL,
    is_active BOOLEAN DEFAULT true,
    permissions JSONB DEFAULT '{}',
    ip_whitelist TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    created_by TEXT DEFAULT 'system'
);

-- Never expose encrypted values in queries
CREATE OR REPLACE VIEW api_keys_public AS
SELECT id, name, environment, is_active, permissions, ip_whitelist,
       created_at, updated_at, last_used_at, created_by
FROM api_keys;
```

### Encryption Service

```python
class EncryptionService:
    """AES-256-GCM encryption for API secrets."""

    def __init__(self, master_key: bytes):
        # Master key from environment variable, never hardcoded
        self._key = master_key

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt string, return nonce + ciphertext + tag."""

    def decrypt(self, encrypted: bytes) -> str:
        """Decrypt and return original string."""
```

### API Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/keys` | POST | Create new API key (encrypted) |
| `/api/keys` | GET | List keys (never returns secret) |
| `/api/keys/{id}` | GET | Get key details (never returns secret) |
| `/api/keys/{id}` | PUT | Update key name/permissions |
| `/api/keys/{id}` | DELETE | Delete key |
| `/api/keys/{id}/test` | POST | Test connectivity with key |
| `/api/keys/{id}/rotate` | POST | Rotate key (new secret, old still works briefly) |

### Security Rules

1. **Never log API keys or secrets** — redact in all log statements
2. **Never return secrets in API responses** — only metadata
3. **Encrypt at rest** — AES-256-GCM with master key from env var
4. **IP whitelist support** — optional restriction to specific IPs
5. **Audit trail** — all key operations logged to `config_change_log`
6. **Rate limiting** — test endpoint rate-limited to prevent abuse

### Tests for 11C

| Test | Description |
|------|-------------|
| `test_encrypt_decrypt_roundtrip` | Encrypt then decrypt returns original |
| `test_different_encryption_produces_different_ciphertext` | Nonce ensures uniqueness |
| `test_create_api_key_encrypts_secret` | Secret encrypted on storage |
| `test_list_keys_never_returns_secret` | API response excludes secret |
| `test_get_key_never_returns_secret` | Single key response excludes secret |
| `test_delete_key_removes_from_db` | Key deleted |
| `test_test_connectivity` | Test endpoint validates key works |
| `test_rotate_key` | Key rotation works |
| `test_ip_whitelist_enforcement` | Requests from non-whitelisted IPs rejected |
| `test_master_key_missing_raises` | Missing env var → error |
| `test_api_key_not_logged` | Log output doesn't contain key |

---

## 11D: Order Dashboard UI

### Purpose

Web interface for managing orders, viewing execution history, and monitoring order status.

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `src/infrastructure/api/routes/orders_gui.py` | **NEW** | Order dashboard API endpoints |
| `src/infrastructure/web/gui/orders.html` | **NEW** | Order management dashboard |
| `src/infrastructure/web/gui/api_keys.html` | **NEW** | API key management page |
| `src/infrastructure/web/gui/assets/orders.js` | **NEW** | Frontend JS for order dashboard |

### Order Dashboard API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/orders/dashboard` | GET | Full order dashboard state |
| `/api/orders/{id}` | GET | Order details with execution history |
| `/api/orders/{id}/cancel` | POST | Cancel an order |
| `/api/orders/stats` | GET | Order statistics (fill rate, avg latency, etc.) |
| `/api/orders/export` | GET | Export orders as CSV |

### Dashboard Data Model

```json
{
  "orders": [
    {
      "order_id": "uuid",
      "symbol": "BTC/USDC",
      "side": "BUY",
      "type": "LIMIT",
      "quantity": 0.001,
      "price": 67500.00,
      "status": "FILLED",
      "fill_price": 67498.50,
      "mode": "testnet",
      "strategy": "MACD Buy Strategy",
      "created_at": "2026-05-17T10:30:00Z",
      "filled_at": "2026-05-17T10:30:01Z",
      "latency_ms": 150
    }
  ],
  "stats": {
    "total_orders_today": 45,
    "filled": 42,
    "rejected": 2,
    "cancelled": 1,
    "fill_rate_pct": 93.3,
    "avg_latency_ms": 180,
    "filter_retries_today": 3
  },
  "active_keys": [
    {
      "id": "uuid",
      "name": "Testnet Key",
      "environment": "testnet",
      "is_active": true,
      "last_used_at": "2026-05-17T10:30:00Z"
    }
  ]
}
```

### Tests for 11D

| Test | Description |
|------|-------------|
| `test_dashboard_returns_orders_and_stats` | Dashboard endpoint returns complete data |
| `test_order_details_endpoint` | Single order details with history |
| `test_cancel_order_endpoint` | Cancel order via API |
| `test_export_csv_endpoint` | CSV export works |
| `test_order_stats_calculation` | Correct statistics |
| `test_gui_page_loads` | HTML dashboard loads |
| `test_api_keys_page_loads` | API key management page loads |

---

## 11E: Backtest Integration

### Purpose

Integrate backtesting strategies with the order execution layer, supporting `create_test_order` for simulated execution.

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `src/application/services/backtest_engine.py` | **MODIFY** | Add order execution mode support |
| `src/infrastructure/market/backtest_market_service.py` | **NEW** | `BacktestMarketService` for simulated execution |
| `tests/unit/market/test_backtest_market_service.py` | **NEW** | Backtest service tests |

### `BacktestMarketService`

```python
class BacktestMarketService(MarketService):
    """
    Market service for backtesting with simulated order execution.

    - Uses historical price data from DB
    - Simulates fills based on OHLCV data
    - Applies realistic slippage and fees
    - Tracks portfolio performance
    """

    async def place_order(self, request: OrderRequest) -> Order:
        """Simulate order execution against historical data."""
        # Get candle data for the order timestamp
        candle = await self._get_candle_at_time(request.symbol, request.timestamp)

        if request.order_type == OrderType.MARKET:
            fill_price = self._simulate_market_fill(candle, request.side)
        else:
            fill_price = self._simulate_limit_fill(candle, request)

        return self._build_fill(request, fill_price)
```

### Tests for 11E

| Test | Description |
|------|-------------|
| `test_backtest_market_fill` | MARKET order fills within candle range |
| `test_backtest_limit_fill` | LIMIT order fills only if price reached |
| `test_backtest_rejected_order` | Order rejected if price not reached |
| `test_backtest_slippage_applied` | Slippage applied to fills |
| `test_backtest_fee_deducted` | Fees deducted from balance |
| `test_backtest_portfolio_tracking` | Portfolio value tracked correctly |

---

## Implementation Prompt for LLM Agent (Step 11)

```text
Implement Step 11: Market Service GUI & Order Execution.

Project constraints:
- Python 3.14, asyncpg, DDD layering, aiohttp for HTTP
- Follow existing code style: Google docstrings, type annotations, ruff/black
- Mirror src/ structure under tests/unit/
- Use relative imports within packages, absolute across packages
- NEVER log or expose API keys/secrets
- All public functions must have full type annotations

Tasks (implement in order 11A → 11B → 11C → 11D → 11E):

11A. Binance Filter Engine:
  1. Create BinanceFilterEngine in src/infrastructure/market/binance_filters.py:
     - Fetch /api/v3/exchangeInfo and parse filters per symbol
     - Cache filters with 5-minute TTL
     - Normalize price to tick_size (PRICE_FILTER)
     - Normalize quantity to step_size (LOT_SIZE / MARKET_LOT_SIZE)
     - Validate min/max bounds and notional
  2. Create OrderNormalizer in src/infrastructure/market/order_normalizer.py:
     - Full order normalization pipeline
     - Retry logic: 3 attempts with ±0.5% adjustment
     - First retry: adjust price, second: quantity, third: both
  3. Modify BinanceExchangeClient: add get_exchange_info(), get_symbol_filters()
  4. Add SymbolFilters dataclass to src/domain/market/order.py
  5. Create migration: migrations/010_symbol_filters.sql
  6. Write 30+ tests for filter engine and normalizer

11B. Order Execution Router:
  1. Create OrderRouter in src/infrastructure/market/order_router.py:
     - Mode 1 (PAPER): PaperMarketService
     - Mode 2 (LIVE/TESTNET): BinanceExchangeClient with filter normalization
     - Mode BACKTEST: create_test_order endpoint
  2. Add ExecutionMode enum to src/domain/market/order.py
  3. Add create_test_order() to BinanceExchangeClient
  4. Update market_service_factory.py to support execution mode
  5. Write tests for all routing modes

11C. API Key Management:
  1. Create EncryptionService in src/infrastructure/security/encryption.py:
     - AES-256-GCM encryption
     - Master key from BINANCE_MASTER_KEY env var
  2. Create ApiKey domain model in src/domain/market/api_key.py
  3. Create ApiKeyService in src/application/services/api_key_service.py
  4. Create API routes in src/infrastructure/api/routes/api_keys.py:
     - CRUD endpoints (never return secrets)
     - Test connectivity endpoint
     - Rotate key endpoint
  5. Create migration: migrations/011_api_keys.sql
  6. Write tests for encryption, CRUD, and security

11D. Order Dashboard UI:
  1. Create order dashboard API in src/infrastructure/api/routes/orders_gui.py
  2. Create HTML dashboard in src/infrastructure/web/gui/orders.html
  3. Create API key management page in src/infrastructure/web/gui/api_keys.html
  4. Write tests for dashboard endpoints

11E. Backtest Integration:
  1. Create BacktestMarketService in src/infrastructure/market/backtest_market_service.py
  2. Modify backtest_engine.py to support order execution mode
  3. Write tests for backtest order simulation

Tests:
  - All tests in tests/unit/market/, tests/unit/security/, tests/unit/services/
  - Minimum 60 tests total across all sub-steps
  - Critical: 30+ tests for filter engine (this is the most error-prone area)
  - Cover: BTC/USDC, DOGE/USDC, SHIB/USDC (different price scales)

Output:
  - Files changed/created
  - Test results (pass/fail count)
  - ruff check + black results
```

## Acceptance Criteria

- [ ] Filter engine correctly normalizes prices for BTC (67000), DOGE (0.15), SHIB (0.00001)
- [ ] Retry logic successfully recovers from filter violations 95%+ of the time
- [ ] Order router correctly routes to paper, live, testnet, and backtest modes
- [ ] API keys encrypted at rest, never logged or exposed in responses
- [ ] API key CRUD works with test connectivity
- [ ] Order dashboard shows orders, stats, and execution history
- [ ] Backtest mode uses create_test_order for simulated execution
- [ ] Pipeline never breaks due to order failures (resilient error handling)
- [ ] All 60+ tests pass
- [ ] `ruff check` and `black` pass with no errors

## Dependencies

- Step 2: Market Service (already implemented)
- Step 10: Strategy Runner & Pipeline Orchestration
- Binance API access (testnet for development)
- Environment variable: `BINANCE_MASTER_KEY` (32-byte hex string for encryption)

## Out of Scope

- WebSocket order updates (future enhancement)
- OCO (One-Cancels-Other) orders
- Margin trading
- Futures trading

## Critical Notes

### Binance Filter Error Codes

| Error Code | Meaning | Our Response |
|------------|---------|--------------|
| `-1013` | Filter failure: quantity/price | Retry with ±0.5% adjustment |
| `-1111` | Precision is over the maximum defined | Re-normalize with correct precision |
| `-2010` | New order rejected (notional) | Adjust quantity to meet minNotional |
| `-1021` | Timestamp outside recvWindow | Resync timestamp, retry |

### Testnet Setup

```bash
# Binance Testnet
# URL: https://testnet.binance.vision
# Create account: https://testnet.binance.vision/
# Get API key/secret from testnet dashboard
# Set environment variables:
export BINANCE_TESTNET_API_KEY="your_testnet_key"
export BINANCE_TESTNET_API_SECRET="your_testnet_secret"
export BINANCE_MASTER_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
```

### Resilience Guarantees

1. **Filter errors never crash the pipeline** — caught, logged, retried
2. **API errors never block strategy execution** — strategies continue, order marked FAILED
3. **Network timeouts don't lose orders** — idempotent via client_order_id, status check on retry
4. **Partial fills handled correctly** — order status updated, remaining quantity tracked
5. **Rate limits respected** — exponential backoff on 429 responses
