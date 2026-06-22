#!/usr/bin/env python3
"""
NBA Player Scraper - Basketball Reference
Scrapes each team's season pages (2000-2024) to build a per-team player database.
Outputs data.js in the format expected by the game.
"""

import requests
import json
import time
import logging
from bs4 import BeautifulSoup, Comment

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

TEAMS = {
    "Atlanta Hawks": "ATL",
    "Boston Celtics": "BOS",
    "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW",
    "Houston Rockets": "HOU",
    "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC",
    "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}

# Historical abbreviations (teams that relocated/renamed)
EXTRA_ABBRS = {
    "Brooklyn Nets": ["NJN"],       # New Jersey Nets
    "New Orleans Pelicans": ["NOH", "NOK"],  # Hornets/OK City Hornets
    "Oklahoma City Thunder": ["SEA"],  # Seattle SuperSonics
    "Washington Wizards": ["WSB"],   # Bullets
    "Charlotte Hornets": ["CHH"],    # Original Hornets (before Bobcats era)
    "Memphis Grizzlies": ["VAN"],    # Vancouver Grizzlies
}

START_YEAR = 2000
END_YEAR = 2025

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

session = requests.Session()
session.headers.update(HEADERS)


def fetch_page(url, retries=3):
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code == 429:
                wait = 30 * (attempt + 1)
                logger.warning(f"Rate limited — waiting {wait}s...")
                time.sleep(wait)
            elif resp.status_code == 404:
                return None
            else:
                logger.warning(f"HTTP {resp.status_code} for {url}")
                time.sleep(5)
        except Exception as e:
            logger.warning(f"Request error ({e}), attempt {attempt + 1}/{retries}")
            time.sleep(5)
    return None


def find_table(soup, table_id):
    """Find a table by id, including ones hidden inside HTML comments."""
    table = soup.find("table", id=table_id)
    if table:
        return table
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        if table_id in comment:
            inner = BeautifulSoup(comment, "html.parser")
            table = inner.find("table", id=table_id)
            if table:
                return table
    return None


def parse_season_stats(html):
    """
    Parse per-game stats from a team season page.
    Returns list of {name, position, games, ppg}.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = find_table(soup, "per_game")
    if not table:
        return []

    players = {}
    tbody = table.find("tbody")
    if not tbody:
        return []

    for row in tbody.find_all("tr"):
        # Skip separator/header rows
        if row.get("class") and "thead" in row.get("class"):
            continue

        name_el = row.find("td", attrs={"data-stat": "player"})
        pos_el = row.find("td", attrs={"data-stat": "pos"})
        g_el = row.find("td", attrs={"data-stat": "g"})
        pts_el = row.find("td", attrs={"data-stat": "pts_per_g"})

        if not name_el:
            continue

        link = name_el.find("a")
        name = link.get_text(strip=True) if link else name_el.get_text(strip=True)
        if not name:
            continue

        pos = pos_el.get_text(strip=True) if pos_el else "G"
        # Normalize multi-position (e.g. "PG-SG" -> "PG")
        pos = pos.split("-")[0] if pos else "G"

        try:
            games = int(g_el.get_text(strip=True)) if g_el else 0
        except ValueError:
            games = 0

        try:
            ppg = float(pts_el.get_text(strip=True)) if pts_el else 0.0
        except ValueError:
            ppg = 0.0

        if name in players:
            # Player appears twice (traded mid-season) — aggregate
            players[name]["games"] += games
            players[name]["weighted_pts"] += games * ppg
        else:
            players[name] = {
                "name": name,
                "position": pos,
                "games": games,
                "weighted_pts": games * ppg,
            }

    return list(players.values())


def scrape_team(team_name, abbrs):
    """Scrape all seasons for a team and return aggregated player list."""
    player_map = {}

    for abbr in abbrs:
        for year in range(START_YEAR, END_YEAR):
            url = f"https://www.basketball-reference.com/teams/{abbr}/{year}.html"
            html = fetch_page(url)

            if not html:
                time.sleep(1)
                continue

            season_players = parse_season_stats(html)
            logger.info(f"  {abbr}/{year}: {len(season_players)} players")

            for p in season_players:
                name = p["name"]
                if name not in player_map:
                    player_map[name] = {
                        "name": name,
                        "position": p["position"],
                        "careerGames": p["games"],
                        "weighted_pts": p["weighted_pts"],
                        "draftRound": None,
                        "allStarAppearances": 0,
                    }
                else:
                    player_map[name]["careerGames"] += p["games"]
                    player_map[name]["weighted_pts"] += p["weighted_pts"]

            time.sleep(4)  # Polite delay — Basketball Reference asks for 3+s

    result = []
    for p in player_map.values():
        games = p["careerGames"]
        p["careerPPG"] = round(p["weighted_pts"] / games, 1) if games > 0 else 0.0
        del p["weighted_pts"]
        result.append(p)

    return result


def main():
    all_data = {}

    for team_name, primary_abbr in TEAMS.items():
        logger.info(f"\n=== {team_name} ===")
        abbrs = [primary_abbr] + EXTRA_ABBRS.get(team_name, [])
        team_players = scrape_team(team_name, abbrs)
        all_data[team_name] = team_players
        logger.info(f"  => {len(team_players)} unique players for {team_name}")

    # Write data.js in the format the game expects
    with open("data.js", "w", encoding="utf-8") as f:
        f.write("const playersData = ")
        json.dump(all_data, f, indent=2, ensure_ascii=False)
        f.write(";\n")

    total = sum(len(v) for v in all_data.values())
    logger.info(f"\nDone! {total} total player-team entries written to data.js")


if __name__ == "__main__":
    main()
