/**
 * Drive an Archonum remote browser over CDP (Node.js + Playwright).
 *
 * There is no local browser here — Archonum *is* the browser. We connect out
 * to it over the Chrome DevTools Protocol (CDP), navigate, and screenshot.
 *
 * Two ways to get a CDP endpoint:
 *
 *   browsers (default) — ask the Archonum API for a per-country browser:
 *       GET {ARCHONUM_BASE_URL}/api/v1/browsers/?country=..&session=..
 *         Authorization: Token {ARCHONUM_TOKEN}
 *       -> endpoint_url
 *     Needs: ARCHONUM_TOKEN, ARCHONUM_COUNTRY
 *
 *   gateway — resolve a websocket debugger URL from the CDP gateway:
 *       GET {ARCHONUM_CDP_BASE_URL}/json/version?username=..&password=..
 *       -> webSocketDebuggerUrl
 *     Needs: ARCHONUM_CDP_BASE_URL, ARCHONUM_CDP_USERNAME, ARCHONUM_CDP_PASSWORD
 *
 * Mode auto-selects from whichever credentials are set; override with CDP_MODE.
 */

import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { chromium } from 'playwright';

const DEFAULT_BASE_URL = 'https://app.archonum.com';
const DEFAULT_CDP_BASE_URL = 'http://app.archonum.com:10900';

const TARGET_URL = process.env.TARGET_URL || 'https://creepjs.org/checker';
const OUTPUT_DIR = process.env.OUTPUT_DIR || 'out';
const CONNECT_TIMEOUT_MS = Number(process.env.CONNECT_TIMEOUT_MS) || 30000;
const CONNECT_RETRIES = Number(process.env.CONNECT_RETRIES) || 5;
// creepjs computes a fingerprint/trust score client-side, which takes a while.
const PAGE_SETTLE_MS = Number(process.env.PAGE_SETTLE_MS) || 15000;

const withCreds = (url, username, password) => {
  const u = new URL(url);
  u.searchParams.set('username', username);
  u.searchParams.set('password', password);
  return u.toString();
};

