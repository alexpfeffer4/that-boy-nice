#!/usr/bin/env python3
"""
NBA Players Scraper - Basketball Reference (league-wide advanced pages)

Fetches ONE page per season (2000-2026) from /leagues/NBA_YYYY_advanced.html.
Each page lists every player in the league that year with VORP, games, team, and a
unique player id. We aggregate career totals by player id (solves duplicate names)
and file each player under EVERY current franchise they ever played for.

Only ~27 requests total — far under any rate limit, no parallelism needed.
Outputs data.js for the "that boy nice" game.
"""

import requests
import time
import logging
import re
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Basketball Reference team_name_abbr codes -> current franchise.
# Codes verified empirically across 2000-2026 league pages.
ABBR_TO_FRANCHISE = {
    'ATL': 'Atlanta Hawks',
    'BOS': 'Boston Celtics',
    'BRK': 'Brooklyn Nets',          'NJN': 'Brooklyn Nets',            # New Jersey Nets
    'CHA': 'Charlotte Hornets',      'CHH': 'Charlotte Hornets',        # Bobcats / original Hornets
    'CHO': 'Charlotte Hornets',
    'CHI': 'Chicago Bulls',
    'CLE': 'Cleveland Cavaliers',
    'DAL': 'Dallas Mavericks',
    'DEN': 'Denver Nuggets',
    'DET': 'Detroit Pistons',
    'GSW': 'Golden State Warriors',
    'HOU': 'Houston Rockets',
    'IND': 'Indiana Pacers',
    'LAC': 'Los Angeles Clippers',
    'LAL': 'Los Angeles Lakers',
    'MEM': 'Memphis Grizzlies',      'VAN': 'Memphis Grizzlies',        # Vancouver Grizzlies
    'MIA': 'Miami Heat',
    'MIL': 'Milwaukee Bucks',
    'MIN': 'Minnesota Timberwolves',
    'NOP': 'New Orleans Pelicans',   'NOH': 'New Orleans Pelicans',     # New Orleans Hornets
    'NOK': 'New Orleans Pelicans',                                      # NO/Oklahoma City Hornets
    'NYK': 'New York Knicks',
    'OKC': 'Oklahoma City Thunder',  'SEA': 'Oklahoma City Thunder',    # Seattle SuperSonics
    'ORL': 'Orlando Magic',
    'PHI': 'Philadelphia 76ers',
    'PHO': 'Phoenix Suns',
    'POR': 'Portland Trail Blazers',
    'SAC': 'Sacramento Kings',
    'SAS': 'San Antonio Spurs',
    'TOR': 'Toronto Raptors',
    'UTA': 'Utah Jazz',
    'WAS': 'Washington Wizards',
}

SEASONS = list(range(2000, 2027))  # 2000 through 2026
BASE = 'https://www.basketball-reference.com'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Multi-team season rows are labeled "2TM", "3TM", etc. (combined season totals)
NTM_RE = re.compile(r'^\d+TM$')


