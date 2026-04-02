import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import sqlite3
import pandas as pd
from time import sleep
from nba_api.stats.endpoints import LeagueGameFinder
from config import DB_PATH, DATA_DIR, TABLE_NAME

os.makedirs(DATA_DIR, exist_ok=True)

SOURCE = "stats_wnba"
WNBA_LEAGUE_ID = "10"


def create_table(conn):
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            home_team TEXT,
            away_team TEXT,
            home_score INTEGER,
            away_score INTEGER,
            source TEXT,
            UNIQUE(date, home_team, away_team)
        )
    """)
    conn.commit()


def fetch_season(season_year):
    """Fetch all completed games for a WNBA season.

    season_year is an int, e.g. 2018.
    Returns a DataFrame with columns: date, home_team, away_team, home_score, away_score.
    """
    print(f"Fetching {season_year} season...")
    finder = LeagueGameFinder(
        league_id_nullable=WNBA_LEAGUE_ID,
        season_nullable=str(season_year),
        player_or_team_abbreviation="T",
    )
    df = finder.get_data_frames()[0]

    if df.empty:
        print(f"  No data returned for {season_year}")
        return pd.DataFrame()

    # Keep only completed games (WL is null for unplayed games)
    df = df[df["WL"].notna()].copy()

    # Identify home vs away from MATCHUP field:
    #   "TEAM vs. OPP"  → home game for TEAM
    #   "TEAM @ OPP"    → away game for TEAM
    df["is_home"] = df["MATCHUP"].str.contains(" vs\\. ")

    home = df[df["is_home"]].copy()
    away = df[~df["is_home"]].copy()

    # Merge on GAME_ID to get both sides in one row
    merged = home.merge(
        away[["GAME_ID", "TEAM_NAME", "PTS"]],
        on="GAME_ID",
        suffixes=("_home", "_away"),
    )

    merged = merged.rename(columns={
        "GAME_DATE": "date",
        "TEAM_NAME_home": "home_team",
        "TEAM_NAME_away": "away_team",
        "PTS_home": "home_score",
        "PTS_away": "away_score",
    })

    return merged[["date", "home_team", "away_team", "home_score", "away_score"]]


def insert_games(conn, games_df):
    inserted = 0
    skipped = 0
    for _, row in games_df.iterrows():
        try:
            cursor = conn.execute(f"""
                INSERT OR IGNORE INTO {TABLE_NAME}
                    (date, home_team, away_team, home_score, away_score, source)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                row["date"], row["home_team"], row["away_team"],
                int(row["home_score"]), int(row["away_score"]),
                SOURCE,
            ))
            if cursor.rowcount == 1:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  Error inserting {row.to_dict()}: {e}")
    conn.commit()
    return inserted, skipped


def main(start_year=2018, end_year=2025):
    conn = sqlite3.connect(DB_PATH)
    create_table(conn)

    total_inserted = 0
    total_skipped = 0

    for year in range(start_year, end_year + 1):
        games = fetch_season(year)
        if games.empty:
            sleep(2)
            continue
        inserted, skipped = insert_games(conn, games)
        print(f"  {inserted} inserted, {skipped} skipped (already exist)")
        total_inserted += inserted
        total_skipped += skipped
        sleep(2)  # be polite to the API

    conn.close()
    print(f"\nDone. Total: {total_inserted} inserted, {total_skipped} skipped.")


if __name__ == "__main__":
    main()
