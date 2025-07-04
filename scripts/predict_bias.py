import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
import argparse
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error
from config import DB_PATH, TABLE_NAME

def get_team_biases_with_decay(conn, decay_days=30):
    query = '''
        SELECT
            date,
            home_team,
            away_team,
            predicted_diff,
            home_score,
            away_score
        FROM predictions
        JOIN games USING (date, home_team, away_team)
        WHERE home_score IS NOT NULL AND away_score IS NOT NULL
    '''
    df = pd.read_sql(query, conn)
    if df.empty:
        return {}

    df["date"] = pd.to_datetime(df["date"])
    df["days_ago"] = (datetime.today() - df["date"]).dt.days
    df["decay_weight"] = np.exp(-df["days_ago"] / decay_days)

    # Home residual
    home_resid = df.copy()
    home_resid["team"] = home_resid["home_team"]
    home_resid["residual"] = home_resid["predicted_diff"] - (home_resid["home_score"] - home_resid["away_score"])

    # Away residual
    away_resid = df.copy()
    away_resid["team"] = away_resid["away_team"]
    away_resid["residual"] = (home_resid["predicted_diff"] * -1) - (home_resid["away_score"] - home_resid["home_score"])

    combined = pd.concat([home_resid[["team", "residual", "decay_weight"]],
                          away_resid[["team", "residual", "decay_weight"]]])

    team_biases = combined.groupby("team").apply(
        lambda g: np.average(g["residual"], weights=g["decay_weight"])
    ).to_dict()

    return team_biases

def main(predict_date, std_multiplier=1.0, ci_low=5, ci_high=95, decay_days=30):
    conn = sqlite3.connect(DB_PATH)
    schedule = pd.read_sql("SELECT * FROM schedule WHERE date = ?", conn, params=(predict_date,))
    games = pd.read_sql(f"SELECT * FROM {TABLE_NAME}", conn)

    # Basic features
    games["date"] = pd.to_datetime(games["date"])
    schedule["date"] = pd.to_datetime(schedule["date"])
    X = games[["home_score", "away_score"]]
    y = games["home_score"] - games["away_score"]

    model = Ridge()
    model.fit(X, y)
    y_pred = model.predict(X)
    residual_std = np.sqrt(mean_squared_error(y, y_pred))

    team_biases = get_team_biases_with_decay(conn, decay_days=decay_days)

    results = []
    for _, row in schedule.iterrows():
        home = row["home_team"]
        away = row["away_team"]

        recent_home = games[(games["home_team"] == home) | (games["away_team"] == home)].sort_values("date", ascending=False).head(5)
        recent_away = games[(games["home_team"] == away) | (games["away_team"] == away)].sort_values("date", ascending=False).head(5)

        if len(recent_home) == 0 or len(recent_away) == 0:
            continue

        home_avg = recent_home["home_score"].mean()
        away_avg = recent_away["away_score"].mean()

        features = pd.DataFrame([[home_avg, away_avg]], columns=["home_score", "away_score"])

        diff = model.predict(features)[0]

        # Bias correction
        home_bias = team_biases.get(home, 0)
        away_bias = team_biases.get(away, 0)
        bias_correction = home_bias - away_bias
        diff -= bias_correction

        samples = np.random.normal(loc=diff, scale=residual_std * std_multiplier, size=10000)
        win_prob = (samples > 0).mean()
        conf_low = np.percentile(samples, ci_low)
        conf_high = np.percentile(samples, ci_high)

        predicted_home = round((100 + diff) / 2)
        predicted_away = 100 - predicted_home

        print(f"{away} @ {home} on {predict_date}")
        print(f"Prediction: {home} {predicted_home} - {predicted_away} {away}")
        print(f"Projected winner: {home if diff > 0 else away} (diff = {diff:.2f})")
        print(f"Win probability: {win_prob*100:.1f}%")
        print(f"{100 - ci_high}%–{ci_high}% CI for score diff: {conf_low:.1f} to {conf_high:.1f}\\n")

        results.append((predict_date, home, away, predicted_home, predicted_away, diff, win_prob, conf_low, conf_high))

    # Save results
    conn.executemany(
        "INSERT OR REPLACE INTO predictions (date, home_team, away_team, predicted_home_score, predicted_away_score, predicted_diff, win_probability, conf_low, conf_high) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        results,
    )
    conn.commit()
    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("date", help="Date of games to predict (YYYY-MM-DD)")
    parser.add_argument("--std-multiplier", type=float, default=1.0)
    parser.add_argument("--ci", nargs=2, type=float, default=[5, 95])
    parser.add_argument("--decay-days", type=int, default=30)
    args = parser.parse_args()

    main(
        args.date,
        std_multiplier=args.std_multiplier,
        ci_low=args.ci[0],
        ci_high=args.ci[1],
        decay_days=args.decay_days,
    )
