import sys
import os
import sqlite3
import requests
from datetime import datetime, timedelta

# Setup shared path and config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import DB_PATH, DATA_DIR

# Make sure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

TABLE_NAME = "games"

def create_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            home_team TEXT,
            away_team TEXT,
            home_score INTEGER,
            away_score INTEGER,
            source TEXT,
            UNIQUE(date, home_team, away_team)
        );
    """)
    conn.commit()
    conn.close()

def fetch_espn_results(date):
    date_str = date.strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates={date_str}"
    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"Failed to fetch data for {date_str}")
        return []

    games = []
    data = resp.json()
    for event in data.get("events", []):
        competition = event.get("competitions", [])[0]
        if competition.get("status", {}).get("type", {}).get("completed") != True:
            continue  # skip future or in-progress games

        competitors = competition["competitors"]
        home = next(c for c in competitors if c["homeAway"] == "home")
        away = next(c for c in competitors if c["homeAway"] == "away")

        game_date = competition["date"][:10]
        home_team = home["team"]["displayName"]
        away_team = away["team"]["displayName"]
        home_score = int(home["score"])
        away_score = int(away["score"])

        games.append({
            "date": game_date,
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
            "source": "espn"
        })
    return games

def insert_games(games):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for game in games:
        try:
            c.execute(f"""
                INSERT OR IGNORE INTO {TABLE_NAME}
                (date, home_team, away_team, home_score, away_score, source)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                game["date"], game["home_team"], game["away_team"],
                game["home_score"], game["away_score"], game["source"]
            ))
        except Exception as e:
            print(f"Failed to insert: {game} — {e}")
    conn.commit()
    conn.close()

def backfill(days=90):
    create_table()
    for i in range(days):
        target_date = datetime.today() - timedelta(days=i)
        print(f"Fetching results for {target_date.date()}...")
        games = fetch_espn_results(target_date)
        insert_games(games)

if __name__ == "__main__":
    backfill(days=90)  # fetch last 90 days of games
