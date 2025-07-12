import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
import sqlite3
import pandas as pd
import numpy as np
from config import DB_PATH

def evaluate_predictions():
    conn = sqlite3.connect(DB_PATH)

    # Join actual results with predictions
    query = """
    SELECT 
        g.date,
        g.home_team,
        g.away_team,
        g.home_score,
        g.away_score,
        p.predicted_home_score,
        p.predicted_away_score,
        p.predicted_diff,
        p.win_probability
    FROM games g
    JOIN predictions p
    ON g.date = p.date
       AND g.home_team = p.home_team
       AND g.away_team = p.away_team
    WHERE g.home_score IS NOT NULL AND g.away_score IS NOT NULL
    ORDER BY g.date DESC
    """
    df = pd.read_sql(query, conn)

    # Calculate prediction errors
    df["actual_diff"] = df["home_score"] - df["away_score"]
    df["error_diff"] = df["predicted_diff"] - df["actual_diff"]
    df["error_home"] = df["predicted_home_score"] - df["home_score"]
    df["error_away"] = df["predicted_away_score"] - df["away_score"]
    df["predicted_winner"] = np.where(df["predicted_diff"] >= 0, df["home_team"], df["away_team"])
    df["actual_winner"] = np.where(df["actual_diff"] >= 0, df["home_team"], df["away_team"])
    df["correct"] = df["predicted_winner"] == df["actual_winner"]

    summary = {
        "Total games evaluated": len(df),
        "Accuracy (winner)": df["correct"].mean(),
        "Avg error (home score)": df["error_home"].mean(),
        "Avg error (away score)": df["error_away"].mean(),
        "Avg error (score diff)": df["error_diff"].mean(),
        "RMSE (score diff)": np.sqrt(np.mean(df["error_diff"]**2)),
    }

    print("📊 Evaluation Summary:")
    for key, value in summary.items():
        print(f"{key}: {value:.4f}" if isinstance(value, float) else f"{key}: {value}")

    conn.close()

if __name__ == "__main__":
    evaluate_predictions()
