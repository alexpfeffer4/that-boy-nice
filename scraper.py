#!/usr/bin/env python3
"""
NBA Players Web Scraper - Basketball Reference
Scrapes all NBA player rosters organized by current team.
Outputs data.js formatted for the "that boy nice" game.
"""

import requests
import time
import logging
from bs4 import BeautifulSoup
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Basketball Reference team abbreviations -> full names
TEAM_NAMES = {
    'ATL': 'Atlanta Hawks',
    'BOS': 'Boston Celtics',
    'BRK': 'Brooklyn Nets',
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
    'MEM': 'Memphis Grizzlies',
    'MIA': 'Miami Heat',
    'MIL': 'Milwaukee Bucks',
    'MIN': 'Minnesota Timberwolves',
    'NOP': 'New Orleans Pelicans',
    'NYK': 'New York Knicks',
    'OKC': 'Oklahoma City Thunder',
    'ORL': 'Orlando Magic',
    'PHI': 'Philadelphia 76ers',
    'PHX': 'Phoenix Suns',
    'POR': 'Portland Trail Blazers',
    'SAC': 'Sacramento Kings',
    'SAS': 'San Antonio Spurs',
    'TOR': 'Toronto Raptors',
    'UTA': 'Utah Jazz',
    'WAS': 'Washington Wizards'
}

