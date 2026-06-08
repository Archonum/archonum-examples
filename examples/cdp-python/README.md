# CDP — Python

Drive an Archonum **remote browser** over the Chrome DevTools Protocol (CDP)
with [Playwright](https://playwright.dev/python/). There is no local browser —
Archonum *is* the browser. We connect out to it, navigate, and screenshot.

## Two ways to get a CDP endpoint

| Mode | How | Needs |
|------|-----|-------|
| `browsers` *(default)* | Ask the Archonum API for a per-country browser | `ARCHONUM_TOKEN`, `ARCHONUM_COUNTRY` |
| `gateway` | Resolve a ws debugger URL from the CDP gateway | `ARCHONUM_CDP_BASE_URL`, `ARCHONUM_CDP_USERNAME`, `ARCHONUM_CDP_PASSWORD` |

The mode auto-selects from whichever credentials are set. Override with `CDP_MODE`.

## Run with Docker

```bash
cp .env.example .env   # fill in your credentials
docker compose up --build
```

Screenshot + `result.json` land in `./out`.

## Run locally

```bash
pip install -r requirements.txt
export ARCHONUM_TOKEN=...  ARCHONUM_COUNTRY=us
python cdp_example.py
```

Connecting over CDP does **not** download a local Chromium.

## Config

| Variable | Default | Purpose |
|----------|---------|---------|
| `TARGET_URL` | `https://creepjs.org/checker` | Page to open |
| `CDP_MODE` | auto | Force `browsers` or `gateway` |
| `OUTPUT_DIR` | `out` | Where the screenshot + result land |
| `ARCHONUM_BASE_URL` | `https://app.archonum.com` | API base (browsers mode) |

## Output

In `out/`:

- `screenshot.png` — the target page, one mobile screenful.
- `result.json` — page url, title, and a summary.

When the target is the creepjs checker (the default), it also captures the
**Collector Coverage** panel as `collector-coverage.png` and parses its numbers
(coverage %, successful / failed / skipped, total collectors, timing) into the
`collector_coverage` field of `result.json`.
