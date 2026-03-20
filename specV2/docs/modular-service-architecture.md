# Modular Service Architecture - Phase 1

## Overview

Design principle: **Each service is independent, can be started/stopped separately, and communicates via PostgreSQL + Redis.**

```
┌────────────────────────────────────────────────────────────────┐
│                    INDEPENDENT SERVICES                         │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Collector  │  │   Enricher   │  │  Asset Sync  │         │
│  │   Service    │  │   Service    │  │   Service    │         │
│  │              │  │              │  │              │         │
│  │ docker-compose│  │docker-compose│  │docker-compose│         │
│  │ -collector.yml│  │ -enricher.yml│  │ -asset-sync.yml│       │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                 │                 │                  │
│         └─────────────────┼─────────────────┘                  │
│                           │                                    │
│              ┌────────────┴────────────┐                       │
│              │   Shared Infrastructure  │                       │
│              │  ┌──────────┐ ┌───────┐ │                       │
│              │  │PostgreSQL│ │ Redis │ │                       │
│              │  └──────────┘ └───────┘ │                       │
│              │  docker-compose-infra.yml│                       │
│              └─────────────────────────┘                       │
└────────────────────────────────────────────────────────────────┘
```

---

## Service Catalog

### Core Services (Always Running)

| Service | Purpose | Start Order | Dependencies |
|---------|---------|-------------|--------------|
| **infrastructure** | PostgreSQL + Redis | 1st | None |
| **data-collector** | Binance WebSocket → PostgreSQL (individual trades) | 2nd | infrastructure |
| **ticker-collector** | Binance WebSocket → PostgreSQL (24hr ticker stats) | 2nd | infrastructure |
| **data-enricher** | PostgreSQL → Indicators → Redis | 3rd | infrastructure, collector |
| **orderbook-collector** | Binance WebSocket → PostgreSQL (order book) | Anytime | infrastructure |

**Note**: 
- `data-collector` collects individual trades (high storage, key symbols only)
- `ticker-collector` collects 24hr ticker statistics (low storage, all symbols)
- Both can run independently or together

### Auxiliary Services (On-Demand / Scheduled)

| Service | Purpose | Start Order | Dependencies |
|---------|---------|-------------|--------------|
| **asset-sync** | Daily Binance metadata sync | Anytime | infrastructure |
| **data-pruner** | Delete old data, compression | Anytime | infrastructure |
| **backfill** | Historical data download | Anytime | infrastructure |
| **gap-filler** | Fill detected data gaps | Anytime | infrastructure, collector |

---

## 1. Infrastructure Service

**File**: `docker/docker-compose-infra.yml`

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    container_name: crypto-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: crypto_trading
      POSTGRES_USER: crypto
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-crypto_secret_change_me}
      POSTGRES_INITDB_ARGS: "-E UTF8"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ../migrations:/docker-entrypoint-initdb.d:ro
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U crypto -d crypto_trading"]
      interval: 10s
      timeout: 5s
      retries: 5
    command: >
      postgres
      -c shared_buffers=256MB
      -c effective_cache_size=768MB
      -c work_mem=64MB
      -c maintenance_work_mem=512MB
      -c max_connections=100
      -c checkpoint_timeout=10min
      -c wal_level=replica
    networks:
      - crypto_network

  redis:
    image: redis:7-alpine
    container_name: crypto-redis
    restart: unless-stopped
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - crypto_network

volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local

networks:
  crypto_network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/16
```

**Start Command**:
```bash
cd docker
docker-compose -f docker-compose-infra.yml up -d
```

---

## 2. Data Collector Service

**File**: `docker/docker-compose-collector.yml`

```yaml
version: '3.8'

