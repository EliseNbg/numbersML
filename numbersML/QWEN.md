## Qwen Added Memories
- ## Current Project State (numbersML)

### Recent Changes (committed: 4f029e9)
- **normalized_value fix**: `src/pipeline/target_value.py` now properly normalizes filtered values to [0..1] range (was returning raw filtered price before)
- **Training pipeline**: `ml/dataset.py` reads `normalized_value` from DB, applies horizon=30 shift
- **Prediction API**: `src/infrastructure/api/routes/ml.py` reads `normalized_value` from DB, applies horizon shift, removed candle scaling
- **Dashboard labels**: Updated to "Normalized 0-1" in prediction.html and prediction.js
- **Dropout added**: `ml/model.py` - added Dropout(0.4) after each CNN block + pre-GRU dropout layer
- **scipy**: Added to requirements.txt (was missing)

### Known Issues
1. **Prediction API hangs** - `/api/ml/predict` times out on CPU. Model is too slow with sequence_length=120 and ~3600 vectors (3480 prediction steps). Each step processes full CNN+GRU pipeline. Server silently crashes/hangs.
2. **Model was trained with sequence_length=120** (saved in checkpoint config), NOT 1000
3. **Model trained with patience=40** (checkpoint config), patience was later changed back to 10 in config.py
4. **Existing models trained with relative targets (*10000)** - need retraining for normalized_value [0..1]
5. **ml/models/norm_params.npz** - binary file, should be in .gitignore

### Model Architecture (CNN_GRUModel)
- Input: 140 features, seq_len=120
- Feature proj: LayerNorm + Linear(140→64) + GELU + Dropout(0.4)
- Multi-scale CNN: 3 blocks (kernel 3,5,7) → each has Conv+BN+GELU+Dropout(0.4)
- Fusion: Conv1d + BN + GELU + Dropout(0.4)
- Pre-GRU Dropout: NEW, Dropout(0.4)
- GRU: hidden=128, layers=2, dropout=0.4
- Attention: Linear(128→64)+Tanh+Linear(64→1)
- MLP: Linear(128→128)+GELU+LN+Dropout(0.6)+Linear(128→64)+GELU+LN+Dropout(0.4)
- Output: Linear(64→1)

### Key Config Defaults (ml/config.py)
- sequence_length: 1000 (but existing model was trained with 120!)
- dropout: 0.4
- gru_hidden_dim: 128, gru_num_layers: 2
- cnn_channels: [32, 64]
- learning_rate: 1e-3, weight_decay: 5e-3
- patience: 10

### Next Steps Needed
- Fix prediction API timeout (model too slow on CPU, need optimization or caching)
- Retrain model with normalized_value [0..1] targets
- Target values need recalculation in DB (POST /api/target-values/calculate)
