#!/usr/bin/env node
/**
 * Fetches all NBA players from BallDontLie API v2 and exports to data.js
 * Requires env var: BALLDONTLIE_API_KEY
 */

const https = require('https');
const fs = require('fs');

const API_KEY = process.env.BALLDONTLIE_API_KEY;
if (!API_KEY) {
  console.error('Missing BALLDONTLIE_API_KEY environment variable');
  process.exit(1);
}

const BASE_URL = 'https://api.balldontlie.io/nba/v1';

const FRANCHISE_MAP = {
  'New Jersey Nets': 'Brooklyn Nets',
  'New Orleans Hornets': 'New Orleans Pelicans',
  'New Orleans/Oklahoma City Hornets': 'New Orleans Pelicans',
  'Seattle SuperSonics': 'Oklahoma City Thunder',
  'Washington Bullets': 'Washington Wizards',
  'Vancouver Grizzlies': 'Memphis Grizzlies',
  'Kansas City Kings': 'Sacramento Kings',
  'San Diego Clippers': 'Los Angeles Clippers',
};

const VALID_TEAMS = new Set([
  'Atlanta Hawks', 'Boston Celtics', 'Brooklyn Nets', 'Charlotte Hornets',
  'Chicago Bulls', 'Cleveland Cavaliers', 'Dallas Mavericks', 'Denver Nuggets',
  'Detroit Pistons', 'Golden State Warriors', 'Houston Rockets', 'Indiana Pacers',
  'Los Angeles Clippers', 'Los Angeles Lakers', 'Memphis Grizzlies', 'Miami Heat',
  'Milwaukee Bucks', 'Minnesota Timberwolves', 'New Orleans Pelicans', 'New York Knicks',
  'Oklahoma City Thunder', 'Orlando Magic', 'Philadelphia 76ers', 'Phoenix Suns',
  'Portland Trail Blazers', 'Sacramento Kings', 'San Antonio Spurs', 'Toronto Raptors',
  'Utah Jazz', 'Washington Wizards'
]);

function fetchJSON(url) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: { 'Authorization': API_KEY } }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (res.statusCode !== 200) {
            reject(new Error(`HTTP ${res.statusCode}: ${JSON.stringify(parsed)}`));
          } else {
            resolve(parsed);
          }
        } catch (e) {
          reject(new Error(`JSON parse error: ${e.message}`));
        }
      });
    });
    req.on('error', reject);
    req.setTimeout(15000, () => { req.destroy(); reject(new Error('Request timeout')); });
  });
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function getAllPlayers() {
  const players = [];
  let cursor = null;
  let page = 1;

  console.log('Fetching all players from BallDontLie API...');

  while (true) {
    const url = cursor
      ? `${BASE_URL}/players?per_page=100&cursor=${cursor}`
      : `${BASE_URL}/players?per_page=100`;

    let result;
    try {
      result = await fetchJSON(url);
    } catch (e) {
      console.error(`Error on page ${page}: ${e.message}`);
      break;
    }

    if (!result.data || result.data.length === 0) break;

    players.push(...result.data);
    console.log(`  Page ${page}: ${result.data.length} players (${players.length} total)`);

    if (!result.meta || !result.meta.next_cursor) break;
    cursor = result.meta.next_cursor;
    page++;

    await sleep(1000); // Stay within free tier rate limits
  }

  console.log(`Fetched ${players.length} players total`);
  return players;
}

function buildDatabase(players) {
  const db = {};
  VALID_TEAMS.forEach(t => db[t] = []);

  players.forEach(p => {
    if (!p.team) return;

    let teamName = p.team.full_name;
    teamName = FRANCHISE_MAP[teamName] || teamName;

    if (!db[teamName]) return;

    const name = `${p.first_name} ${p.last_name}`.trim();
    if (db[teamName].some(existing => existing.name === name)) return;

    db[teamName].push({
      name,
      position: p.position || 'G',
      careerGames: 200,
      careerPPG: 10.0,
      draftRound: p.draft_round || 3,
      allStarAppearances: 0
    });
  });

  return db;
}

function exportToDataJs(db, filename = 'data.js') {
  const teams = Object.keys(db).filter(k => db[k].length > 0).sort();
  const lines = ['const playersData = {'];

  teams.forEach((team, i) => {
    lines.push(`  "${team}": [`);
    db[team].forEach((p, j) => {
      const comma = j < db[team].length - 1 ? ',' : '';
      const safeName = p.name.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
      lines.push(
        `    {"name": "${safeName}", "position": "${p.position}", ` +
        `"careerGames": ${p.careerGames}, "careerPPG": ${p.careerPPG}, ` +
        `"draftRound": ${p.draftRound}, "allStarAppearances": ${p.allStarAppearances}}${comma}`
      );
    });
    const teamComma = i < teams.length - 1 ? ',' : '';
    lines.push(`  ]${teamComma}`);
  });

  lines.push('};');
  fs.writeFileSync(filename, lines.join('\n') + '\n');

  const total = teams.reduce((sum, t) => sum + db[t].length, 0);
  console.log(`Exported ${total} players across ${teams.length} teams to ${filename}`);
  teams.forEach(t => console.log(`  ${t}: ${db[t].length}`));
}

async function main() {
  try {
    const players = await getAllPlayers();
    if (players.length === 0) {
      console.error('No players fetched — check API key and endpoint');
      process.exit(1);
    }
    const db = buildDatabase(players);
    exportToDataJs(db);
  } catch (e) {
    console.error('Fatal error:', e);
    process.exit(1);
  }
}

main();
