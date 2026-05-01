#!/bin/bash
# Load test data into the database for integration tests
# Usage: ./scripts/load_test_data.sh [psql connection options]
# Environment variables: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS

set -e

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-crypto_trading}"
DB_USER="${DB_USER:-crypto}"
DB_PASS="${DB_PASS:-crypto_secret}"

export PGPASSWORD="$DB_PASS"

echo "Loading test data into $DB_NAME at $DB_HOST:$DB_PORT..."

# Run migrations first
echo "Running migrations..."
for migration in migrations/*.sql; do
    if [ "$migration" != "migrations/test_data.sql" ]; then
        echo "  Running $migration..."
        psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$migration" -q || echo "  Warning: $migration failed (may already be applied)"
    fi
done

# Load test data
echo "Loading test data..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f migrations/test_data.sql

echo "Test data loaded successfully!"

# Show summary
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "
SELECT 'Symbols' as table_name, count(*) as count FROM symbols WHERE is_test = true
UNION ALL
SELECT 'Candles', count(*) FROM candles_1s c JOIN symbols s ON s.id = c.symbol_id WHERE s.is_test = true
UNION ALL
SELECT 'Indicators', count(*) FROM candle_indicators ci JOIN symbols s ON s.id = ci.symbol_id WHERE s.is_test = true;
"