services:
  data-collector:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: crypto-data-collector
    restart: unless-stopped
    environment:
      # Application
      APP_SERVICE: data_collector
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      
      # Database
      DATABASE_URL: postgresql://crypto:${POSTGRES_PASSWORD:-crypto_secret_change_me}@postgres:5432/crypto_trading
      
      # Redis (for health checks)
      REDIS_URL: redis://redis:6379
      
      # Collector config
      COLLECTOR_SYMBOLS: ${COLLECTOR_SYMBOLS:-BTC/USDT,ETH/USDT,BNB/USDT}
      COLLECTOR_BATCH_SIZE: ${COLLECTOR_BATCH_SIZE:-500}
      COLLECTOR_BATCH_INTERVAL_MS: ${COLLECTOR_BATCH_INTERVAL_MS:-500}
      
      # Data quality
      QUALITY_MAX_PRICE_MOVE_PCT: ${QUALITY_MAX_PRICE_MOVE_PCT:-10}
      QUALITY_MAX_GAP_SECONDS: ${QUALITY_MAX_GAP_SECONDS:-5}
      QUALITY_ENABLE_VALIDATION: ${QUALITY_ENABLE_VALIDATION:-true}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - collector_logs:/app/logs
      - ../config:/app/config:ro
    networks:
      - crypto_network
    healthcheck:
      test: ["CMD", "python", "-m", "src.cli.health_check"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    # Resource limits
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G

volumes:
  collector_logs:
    driver: local

networks:
  crypto_network:
    external: true
    name: docker_crypto_network
```

**Start Command**:
```bash
docker-compose -f docker-compose-collector.yml up -d
```

**Stop Command**:
```bash
docker-compose -f docker-compose-collector.yml down
```

**Check Status**:
```bash
docker-compose -f docker-compose-collector.yml ps
docker logs crypto-data-collector -f
```

---

## 3. Data Enricher Service

**File**: `docker/docker-compose-enricher.yml`

```yaml
version: '3.8'

services:
  data-enricher:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: crypto-data-enricher
    restart: unless-stopped
    environment:
      # Application
      APP_SERVICE: data_enricher
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      
      # Database
      DATABASE_URL: postgresql://crypto:${POSTGRES_PASSWORD:-crypto_secret_change_me}@postgres:5432/crypto_trading
      
      # Redis (for publishing enriched ticks)
      REDIS_URL: redis://redis:6379
      
      # Enricher config
      ENRICHER_WINDOW_SIZE: ${ENRICHER_WINDOW_SIZE:-1000}
      ENRICHER_BATCH_SIZE: ${ENRICHER_BATCH_SIZE:-100}
      ENRICHER_INDICATORS: ${ENRICHER_INDICATORS:-rsi_14,macd,sma_20,ema_20,bollinger}
      
      # Performance
      ENRICHER_MAX_LATENCY_MS: ${ENRICHER_MAX_LATENCY_MS:-100}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - enricher_logs:/app/logs
      - ../config:/app/config:ro
    networks:
      - crypto_network
    healthcheck:
      test: ["CMD", "python", "-m", "src.cli.health_check"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    deploy:
      resources:
        limits:
          cpus: '4.0'
          memory: 4G
        reservations:
          cpus: '2.0'
          memory: 2G

volumes:
  enricher_logs:
    driver: local

networks:
  crypto_network:
    external: true
    name: docker_crypto_network
```

---

## 4. Order Book Collector Service (Future Implementation)

**File**: `docker/docker-compose-orderbook.yml`

```yaml
version: '3.8'

services:
  orderbook-collector:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: crypto-orderbook-collector
    restart: unless-stopped
    environment:
      # Application
      APP_SERVICE: orderbook_collector
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      
      # Database
      DATABASE_URL: postgresql://crypto:${POSTGRES_PASSWORD:-crypto_secret_change_me}@postgres:5432/crypto_trading
      
      # Collector config
      ORDERBOOK_SYMBOLS: ${ORDERBOOK_SYMBOLS:-BTC/USDT,ETH/USDT}
      ORDERBOOK_LEVELS: ${ORDERBOOK_LEVELS:-10}  # 10, 20, or full depth
      ORDERBOOK_INTERVAL_SEC: ${ORDERBOOK_INTERVAL_SEC:-1}  # 1s, 5s, etc.
      ORDERBOOK_STORAGE_MODE: ${ORDERBOOK_STORAGE_MODE:-arrays}  # arrays, normalized
      
      # Feature flags (dynamic configuration ready)
      ORDERBOOK_ENABLED: ${ORDERBOOK_ENABLED:-false}  # Enable/disable without restart
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - orderbook_logs:/app/logs
      - ../config:/app/config:ro
    networks:
      - crypto_network
    healthcheck:
      test: ["CMD", "python", "-m", "src.cli.health_check"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
    # Profile: only starts when explicitly enabled
    profiles:
      - orderbook

volumes:
  orderbook_logs:
    driver: local

networks:
  crypto_network:
    external: true
    name: docker_crypto_network
```

**Start Order Book Collector** (when implemented):

```bash
# Start with orderbook profile
docker-compose -f docker-compose-orderbook.yml --profile orderbook up -d

# Or start manually
docker-compose -f docker-compose-orderbook.yml up orderbook-collector
```

**Note**: This service is designed but not yet implemented. When you're ready to collect order book data:
1. Implement OrderBookCollector class (see orderbook-collection-design.md)
2. Create orderbook_snapshots table
3. Enable this service

---

## 4. Asset Sync Service (Scheduled/On-Demand)

**File**: `docker/docker-compose-asset-sync.yml`

```yaml
version: '3.8'

services:
  asset-sync:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: crypto-asset-sync
    restart: "no"  # Don't auto-restart, runs on schedule
    environment:
      # Application
      APP_SERVICE: asset_sync
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      
      # Database
      DATABASE_URL: postgresql://crypto:${POSTGRES_PASSWORD:-crypto_secret_change_me}@postgres:5432/crypto_trading
      
      # Sync config
      SYNC_SCHEDULE: ${SYNC_SCHEDULE:-0 0 * * *}  # Daily at midnight (cron format)
      SYNC_AUTO_ACTIVATE: ${SYNC_AUTO_ACTIVATE:-true}
      SYNC_AUTO_DEACTIVATE_DELISTED: ${SYNC_AUTO_DEACTIVATE_DELISTED:-true}
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - asset_sync_logs:/app/logs
      - ../config:/app/config:ro
    networks:
      - crypto_network
    
  # Optional: Run sync manually via CLI
  asset-sync-manual:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: crypto-asset-sync-manual
    environment:
      APP_SERVICE: asset_sync_cli
      DATABASE_URL: postgresql://crypto:${POSTGRES_PASSWORD:-crypto_secret_change_me}@postgres:5432/crypto_trading
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ../config:/app/config:ro
    networks:
      - crypto_network
    command: ["python", "-m", "src.cli.sync_assets", "--dry-run"]
    profiles:
      - manual  # Only runs when explicitly started

volumes:
  asset_sync_logs:
    driver: local

networks:
  crypto_network:
    external: true
    name: docker_crypto_network
```

**Start Scheduled Service**:
```bash
docker-compose -f docker-compose-asset-sync.yml up -d
```

**Run Manual Sync**:
```bash
docker-compose -f docker-compose-asset-sync.yml --profile manual up asset-sync-manual
```

**Run with Arguments**:
```bash
docker-compose -f docker-compose-asset-sync.yml --profile manual run asset-sync-manual \
  python -m src.cli.sync_assets --dry-run
```

---

## 5. Data Pruner Service (On-Demand)

**File**: `docker/docker-compose-pruner.yml`

```yaml
version: '3.8'

services:
  data-pruner:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: crypto-data-pruner
    restart: "no"  # Don't auto-restart
    environment:
      # Application
      APP_SERVICE: data_pruner
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      
      # Database
      DATABASE_URL: postgresql://crypto:${POSTGRES_PASSWORD:-crypto_secret_change_me}@postgres:5432/crypto_trading
      
      # Pruning config
      PRUNE_TICKS_OLDER_THAN_DAYS: ${PRUNE_TICKS_OLDER_THAN_DAYS:-90}
      PRUNE_INDICATORS_OLDER_THAN_DAYS: ${PRUNE_INDICATORS_OLDER_THAN_DAYS:-180}
      PRUNE_DRY_RUN: ${PRUNE_DRY_RUN:-false}
      PRUNE_SYMBOLS: ${PRUNE_SYMBOLS:-}  # Empty = all symbols
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - pruner_logs:/app/logs
      - ../config:/app/config:ro
    networks:
      - crypto_network
    command: ["python", "-m", "src.cli.data_pruner"]

volumes:
  pruner_logs:
    driver: local

networks:
  crypto_network:
    external: true
    name: docker_crypto_network
```

**Run Pruner**:
```bash
# Dry run (see what would be deleted)
docker-compose -f docker-compose-pruner.yml run data-pruner \
  python -m src.cli.data_pruner --dry-run

# Actually delete (older than 90 days)
docker-compose -f docker-compose-pruner.yml run data-pruner \
  python -m src.cli.data_pruner --days 90

# Only for specific symbol
docker-compose -f docker-compose-pruner.yml run data-pruner \
  python -m src.cli.data_pruner --days 90 --symbol BTC/USDT
```

---

## 6. Backfill Service (On-Demand)

**File**: `docker/docker-compose-backfill.yml`

```yaml
version: '3.8'

services:
  backfill:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: crypto-backfill
    restart: "no"
    environment:
      # Application
      APP_SERVICE: backfill
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      
      # Database
      DATABASE_URL: postgresql://crypto:${POSTGRES_PASSWORD:-crypto_secret_change_me}@postgres:5432/crypto_trading
      
      # Backfill config
      BACKFILL_SYMBOLS: ${BACKFILL_SYMBOLS:-BTC/USDT,ETH/USDT}
      BACKFILL_DAYS: ${BACKFILL_DAYS:-30}
      BACKFILL_DATA_TYPE: ${BACKFILL_DATA_TYPE:-candles_1m}  # candles_1m, candles_1h, trades
      BACKFILL_PARALLEL: ${BACKFILL_PARALLEL:-2}  # Number of parallel downloads
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - backfill_logs:/app/logs
      - ../config:/app/config:ro
      - backfill_data:/app/data
    networks:
      - crypto_network
    command: ["python", "-m", "src.cli.backfill"]

volumes:
  backfill_logs:
    driver: local
  backfill_data:
    driver: local

networks:
  crypto_network:
    external: true
    name: docker_crypto_network
```

**Run Backfill**:
```bash
# Backfill 30 days of 1-minute candles for BTC/USDT
docker-compose -f docker-compose-backfill.yml run backfill \
  python -m src.cli.backfill --symbols BTC/USDT --days 30 --type candles_1m

# Backfill 6 months for multiple symbols
docker-compose -f docker-compose-backfill.yml run backfill \
  python -m src.cli.backfill --symbols BTC/USDT,ETH/USDT,BNB/USDT --days 180
```

---

## 7. Gap Filler Service (On-Demand / Triggered)

**File**: `docker/docker-compose-gap-filler.yml`

```yaml
version: '3.8'

services:
  gap-filler:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: crypto-gap-filler
    restart: "no"
    environment:
      # Application
      APP_SERVICE: gap_filler
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      
      # Database
      DATABASE_URL: postgresql://crypto:${POSTGRES_PASSWORD:-crypto_secret_change_me}@postgres:5432/crypto_trading
      
      # Gap filler config
      GAP_FILL_MAX_GAP_SECONDS: ${GAP_FILL_MAX_GAP_SECONDS:-300}  # Max 5 minutes
      GAP_FILL_SYMBOLS: ${GAP_FILL_SYMBOLS:-}  # Empty = check all active symbols
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - gap_filler_logs:/app/logs
      - ../config:/app/config:ro
    networks:
      - crypto_network
    command: ["python", "-m", "src.cli.gap_filler"]

volumes:
  gap_filler_logs:
    driver: local

networks:
  crypto_network:
    external: true
    name: docker_crypto_network
```

**Run Gap Filler**:
```bash
# Check and fill gaps for all active symbols
docker-compose -f docker-compose-gap-filler.yml run gap-filler \
  python -m src.cli.gap_filler

# Only for specific symbol
docker-compose -f docker-compose-gap-filler.yml run gap-filler \
  python -m src.cli.gap_filler --symbol BTC/USDT
```

---

## 8. Management Scripts

**File**: `scripts/manage.sh`

```bash
#!/bin/bash

# Crypto Trading System - Service Management

set -e

COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../docker" && pwd)"
cd "$COMPOSE_DIR"

case "$1" in
  start-infra)
    echo "Starting infrastructure (PostgreSQL + Redis)..."
    docker-compose -f docker-compose-infra.yml up -d
    echo "Waiting for services to be healthy..."
    sleep 10
    docker-compose -f docker-compose-infra.yml ps
    ;;
  
  start-collector)
    echo "Starting data collector..."
    docker-compose -f docker-compose-collector.yml up -d
    ;;
  
  start-enricher)
    echo "Starting data enricher..."
    docker-compose -f docker-compose-enricher.yml up -d
    ;;
  
  start-all)
    echo "Starting all core services..."
    $0 start-infra
    $0 start-collector
    $0 start-enricher
    echo "All services started!"
    docker ps --filter "name=crypto-"
    ;;
  
  stop-collector)
    echo "Stopping data collector..."
    docker-compose -f docker-compose-collector.yml down
    ;;
  
  stop-enricher)
    echo "Stopping data enricher..."
    docker-compose -f docker-compose-enricher.yml down
    ;;
  
  stop-all)
    echo "Stopping all services..."
    docker-compose -f docker-compose-collector.yml down
    docker-compose -f docker-compose-enricher.yml down
    docker-compose -f docker-compose-infra.yml down
    ;;
  
  status)
    echo "Service Status:"
    echo "==============="
    docker ps -a --filter "name=crypto-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    ;;
  
  logs)
    if [ -z "$2" ]; then
      echo "Usage: $0 logs <service-name>"
      echo "Available services: collector, enricher, asset-sync, pruner, backfill, gap-filler"
      exit 1
    fi
    docker logs crypto-$2 -f
    ;;
  
  run-sync)
    echo "Running asset sync..."
    docker-compose -f docker-compose-asset-sync.yml --profile manual run asset-sync-manual \
      python -m src.cli.sync_assets ${@:2}
    ;;
  
  run-pruner)
    echo "Running data pruner..."
    docker-compose -f docker-compose-pruner.yml run data-pruner \
      python -m src.cli.data_pruner ${@:2}
    ;;
  
  run-backfill)
    echo "Running backfill..."
    docker-compose -f docker-compose-backfill.yml run backfill \
      python -m src.cli.backfill ${@:2}
    ;;
  
  run-gap-filler)
    echo "Running gap filler..."
    docker-compose -f docker-compose-gap-filler.yml run gap-filler \
      python -m src.cli.gap_filler ${@:2}
    ;;
  
  health)
    echo "Health Check:"
    echo "============="
    docker exec crypto-postgres pg_isready -U crypto -d crypto_trading
    docker exec crypto-redis redis-cli ping
    ;;
  
  *)
    echo "Crypto Trading System - Service Management"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  start-infra          Start infrastructure (PostgreSQL + Redis)"
    echo "  start-collector      Start data collector service"
    echo "  start-enricher       Start data enricher service"
    echo "  start-all            Start all core services"
    echo "  stop-collector       Stop data collector"
    echo "  stop-enricher        Stop data enricher"
    echo "  stop-all             Stop all services"
    echo "  status               Show service status"
    echo "  logs <service>       Follow logs for service"
    echo "  run-sync [opts]      Run asset sync manually"
    echo "  run-pruner [opts]    Run data pruner"
    echo "  run-backfill [opts]  Run backfill"
    echo "  run-gap-filler [opts] Run gap filler"
    echo "  health               Check health of infrastructure"
    echo ""
    echo "Examples:"
    echo "  $0 start-all"
    echo "  $0 logs collector"
    echo "  $0 run-sync --dry-run"
    echo "  $0 run-pruner --days 90"
    echo "  $0 run-backfill --symbols BTC/USDT --days 30"
    ;;
