import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.dirname(__file__))

import argparse
import sqlite3
import requests
import pandas as pd
from datetime import datetime, timedelta
from dateutil import parser as dateparser
import pytz

from config import DB_PATH, TABLE_NAME
import predict as predict_base
import predict_bias as predict_bias_mod

LOCAL_TZ = pytz.timezone("US/Central")


def fetch_espn_results(date):
    """Fetch completed game results from ESPN for a given date."""
    date_str = date.strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates={date_str}"
    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"  ESPN fetch failed for {date_str} (status {resp.status_code})")
        return []

    games = []
    for event in resp.json().get("events", []):
        competition = event.get("competitions", [])[0]
        if not competition.get("status", {}).get("type", {}).get("completed"):
            continue
        competitors = competition["competitors"]
        home = next(c for c in competitors if c["homeAway"] == "home")
        away = next(c for c in competitors if c["homeAway"] == "away")
        game_date = competition["date"][:10]
        games.append({
            "date": game_date,
            "home_team": home["team"]["displayName"],
            "away_team": away["team"]["displayName"],
            "home_score": int(home["score"]),
            "away_score": int(away["score"]),
        })
    return games


def insert_results(conn, games):
    """Insert completed results, updating score if a row already exists."""
    inserted = updated = skipped = 0
    for g in games:
        row = conn.execute(
            f"SELECT home_score, away_score FROM {TABLE_NAME} "
            "WHERE date = ? AND home_team = ? AND away_team = ?",
            (g["date"], g["home_team"], g["away_team"])
        ).fetchone()

        if row is None:
            conn.execute(
                f"INSERT INTO {TABLE_NAME} (date, home_team, away_team, home_score, away_score, source) "
                "VALUES (?, ?, ?, ?, ?, 'espn')",
                (g["date"], g["home_team"], g["away_team"], g["home_score"], g["away_score"])
            )
            inserted += 1
        elif row[0] != g["home_score"] or row[1] != g["away_score"]:
            conn.execute(
                f"UPDATE {TABLE_NAME} SET home_score = ?, away_score = ? "
                "WHERE date = ? AND home_team = ? AND away_team = ?",
                (g["home_score"], g["away_score"], g["date"], g["home_team"], g["away_team"])
            )
            updated += 1
        else:
            skipped += 1
    conn.commit()
    return inserted, updated, skipped


def fetch_recent_results(conn, lookback_days):
    """Pull completed results for the last N days from ESPN."""
    print(f"Fetching results for last {lookback_days} days...")
    total_inserted = total_updated = 0
    for i in range(lookback_days, 0, -1):
        date = datetime.today() - timedelta(days=i)
        games = fetch_espn_results(date)
        if games:
            inserted, updated, _ = insert_results(conn, games)
            total_inserted += inserted
            total_updated += updated
    print(f"  Results: {total_inserted} new, {total_updated} updated.\n")


def find_unpredicted_dates(conn):
    """Return scheduled dates from today onward that have no predictions."""
    today = datetime.today().strftime("%Y-%m-%d")
    query = """
        SELECT DISTINCT s.date
        FROM schedule s
        LEFT JOIN predictions p
            ON s.date = p.date
           AND s.home_team = p.home_team
           AND s.away_team = p.away_team
        WHERE s.date >= ?
          AND p.date IS NULL
        ORDER BY s.date ASC
    """
    rows = conn.execute(query, (today,)).fetchall()
    return [row[0] for row in rows]


def run_predictions(dates, mode, dry_run):
    """Run predictions for each date."""
    if not dates:
        print("No unpredicted upcoming games found.")
        return

    print(f"Running {mode} predictions for {len(dates)} date(s)...")
    for date_str in dates:
        print(f"  Predicting {date_str}...")
        if dry_run:
            print(f"    [dry run] Would predict {date_str}")
            continue
        try:
            if mode == "bias":
                predict_bias_mod.main(date_str)
            else:
                predict_base.main(date_str)
        except Exception as e:
            print(f"    Error predicting {date_str}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Fetch latest results and predict upcoming WNBA games.")
    parser.add_argument("--lookback", type=int, default=3,
                        help="Days of past results to fetch from ESPN (default: 3)")
    parser.add_argument("--mode", choices=["base", "bias"], default="base",
                        help="Prediction mode: base or bias-corrected (default: base)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without writing predictions")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)

    fetch_recent_results(conn, args.lookback)

    unpredicted = find_unpredicted_dates(conn)
    if unpredicted:
        print(f"Found {len(unpredicted)} unpredicted date(s): {unpredicted[0]} → {unpredicted[-1]}")
    conn.close()

    run_predictions(unpredicted, args.mode, args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
