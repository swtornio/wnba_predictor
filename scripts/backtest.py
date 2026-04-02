import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import argparse
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error
from config import DB_PATH, TABLE_NAME
from ratings import compute_srs, compute_rest_days_for_training, get_rest_days


def setup_db(conn):
    """Create predictions table if needed and add source column if absent."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            date TEXT,
            home_team TEXT,
            away_team TEXT,
            predicted_home_score INTEGER,
            predicted_away_score INTEGER,
            predicted_diff REAL,
            win_probability REAL,
            conf_low REAL,
            conf_high REAL,
            source TEXT,
            UNIQUE(date, home_team, away_team)
        )
    """)
    try:
        conn.execute("ALTER TABLE predictions ADD COLUMN source TEXT")
    except Exception:
        pass  # column already exists
    conn.commit()


def train_model(prior_games, srs):
    """Train Ridge on SRS + rest day features. srs is a dict of team -> rating."""
    training = compute_rest_days_for_training(prior_games)
    X = pd.DataFrame({
        "home_srs": training["home_team"].map(lambda t: srs.get(t, 0.0)),
        "away_srs": training["away_team"].map(lambda t: srs.get(t, 0.0)),
        "home_rest_days": training["home_rest_days"],
        "away_rest_days": training["away_rest_days"],
    })
    y = training["home_score"] - training["away_score"]
    model = Ridge()
    model.fit(X, y)
    y_pred = model.predict(X)
    residual_std = max(np.sqrt(mean_squared_error(y, y_pred)), 1.0)
    return model, residual_std


def get_recent_form(games_df, team, n=5):
    mask = (games_df["home_team"] == team) | (games_df["away_team"] == team)
    return games_df[mask].sort_values("date", ascending=False).head(n)


def predict_game(model, residual_std, prior_games, home, away, predict_date,
                 home_srs, away_srs, home_rest, away_rest, std_multiplier, ci_low, ci_high):
    recent_home = get_recent_form(prior_games, home)
    recent_away = get_recent_form(prior_games, away)

    if recent_home.empty:
        return None, f"no prior form for {home}"
    if recent_away.empty:
        return None, f"no prior form for {away}"

    features = pd.DataFrame(
        [[home_srs, away_srs, home_rest, away_rest]],
        columns=["home_srs", "away_srs", "home_rest_days", "away_rest_days"]
    )
    diff = model.predict(features)[0]

    home_off = recent_home["home_score"].mean()
    home_def = recent_home["away_score"].mean()
    away_off = recent_away["away_score"].mean()
    away_def = recent_away["home_score"].mean()
    expected_total = (home_off + away_def + away_off + home_def) / 2

    predicted_home = round((expected_total + diff) / 2)
    predicted_away = round((expected_total - diff) / 2)

    samples = np.random.normal(diff, residual_std * std_multiplier, size=10000)
    win_prob = (samples > 0).mean()
    conf_low_val = np.percentile(samples, ci_low)
    conf_high_val = np.percentile(samples, ci_high)

    return (predict_date, home, away, predicted_home, predicted_away,
            diff, win_prob, conf_low_val, conf_high_val), None


def get_team_biases(conn, before_date, prediction_date, decay_days):
    """Compute per-team prediction bias using only backtest predictions before before_date.

    Uses prediction_date (not today) as the decay reference to avoid lookahead.
    """
    query = """
        SELECT
            p.date,
            p.home_team,
            p.away_team,
            p.predicted_diff,
            g.home_score,
            g.away_score
        FROM predictions p
        JOIN games g USING (date, home_team, away_team)
        WHERE p.date < ?
          AND p.source = 'backtest'
          AND g.home_score IS NOT NULL
          AND g.away_score IS NOT NULL
    """
    df = pd.read_sql(query, conn, params=(before_date,))
    if df.empty:
        return {}

    df["date"] = pd.to_datetime(df["date"])
    df["days_ago"] = (prediction_date - df["date"]).dt.days
    df["decay_weight"] = np.exp(-df["days_ago"] / decay_days)

    home_resid = df.copy()
    home_resid["team"] = home_resid["home_team"]
    home_resid["residual"] = home_resid["predicted_diff"] - (home_resid["home_score"] - home_resid["away_score"])

    away_resid = df.copy()
    away_resid["team"] = away_resid["away_team"]
    away_resid["residual"] = (-away_resid["predicted_diff"]) - (away_resid["away_score"] - away_resid["home_score"])

    combined = pd.concat([
        home_resid[["team", "residual", "decay_weight"]],
        away_resid[["team", "residual", "decay_weight"]],
    ])

    grouped = combined.groupby("team")[["residual", "decay_weight"]]
    return grouped.apply(lambda g: np.average(g["residual"], weights=g["decay_weight"])).to_dict()


def predict_game_bias(model, residual_std, prior_games, home, away, predict_date,
                      home_srs, away_srs, home_rest, away_rest, team_biases,
                      std_multiplier, ci_low, ci_high):
    recent_home = get_recent_form(prior_games, home)
    recent_away = get_recent_form(prior_games, away)

    if recent_home.empty:
        return None, f"no prior form for {home}"
    if recent_away.empty:
        return None, f"no prior form for {away}"

    features = pd.DataFrame(
        [[home_srs, away_srs, home_rest, away_rest]],
        columns=["home_srs", "away_srs", "home_rest_days", "away_rest_days"]
    )
    diff = model.predict(features)[0]

    home_bias = team_biases.get(home, 0)
    away_bias = team_biases.get(away, 0)
    diff -= (home_bias - away_bias)

    home_off = recent_home["home_score"].mean()
    home_def = recent_home["away_score"].mean()
    away_off = recent_away["away_score"].mean()
    away_def = recent_away["home_score"].mean()
    expected_total = (home_off + away_def + away_off + home_def) / 2

    predicted_home = round((expected_total + diff) / 2)
    predicted_away = round((expected_total - diff) / 2)

    samples = np.random.normal(diff, residual_std * std_multiplier, size=10000)
    win_prob = (samples > 0).mean()
    conf_low_val = np.percentile(samples, ci_low)
    conf_high_val = np.percentile(samples, ci_high)

    return (predict_date, home, away, predicted_home, predicted_away,
            diff, win_prob, conf_low_val, conf_high_val), None