esac
```

**Make Executable**:
```bash
chmod +x scripts/manage.sh
```

---

## 9. Usage Examples

### Initial Setup

```bash
# 1. Start infrastructure
./scripts/manage.sh start-infra

# 2. Wait for database to be ready
sleep 10

# 3. Run migrations
docker-compose -f docker-compose-infra.yml exec postgres \
  psql -U crypto -d crypto_trading -f /docker-entrypoint-initdb.d/001_initial_schema.sql

# 4. Sync asset metadata
./scripts/manage.sh run-sync

# 5. Activate some symbols
docker exec crypto-postgres psql -U crypto -d crypto_trading -c \
  "UPDATE symbols SET is_active = true WHERE symbol IN ('BTC/USDT', 'ETH/USDT');"

# 6. Start data collection
./scripts/manage.sh start-collector

# 7. Start enrichment
./scripts/manage.sh start-enricher

# 8. Check status
./scripts/manage.sh status
```

### Daily Operations

```bash
# Check service status
./scripts/manage.sh status

# View collector logs
./scripts/manage.sh logs collector

# View enricher logs
./scripts/manage.sh logs enricher

# Run asset sync manually
./scripts/manage.sh run-sync

# Check health
./scripts/manage.sh health
```

### Maintenance

```bash
# Run data pruner (dry run first)
./scripts/manage.sh run-pruner --dry-run
./scripts/manage.sh run-pruner --days 90

