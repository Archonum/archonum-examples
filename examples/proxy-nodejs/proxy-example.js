/**
 * Route HTTP requests through an Archonum proxy (Node.js + fetch/undici).
 *
 * Archonum hands out per-country HTTP proxies. We ask the API for one, then
 * make a normal fetch through it — the exit IP comes out in the chosen
 * country. Node's global fetch doesn't speak proxies, so we route it through
 * undici's ProxyAgent (undici is Node's own HTTP client, added as a dependency
 * here so we can import ProxyAgent).
 *
 *   GET {ARCHONUM_BASE_URL}/api/v1/proxies/?country=..&session=..
 *     Authorization: Token {ARCHONUM_TOKEN}
 *   -> { host, http_port, username, password, country, session }
 *
 * Needs: ARCHONUM_TOKEN, ARCHONUM_COUNTRY
 */

import { ProxyAgent } from 'undici';

const DEFAULT_BASE_URL = 'https://app.archonum.com';
const TARGET_URL = process.env.TARGET_URL || 'https://api.ipify.org?format=json';

/** Ask the Archonum API for a per-country HTTP proxy. */
async function fetchProxy() {
  const token = process.env.ARCHONUM_TOKEN;
  const country = (process.env.ARCHONUM_COUNTRY || '').toLowerCase();
  if (!token || !country) throw new Error('set ARCHONUM_TOKEN and ARCHONUM_COUNTRY');
  const base = (process.env.ARCHONUM_BASE_URL || DEFAULT_BASE_URL).replace(/\/$/, '');
  const session = process.env.ARCHONUM_SESSION || 'example';

  const url = `${base}/api/v1/proxies/?country=${country}&session=${session}`;
  console.log(`fetching Archonum proxy -> ${url}`);
  const res = await fetch(url, { headers: { Authorization: `Token ${token}` } });
  if (!res.ok) throw new Error(`Archonum returned HTTP ${res.status}`);
  const body = await res.json();
  if (body.error) throw new Error(`Archonum returned no proxy for ${country}: ${body.error}`);
  console.log(`  proxy ${body.host}:${body.http_port} country=${body.country}`);
  return body;
}

async function main() {
  const proxy = await fetchProxy();
  // uri is the proxy address; token is the Proxy-Authorization header value.
  const dispatcher = new ProxyAgent({
    uri: `http://${proxy.host}:${proxy.http_port}`,
    token: `Basic ${Buffer.from(`${proxy.username}:${proxy.password}`).toString('base64')}`,
  });

  // Node's global fetch has no proxy option, so route it through the dispatcher.
  console.log(`requesting ${TARGET_URL} through the proxy...`);
  const res = await fetch(TARGET_URL, { dispatcher });
  const text = (await res.text()).trim();
  console.log(`  status -> ${res.status}`);
  console.log(`  body   -> ${text}`);
}

main().catch((e) => {
  console.error(e.message || e);
  process.exit(1);
});
