#!/bin/bash
# Test script to verify strategy deactivation and check status

STRATEGY_ID="${1:-374f2af4-7492-492d-a040-048fd3c5892a}"
BASE_URL="http://localhost:8000"

echo "=========================================="
echo "Strategy Status Test"
echo "=========================================="
echo "Strategy ID: $STRATEGY_ID"
echo ""

# 1. Get current status BEFORE deactivate
echo "1. Getting current strategy status BEFORE deactivate..."
curl -s "$BASE_URL/api/strategies/$STRATEGY_ID" | python3 -m json.tool
echo ""

# 2. Call deactivate
echo "2. Calling deactivate..."
curl -s -X POST "$BASE_URL/api/strategies/$STRATEGY_ID/deactivate" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool
echo ""

# 3. Get status immediately after
echo "3. Getting status immediately after deactivate (0ms delay)..."
curl -s "$BASE_URL/api/strategies/$STRATEGY_ID" | python3 -m json.tool
echo ""

# 4. Get status with 500ms delay
echo "4. Waiting 500ms then getting status..."
sleep 0.5
curl -s "$BASE_URL/api/strategies/$STRATEGY_ID" | python3 -m json.tool
echo ""

# 5. Use debug endpoint
echo "5. Using debug endpoint to check raw DB state..."
curl -s "$BASE_URL/api/strategies/$STRATEGY_ID/debug-status" | python3 -m json.tool
echo ""

# 6. List all strategies to verify
echo "6. Listing all strategies..."
curl -s "$BASE_URL/api/strategies" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for s in data:
    print(f\"ID: {s['id']} | Name: {s['name'][:20]:20} | Status: {s['status']}\")"
echo ""

echo "=========================================="
echo "Test complete"
echo "=========================================="