# Fill data gaps
./scripts/manage.sh run-gap-filler

# Backfill historical data
./scripts/manage.sh run-backfill --symbols BTC/USDT --days 30

# Stop collector for maintenance
./scripts/manage.sh stop-collector

# Restart enricher
./scripts/manage.sh stop-enricher
./scripts/manage.sh start-enricher
```

### Shutdown

```bash
# Stop all services
./scripts/manage.sh stop-all

# Or stop individual services
./scripts/manage.sh stop-collector
./scripts/manage.sh stop-enricher

# Stop infrastructure (database + redis)
docker-compose -f docker-compose-infra.yml down
```

---

## 10. Environment Configuration

**File**: `.env`

```bash
# Security
POSTGRES_PASSWORD=crypto_secret_change_me_in_production

# Logging
LOG_LEVEL=INFO

# Collector Configuration
COLLECTOR_SYMBOLS=BTC/USDT,ETH/USDT,BNB/USDT,SOL/USDT,XRP/USDT
COLLECTOR_BATCH_SIZE=500
COLLECTOR_BATCH_INTERVAL_MS=500

# Data Quality
QUALITY_MAX_PRICE_MOVE_PCT=10
QUALITY_MAX_GAP_SECONDS=5
QUALITY_ENABLE_VALIDATION=true