class NBAScraperBasketballRef:
    BASE_URL = "https://www.basketball-reference.com"
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self.players_by_team = {team_name: [] for team_name in TEAM_NAMES.values()}

    def fetch(self, url: str, max_retries: int = 3) -> Optional[str]:
        """Fetch URL with retries and polite delay."""
        for attempt in range(max_retries):
            try:
                logger.info(f"Fetching: {url} (attempt {attempt + 1}/{max_retries})")
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()
                time.sleep(1.5)  # Be polite to Basketball Reference
                return resp.text
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(3)
        return None

    def scrape_team_roster(self, team_abbr: str, season: int = 2024) -> List[Dict]:
        """Scrape a team's roster and each player's career stats."""
        url = f"{self.BASE_URL}/teams/{team_abbr}/{season}.html"
        html = self.fetch(url)
        if not html:
            logger.error(f"Could not fetch {team_abbr}")
            return []

        players = []
        try:
            soup = BeautifulSoup(html, 'html.parser')
            table = soup.find('table', {'id': 'roster'})
            if not table:
                logger.warning(f"No roster table for {team_abbr}")
                return []

            for row in table.select('tbody tr'):
                # Use data-stat attributes — roster rows have th for number, td for everything else
                name_td = row.find('td', {'data-stat': 'player'})
                pos_td = row.find('td', {'data-stat': 'pos'})

                if not name_td or not pos_td:
                    continue

                name = name_td.get_text(strip=True)
                pos = pos_td.get_text(strip=True)

                if not name:
                    continue

                # Get player stats page link
                player_link = name_td.find('a')
                if player_link and player_link.get('href'):
                    player_url = f"{self.BASE_URL}{player_link['href']}"
                    stats = self.scrape_player_stats(player_url)
                    if stats:
                        stats['name'] = name
                        stats['position'] = pos
                        players.append(stats)
                        logger.info(f"  + {name} ({pos}) — {stats['careerGames']}G, {stats['careerPPG']} PPG")
                        continue

                # Fallback if stats page fails
                players.append({
                    'name': name,
                    'position': pos,
                    'careerGames': 100,
                    'careerPPG': 10.0,
                    'draftRound': 1,
                    'allStarAppearances': 0
                })

        except Exception as e:
            logger.error(f"Error scraping {team_abbr} roster: {e}")

        return players

    def scrape_player_stats(self, player_url: str) -> Optional[Dict]:
        """Scrape career stats from a player's Basketball Reference page."""
        html = self.fetch(player_url, max_retries=2)
        if not html:
            return None

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Table ID is per_game_stats (not per_game)
            stats_table = soup.find('table', {'id': 'per_game_stats'})
            if not stats_table:
                return None

            # Track seasons to avoid double-counting multi-team seasons.
            # Basketball Reference shows individual team rows AND an aggregate
            # row (e.g. "2TM") when a player played for multiple teams in one year.
            seen_seasons: Dict[str, Dict] = {}

            for row in stats_table.select('tbody tr'):
                # Get season from the th element (year_id)
                season_th = row.find('th', {'data-stat': 'year_id'})
                if not season_th:
                    continue
                season = season_th.get_text(strip=True)
                if not season or not season[0].isdigit():
                    continue  # Skip header/total rows

                # Only count NBA rows
                lg_td = row.find('td', {'data-stat': 'comp_name_abbr'})
                if not lg_td or 'NBA' not in lg_td.get_text():
                    continue

                team_td = row.find('td', {'data-stat': 'team_name_abbr'})
                team = team_td.get_text(strip=True) if team_td else ''

                g_td = row.find('td', {'data-stat': 'games'})
                pts_td = row.find('td', {'data-stat': 'pts_per_g'})
                if not g_td or not pts_td:
                    continue

                try:
                    g = int(g_td.get_text(strip=True) or 0)
                    ppg = float(pts_td.get_text(strip=True) or 0)
                except (ValueError, TypeError):
                    continue

                # Aggregate rows (2TM, 3TM) start with a digit — they represent
                # the full season total when a player changed teams mid-year.
                is_aggregate = len(team) > 0 and team[0].isdigit()

                if season not in seen_seasons:
                    seen_seasons[season] = {'g': g, 'pts': g * ppg, 'is_agg': is_aggregate}
                elif is_aggregate:
                    # Replace individual team row(s) with the season aggregate
                    seen_seasons[season] = {'g': g, 'pts': g * ppg, 'is_agg': True}
                # If season already recorded as aggregate, skip individual team rows

            if not seen_seasons:
                return None

            career_games = sum(s['g'] for s in seen_seasons.values())
            career_pts = sum(s['pts'] for s in seen_seasons.values())
            career_ppg = career_pts / career_games if career_games > 0 else 0

            return {
                'careerGames': career_games,
                'careerPPG': round(career_ppg, 1),
                'draftRound': 1,
                'allStarAppearances': 0
            }

        except Exception as e:
            logger.debug(f"Error scraping player stats from {player_url}: {e}")
            return None

    def run(self) -> bool:
        """Scrape all 30 team rosters."""
        logger.info(f"Starting scrape for {len(TEAM_NAMES)} teams...")
        total_players = 0

        for team_abbr, team_name in sorted(TEAM_NAMES.items()):
            logger.info(f"\n--- {team_name} ({team_abbr}) ---")
            roster = self.scrape_team_roster(team_abbr)

            if roster:
                self.players_by_team[team_name] = roster
                total_players += len(roster)
                logger.info(f"  => {len(roster)} players")
            else:
                logger.warning(f"  => No players found!")

        logger.info(f"\nTotal players scraped: {total_players}")
        return total_players > 0

    def export_to_datajs(self, filename: str = 'data.js') -> bool:
        """Export player data in the format expected by the game's data.js."""
        try:
            lines = ['const playersData = {']

            teams = sorted(k for k, v in self.players_by_team.items() if v)
            for i, team_name in enumerate(teams):
                players = self.players_by_team[team_name]
                lines.append(f'  "{team_name}": [')

                for j, p in enumerate(players):
                    comma = ',' if j < len(players) - 1 else ''
                    # Escape any quotes in names
                    safe_name = p.get('name', '').replace('"', '\\"')
                    safe_pos = p.get('position', 'C').replace('"', '\\"')
                    lines.append(
                        f'    {{"name": "{safe_name}", "position": "{safe_pos}", '
                        f'"careerGames": {p.get("careerGames", 100)}, '
                        f'"careerPPG": {p.get("careerPPG", 10.0)}, '
                        f'"draftRound": {p.get("draftRound", 1)}, '
                        f'"allStarAppearances": {p.get("allStarAppearances", 0)}}}{comma}'
                    )

                team_comma = ',' if i < len(teams) - 1 else ''
                lines.append(f'  ]{team_comma}')

            lines.append('};')

            with open(filename, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')

            logger.info(f"Exported {sum(len(v) for v in self.players_by_team.values())} players to {filename}")
            return True

        except Exception as e:
            logger.error(f"Export failed: {e}")
            return False


def main():
    scraper = NBAScraperBasketballRef()
    if scraper.run():
        scraper.export_to_datajs()
        logger.info("Done!")
        return 0
    logger.error("Scraping failed — no players found")
    return 1


if __name__ == '__main__':
    exit(main())
