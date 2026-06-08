# Proxy — Node.js

Route HTTP requests through an Archonum **per-country proxy** using `fetch`.
Node's global `fetch` doesn't speak proxies, so we pass undici's `ProxyAgent`
as the dispatcher (undici is Node's own HTTP client; we add it as a dependency
to import `ProxyAgent`). Ask the API for a proxy, then make a normal fetch
through it — the exit IP comes out in the chosen country.

```
GET {ARCHONUM_BASE_URL}/api/v1/proxies/?country=..&session=..
  Authorization: Token {ARCHONUM_TOKEN}
-> { host, http_port, username, password, country, session }
```

## Run with Docker

```bash
cp .env.example .env   # fill in your credentials
docker compose up --build
```

## Run locally

```bash
npm install
export ARCHONUM_TOKEN=...  ARCHONUM_COUNTRY=us
npm start
```

Requires Node 24 (or any Node 18+ for global `fetch`).

## Config

| Variable            | Default                             | Purpose                            |
| ------------------- | ----------------------------------- | ---------------------------------- |
| `ARCHONUM_TOKEN`    | —                                   | API token (required)               |
| `ARCHONUM_COUNTRY`  | —                                   | Exit country, e.g. `us` (required) |
| `TARGET_URL`        | `https://api.ipify.org?format=json` | URL to request through the proxy   |
| `ARCHONUM_BASE_URL` | `https://app.archonum.com`          | API base                           |
