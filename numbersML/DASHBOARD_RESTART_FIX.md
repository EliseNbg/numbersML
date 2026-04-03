# ⚠️ CNN+GRU Model Not Showing in Dashboard - FIXED

## Problem

CNN+GRU model wasn't appearing in the prediction page dropdown.

## Root Cause

The dashboard server was running with **old code** from April 2nd, before the CNN+GRU integration was added.

```
Old server PID: 1101052
Started: Apr 02
Missing: CNN+GRU label in type_labels dictionary
```

## Solution

**Restarted the server with updated code:**

```bash
# Kill old server
kill 1101052

# Start new server with updated code
cd /home/andy/projects/numbers/numbersML
.venv/bin/python -m uvicorn src.infrastructure.api.app:app --host 0.0.0.0 --port 8000 &
```

## Result

✅ **CNN+GRU now appears in API response:**

```json
{
    "name": "cnn_gru/cnn_gru_42_T01USDC_20260403.pt",
    "type": "cnn_gru",
    "label": "CNN+GRU",
    "path": "ml/models/cnn_gru/cnn_gru_42_T01USDC_20260403.pt",
    "size_mb": 2.33,
    "modified": "2026-04-03T09:44:47.584848"
}
```

## How to Verify

1. **Check API endpoint:**
   ```bash
   curl http://localhost:8000/api/ml/models
   ```
   Should show CNN+GRU model.

2. **Open dashboard:**
   ```
   http://localhost:8000/dashboard/prediction.html
   ```
   CNN+GRU should appear in model dropdown.

## Prevent This in Future

When you update the code, always restart the server:

```bash
# Find running server
ps aux | grep uvicorn

# Kill it
kill <PID>

# Restart
.venv/bin/python -m uvicorn src.infrastructure.api.app:app --host 0.0.0.0 --port 8000 &
```

Or use a convenience script:

```bash
#!/bin/bash
# restart_dashboard.sh
pkill -f "uvicorn.*app:app"
sleep 2
cd /home/andy/projects/numbers/numbersML
.venv/bin/python -m uvicorn src.infrastructure.api.app:app --host 0.0.0.0 --port 8000 &
echo "Dashboard restarted on port 8000"
```

## Status

✅ **FIXED** - CNN+GRU model now visible in dashboard dropdown!
