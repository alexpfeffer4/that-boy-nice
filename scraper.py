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

# Map team abbreviations to full names
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
        """Fetch URL with retries."""
        for attempt in range(max_retries):
            try:
                logger.info(f"Fetching: {url} (attempt {attempt + 1}/{max_retries})")
                resp = self.session.get(url, timeout=10)
                resp.raise_for_status()
                time.sleep(1)  # Be polite
                return resp.text
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
        return None

    def scrape_team_roster(self, team_abbr: str, season: int = 2024) -> List[Dict]:
        """Scrape a single team's roster."""
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
                logger.warning(f"No roster table found for {team_abbr}")
                return []

            for row in table.find_all('tr')[1:]:
                cols = row.find_all('td')
                if len(cols) < 8:
                    continue

                try:
                    name = cols[1].get_text(strip=True)
                    pos = cols[2].get_text(strip=True)

                    # Try to extract stats from individual player page
                    player_link = cols[1].find('a')
                    if player_link and player_link.get('href'):
                        player_url = f"{self.BASE_URL}{player_link['href']}"
                        stats = self.scrape_player_stats(player_url)
                        if stats:
                            stats['position'] = pos
                            stats['name'] = name
                            players.append(stats)
                            logger.info(f"  Added {name} ({pos}) - {stats.get('careerGames', 0)} games")
                        else:
                            # Fallback with minimal stats
                            players.append({
                                'name': name,
                                'position': pos,
                                'careerGames': 100,
                                'careerPPG': 10.0,
                                'draftRound': 1,
                                'allStarAppearances': 0
                            })
                except Exception as e:
                    logger.debug(f"Error parsing row: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error scraping {team_abbr}: {e}")

        return players

    def scrape_player_stats(self, player_url: str) -> Optional[Dict]:
        """Scrape individual player stats page."""
        html = self.fetch(player_url, max_retries=2)
        if not html:
            return None

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Look for career stats table
            stats_table = soup.find('table', {'id': 'per_game'})
            if not stats_table:
                return None

            # Sum career stats from all rows
            career_games = 0
            career_points = 0
            seasons = 0

            for row in stats_table.find_all('tr')[1:]:
                if row.find('th'):  # Skip header rows
                    continue
                cols = row.find_all('td')
                if len(cols) < 10:
                    continue

                try:
                    # Skip non-season rows
                    season_str = cols[0].get_text(strip=True)
                    if 'NBA' not in season_str and not season_str[0].isdigit():
                        continue

                    # Games
                    g = int(cols[5].get_text(strip=True) or 0)
                    # Points per game
                    ppg = float(cols[9].get_text(strip=True) or 0)

                    career_games += g
                    career_points += g * ppg
                    seasons += 1
                except:
                    continue

            if seasons == 0:
                return None

            career_ppg = career_points / career_games if career_games > 0 else 0

            return {
                'careerGames': career_games,
                'careerPPG': round(career_ppg, 1),
                'draftRound': 1,
                'allStarAppearances': 0
            }
        except Exception as e:
            logger.debug(f"Error scraping player stats: {e}")
            return None

    def run(self) -> bool:
        """Run scraper for all teams."""
        logger.info(f"Scraping {len(TEAM_NAMES)} teams...")
        total_players = 0

        for team_abbr, team_name in sorted(TEAM_NAMES.items()):
            logger.info(f"\nScraping {team_name}...")
            roster = self.scrape_team_roster(team_abbr)

            if roster:
                self.players_by_team[team_name] = roster
                total_players += len(roster)
                logger.info(f"  ✓ {team_name}: {len(roster)} players")
            else:
                logger.warning(f"  ✗ {team_name}: No players found")

        logger.info(f"\nTotal players scraped: {total_players}")
        return total_players > 0

    def export_to_datajs(self, filename: str = 'data.js') -> bool:
        """Export to data.js format."""
        try:
            # Build the JavaScript object
            js_content = "const playersData = {\n"

            for team_name in sorted(self.players_by_team.keys()):
                players = self.players_by_team[team_name]
                if not players:
                    continue

                js_content += f'  "{team_name}": [\n'

                for player in players:
                    js_content += f'    {{\n'
                    js_content += f'      "name": "{player.get("name", "")}",\n'
                    js_content += f'      "position": "{player.get("position", "C")}",\n'
                    js_content += f'      "careerGames": {player.get("careerGames", 100)},\n'
                    js_content += f'      "careerPPG": {player.get("careerPPG", 10.0)},\n'
                    js_content += f'      "draftRound": {player.get("draftRound", 1)},\n'
                    js_content += f'      "allStarAppearances": {player.get("allStarAppearances", 0)}\n'
                    js_content += f'    }},\n'

                js_content = js_content.rstrip(',\n') + '\n  ],\n'

            js_content = js_content.rstrip(',\n') + '\n};\n'

            with open(filename, 'w', encoding='utf-8') as f:
                f.write(js_content)

            logger.info(f"✓ Exported to {filename}")
            return True
        except Exception as e:
            logger.error(f"Error exporting: {e}")
            return False


def main():
    scraper = NBAScraperBasketballRef()
    if scraper.run():
        scraper.export_to_datajs()
        logger.info("Scraping complete!")
        return 0
    else:
        logger.error("Scraping failed")
        return 1


if __name__ == '__main__':
    exit(main())
