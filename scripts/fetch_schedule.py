import os
import sys
import sqlite3
import requests
from datetime import datetime, timedelta
from dateutil import parser
import pytz

# Load config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import DB_PATH, DATA_DIR

os.makedirs(DATA_DIR, exist_ok=True)

LOCAL_TZ = pytz.timezone("US/Central")  # adjust if needed

def create_schedule_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            home_team TEXT,
            away_team TEXT,
            game_time TEXT,
            game_time_local TEXT,
            source TEXT,
            UNIQUE(date, home_team, away_team)
        );
    """)
    conn.commit()
    conn.close()

def fetch_schedule_for_date(target_date):
    date_str = target_date.strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates={date_str}"
    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"Failed to fetch for {date_str}")
        return []

    games = []
    data = resp.json()
    for event in data.get("events", []):
        competition = event["competitions"][0]
        competitors = competition["competitors"]

        home = next(c for c in competitors if c["homeAway"] == "home")
        away = next(c for c in competitors if c["homeAway"] == "away")

        # Time conversion
        game_datetime_utc = parser.parse(competition["date"])
        game_datetime_local = game_datetime_utc.astimezone(LOCAL_TZ)
        local_date = game_datetime_local.date()

        games.append({
            "date": str(local_date),
            "home_team": home["team"]["displayName"],
            "away_team": away["team"]["displayName"],
            "game_time": game_datetime_utc.isoformat(),
            "game_time_local": game_datetime_local.isoformat(),
            "source": "espn"
        })
    return games

def insert_schedule(games):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for game in games:
        try:
            c.execute("""
                INSERT OR IGNORE INTO schedule (date, home_team, away_team, game_time, game_time_local, source)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                game["date"], game["home_team"], game["away_team"],
                game["game_time"], game["game_time_local"], game["source"]
            ))
        except Exception as e:
            print(f"Error inserting game: {game} — {e}")
    conn.commit()
    conn.close()

def main(start_date, days=90):
    create_schedule_table()
    for i in range(days):
        date = start_date + timedelta(days=i)
        print(f"Fetching {date.date()}...")
        games = fetch_schedule_for_date(date)
        insert_schedule(games)

if __name__ == "__main__":
    start = datetime.today()
    main(start_date=start, days=90)