def run_backtest(conn, all_games, mode, min_history, start_date, end_date,
                 std_multiplier, ci_low, ci_high, decay_days, dry_run):
    dates = sorted(all_games["date"].dt.date.unique())

    if start_date:
        dates = [d for d in dates if d >= start_date]
    if end_date:
        dates = [d for d in dates if d <= end_date]

    total_predicted = 0
    total_skipped_form = 0
    total_written = 0
    total_ignored = 0

    for date in dates:
        ts = pd.Timestamp(date)
        prior_games = all_games[all_games["date"] < ts].copy()

        if len(prior_games) < min_history:
            print(f"[{date}] Skipping — only {len(prior_games)} prior games (min: {min_history})")
            continue

        day_games = all_games[all_games["date"] == ts]

        # Compute SRS on current-season prior games only (no cross-season bleed)
        season_prior = prior_games[prior_games["date"].dt.year == ts.year]
        srs = compute_srs(season_prior)
        model, residual_std = train_model(prior_games, srs)

        team_biases = {}
        if mode == "bias":
            team_biases = get_team_biases(conn, str(date), ts, decay_days)

        results = []
        skipped = []

        for _, row in day_games.iterrows():
            home, away = row["home_team"], row["away_team"]
            home_srs = srs.get(home, 0.0)
            away_srs = srs.get(away, 0.0)
            home_rest = get_rest_days(prior_games, home, ts)
            away_rest = get_rest_days(prior_games, away, ts)

            if mode == "bias":
                result, err = predict_game_bias(
                    model, residual_std, prior_games, home, away, str(date),
                    home_srs, away_srs, home_rest, away_rest, team_biases,
                    std_multiplier, ci_low, ci_high
                )
            else:
                result, err = predict_game(
                    model, residual_std, prior_games, home, away, str(date),
                    home_srs, away_srs, home_rest, away_rest, std_multiplier, ci_low, ci_high
                )

            if err:
                skipped.append(f"{away} @ {home} ({err})")
            else:
                results.append(result)

        for s in skipped:
            print(f"[{date}] Skipped: {s}")

        written = 0
        ignored = 0
        if not dry_run and results:
            for r in results:
                cursor = conn.execute("""
                    INSERT OR IGNORE INTO predictions
                        (date, home_team, away_team, predicted_home_score, predicted_away_score,
                         predicted_diff, win_probability, conf_low, conf_high, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'backtest')
                """, r)
                if cursor.rowcount == 1:
                    written += 1
                else:
                    ignored += 1
            conn.commit()

        total_predicted += len(results)
        total_skipped_form += len(skipped)
        total_written += written
        total_ignored += ignored

        print(f"[{date}] {len(results)} predicted, {len(skipped)} skipped"
              + (f", {written} written, {ignored} already exist" if not dry_run else " (dry run)")
              + f" — {len(prior_games)} prior games")

    print(f"\nDone. {total_predicted} predictions, {total_skipped_form} skipped (no form).")
    if not dry_run:
        print(f"DB: {total_written} written, {total_ignored} already existed.")


def main():
    parser = argparse.ArgumentParser(description="Backtest WNBA predictions against historical data.")
    parser.add_argument("--mode", choices=["base", "bias"], default="base",
                        help="base: Ridge only; bias: Ridge + bias correction (default: base)")
    parser.add_argument("--min-history", type=int, default=30,
                        help="Minimum prior games required before predicting (default: 30)")
    parser.add_argument("--start-date", type=str, default=None,
                        help="Only predict on or after this date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default=None,
                        help="Only predict on or before this date (YYYY-MM-DD)")
    parser.add_argument("--std-multiplier", type=float, default=1.0,
                        help="CI width multiplier (default: 1.0)")
    parser.add_argument("--ci", nargs=2, type=float, default=[5, 95],
                        help="Confidence interval percentiles (default: 5 95)")
    parser.add_argument("--decay-days", type=int, default=30,
                        help="Bias decay half-life in days; only used with --mode bias (default: 30)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run prediction logic but do not write to the database")
    args = parser.parse_args()

    start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date() if args.start_date else None
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date() if args.end_date else None

    conn = sqlite3.connect(DB_PATH)
    setup_db(conn)

    all_games = pd.read_sql(
        f"SELECT DISTINCT date, home_team, away_team, home_score, away_score FROM {TABLE_NAME} "
        f"WHERE home_score IS NOT NULL AND away_score IS NOT NULL",
        conn
    )
    all_games["date"] = pd.to_datetime(all_games["date"])

    print(f"Loaded {len(all_games)} games. Mode: {args.mode}. Dry run: {args.dry_run}\n")

    run_backtest(
        conn=conn,
        all_games=all_games,
        mode=args.mode,
        min_history=args.min_history,
        start_date=start_date,
        end_date=end_date,
        std_multiplier=args.std_multiplier,
        ci_low=args.ci[0],
        ci_high=args.ci[1],
        decay_days=args.decay_days,
        dry_run=args.dry_run,
    )

    conn.close()


if __name__ == "__main__":
    main()
