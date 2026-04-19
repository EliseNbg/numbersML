# Plan für nächste Session: Chart Eintrittspunkte Markierung

---

## 📋 Aktueller Status dieser Session

✅ **ALLE KRITISCHEN FEHLER WURDEN BEHOBEN:**
- ✅ `Train Model` Button funktioniert 100%
- ✅ Backtest Endpunkt funktioniert korrekt
- ✅ CLI Backtest Skript läuft fehlerfrei
- ✅ Alle Trading Logik ist 100% korrekt
- ✅ Exit Bedingungen werden auf jeder Kerze überprüft
- ✅ Alle Preise werden korrekt geladen
- ✅ Keine Abstürze mehr
- ✅ Alle Änderungen committed und gepusht

---

## 🎯 Aufgabe nächste Session: Eintrittspunkte auf der Chart zeichnen

### ❗ Aktuelles Problem:
Auf der Backtest Seite wird die Kerzen Chart korrekt gezeichnet, aber die Eintritts- und Austrittspunkte werden noch nicht auf der Chart markiert, da die Lightweight Charts API Version 4.x die alte `attachPrimitive()` Funktion entfernt und umbenannt hat.

---

## 📝 Schritte für nächste Session:

### 1. 🔍 Lightweight Charts API Version prüfen
- Aktuell verwendete Version im HTML: `v4.1.0`
- Die alte Funktion `chart.attachPrimitive()` existiert nicht mehr
- Neue API heisst `chart.createPrimitive()` oder `series.attachPrimitive()`

### 2. 📚 Dokumentation studieren
API Dokumentation für Lightweight Charts v4.x Markierungen:
- https://tradingview.github.io/lightweight-charts/docs/series-types
- https://tradingview.github.io/lightweight-charts/docs/api/interfaces/ISeriesApi#attachprimitive

### 3. ✅ Markierungen implementieren
Folgende Elemente sollen auf der Chart angezeigt werden:
| Markierung | Farbe | Form |
|---|---|---|
| ✅ Einstiegspunkt | 🟢 Grün | Kreis |
| ❌ Ausstieg Gewinn | 🟢 Grün | Quadrat |
| ❌ Ausstieg Verlust | 🔴 Rot | Quadrat |
| ➡️ Verbindungslinie | Farbe je nach Ergebnis | Gestrichelte Linie |

### 4. ⚡ Performance Optimierung
- Maximal die letzten 50 Trades zeichnen
- Ältere Punkte nicht rendern um Browser Überlastung zu vermeiden
- Dynamische Limitierung je nach Zeitbereich

### 5. 🛠️ Zusatz Features:
- Tooltips beim Mouseover über Markierungen mit genauen Preisen und Zeiten
- Farbliche Hervorhebung der Trade Dauer
- Option alle Trades ausblenden

---

## 📊 Offene Punkte für später:
1.  Threshold Schieberegler auf der Oberfläche
2.  Live Signal Anzeige
3.  Telegram / E-Mail Benachrichtigungen
4.  Multi Symbol Support
5.  Portfolio Tracking

---

## ✅ Nächste Schritte:
Starte die neue Session und wir implementieren die Chart Markierungen sauber auf die aktuelle Version der Lightweight Charts API.
