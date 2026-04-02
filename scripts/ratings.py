import numpy as np
import pandas as pd


def compute_srs(games_df, min_games=5, n_iter=100):
    """Compute Simple Rating System (SRS) ratings for each team.

    SRS is an opponent-adjusted point differential rating. A team rated +5
    is expected to beat an average team by 5 points on a neutral court.

    Args:
        games_df: DataFrame with columns home_team, away_team, home_score, away_score.
                  Should contain only completed games (no nulls in scores).
        min_games: Teams with fewer appearances get rating 0.0 (league average).
        n_iter:   Number of iterations for convergence (100 is sufficient).

    Returns:
        dict mapping team name -> SRS rating (float). League average = 0.0.
    """
    if games_df.empty:
        return {}

    teams = list(set(games_df["home_team"].tolist() + games_df["away_team"].tolist()))
    srs = {team: 0.0 for team in teams}

    # Count appearances and compute raw average margin per team
    game_counts = {team: 0 for team in teams}
    raw_margins = {team: [] for team in teams}

    for _, row in games_df.iterrows():
        home, away = row["home_team"], row["away_team"]
        margin = row["home_score"] - row["away_score"]
        raw_margins[home].append(margin)
        raw_margins[away].append(-margin)
        game_counts[home] += 1
        game_counts[away] += 1

    avg_margin = {team: np.mean(margins) if margins else 0.0
                  for team, margins in raw_margins.items()}

    # Build opponent list per team for fast iteration
    opponents = {team: [] for team in teams}
    for _, row in games_df.iterrows():
        opponents[row["home_team"]].append(row["away_team"])
        opponents[row["away_team"]].append(row["home_team"])

    # Iterative SRS solve: rating = avg_margin + avg(opponent ratings)
    for _ in range(n_iter):
        new_srs = {}
        for team in teams:
            if not opponents[team]:
                new_srs[team] = 0.0
                continue
            opp_avg = np.mean([srs[opp] for opp in opponents[team]])
            new_srs[team] = avg_margin[team] + opp_avg
        srs = new_srs

    # Zero-center so league average = 0.0
    league_avg = np.mean(list(srs.values()))
    srs = {team: rating - league_avg for team, rating in srs.items()}

    # Teams below the minimum game threshold revert to league average (0.0)
    for team, count in game_counts.items():
        if count < min_games:
            srs[team] = 0.0

    return srs


def compute_rest_days_for_training(games_df, default=7, max_days=14):
    """Add home_rest_days and away_rest_days columns to a games DataFrame.

    Computed chronologically, resetting at season boundaries so prior-season
    games do not bleed into a new season's rest calculation.

    Args:
        games_df: DataFrame with columns date, home_team, away_team.
                  date must be a datetime column.
        default:  Rest days assigned for a team's first game of a season.
        max_days: Cap to avoid outsized values from long breaks.

    Returns:
        A copy of games_df sorted by date with new columns added.
    """
    games = games_df.sort_values("date").reset_index(drop=True).copy()
    last_game = {}  # team -> (date, year)
    home_rest_list = []
    away_rest_list = []

    for _, row in games.iterrows():
        home, away = row["home_team"], row["away_team"]
        game_date = row["date"]
        game_year = game_date.year

        if home in last_game and last_game[home][1] == game_year:
            h_rest = min((game_date - last_game[home][0]).days, max_days)
        else:
            h_rest = default

        if away in last_game and last_game[away][1] == game_year:
            a_rest = min((game_date - last_game[away][0]).days, max_days)
        else:
            a_rest = default

        home_rest_list.append(h_rest)
        away_rest_list.append(a_rest)

        last_game[home] = (game_date, game_year)
        last_game[away] = (game_date, game_year)

    games["home_rest_days"] = home_rest_list
    games["away_rest_days"] = away_rest_list
    return games


def get_rest_days(prior_games, team, game_date, default=7, max_days=14):
    """Days since a team's last game in the current season, for live prediction.

    Args:
        prior_games: DataFrame of completed games before game_date.
        team:        Team name.
        game_date:   The prediction date as a pd.Timestamp.
        default:     Returned if the team has no prior games this season.
        max_days:    Cap on returned value.

    Returns:
        int: rest days, capped at max_days.
    """
    season_year = game_date.year
    team_games = prior_games[
        ((prior_games["home_team"] == team) | (prior_games["away_team"] == team)) &
        (prior_games["date"].dt.year == season_year)
    ]
    if team_games.empty:
        return default
    last_game_date = team_games["date"].max()
    return min((game_date - last_game_date).days, max_days)
