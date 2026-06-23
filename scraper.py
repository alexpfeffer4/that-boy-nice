#!/usr/bin/env python3
"""
NBA Players Scraper - Basketball Reference
Scrapes multiple seasons per team to get historical players.
Outputs data.js for the "that boy nice" game.
"""

import requests
import time
import logging
import json
from bs4 import BeautifulSoup
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Seasons to scrape per team — spread across eras for historical coverage
SEASONS = [2000, 2004, 2008, 2012, 2016, 2019, 2021, 2023, 2024]

TEAM_ABBRS = [
    'ATL', 'BOS', 'BRK', 'CHO', 'CHI', 'CLE', 'DAL', 'DEN', 'DET', 'GSW',
    'HOU', 'IND', 'LAC', 'LAL', 'MEM', 'MIA', 'MIL', 'MIN', 'NOP', 'NYK',
    'OKC', 'ORL', 'PHI', 'PHX', 'POR', 'SAC', 'SAS', 'TOR', 'UTA', 'WAS'
]

# Map Basketball Reference abbreviations to game's team names
TEAM_NAMES = {
    'ATL': 'Atlanta Hawks',      'BOS': 'Boston Celtics',
    'BRK': 'Brooklyn Nets',      'CHO': 'Charlotte Hornets',
    'CHI': 'Chicago Bulls',      'CLE': 'Cleveland Cavaliers',
    'DAL': 'Dallas Mavericks',   'DEN': 'Denver Nuggets',
    'DET': 'Detroit Pistons',    'GSW': 'Golden State Warriors',
    'HOU': 'Houston Rockets',    'IND': 'Indiana Pacers',
    'LAC': 'Los Angeles Clippers','LAL': 'Los Angeles Lakers',
    'MEM': 'Memphis Grizzlies',  'MIA': 'Miami Heat',
    'MIL': 'Milwaukee Bucks',    'MIN': 'Minnesota Timberwolves',
    'NOP': 'New Orleans Pelicans','NYK': 'New York Knicks',
    'OKC': 'Oklahoma City Thunder','ORL': 'Orlando Magic',
    'PHI': 'Philadelphia 76ers', 'PHX': 'Phoenix Suns',
    'POR': 'Portland Trail Blazers','SAC': 'Sacramento Kings',
    'SAS': 'San Antonio Spurs',  'TOR': 'Toronto Raptors',
    'UTA': 'Utah Jazz',          'WAS': 'Washington Wizards'
}

BASE_URL = 'https://www.basketball-reference.com'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def fetch(url: str, max_retries: int = 3) -> Optional[str]:
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 429:
                logger.warning('Rate limited — waiting 10s...')
                time.sleep(10)
                continue
            resp.raise_for_status()
            time.sleep(2)  # Polite delay
            return resp.text
        except Exception as e:
            logger.warning(f'Attempt {attempt+1} failed for {url}: {e}')
            if attempt < max_retries - 1:
                time.sleep(3)
    return None


def scrape_team_season(team_abbr: str, season: int) -> List[Dict]:
    """
    Scrape the per_game_stats table from a team's season page.
    Returns players with that season's stats.
    """
    url = f'{BASE_URL}/teams/{team_abbr}/{season}.html'
    html = fetch(url)
    if not html:
        logger.warning(f'Could not fetch {team_abbr} {season}')
        return []

    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table', {'id': 'per_game_stats'})
    if not table:
        logger.warning(f'No per_game_stats table for {team_abbr} {season}')
        return []

    players = []
    for row in table.select('tbody tr'):
        # Skip separator/header rows
        if 'class' in row.attrs and 'thead' in row.get('class', []):
            continue

        name_td = row.find('td', {'data-stat': 'name_display'})
        if not name_td:
            continue

        name = name_td.get_text(strip=True)
        if not name or name == 'Team Totals':
            continue

        # Position comes from a th on the team stats page
        pos_th = row.find(['td', 'th'], {'data-stat': 'pos'})
        pos = pos_th.get_text(strip=True) if pos_th else 'G'

        g_td = row.find('td', {'data-stat': 'games'})
        pts_td = row.find('td', {'data-stat': 'pts_per_g'})

        try:
            games = int(g_td.get_text(strip=True) or 0) if g_td else 0
        except ValueError:
            games = 0

        try:
            ppg = float(pts_td.get_text(strip=True) or 0) if pts_td else 0.0
        except ValueError:
            ppg = 0.0

        players.append({
            'name': name,
            'position': pos or 'G',
            'games': games,
            'ppg': ppg,
        })

    logger.info(f'  {team_abbr} {season}: {len(players)} players')
    return players


