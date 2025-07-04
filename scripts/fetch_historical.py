import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import DB_PATH, DATA_DIR
import sqlite3
import pandas as pd
import requests
from bs4 import BeautifulSoup
from time import sleep
from datetime import datetime

# Ensure the data directory exists

from config import DB_PATH, DATA_DIR
os.makedirs(DATA_DIR, exist_ok=True)


DB_PATH = os.path.join(DATA_DIR, "games.db")
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

def parse_game_row(row):
    try:
        date = row.find("th", {"data-stat": "date_game"}).text.strip()
        date = datetime.strptime(date, "%a, %b %d, %Y").date()

        teams = row.find_all("td", {"data-stat": "team_name"})
        if len(teams) != 2:
            return None

        away_team = teams[0].text.strip()
        home_team = teams[1].text.strip()

        scores = row.find_all("td", {"data-stat": "pts"})
        if len(scores) != 2:
            return None

        away_score = int(scores[0].text.strip())
        home_score = int(scores[1].text.strip())

        return {
            "date": str(date),
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
            "source": "basketball_reference"
        }
    except:
        return None

def fetch_season_games(season):
    print(f"Fetching {season} season...")
    url = f"https://www.basketball-reference.com/wnba/years/{season}_games.html"
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to fetch {url}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    tables = soup.find_all("table")

    games = []
    for table in tables:
        rows = table.find("tbody").find_all("tr")
        for row in rows:
            if "class" in row.attrs and "thead" in row["class"]:
                continue  # Skip subheaders
            game = parse_game_row(row)
            if game:
                games.append(game)
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
            print(f"Error inserting game: {game} – {e}")
    conn.commit()
    conn.close()

def main(start_year=2018, end_year=2024):
    create_table()
    for season in range(start_year, end_year + 1):
        games = fetch_season_games(season)
        insert_games(games)
        sleep(2)  # Be polite to the server

if __name__ == "__main__":
    main()