# Enricher Configuration
ENRICHER_WINDOW_SIZE=1000
ENRICHER_BATCH_SIZE=100
ENRICHER_INDICATORS=rsi_14,macd,sma_20,ema_20,bollinger
ENRICHER_MAX_LATENCY_MS=100

# Asset Sync Configuration
SYNC_SCHEDULE=0 0 * * *  # Daily at midnight
SYNC_AUTO_ACTIVATE=true
SYNC_AUTO_DEACTIVATE_DELISTED=true

# Pruner Configuration
PRUNE_TICKS_OLDER_THAN_DAYS=90
PRUNE_INDICATORS_OLDER_THAN_DAYS=180
PRUNE_DRY_RUN=false

# Backfill Configuration
BACKFILL_DAYS=30
BACKFILL_PARALLEL=2
```

---

## 11. Dockerfile

**File**: `docker/Dockerfile`

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libta-lib-dev \
    libta-lib0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Create logs directory
RUN mkdir -p /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -m src.cli.health_check || exit 1

# Default command (overridden by docker-compose)
CMD ["python", "-m", "src.main"]
```

---

## 12. Service Communication

```
┌────────────────────────────────────────────────────────────┐
│                 SERVICE COMMUNICATION                       │
│                                                             │
│  Collector ──┬──► PostgreSQL (trades table)                │
│              │                                              │
│  Enricher ───┼──► PostgreSQL (LISTEN new_tick)             │
│              │                                              │
│              ├──► Calculate indicators                      │
│              │                                              │
│              ├──► PostgreSQL (tick_indicators table)        │
│              │                                              │
│              └──► Redis (publish enriched_tick)             │
│                                                             │
│  Asset Sync ────► PostgreSQL (symbols table)                │
│                                                             │
│  Pruner ───────► PostgreSQL (DELETE old data)               │
│                                                             │
│  Backfill ─────► PostgreSQL (INSERT historical)             │
│                                                             │
│  Gap Filler ───► PostgreSQL (SELECT gaps, INSERT fills)     │
└────────────────────────────────────────────────────────────┘
```

**All services communicate via:**
1. **PostgreSQL** - Primary data store + NOTIFY/LISTEN
2. **Redis** - Pub/Sub for real-time enriched ticks
3. **No direct service-to-service calls** - Fully decoupled

---

## Summary

### Benefits of This Architecture

✅ **Independent Scaling**: Scale collector/enricher separately  
✅ **Independent Deployment**: Update one service without restarting others  
✅ **Fault Isolation**: One service failing doesn't crash others  
✅ **Flexible Operations**: Start/stop services as needed  
✅ **Easy Maintenance**: Run pruner/backfill on-demand  
✅ **Clear Boundaries**: Each service has single responsibility  

### Next Steps

1. Create Dockerfile
2. Create docker-compose files (infra, collector, enricher, etc.)
3. Create management scripts
4. Test each service independently
5. Test service combinations

**Ready to implement?**
