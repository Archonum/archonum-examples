# Proxy — Python

Route HTTP requests through an Archonum **per-country proxy** using
[`requests`](https://requests.readthedocs.io/). Ask the API for a proxy, then
make a normal request through it — the exit IP comes out in the chosen country.

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
pip install -r requirements.txt
export ARCHONUM_TOKEN=...  ARCHONUM_COUNTRY=us
python proxy_example.py
```

## Config

| Variable | Default | Purpose |
|----------|---------|---------|
| `ARCHONUM_TOKEN` | — | API token (required) |
| `ARCHONUM_COUNTRY` | — | Exit country, e.g. `us` (required) |
| `TARGET_URL` | `https://api.ipify.org?format=json` | URL to request through the proxy |
| `ARCHONUM_BASE_URL` | `https://app.archonum.com` | API base |

The same proxy works with any HTTP client — set the standard
`HTTP_PROXY`/`HTTPS_PROXY` env vars to `http://user:pass@host:port` to route a
whole tool through it.
