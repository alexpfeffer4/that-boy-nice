const https = require('https');
const fs = require('fs');

const API_BASE = 'https://api.balldontlie.io/api/v1';

// Map old franchise names to current ones
const FRANCHISE_MAP = {
  'New Jersey Nets': 'Brooklyn Nets',
  'New Orleans Hornets': 'New Orleans Pelicans',
  'Seattle SuperSonics': 'Oklahoma City Thunder',
  'Washington Bullets': 'Washington Wizards',
  'Vancouver Grizzlies': 'Memphis Grizzlies',
  'Charlotte Hornets (2004)': 'Charlotte Hornets', // Handle duplicate
};

function fetchAPI(endpoint) {
  return new Promise((resolve, reject) => {
    const url = `${API_BASE}${endpoint}`;
    https.get(url, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          reject(e);
        }
      });
    }).on('error', reject);
  });
}

async function getAllPlayers() {
  const players = [];
  let perPage = 100;
  let page = 1;
  let hasMore = true;

  console.log('Fetching all players...');

  while (hasMore) {
    try {
      const res = await fetchAPI(`/players?page=${page}&per_page=${perPage}`);
      if (res.data && res.data.length > 0) {
        players.push(...res.data);
        console.log(`  Fetched page ${page} (${players.length} total so far)`);
        page++;
        hasMore = res.data.length === perPage;
      } else {
        hasMore = false;
      }
    } catch (e) {
      console.error(`Error fetching page ${page}:`, e.message);
      hasMore = false;
    }
  }

  return players;
}

async function getPlayerStats(playerId) {
  try {
    const res = await fetchAPI(`/stats?player_ids[]=${playerId}&per_page=100`);
    return res.data || [];
  } catch (e) {
    console.error(`Error fetching stats for player ${playerId}:`, e.message);
    return [];
  }
}

function normalizeFranchise(name) {
  return FRANCHISE_MAP[name] || name;
}

async function buildPlayerDatabase(players) {
  const db = {};

  // Initialize franchises
  const franchises = new Set();
  players.forEach(p => {
    if (p.team) {
      franchises.add(normalizeFranchise(p.team.full_name));
    }
  });

  franchises.forEach(f => {
    db[f] = [];
  });

  console.log(`\nProcessing ${players.length} players across ${franchises.size} franchises...`);

  for (let i = 0; i < players.length; i++) {
    const p = players[i];

    if (i % 50 === 0) {
      console.log(`  Processing player ${i}/${players.length}`);
    }

    // Get season stats for career totals
    const stats = await getPlayerStats(p.id);

    let careerGames = 0;
    let careerPoints = 0;
    const teamSet = new Set();

    stats.forEach(s => {
      if (s.game && s.player) {
        careerGames += s.min ? 1 : 0;
        if (s.pts) careerPoints += s.pts;
        if (s.team) {
          teamSet.add(normalizeFranchise(s.team.full_name));
        }
      }
    });

    const careerPPG = careerGames > 0 ? (careerPoints / careerGames).toFixed(1) : 0;

    const playerObj = {
      name: p.first_name + ' ' + p.last_name,
      position: p.position || 'Unknown',
      height: p.height_feet ? `${p.height_feet}'${p.height_inches}"` : null,
      weight: p.weight_pounds || null,
      college: p.college || null,
      country: p.country || null,
      draftYear: p.draft_year || null,
      draftRound: p.draft_round || null,
      draftNumber: p.draft_number || null,
      careerGames,
      careerPPG: parseFloat(careerPPG),
      // Note: All-Star data would need separate API or scraping
    };

    // Add to all teams this player played for
    if (teamSet.size > 0) {
      teamSet.forEach(team => {
        if (db[team]) {
          db[team].push(playerObj);
        }
      });
    } else if (p.team) {
      // Fallback to current team if no stats found
      const franchise = normalizeFranchise(p.team.full_name);
      if (db[franchise]) {
        db[franchise].push(playerObj);
      }
    }
  }

  // Remove duplicates within each franchise
  Object.keys(db).forEach(franchise => {
    const seen = new Set();
    db[franchise] = db[franchise].filter(p => {
      const key = p.name.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  });

  return db;
}

async function main() {
  try {
    const players = await getAllPlayers();
    console.log(`\nFetched ${players.length} players total`);

    const db = await buildPlayerDatabase(players);

    // Write to file
    fs.writeFileSync(
      'players.json',
      JSON.stringify(db, null, 2)
    );

    console.log('\nDone! Wrote players.json');
    console.log('Franchises:', Object.keys(db).length);
    Object.keys(db).forEach(franchise => {
      console.log(`  ${franchise}: ${db[franchise].length} players`);
    });
  } catch (e) {
    console.error('Fatal error:', e);
    process.exit(1);
  }
}

main();