def build_database() -> Dict:
    """
    Scrape all teams across multiple seasons.
    Aggregates career games and computes weighted career PPG.
    """
    # Structure: team_name -> player_name -> {games, pts, seasons}
    raw: Dict[str, Dict[str, Dict]] = {name: {} for name in TEAM_NAMES.values()}

    total_requests = len(TEAM_ABBRS) * len(SEASONS)
    done = 0

    for team_abbr in TEAM_ABBRS:
        team_name = TEAM_NAMES[team_abbr]
        logger.info(f'\n=== {team_name} ===')

        for season in SEASONS:
            players = scrape_team_season(team_abbr, season)
            done += 1
            logger.info(f'Progress: {done}/{total_requests} pages')

            for p in players:
                name = p['name']
                if name not in raw[team_name]:
                    raw[team_name][name] = {
                        'position': p['position'],
                        'total_games': 0,
                        'total_pts': 0,
                        'seasons': 0,
                    }
                entry = raw[team_name][name]
                entry['total_games'] += p['games']
                entry['total_pts'] += p['games'] * p['ppg']
                entry['seasons'] += 1

    # Convert to final format
    db = {}
    for team_name, players in raw.items():
        if not players:
            continue
        db[team_name] = []
        for name, data in players.items():
            games = data['total_games']
            ppg = round(data['total_pts'] / games, 1) if games > 0 else 0.0
            db[team_name].append({
                'name': name,
                'position': data['position'],
                'careerGames': games,
                'careerPPG': ppg,
                'draftRound': 1,        # Not available from team pages
                'allStarAppearances': 0  # Not available from team pages
            })

    return db


def export_to_datajs(db: Dict, filename: str = 'data.js'):
    teams = sorted(k for k, v in db.items() if v)
    lines = ['const playersData = {']

    for i, team in enumerate(teams):
        players = db[team]
        lines.append(f'  "{team}": [')
        for j, p in enumerate(players):
            comma = ',' if j < len(players) - 1 else ''
            safe_name = p['name'].replace('\\', '\\\\').replace('"', '\\"')
            lines.append(
                f'    {{"name": "{safe_name}", "position": "{p["position"]}", '
                f'"careerGames": {p["careerGames"]}, "careerPPG": {p["careerPPG"]}, '
                f'"draftRound": {p["draftRound"]}, "allStarAppearances": {p["allStarAppearances"]}}}{comma}'
            )
        team_comma = ',' if i < len(teams) - 1 else ''
        lines.append(f'  ]{team_comma}')

    lines.append('};')

    with open(filename, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    total = sum(len(db[t]) for t in teams)
    logger.info(f'\nExported {total} players across {len(teams)} teams to {filename}')
    for t in teams:
        logger.info(f'  {t}: {len(db[t])} players')


def main():
    logger.info(f'Scraping {len(TEAM_ABBRS)} teams × {len(SEASONS)} seasons = {len(TEAM_ABBRS)*len(SEASONS)} pages')
    db = build_database()

    total = sum(len(v) for v in db.values())
    if total == 0:
        logger.error('No players scraped')
        return 1

    export_to_datajs(db)
    logger.info('Done!')
    return 0


if __name__ == '__main__':
    exit(main())
