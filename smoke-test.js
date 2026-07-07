// Minimal pre-deploy smoke test.
//
// Loads the game, plays through one real Team Challenge guess, and fails the build
// if anything throws, logs a console error, or renders a stringified object like
// "[object HTMLDivElement]" into the page — the exact two bug classes that shipped
// to production before this test existed (a buildPlayerCard() return value passed
// through Array.join('') instead of appendChild, and a call to an undefined
// fuzzyDistance() in a since-removed code path).
//
// Usage: node smoke-test.js (expects the game to already be served at SMOKE_TEST_URL)
const { chromium } = require('playwright');

const URL = process.env.SMOKE_TEST_URL || 'http://localhost:8080';

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  const errors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(`console.error: ${msg.text()}`);
  });
  page.on('pageerror', (err) => errors.push(`uncaught exception: ${err.message}`));

  // Skip the how-to-play modal so the flow is deterministic.
  await page.addInitScript(() => {
    localStorage.setItem('tbn_htp_skip', '1');
  });

  await page.goto(URL, { waitUntil: 'networkidle' });

  await page.click('.team-challenge-btn');
  await page.waitForSelector('.team-select-btn');
  await page.click('.team-select-btn:has-text("Los Angeles Lakers")');

  await page.waitForSelector('#playerInput:not([disabled])', { timeout: 10000 });
  await page.fill('#playerInput', 'LeBron James');
  await page.click('#submitBtn');

  // Let the pick render (breakdown chips, lineup slot) before checking.
  await page.waitForTimeout(2000);

  const bodyHTML = await page.evaluate(() => document.body.innerHTML);
  if (bodyHTML.includes('[object ')) {
    throw new Error('Found a stringified object ("[object ...]") in the rendered page.');
  }

  const lineupHTML = await page.evaluate(() => document.getElementById('lineup').innerHTML);
  if (!lineupHTML.includes('LeBron James')) {
    throw new Error('LeBron James was not accepted into the lineup — guess submission may be broken.');
  }

  if (errors.length > 0) {
    throw new Error(`Console/runtime errors during smoke test:\n${errors.join('\n')}`);
  }

  console.log('Smoke test passed: game loads, accepts a valid guess, no console errors, no stringified objects.');
  await browser.close();
  process.exit(0);
}

main().catch((err) => {
  console.error('Smoke test FAILED:', err.message);
  process.exit(1);
});
