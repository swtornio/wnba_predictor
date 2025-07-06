import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
import requests
import sqlite3
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from config import DB_PATH, TABLE_NAME

def fetch_espn_scoreboard():
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def parse_game(game):
    home_team = game["competitions"][0]["competitors"][0]
    away_team = game["competitions"][0]["competitors"][1]
    if home_team["homeAway"] == "away":
        home_team, away_team = away_team, home_team

    home_name = home_team["team"]["displayName"]
    away_name = away_team["team"]["displayName"]

    home_score = int(home_team["score"]) if home_team["score"] else None
    away_score = int(away_team["score"]) if away_team["score"] else None

    start_time = datetime.fromisoformat(game["date"]).astimezone(ZoneInfo("America/Chicago"))
    date_str = start_time.strftime("%Y-%m-%d")

    return date_str, home_name, away_name, home_score, away_score

def update_or_insert_game(cursor, date, home_team, away_team, home_score, away_score):
    cursor.execute("""
        SELECT home_score, away_score
        FROM games
        WHERE date = ? AND home_team = ? AND away_team = ?
    """, (date, home_team, away_team))
    row = cursor.fetchone()

    # if row:
    #     if (row[0] is None or row[1] is None) and (home_score is not None and away_score is not None):
    #         cursor.execute("""
    #             UPDATE games
    #             SET home_score = ?, away_score = ?
    #             WHERE date = ? AND home_team = ? AND away_team = ?
    #         """, (home_score, away_score, date, home_team, away_team))
    # else:
    #     cursor.execute("""
    #         INSERT INTO games (date, home_team, away_team, home_score, away_score)
    #         VALUES (?, ?, ?, ?, ?)
    #     """, (date, home_team, away_team, home_score, away_score))

    # If there's no row, insert
    if not row:
        cursor.execute("""
            INSERT INTO games (date, home_team, away_team, home_score, away_score)
            VALUES (?, ?, ?, ?, ?)
        """, (date, home_team, away_team, home_score, away_score))

    # If the row exists and the new score is higher or previously zero, update
    elif (
        (row[0] is None or row[1] is None)
        or (home_score is not None and away_score is not None and (row[0] == 0 and row[1] == 0))
        or (home_score != row[0] or away_score != row[1])
    ):
        cursor.execute("""
            UPDATE games
            SET home_score = ?, away_score = ?
            WHERE date = ? AND home_team = ? AND away_team = ?
        """, (home_score, away_score, date, home_team, away_team))

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        date TEXT,
        home_team TEXT,
        away_team TEXT,
        home_score INTEGER,
        away_score INTEGER,
        PRIMARY KEY (date, home_team, away_team)
    )""")
    conn.commit()

    data = fetch_espn_scoreboard()
    games = data.get("events", [])

    for game_data in games:
        try:
            date, home_team, away_team, home_score, away_score = parse_game(game_data)
            update_or_insert_game(cursor, date, home_team, away_team, home_score, away_score)
        except Exception as e:
            print(f"Failed to parse or insert game: {e}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
