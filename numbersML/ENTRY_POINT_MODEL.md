# Entry Point Model Dokumentation

## Übersicht

Entry Point Modell ist ein binärer Klassifikator der optimale Einstiegspunkte für Long Positionen auf Basis technischer Indikatoren vorhersagt.

---

## 🚀 Kommandozeile Befehle

### 1. Modell trainieren
```bash
.venv/bin/python train_entry_model.py \
    --symbol DASH/USDC \
    --hours 720 \
    --profit 0.009 \
    --stop 0.003 \
    --lookahead 2700
```

| Parameter | Beschreibung | Einheit | Beispiel |
|---|---|---|---|
| `--symbol` | Handelspaar | String | `DASH/USDC` |
| `--hours` | Trainingsdaten Historie | Stunden | `720` = 30 Tage |
| `--profit` | Take Profit Ziel | Faktor | `0.009` = **0.9%** |
| `--stop` | Stop Loss | Faktor | `0.003` = **0.3%** |
| `--lookahead` | Vorausschau Fenster | Sekunden | `2700` = 45 Minuten |

---

### 2. Backtest ausführen
```bash
.venv/bin/python -m ml.backtest \
    --model entry_model_DASH_USDC_20260418_1743.pkl \
    --symbol DASH/USDC \
    --hours 24 \
    --threshold 0.72 \
    --print-trades
```

| Parameter | Beschreibung | Standard |
|---|---|---|
| `--model` | Pfad zur gespeicherten Modell Datei | Pflicht |
| `--symbol` | Handelspaar | Pflicht |
| `--hours` | Backtest Zeitfenster | `168` |
| `--threshold` | Klassifizierungs Grenze | `0.65` |
| `--print-trades` | Ausgabe aller einzelnen Trades | Aus |

---

### 3. Web Interface Bedienung

Der `Train Model` Button auf `/dashboard/backtest.html` führt genau das gleiche Training aus wie das CLI Skript. Alle Parameter aus dem Formular werden 1:1 korrekt übergeben.

---

## ✅ Modell Eigenschaften

| Eigenschaft | Wert |
|---|---|
| Modell Typ | LightGBM Binary Classifier |
| Eingabe Features | 140 technische Indikatoren |
| Sequenzlänge | 1 |
| Ausgabewert | Wahrscheinlichkeit [0..1] |
| Trainingszeit | ~ 15 Sekunden |
| Vorhersagegeschwindigkeit | > 50.000 / Sekunde |
| Zustand | Stateless (kein Gedächtnis) |

---

## 📊 Empfohlene Einstellungen

| Szenario | Profit Target | Stop Loss | Threshold | Trades pro Tag |
|---|---|---|---|---|
| Sehr konservativ | 0.9% | 0.3% | 0.72 | 1-3 |
| Balanciert | 0.45% | 0.15% | 0.62 | 8-12 |
| Aggressiv | 0.2% | 0.1% | 0.55 | 15-25 |

---

## 📂 Speicherorte

- Trainierte Modelle: `./entry_model_*.pkl`
- Backtest Logik: `ml/backtest.py`
- Training Logik: `ml/entry_model.py`
- Dataset Generator: `ml/entry_dataset.py`
