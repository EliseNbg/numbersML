#!/bin/bash
# Start Data Collection for Volatile Symbols
#
# This script:
# 1. Finds the 5 most volatile symbols on Binance
# 2. Sets up the database
# 3. Starts the data collection service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "========================================"
echo "Crypto Trading System - Data Collection"
echo "========================================"
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install dependencies if needed
if ! python -c "import asyncpg" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -q -r requirements.txt
fi

echo ""
echo "Step 1: Finding most volatile symbols..."
echo "----------------------------------------"

# Find volatile symbols
VOLATILE_SYMBOLS=$(python -c "
import asyncio
import sys
sys.path.insert(0, 'src')
from cli.find_volatile_symbols import get_most_volatile_symbols
symbols = asyncio.run(get_most_volatile_symbols(5))
print(','.join([s['symbol'] for s in symbols]))
")

echo "Most volatile symbols: $VOLATILE_SYMBOLS"
echo ""

# Save to config file
echo "Step 2: Creating configuration..."
echo "----------------------------------------"

cat > config/collect_symbols.txt << EOF
# Volatile symbols for data collection
# Generated: $(date)
$VOLATILE_SYMBOLS
EOF

echo "Configuration saved to config/collect_symbols.txt"
echo ""

# Check if Docker is running
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed or not in PATH"
    echo "Please install Docker and Docker Compose"
    exit 1
fi

echo "Step 3: Starting infrastructure (PostgreSQL + Redis)..."
echo "----------------------------------------"

# Start infrastructure
docker-compose -f docker/docker-compose-infra.yml up -d

echo "Waiting for services to be healthy..."
sleep 5

# Check health
docker-compose -f docker/docker-compose-infra.yml ps

echo ""
echo "Step 4: Running database migrations..."
echo "----------------------------------------"

# Wait for PostgreSQL to be ready
until docker-compose -f docker/docker-compose-infra.yml exec -T postgres pg_isready -U crypto -d crypto_trading > /dev/null 2>&1; do
    echo "Waiting for PostgreSQL..."
    sleep 2
done

# Run migrations
docker-compose -f docker/docker-compose-infra.yml exec -T postgres \
    psql -U crypto -d crypto_trading -c "SELECT 1" > /dev/null 2>&1

echo "Database is ready!"
echo ""

# Insert symbols into database
echo "Step 5: Registering symbols in database..."
echo "----------------------------------------"

# Convert symbols to SQL format
SYMBOLS_SQL=$(echo "$VOLATILE_SYMBOLS" | tr ',' '\n' | while read symbol; do
    base=$(echo "$symbol" | cut -d'/' -f1)
    quote=$(echo "$symbol" | cut -d'/' -f2)
    echo "('$symbol', '$base', '$quote', 'binance', 0.01, 0.00001, 10, true, true)"
done | paste -sd ',' -)

docker-compose -f docker/docker-compose-infra.yml exec -T postgres psql -U crypto -d crypto_trading << EOF
-- Insert symbols (upsert)
INSERT INTO symbols (symbol, base_asset, quote_asset, exchange, tick_size, step_size, min_notional, is_allowed, is_active)
VALUES $SYMBOLS_SQL
ON CONFLICT (symbol) DO UPDATE SET
    is_active = true,
    is_allowed = true,
    updated_at = NOW();

-- Show active symbols
SELECT symbol, base_asset, quote_asset, is_active FROM symbols WHERE is_active = true;
EOF

echo ""
echo "Step 6: Starting data collection service..."
echo "----------------------------------------"

# Export environment variables
export DATABASE_URL="postgresql://crypto:crypto@localhost:5432/crypto_trading"
export COLLECTOR_SYMBOLS="$VOLATILE_SYMBOLS"

echo "Starting collection for: $VOLATILE_SYMBOLS"
echo ""
echo "========================================"
echo "Data collection is starting!"
echo "========================================"
echo ""
echo "Symbols: $VOLATILE_SYMBOLS"
echo "Database: postgresql://crypto:crypto@localhost:5432/crypto_trading"
echo ""
echo "To monitor:"
echo "  docker logs crypto-data-collector -f"
echo ""
echo "To stop:"
echo "  docker-compose -f docker/docker-compose-collector.yml down"
echo ""
echo "To view collected data:"
echo "  docker-compose -f docker/docker-compose-infra.yml exec postgres psql -U crypto -d crypto_trading"
echo "  SELECT symbol, COUNT(*) FROM trades t JOIN symbols s ON s.id = t.symbol_id GROUP BY symbol;"
echo ""

# Start the collector
python src/main.py
