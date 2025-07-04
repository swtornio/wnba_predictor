import sys
import os
import argparse
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import mean_squared_error

# Load shared config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import DB_PATH

# Configuration
SIM_STD_MULTIPLIER = 1.0     # Adjust for tighter/wider confidence intervals
CI_PERCENTILES = [2.5, 97.5]  # 95% CI

# Model pipeline
model = Pipeline([
    ("scaler", StandardScaler()),
    ("reg", Ridge(alpha=1.0))
])

def get_historical_data(conn):
    df = pd.read_sql("SELECT * FROM games", conn, parse_dates=["date"])
    df["score_diff"] = df["home_score"] - df["away_score"]
    return df

def calculate_elo(df):
    ratings = {team: 1500 for team in pd.concat([df["home_team"], df["away_team"]]).unique()}
    K = 20
    for _, game in df.sort_values("date").iterrows():
        home, away = game["home_team"], game["away_team"]
        hs, as_ = game["home_score"], game["away_score"]
        ra, rb = ratings[home], ratings[away]
        ea = 1 / (1 + 10 ** ((rb - ra) / 400))
        result = 0.5 + (hs - as_) / (abs(hs - as_) + 3)
        ratings[home] += K * (result - ea)
        ratings[away] += K * ((1 - result) - (1 - ea))
    return ratings

def compute_features(df, target_games):
    ratings = calculate_elo(df)

    def team_form(team, date, is_home):
        if team not in df["home_team"].values and team not in df["away_team"].values:
            return 0
        games = df[
            ((df["home_team"] == team) & is_home) |
            ((df["away_team"] == team) & (not is_home))
        ]
        games = games[games["date"] < date].sort_values("date").tail(5)
        if games.empty:
            return 0
        return games["score_diff"].mean() if is_home else -games["score_diff"].mean()

    def rest_days(team, date):
        if team not in df["home_team"].values and team not in df["away_team"].values:
            return 7
        team_games = df[(df["home_team"] == team) | (df["away_team"] == team)]
        past_games = team_games[team_games["date"] < date]
        if past_games.empty:
            return 7
        last_date = past_games["date"].max()
        return min((date - last_date).days, 14)

    features = []
    for _, game in target_games.iterrows():
        date = pd.to_datetime(game["date"])
        home = game["home_team"]
        away = game["away_team"]
        row = {
            "home_rating": ratings.get(home, 1500),
            "away_rating": ratings.get(away, 1500),
            "home_form": team_form(home, date, is_home=True),
            "away_form": team_form(away, date, is_home=False),
            "home_rest": rest_days(home, date),
            "away_rest": rest_days(away, date)
        }
        features.append(row)

    X = pd.DataFrame(features)
    X.fillna(0, inplace=True)
    return X

def create_predictions_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            home_team TEXT,
            away_team TEXT,
            predicted_home_score INTEGER,
            predicted_away_score INTEGER,
            predicted_diff REAL,
            win_probability REAL,
            conf_low REAL,
            conf_high REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, home_team, away_team)
        );
    """)
    conn.commit()

def main(target_date_str):
    target_date = pd.to_datetime(target_date_str).date()
    conn = sqlite3.connect(DB_PATH)
    create_predictions_table(conn)

    df = get_historical_data(conn)

    schedule = pd.read_sql("SELECT * FROM schedule WHERE date = ?", conn, params=(str(target_date),))
    if schedule.empty:
        print(f"No scheduled games found for {target_date}")
        return

    print("\nScheduled games:")
    print(schedule[["date", "home_team", "away_team"]])

    # Train model
    X_train = compute_features(df, df)
    y_train = df["score_diff"].values
    model.fit(X_train, y_train)

    # Residual std for confidence intervals
    y_pred_train = model.predict(X_train)
    residual_std = np.sqrt(mean_squared_error(y_train, y_pred_train))

    # Predict
    X_test = compute_features(df, schedule)
    preds = model.predict(X_test)

    for i, row in enumerate(schedule.itertuples()):
        diff = preds[i]

        # Monte Carlo simulation
        samples = np.random.normal(loc=diff, scale=residual_std * SIM_STD_MULTIPLIER, size=10000)
        win_prob = (samples > 0).mean()
        conf_int = np.percentile(samples, CI_PERCENTILES)

        home_score = round(max(diff / 2 + 80, 50))
        away_score = round(max(-diff / 2 + 80, 50))
        winner = row.home_team if diff > 0 else row.away_team

        print(f"\n{row.away_team} @ {row.home_team} on {row.date}")
        print(f"Prediction: {row.home_team} {home_score} - {away_score} {row.away_team}")
        print(f"Projected winner: {winner} (diff = {diff:.2f})")
        print(f"Win probability: {win_prob:.1%}")
        print(f"{int(CI_PERCENTILES[1] - CI_PERCENTILES[0])}% CI for score diff: {conf_int[0]:.1f} to {conf_int[1]:.1f}")

        # Store prediction
        try:
            conn.execute("""
                INSERT OR REPLACE INTO predictions (
                    date, home_team, away_team,
                    predicted_home_score, predicted_away_score,
                    predicted_diff, win_probability,
                    conf_low, conf_high,
                    ci_lower_bound, ci_upper_bound, std_multiplier
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row.date, row.home_team, row.away_team,
                home_score, away_score, diff,
                win_prob, conf_int[0], conf_int[1],
                CI_PERCENTILES[0], CI_PERCENTILES[1], SIM_STD_MULTIPLIER
            ))

            conn.commit()
        except Exception as e:
            print(f"Failed to insert prediction: {e}")

    conn.close()

import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WNBA game prediction with confidence intervals.")
    parser.add_argument("date", help="Date of games to predict (YYYY-MM-DD)")
    parser.add_argument("--std-multiplier", type=float, default=1.0,
                        help="Standard deviation multiplier for confidence interval (default: 1.0)")
    parser.add_argument("--ci", type=float, nargs=2, default=[2.5, 97.5],
                        help="Confidence interval bounds as two percentiles (default: 2.5 97.5 for 95%% CI)")

    args = parser.parse_args()

    SIM_STD_MULTIPLIER = args.std_multiplier
    CI_PERCENTILES = args.ci

    main(args.date)

