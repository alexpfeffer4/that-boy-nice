// Simple Levenshtein distance for fuzzy matching
function levenshteinDistance(a, b) {
  const aL = a.length, bL = b.length;
  const dp = Array(bL + 1).fill(0).map(() => Array(aL + 1).fill(0));
  for (let i = 0; i <= aL; i++) dp[0][i] = i;
  for (j = 0; j <= bL; j++) dp[j][0] = j;
  for (let j = 1; j <= bL; j++) {
    for (let i = 1; i <= aL; i++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      dp[j][i] = Math.min(
        dp[j][i - 1] + 1,
        dp[j - 1][i] + 1,
        dp[j - 1][i - 1] + cost
      );
    }
  }
  return dp[bL][aL];
}

// Fuzzy match a player name against a list
function fuzzyMatchPlayer(input, franchisePlayers) {
  const normalized = input.toLowerCase().trim();
  let bestMatch = null;
  let bestDistance = Infinity;

  franchisePlayers.forEach(p => {
    const playerName = p.name.toLowerCase();
    const distance = levenshteinDistance(normalized, playerName);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestMatch = p;
    }
  });

  // Only match if distance is reasonable (< 3 chars off)
  if (bestDistance <= 3) {
    return bestMatch;
  }
  return null;
}

// Calculate obscurity score (0-100, higher = more obscure)
function calculateObscurityScore(player) {
  let score = 50; // baseline

  // Games played: fewer = more obscure
  if (player.careerGames < 100) score += 30;
  else if (player.careerGames < 300) score += 20;
  else if (player.careerGames < 600) score += 10;
  else score -= 10;

  // PPG: lower = more obscure
  if (player.careerPPG < 5) score += 25;
  else if (player.careerPPG < 10) score += 15;
  else if (player.careerPPG < 15) score += 5;
  else if (player.careerPPG > 25) score -= 20;

  // Draft: undrafted/late = more obscure
  if (player.draftRound === 2) score += 15;
  else if (player.draftRound > 2) score += 25;

  // All-Star: any appearance = less obscure
  if (player.allStarAppearances > 0) {
    score -= player.allStarAppearances * 5;
  }

  // Clamp to 1-99 (save 0 and 100 for edge cases)
  return Math.max(1, Math.min(99, score));
}

// Main game logic
export function submitPlayerGuess(input, teamName, players) {
  const franchise = Object.keys(players).find(f => f.toLowerCase() === teamName.toLowerCase());
  if (!franchise) return { success: false, error: 'Team not found' };

  const franchisePlayers = players[franchise];
  const matched = fuzzyMatchPlayer(input, franchisePlayers);

  if (!matched) {
    return { success: false, error: 'Player not found on this team' };
  }

  const score = calculateObscurityScore(matched);
  return { success: true, player: matched, score, franchise };
}
