import sqlite3
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pandas as pd
from config import DB_PATH

def evaluate_predictions():
    conn = sqlite3.connect(DB_PATH)

    # Join predictions to actual games
    query = """
        SELECT
            p.date,
            p.home_team,
            p.away_team,
            p.predicted_home_score,
            p.predicted_away_score,
            p.predicted_diff,
            p.win_probability,
            g.home_score AS actual_home_score,
            g.away_score AS actual_away_score,
            (g.home_score - g.away_score) AS actual_diff
        FROM predictions p
        JOIN games g
            ON p.date = g.date
           AND p.home_team = g.home_team
           AND p.away_team = g.away_team
        WHERE g.home_score IS NOT NULL AND g.away_score IS NOT NULL
    """

    df = pd.read_sql(query, conn)
    if df.empty:
        print("No predictions matched with completed games yet.")
        return

    df["error"] = (df["predicted_diff"] - df["actual_diff"]).abs()
    df["winner_correct"] = (
        ((df["predicted_diff"] > 0) & (df["actual_diff"] > 0)) |
        ((df["predicted_diff"] < 0) & (df["actual_diff"] < 0))
    )

    print("\nRecent Predictions:")
    print(df[[
        "date", "away_team", "home_team",
        "predicted_home_score", "predicted_away_score",
        "actual_home_score", "actual_away_score",
        "predicted_diff", "actual_diff", "error", "winner_correct"
    ]].sort_values("date", ascending=False).to_string(index=False))

    print("\nEvaluation Summary:")
    print(f"Total evaluated games: {len(df)}")
    print(f"Mean Absolute Error (MAE): {df['error'].mean():.2f}")
    print(f"Median Absolute Error: {df['error'].median():.2f}")
    print(f"Correct winner prediction: {df['winner_correct'].mean():.1%}")

    conn.close()

if __name__ == "__main__":
    evaluate_predictions()
