import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import DB_PATH, DATA_DIR
import requests
import sqlite3
import pandas as pd
from datetime import datetime


TABLE_NAME = "games"

def create_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f'''
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
    ''')
    conn.commit()
    conn.close()

def fetch_espn_results():
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
    response = requests.get(url)
    games = response.json().get("events", [])

    results = []
    for game in games:
        try:
            date = game["date"][:10]
            competitors = game["competitions"][0]["competitors"]
            home = next(team for team in competitors if team["homeAway"] == "home")
            away = next(team for team in competitors if team["homeAway"] == "away")
            home_team = home["team"]["displayName"]
            away_team = away["team"]["displayName"]
            home_score = int(home["score"])
            away_score = int(away["score"])
            results.append((date, home_team, away_team, home_score, away_score, "espn"))
        except Exception as e:
            print(f"Error processing game: {e}")
    return results

def insert_games(games):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for game in games:
        try:
            c.execute(f'''
                INSERT OR IGNORE INTO {TABLE_NAME} 
                (date, home_team, away_team, home_score, away_score, source) 
                VALUES (?, ?, ?, ?, ?, ?);
            ''', game)
        except Exception as e:
            print(f"Insert error: {e}")
    conn.commit()
    conn.close()

def main():
    create_table()
    results = fetch_espn_results()
    insert_games(results)
    print(f"Inserted {len(results)} games.")

if __name__ == "__main__":
    main()
