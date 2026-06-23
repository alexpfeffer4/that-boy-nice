#!/usr/bin/env python3
"""
NBA Players Scraper - Basketball Reference (1980-2026 seasons + awards + draft)

Fetches:
- ONE page per season (1980-2026) from /leagues/NBA_YYYY_advanced.html (~47 pages)
- 7 award pages (All-Star, MVP, ROY, DPOY, SMOY, MIP, FMVP)
- 26 draft pages (2000-2025)

Each season page lists every player with VORP, games, team, and unique player id.
Award pages track wins/appearances per player. Draft pages capture pick numbers.
Aggregates career totals by player id and files under every franchise played for.

~60 total requests, runs in ~5-10 minutes.
Outputs data.js for the "that boy nice" game.
"""

import requests
import time
import logging
import re
from bs4 import BeautifulSoup, Comment

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Basketball Reference team_name_abbr codes -> current franchise.
ABBR_TO_FRANCHISE = {
    'ATL': 'Atlanta Hawks',
    'BOS': 'Boston Celtics',
    'BRK': 'Brooklyn Nets',          'NJN': 'Brooklyn Nets',
    'CHA': 'Charlotte Hornets',      'CHH': 'Charlotte Hornets',
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
    'MEM': 'Memphis Grizzlies',      'VAN': 'Memphis Grizzlies',
    'MIA': 'Miami Heat',
    'MIL': 'Milwaukee Bucks',
    'MIN': 'Minnesota Timberwolves',
    'NOP': 'New Orleans Pelicans',   'NOH': 'New Orleans Pelicans',
    'NOK': 'New Orleans Pelicans',
    'NYK': 'New York Knicks',
    'OKC': 'Oklahoma City Thunder',  'SEA': 'Oklahoma City Thunder',
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

SEASONS = list(range(1980, 2027))  # 1980 through 2026
DRAFT_SEASONS = list(range(1980, 2026))  # 1980 through 2025 (captures everyone's draft era)
BASE = 'https://www.basketball-reference.com'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

NTM_RE = re.compile(r'^\d+TM$')


def normalize_name(name: str) -> str:
    """Normalize player name for matching: lowercase, strip extra whitespace."""
    return ' '.join(name.lower().split())


def find_table(soup, *table_ids):
    """Find a table by any of the given IDs, including tables hidden in HTML comments (BBRef pattern)."""
    for tid in table_ids:
        table = soup.find('table', {'id': tid})
        if table:
            return table
    # BBRef hides some tables inside HTML comments — parse them too
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment_str = str(comment)
        for tid in table_ids:
            if tid in comment_str:
                comment_soup = BeautifulSoup(comment_str, 'html.parser')
                table = comment_soup.find('table', {'id': tid})
                if table:
                    return table
    return None


def fetch(url: str, max_retries: int = 5, timeout: int = 30):
    """Fetch a URL with retries and exponential backoff on rate limits."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 429:
                wait = 30 * (2 ** attempt)
                logger.warning(f'429 rate limited — waiting {wait}s (attempt {attempt+1}/{max_retries})')
                time.sleep(wait)
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            time.sleep(2)  # Polite delay
            return resp.text
        except requests.exceptions.Timeout:
            logger.warning(f'Timeout on attempt {attempt+1} for {url}')
            if attempt < max_retries - 1:
                time.sleep(5)
        except Exception as e:
            logger.warning(f'Attempt {attempt+1} failed for {url}: {e}')
            if attempt < max_retries - 1:
                time.sleep(5)
    return None


def scrape_season(year: int, players: dict) -> int:
    """Parse one season's advanced page; aggregate into the players dict."""
    url = f'{BASE}/leagues/NBA_{year}_advanced.html'
    html = fetch(url)
    if not html:
        logger.warning(f'{year}: no data')
        return 0

    soup = BeautifulSoup(html, 'html.parser')
    table = find_table(soup, 'advanced', 'advanced_stats')
    if not table:
        logger.warning(f'{year}: no advanced table')
        return 0

    season_rows: dict = {}
    for row in table.select('tbody tr'):
        name_td = row.find('td', {'data-stat': 'name_display'})
        if not name_td:
            continue
        link = name_td.find('a')
        if not link or not link.get('href'):
            continue

        pid = link['href'].split('/')[-1].replace('.html', '')
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
            players[pid] = {
                'name': name, 'positions': {}, 'games': 0, 'vorp': 0.0, 'franchises': set(),
                'mvpAwards': 0, 'fmvpAwards': 0, 'dpoyAwards': 0,
                'royAward': 0, 'smoyAwards': 0, 'mipAwards': 0, 'draftPick': 0
            }

        p = players[pid]
        p['games'] += season_g
        p['vorp'] += season_vorp
        p['name'] = name
        p['positions'][pos] = p['positions'].get(pos, 0) + 1
        for t in teams:
            fr = ABBR_TO_FRANCHISE.get(t)
            if fr:
                p['franchises'].add(fr)
        count += 1

    logger.info(f'{year}: {count} players')
    return count


def scrape_all_star() -> dict:
    """Scrape All-Star by player page; return {name: count}."""
    url = f'{BASE}/awards/all_star_by_player.html'
    html = fetch(url)
    if not html:
        logger.warning('All-Star: no data')
        return {}

    soup = BeautifulSoup(html, 'html.parser')
    table = find_table(soup, 'all_star_by_player', 'div_all_star_by_player')
    if not table:
        logger.warning('All-Star: no table')
        return {}

    stars = {}
    for row in table.select('tbody tr'):
        # Find player link in any td
        link = row.find('a', href=lambda h: h and '/players/' in h)
        if not link:
            continue

        name = normalize_name(link.get_text(strip=True))

        # BBRef all_star_by_player table has no data-stat attributes.
        # Column layout: [rank, player_name, total_selections, ...year_columns...]
        # Total selections is at index 2.
        all_tds = row.find_all('td')
        if len(all_tds) >= 3:
            try:
                apps = int(all_tds[2].get_text(strip=True) or 0)
                if apps > 0:
                    stars[name] = apps
            except (ValueError, TypeError):
                pass

    logger.info(f'All-Star: {len(stars)} players')
    return stars


def scrape_award(award_name: str, award_id: str, field: str) -> dict:
    """Scrape a single award page; return {name: count}."""
    url = f'{BASE}/awards/{award_id}.html'
    html = fetch(url)
    if not html:
        logger.warning(f'{award_name}: no data')
        return {}

    soup = BeautifulSoup(html, 'html.parser')
    # BBRef uses several table ID patterns; try all likely variants
    table = find_table(soup, award_id, f'awards_{award_id}', f'{award_id}_NBA', f'div_{award_id}')
    if not table:
        logger.warning(f'{award_name}: no table')
        return {}

    awards = {}
    for row in table.select('tbody tr'):
        link = row.find('a', href=lambda h: h and '/players/' in h)
        if not link:
            continue
        name = normalize_name(link.get_text(strip=True))
        awards[name] = awards.get(name, 0) + 1

    logger.info(f'{award_name}: {len(awards)} players')
    return awards


def scrape_draft(year: int) -> dict:
    """Scrape a single draft page; return {name: overall_pick}."""
    url = f'{BASE}/draft/NBA_{year}.html'
    html = fetch(url, timeout=30)
    if not html:
        logger.info(f'Draft {year}: fetch failed')
        return {}

    soup = BeautifulSoup(html, 'html.parser')

    # Log all table IDs to see what's on the page
    all_tables = soup.find_all('table')
    table_ids = [t.get('id', 'no-id') for t in all_tables]
    logger.info(f'Draft {year}: found {len(all_tables)} tables with IDs: {table_ids}')

    # Try to find the draft table - look for any table with player links
    table = None
    for t in all_tables:
        if t.find('a', href=lambda h: h and '/players/' in h):
            table = t
            logger.info(f'Draft {year}: found table with player links (id={t.get("id", "no-id")})')
            break

    if not table:
        logger.info(f'Draft {year}: no table with player links found')
        return {}

    picks = {}
    tbody = table.find('tbody')
    if not tbody:
        logger.info(f'Draft {year}: table has no tbody')
        return {}

    rows = tbody.find_all('tr')
    logged_stats = False
    for row in rows:
        link = row.find('a', href=lambda h: h and '/players/' in h)
        if not link:
            continue

        name = normalize_name(link.get_text(strip=True))

        # Log first row data-stats to confirm pick column name
        if not logged_stats and year == 2024:
            all_tds = row.find_all('td')
            stat_map = {td.get('data-stat', ''): td.get_text(strip=True) for td in all_tds[:8]}
            logger.info(f'Draft {year} first row data-stats: {stat_map}')
            logged_stats = True

        # Try multiple data-stat variants for pick number
        pick_td = (row.find('td', {'data-stat': 'pick_number'}) or
                   row.find('td', {'data-stat': 'pick_overall'}) or
                   row.find('td', {'data-stat': 'overall_pick'}))
        try:
            pick = int(pick_td.get_text(strip=True) or 0) if pick_td else 0
        except (ValueError, TypeError):
            pick = 0

        if pick > 0 and name not in picks:
            picks[name] = pick

    if picks:
        logger.info(f'Draft {year}: {len(picks)} picks')
    else:
        logger.info(f'Draft {year}: 0 picks (table found but no valid rows)')
    return picks


def scrape_all_drafts() -> dict:
    """Scrape all draft pages (1980-2025); return {name: overall_pick} (earliest draft only)."""
    all_picks = {}
    success_count = 0
    for year in DRAFT_SEASONS:
        picks = scrape_draft(year)
        if picks:
            success_count += 1
        for name, pick in picks.items():
            if name not in all_picks:
                all_picks[name] = pick
    logger.info(f'Drafts (1980-2025): {len(all_picks)} unique players with pick numbers ({success_count}/{len(DRAFT_SEASONS)} years)')
    return all_picks


def build_seasons() -> dict:
    """Scrape all seasons and return players dict."""
    players: dict = {}
    for yr in SEASONS:
        scrape_season(yr, players)
    return players


def merge_awards(players: dict):
    """Merge award data into players dict (matched by player name)."""
    logger.info('Scraping awards pages...')
    all_star_data = scrape_all_star()
    mvp_data = scrape_award('MVP', 'mvp', 'mvpAwards')
    dpoy_data = scrape_award('DPOY', 'dpoy', 'dpoyAwards')
    roy_data = scrape_award('ROY', 'roy', 'royAward')
    smoy_data = scrape_award('SMOY', 'smoy', 'smoyAwards')
    mip_data = scrape_award('MIP', 'mip', 'mipAwards')
    fmvp_data = scrape_award('FMVP', 'finals_mvp', 'fmvpAwards')

    for pid, p in players.items():
        name = normalize_name(p['name'])
        p['mvpAwards'] = mvp_data.get(name, 0)
        p['fmvpAwards'] = fmvp_data.get(name, 0)
        p['dpoyAwards'] = dpoy_data.get(name, 0)
        p['royAward'] = roy_data.get(name, 0)
        p['smoyAwards'] = smoy_data.get(name, 0)
        p['mipAwards'] = mip_data.get(name, 0)
        if name in all_star_data:
            p['allStarAppearances'] = all_star_data[name]


def merge_draft(players: dict):
    """Merge draft data into players dict (matched by player name)."""
    logger.info('Scraping draft pages...')
    draft_picks = scrape_all_drafts()
    matched = 0
    for pid, p in players.items():
        name = normalize_name(p['name'])
        if name in draft_picks:
            p['draftPick'] = draft_picks[name]
            matched += 1
    logger.info(f'Draft: matched {matched}/{len(players)} players')


def organize_by_team(players: dict) -> dict:
    """File each player under every current franchise they played for."""
    teams = {fr: [] for fr in set(ABBR_TO_FRANCHISE.values())}
    for pid, p in players.items():
        # Get top 2 positions by frequency (or default to 'G')
        if p['positions']:
            pos_list = sorted(p['positions'].items(), key=lambda x: x[1], reverse=True)
            positions = [pos[0] for pos in pos_list[:2]]
        else:
            positions = ['G']

        entry = {
            'name': p['name'],
            'positions': positions,
            'careerGames': p['games'],
            'careerVORP': round(p['vorp'], 1),
            'draftPick': p['draftPick'],
            'mvpAwards': p['mvpAwards'],
            'fmvpAwards': p['fmvpAwards'],
            'dpoyAwards': p['dpoyAwards'],
            'royAward': p['royAward'],
            'smoyAwards': p['smoyAwards'],
            'mipAwards': p['mipAwards'],
            'allStarAppearances': p.get('allStarAppearances', 0),
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
            pos_json = ', '.join(f'"{pos}"' for pos in p['positions'])
            lines.append(
                f'    {{'
                f'"name": "{sn}", "positions": [{pos_json}], '
                f'"careerGames": {p["careerGames"]}, "careerVORP": {p["careerVORP"]}, '
                f'"draftPick": {p["draftPick"]}, '
                f'"mvpAwards": {p["mvpAwards"]}, "fmvpAwards": {p["fmvpAwards"]}, '
                f'"dpoyAwards": {p["dpoyAwards"]}, "royAward": {p["royAward"]}, '
                f'"smoyAwards": {p["smoyAwards"]}, "mipAwards": {p["mipAwards"]}, '
                f'"allStarAppearances": {p["allStarAppearances"]}'
                f'}}{comma}'
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
    players = build_seasons()
    if not players:
        logger.error('No players scraped')
        return 1
    logger.info(f'\nAggregated {len(players)} unique players from seasons')

    merge_awards(players)
    merge_draft(players)

    logger.info(f'Merged awards and draft data')
    export_to_datajs(organize_by_team(players))
    logger.info('Done!')
    return 0


if __name__ == '__main__':
    exit(main())