const redact = (url) => {
  const u = new URL(url);
  for (const k of ['username', 'password']) if (u.searchParams.has(k)) u.searchParams.set(k, '***');
  return u.toString();
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function getJson(url, headers = {}) {
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status} from ${redact(url)}`);
  return res.json();
}

/** browsers mode: ask the Archonum API for a per-country CDP endpoint. */
async function resolveBrowsers() {
  const token = process.env.ARCHONUM_TOKEN;
  const country = (process.env.ARCHONUM_COUNTRY || '').toLowerCase();
  if (!token || !country) throw new Error('set ARCHONUM_TOKEN and ARCHONUM_COUNTRY');
  const base = (process.env.ARCHONUM_BASE_URL || DEFAULT_BASE_URL).replace(/\/$/, '');
  const session = process.env.ARCHONUM_SESSION || 'example';

  const url = `${base}/api/v1/browsers/?country=${country}&session=${session}`;
  console.log(`fetching Archonum browser -> ${url}`);
  const body = await getJson(url, { Authorization: `Token ${token}` });
  if (!body.endpoint_url) throw new Error(`Archonum returned no CDP endpoint for ${country}`);
  console.log(`  country=${body.country || country.toUpperCase()} ${body.country_name || ''}`);
  return body.endpoint_url;
}

/** gateway mode: read the ws debugger URL from the CDP gateway. */
async function resolveGateway() {
  const base = (process.env.ARCHONUM_CDP_BASE_URL || DEFAULT_CDP_BASE_URL).replace(/\/$/, '');
  const username = process.env.ARCHONUM_CDP_USERNAME;
  const password = process.env.ARCHONUM_CDP_PASSWORD;
  if (!username || !password) throw new Error('set ARCHONUM_CDP_USERNAME and ARCHONUM_CDP_PASSWORD');

  const versionUrl = withCreds(`${base}/json/version`, username, password);
  console.log(`fetching CDP version -> ${redact(versionUrl)}`);
  const body = await getJson(versionUrl);
  if (!body.webSocketDebuggerUrl) throw new Error('CDP version metadata had no webSocketDebuggerUrl');
  console.log(`  Browser=${body.Browser || '?'}`);
  return withCreds(body.webSocketDebuggerUrl, username, password);
}

async function resolveEndpoint() {
  const mode = process.env.CDP_MODE || (process.env.ARCHONUM_TOKEN ? 'browsers' : 'gateway');
  console.log(`mode: ${mode}`);
  return mode === 'browsers' ? resolveBrowsers() : resolveGateway();
}

/** connectOverCDP, retrying transient 502s while the browser spins up. */
async function connectWithRetry(endpoint) {
  for (let attempt = 1; attempt <= CONNECT_RETRIES; attempt++) {
    try {
      return await chromium.connectOverCDP(endpoint, { timeout: CONNECT_TIMEOUT_MS });
    } catch (e) {
      if (!String(e).includes('502') || attempt === CONNECT_RETRIES) throw e;
      const wait = Math.min(2 ** attempt, 8);
      console.log(`  connect attempt ${attempt} got 502, retrying in ${wait}s...`);
      await sleep(wait * 1000);
    }
  }
}

/**
 * Find the card containing `heading`, scroll it to the top, screenshot that
 * screenful, and pull the numbers out of the card's text. Generic: anchors on
 * the leaf element whose own text is the heading, then climbs to the smallest
 * ancestor holding the panel's "Total Collectors" summary.
 */
async function capturePanel(page, heading, clip, outPath) {
  const handle = await page.evaluateHandle((h) => {
    const want = h.toLowerCase();
    const node = [...document.querySelectorAll('*')].find(
      (e) => e.childElementCount === 0 && (e.textContent || '').trim().toLowerCase() === want,
    );
    if (!node) return null;
    let el = node;
    while (el.parentElement && !/Total Collectors/i.test(el.textContent || '')) el = el.parentElement;
    return el;
  }, heading);
  const element = handle.asElement();
  if (!element) return null;

  const text = await element.innerText();
  await element.evaluate((el) => el.scrollIntoView({ block: 'start' }));
  await page.waitForTimeout(500);
  await page.screenshot({ path: outPath, animations: 'disabled', clip });

  const num = (re) => text.match(re)?.[1] ?? null;
  return {
    coverage: num(/([\d.]+)%\s+Coverage/i),
    successful: num(/(\d+)\s+Successful/i),
    failed: num(/(\d+)\s+Failed/i),
    skipped: num(/(\d+)\s+Skipped/i),
    total_collectors: num(/(\d+)\s+Total Collectors/i),
    total_time: num(/([\d.]+ms)\s+Total Time/i),
    avg_per_attempt: num(/([\d.]+ms)\s+Avg/i),
  };
}

async function main() {
  await mkdir(OUTPUT_DIR, { recursive: true });
  const endpoint = await resolveEndpoint();

  console.log(`connecting over CDP -> ${redact(endpoint)}`);
  const browser = await connectWithRetry(endpoint);

  // The remote browser already has a context + page open; reuse them.
  const context = browser.contexts()[0] || (await browser.newContext());
  const page = context.pages()[0] || (await context.newPage());

  console.log(`navigating -> ${TARGET_URL}`);
  await page.goto(TARGET_URL, { waitUntil: 'load', timeout: CONNECT_TIMEOUT_MS });
  await page.waitForTimeout(PAGE_SETTLE_MS);

  const title = await page.title();
  const bodyText = (await page.evaluate(() => document.body.innerText.slice(0, 500))).trim();
  console.log(`  title -> ${title}`);
  console.log(`  body  -> ${bodyText}`);

  // The remote browser is a mobile device whose layout viewport is larger than
  // the physical screen, so a default capture tiles the page. Clip to the
  // device screen to get one clean screenful.
  const vp = await page.evaluate(() => ({ sw: screen.width, sh: screen.height }));
  const clip = { x: 0, y: 0, width: vp.sw, height: vp.sh };

  const shot = join(OUTPUT_DIR, 'screenshot.png');
  await page.screenshot({ path: shot, animations: 'disabled', clip });
  console.log(`  shot  -> ${shot}`);

  // On the creepjs checker, grab the "Collector Coverage" summary panel.
  let coverage = null;
  if (TARGET_URL.toLowerCase().includes('creepjs')) {
    const covShot = join(OUTPUT_DIR, 'collector-coverage.png');
    coverage = await capturePanel(page, 'Collector Coverage', clip, covShot);
    if (coverage) {
      console.log(`  coverage -> ${JSON.stringify(coverage)}`);
      console.log(`  panel    -> ${covShot}`);
    } else {
      console.log('  Collector Coverage panel not found');
    }
  }

  const result = {
    endpoint: redact(endpoint),
    target: TARGET_URL,
    url: page.url(),
    title,
    body: bodyText,
    screenshot: shot,
    collector_coverage: coverage,
  };
  await writeFile(join(OUTPUT_DIR, 'result.json'), JSON.stringify(result, null, 2) + '\n');
  console.log(`saved -> ${join(OUTPUT_DIR, 'result.json')}`);

  await browser.close();
}

main().catch((e) => {
  console.error(e.message || e);
  process.exit(1);
});
