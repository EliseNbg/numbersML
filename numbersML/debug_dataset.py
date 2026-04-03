#!/usr/bin/env python3
"""
Debug script for ML dataset loading
"""

import sys
import psycopg2
from datetime import datetime, timedelta, timezone

sys.path.insert(0, '.')

# Test database connection directly
print("Connecting to database...")
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="crypto_trading",
    user="crypto",
    password="crypto_secret",
)

cur = conn.cursor()

# Test 1: Get symbol id
symbol = 'T01/USDC'
cur.execute('SELECT id FROM symbols WHERE symbol = %s', (symbol,))
symbol_id = cur.fetchone()[0]
print(f'Symbol {symbol} id: {symbol_id}')

# Test 2: Count valid samples
end_time = datetime.now(timezone.utc)
start_time = end_time - timedelta(hours=2)

print(f"Querying samples from {start_time} to {end_time}")

cur.execute('''
    SELECT COUNT(*)
    FROM wide_vectors wv
    INNER JOIN candles_1s c ON c.time = wv.time AND c.symbol_id = %s
    WHERE wv.time >= %s AND wv.time < %s
      AND wv.vector_size >= 50
''', (symbol_id, start_time, end_time))

count = cur.fetchone()[0]
print(f'Found {count} valid samples')

# Test 3: Check single row
cur.execute('''
    SELECT wv.time, wv.vector_size, c.close
    FROM wide_vectors wv
    INNER JOIN candles_1s c ON c.time = wv.time AND c.symbol_id = %s
    WHERE wv.time >= %s AND wv.time < %s
      AND wv.vector_size >= 50
    LIMIT 1
''', (symbol_id, start_time, end_time))

row = cur.fetchone()
if row:
    print(f'Sample: time={row[0]}, vector_size={row[1]}, close={row[2]}')

cur.close()
conn.close()

print("\n✅ All queries succeeded")