def fetch(url: str, max_retries: int = 4):
    """Fetch a URL with retries and exponential backoff on rate limits."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 429:
                wait = 30 * (2 ** attempt)  # 30s, 60s, 120s, 240s
                logger.warning(f'429 rate limited — waiting {wait}s (attempt {attempt+1}/{max_retries})')
                time.sleep(wait)
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            time.sleep(4)  # Polite delay — only 27 requests total
            return resp.text
        except Exception as e:
            logger.warning(f'Attempt {attempt+1} failed for {url}: {e}')
            if attempt < max_retries - 1:
                time.sleep(5)
    return None


def scrape_season(year: int, players: dict) -> int:
    """Parse one season's advanced page; aggregate into the players dict (keyed by player id)."""
    url = f'{BASE}/leagues/NBA_{year}_advanced.html'
    html = fetch(url)
    if not html:
        logger.warning(f'{year}: no data')
        return 0

    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table', {'id': 'advanced'})
    if not table:
        logger.warning(f'{year}: no advanced table')
        return 0

    # Group this season's rows by player id (a player traded mid-year has multiple rows)
    season_rows: dict = {}
    for row in table.select('tbody tr'):
        name_td = row.find('td', {'data-stat': 'name_display'})
        if not name_td:
            continue
        link = name_td.find('a')
        if not link or not link.get('href'):
            continue

        pid = link['href'].split('/')[-1].replace('.html', '')  # e.g. "wallage01"
        name = name_td.get_text(strip=True)

        team_td = row.find('td', {'data-stat': 'team_name_abbr'})
        team = team_td.get_text(strip=True) if team_td else ''

        pos_td = row.find('td', {'data-stat': 'pos'})
        pos = pos_td.get_text(strip=True) if pos_td else 'G'

        g_td = row.find('td', {'data-stat': 'games'})
        vorp_td = row.find('td', {'data-stat': 'vorp'})
        try:
            g = int(g_td.get_text(strip=True) or 0)
        except (ValueError, TypeError):
            g = 0
        try:
            vorp = float(vorp_td.get_text(strip=True) or 0)
        except (ValueError, TypeError):
            vorp = 0.0

        season_rows.setdefault(pid, []).append({
            'name': name, 'team': team, 'pos': pos, 'g': g, 'vorp': vorp
        })

    count = 0
    for pid, rows in season_rows.items():
        # If a combined NTM row exists, it holds the full-season total (avoids double-count).
        combined = next((r for r in rows if NTM_RE.match(r['team'])), None)
        if combined:
            season_g = combined['g']
            season_vorp = combined['vorp']
            teams = [r['team'] for r in rows if not NTM_RE.match(r['team'])]
        else:
            r0 = rows[0]
            season_g = r0['g']
            season_vorp = r0['vorp']
            teams = [r0['team']]

        name = rows[0]['name']
        pos = rows[0]['pos']

        if pid not in players:
            players[pid] = {'name': name, 'pos': pos, 'games': 0, 'vorp': 0.0, 'franchises': set()}

        p = players[pid]
        p['games'] += season_g
        p['vorp'] += season_vorp
        p['name'] = name
        p['pos'] = pos  # keep most recent position
        for t in teams:
            fr = ABBR_TO_FRANCHISE.get(t)
            if fr:
                p['franchises'].add(fr)
        count += 1

    logger.info(f'{year}: {count} players')
    return count


def build() -> dict:
    players: dict = {}
    for yr in SEASONS:
        scrape_season(yr, players)
    return players


def organize_by_team(players: dict) -> dict:
    """File each player under every current franchise they played for."""
    teams = {fr: [] for fr in set(ABBR_TO_FRANCHISE.values())}
    for pid, p in players.items():
        entry = {
            'name': p['name'],
            'position': p['pos'] or 'G',
            'careerGames': p['games'],
            'careerVORP': round(p['vorp'], 1),
            'draftRound': 1,
            'allStarAppearances': 0,
        }
        for fr in p['franchises']:
            teams[fr].append(entry)
    return teams


def export_to_datajs(teams: dict, filename: str = 'data.js'):
    names = sorted(k for k, v in teams.items() if v)
    lines = ['const playersData = {']

    for i, fr in enumerate(names):
        roster = sorted(teams[fr], key=lambda x: x['name'])
        lines.append(f'  "{fr}": [')
        for j, p in enumerate(roster):
            comma = ',' if j < len(roster) - 1 else ''
            sn = p['name'].replace('\\', '\\\\').replace('"', '\\"')
            lines.append(
                f'    {{"name": "{sn}", "position": "{p["position"]}", '
                f'"careerGames": {p["careerGames"]}, "careerVORP": {p["careerVORP"]}, '
                f'"draftRound": {p["draftRound"]}, "allStarAppearances": {p["allStarAppearances"]}}}{comma}'
            )
        team_comma = ',' if i < len(names) - 1 else ''
        lines.append(f'  ]{team_comma}')

    lines.append('};')

    with open(filename, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    total = sum(len(teams[t]) for t in names)
    logger.info(f'\nExported {total} player-team entries across {len(names)} teams to {filename}')
    for t in names:
        logger.info(f'  {t}: {len(teams[t])}')


def main():
    logger.info(f'Scraping {len(SEASONS)} league-advanced pages ({SEASONS[0]}-{SEASONS[-1]})')
    players = build()
    if not players:
        logger.error('No players scraped')
        return 1
    logger.info(f'\nAggregated {len(players)} unique players')
    export_to_datajs(organize_by_team(players))
    logger.info('Done!')
    return 0


if __name__ == '__main__':
    exit(main())
