# Plan: Add Model Type Selection (Simple/Full/Transformer)

## Context
The ML prediction page currently has a model dropdown populated from `/api/ml/models`, which only lists `.pt` files in the root `ml/models/` directory. Models exist in subdirectories (`simple/`, `full/`, `transformer/`), each with their own `best_model.pt` and `norm_params.npz`. The user wants a clear model type selector on the frontend.

## Changes

### 1. Backend: Update `list_models` endpoint (`src/infrastructure/api/routes/ml.py:96-123`)
- Scan subdirectories (`simple/`, `full/`, `transformer/`) in addition to root
- Return model type label alongside the model path
- Each entry: `{ "name": "simple/best_model.pt", "type": "simple", "path": "ml/models/simple/best_model.pt", ... }`

### 2. Frontend: Update model dropdown (`dashboard/js/prediction.js:70-96`)
- Update `loadModels()` to display model type (Simple/Full/Transformer) as the label
- Keep auto-selecting the first available model
- The `model` value sent to API will be e.g. `simple/best_model.pt`

### 3. Frontend: No HTML changes needed (`dashboard/prediction.html`)
- The existing `<select id="prediction-model">` already exists and will be repopulated with the new model list

## Files to modify
1. `src/infrastructure/api/routes/ml.py` - Update `list_models()` to scan subdirectories
2. `dashboard/js/prediction.js` - Update `loadModels()` display labels

## Verification
- `curl http://localhost:8000/api/ml/models` should return models from all 3 subdirectories
- Frontend dropdown should show "Simple", "Full", "Transformer" options
- Selecting a model type and clicking "Load & Predict" should pass the correct model path to `/api/ml/predict`
