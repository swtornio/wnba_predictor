# 🏀 WNBA Game Predictor

A Python-based system to forecast WNBA game outcomes using historical results, upcoming schedules, and machine learning. It includes score predictions, win probabilities, confidence intervals, and a bias-correction engine that learns from past errors.

---

## 📦 Project Structure

```
wnba-predictor/
├── config.py                  # Shared DB config
├── data/                      # Stores the games.db (ignored in .gitignore)
├── notebooks/
│   └── evaluate_predictions.ipynb  # Track model performance over time
├── scripts/
│   ├── fetch_data.py          # Daily updater for latest scores
│   ├── fetch_schedule.py      # One-time or periodic fetch of full schedule
│   ├── fetch_historical.py    # One-time importer for past seasons
│   ├── predict.py             # Main prediction script
│   └── predict_bias.py        # Bias-corrected prediction script
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 🛠 Setup

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## 📋 One-Time Data Import

```bash
python scripts/fetch_historical.py    # Load past results
python scripts/fetch_schedule.py      # Load schedule for the season
```

---

## 🔁 Daily Update

```bash
python scripts/fetch_data.py          # Fetch recent results and store
```

---

## 🔮 Making Predictions

### Without Bias Correction
```bash
python scripts/predict.py 2025-07-06
```

### With Bias Correction (after real results are available)
```bash
python scripts/predict_bias.py 2025-07-06
```

---

## ⚙️ CLI Options

| Option               | Description                                                | Example                     |
|----------------------|------------------------------------------------------------|-----------------------------|
| `--std-multiplier`   | Controls CI width (spread of simulated diffs)              | `--std-multiplier 1.2`      |
| `--ci LOW HIGH`      | Confidence interval bounds (e.g., `--ci 1 99`)             | `--ci 5 95`                 |
| `--decay-days`       | Days of historical decay to weight bias correction         | `--decay-days 30`          |

---

## 📊 Evaluation

To analyze prediction performance:

```bash
jupyter notebook notebooks/evaluate_predictions.ipynb
```

---

## 🔭 Future Improvements

- ELO or rolling performance ratings
- Alternate ML models (e.g. ensemble or XGBoost)
- Web-based dashboard
- Playoff logic & game re-fetching

---

## 👤 Author

vibe coded



## Utility Scripts


If games get rescheduled
```bash
python scripts/clear_schedule.py   # Deletes future games only
python scripts/fetch_schedule.py   # Re-adds corrected games

```

Sample Run
```bash
.venvdanny@Dannys-MacBook-Pro v2 % python scripts/predict.py 2025-07-05 

Scheduled games:
         date       home_team               away_team
0  2025-07-05   Indiana Fever      Los Angeles Sparks
1  2025-07-05  Minnesota Lynx  Golden State Valkyries

Los Angeles Sparks @ Indiana Fever on 2025-07-05
Prediction: Indiana Fever 87 - 73 Los Angeles Sparks
Projected winner: Indiana Fever (diff = 13.06)
Win probability: 81.4%
95% CI for score diff: -15.4 to 40.9

Golden State Valkyries @ Minnesota Lynx on 2025-07-05
Prediction: Minnesota Lynx 86 - 74 Golden State Valkyries
Projected winner: Minnesota Lynx (diff = 11.05)
Win probability: 79.0%
95% CI for score diff: -16.3 to 39.9
```

##
SQL

View Existing Predictions
```bash
SELECT 
  date, 
  home_team, 
  away_team, 
  predicted_home_score, 
  predicted_away_score, 
  predicted_diff, 
  win_probability, 
  conf_low, 
  conf_high
FROM predictions
ORDER BY date DESC
LIMIT 10;
```

View Most Recent Games
```bash
SELECT date, home_team, away_team, home_score, away_score
FROM games
WHERE home_score IS NOT NULL
ORDER BY date DESC
LIMIT 10;
```

View Upcoming Games
```bash
SELECT date, home_team, away_team
FROM schedule
WHERE date BETWEEN date('now') AND date('now', '+1 day')
ORDER BY date ASC;
```