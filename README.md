# WNBA Game Predictor

A Python-based system to forecast WNBA game outcomes using historical results, upcoming schedules, and machine learning. Outputs score predictions, win probabilities, and confidence intervals. Includes a bias-correction engine that learns from past errors.

---

## Project Structure

```
wnba-predictor/
├── config.py
├── data/                          # SQLite database (gitignored)
├── notebooks/
│   └── evaluate_predictions.ipynb
├── scripts/
│   ├── ratings.py                 # SRS and rest-day feature computation (shared)
│   ├── fetch_historical_wnba.py   # One-time: import 2018–present via nba_api
│   ├── fetch_schedule.py          # One-time (per season): load schedule from ESPN
│   ├── clear_schedule.py          # Utility: delete future games (use before re-fetch)
│   ├── backfill_espn.py           # Utility: backfill results from ESPN
│   ├── fetch_data.py              # Utility: fetch today's results from ESPN
│   ├── predict.py                 # Predict games for a specific date (base model)
│   ├── predict_bias.py            # Predict with bias correction
│   ├── backtest.py                # Backtest predictions against historical data
│   ├── daily_update.py            # Daily driver: fetch results + predict upcoming games
│   └── evaluate_predictions.py   # Score prediction accuracy
├── requirements.txt
└── README.md
```

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## One-Time Data Import

Run once to populate the database with historical game results (2018–present) and the current season schedule:

```bash
python scripts/fetch_historical_wnba.py   # loads completed games via nba_api
python scripts/fetch_schedule.py          # loads upcoming schedule from ESPN (90 days)
```

Re-run `fetch_schedule.py` at the start of each new season once the schedule is published.

---

## Daily Usage

During the season, one command handles everything:

```bash
python scripts/daily_update.py
```

This will:
1. Fetch completed results from the last 3 days (ESPN)
2. Find any upcoming scheduled games without predictions
3. Run predictions for those dates automatically

If you've missed several days, increase the lookback window:

```bash
python scripts/daily_update.py --lookback 14
```

To use the bias-corrected model (recommended once enough predictions have accumulated):

```bash
python scripts/daily_update.py --mode bias
```

---

## Backtesting

Run against all historical data to evaluate model accuracy:

```bash
python scripts/backtest.py
```

Dry-run first to verify output without writing to the database:

```bash
python scripts/backtest.py --dry-run
```

Backtest a specific date range:

```bash
python scripts/backtest.py --start-date 2023-05-01 --end-date 2023-10-01
```

Bias-corrected backtest (requires base backtest rows to already exist):

```bash
python scripts/backtest.py --mode bias
```

---

## Evaluating Accuracy

```bash
python scripts/evaluate_predictions.py
```

Or open the notebook for a more detailed breakdown:

```bash
jupyter notebook notebooks/evaluate_predictions.ipynb
```

---

## CLI Options

### `daily_update.py`

| Option | Default | Description |
|---|---|---|
| `--lookback N` | `3` | Days of past results to fetch from ESPN |
| `--mode` | `base` | `base` or `bias` prediction model |
| `--dry-run` | off | Show what would run without writing predictions |

### `predict.py` / `predict_bias.py`

```bash
python scripts/predict.py 2026-07-04
python scripts/predict_bias.py 2026-07-04
```

| Option | Default | Description |
|---|---|---|
| `--std-multiplier` | `1.0` | Controls confidence interval width |
| `--ci LOW HIGH` | `5 95` | Confidence interval percentile bounds |
| `--decay-days N` | `30` | Bias decay half-life in days (`predict_bias.py` only) |

### `backtest.py`

| Option | Default | Description |
|---|---|---|
| `--mode` | `base` | `base` or `bias` |
| `--min-history N` | `30` | Minimum prior games before predicting |
| `--start-date` | first game | Backtest from this date |
| `--end-date` | last game | Backtest through this date |
| `--std-multiplier` | `1.0` | Controls confidence interval width |
| `--ci LOW HIGH` | `5 95` | Confidence interval percentile bounds |
| `--decay-days N` | `30` | Bias decay half-life (`--mode bias` only) |
| `--dry-run` | off | Run without writing to the database |

---

## Model Overview

The model uses **Simple Rating System (SRS)** ratings — opponent-adjusted point differentials — as its primary features, along with rest days for each team. A Ridge regression model predicts the expected score differential, which is used to derive:

- Predicted final score
- Win probability (via Monte Carlo simulation)
- Confidence interval on the score differential

SRS ratings reset each season and are computed only on games prior to the prediction date, ensuring no lookahead bias.

The bias-corrected variant (`predict_bias.py`, `--mode bias`) additionally learns each team's historical prediction error with exponential time decay, adjusting the raw prediction accordingly.

---

## Useful SQL Queries

**View recent predictions:**
```sql
SELECT date, home_team, away_team, predicted_home_score, predicted_away_score,
       predicted_diff, win_probability, conf_low, conf_high
FROM predictions
ORDER BY date DESC
LIMIT 10;
```

**View most recent completed games:**
```sql
SELECT date, home_team, away_team, home_score, away_score
FROM games
WHERE home_score IS NOT NULL
ORDER BY date DESC
LIMIT 10;
```

**View upcoming scheduled games:**
```sql
SELECT date, home_team, away_team
FROM schedule
WHERE date >= date('now')
ORDER BY date ASC;
```
