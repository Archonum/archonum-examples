"""
Drive an Archonum remote browser over CDP (Python + Playwright).

There is no local browser here — Archonum *is* the browser. We connect out to
it over the Chrome DevTools Protocol (CDP), navigate, and take a screenshot.

Two ways to get a CDP endpoint:

  browsers (default) — ask the Archonum API for a per-country browser:
      GET {ARCHONUM_BASE_URL}/api/v1/browsers/?country=..&session=..
        Authorization: Token {ARCHONUM_TOKEN}
      -> endpoint_url
    Needs: ARCHONUM_TOKEN, ARCHONUM_COUNTRY

  gateway — resolve a websocket debugger URL from the CDP gateway:
      GET {ARCHONUM_CDP_BASE_URL}/json/version?username=..&password=..
      -> webSocketDebuggerUrl
    Needs: ARCHONUM_CDP_BASE_URL, ARCHONUM_CDP_USERNAME, ARCHONUM_CDP_PASSWORD

Mode auto-selects from whichever credentials are set; override with CDP_MODE.
"""

import json
import os
import re
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from playwright.sync_api import sync_playwright

DEFAULT_BASE_URL = "https://app.archonum.com"
DEFAULT_CDP_BASE_URL = "http://app.archonum.com:10900"

TARGET_URL = os.environ.get("TARGET_URL", "https://creepjs.org/checker")
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "out"))
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT_MS", "10000")) / 1000
CONNECT_TIMEOUT_MS = float(os.environ.get("CONNECT_TIMEOUT_MS", "30000"))
CONNECT_RETRIES = int(os.environ.get("CONNECT_RETRIES", "5"))
# creepjs computes a fingerprint/trust score client-side, which takes a while.
PAGE_SETTLE_MS = float(os.environ.get("PAGE_SETTLE_MS", "15000"))


def _with_creds(url: str, username: str, password: str) -> str:
    """Append username/password query params to a URL."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["username"] = username
    query["password"] = password
    return urlunsplit(parts._replace(query=urlencode(query)))


def _redact(url: str) -> str:
    """Hide credentials before logging a URL."""
    parts = urlsplit(url)
    query = [(k, "***" if k in ("username", "password") else v)
             for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit(parts._replace(query=urlencode(query)))


def _get_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as res:
        return json.load(res)


def resolve_browsers() -> str:
    """browsers mode: ask the Archonum API for a per-country CDP endpoint."""
    token = os.environ.get("ARCHONUM_TOKEN")
    country = (os.environ.get("ARCHONUM_COUNTRY") or "").lower()
    if not token or not country:
        raise SystemExit("set ARCHONUM_TOKEN and ARCHONUM_COUNTRY")
    base = os.environ.get("ARCHONUM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    session = os.environ.get("ARCHONUM_SESSION", "example")

    url = f"{base}/api/v1/browsers/?country={country}&session={session}"
    print(f"fetching Archonum browser -> {url}")
    body = _get_json(url, {"Authorization": f"Token {token}"})
    endpoint = body.get("endpoint_url")
    if not endpoint:
        raise SystemExit(f"Archonum returned no CDP endpoint for {country}")
    print(f"  country={body.get('country', country.upper())} {body.get('country_name', '')}")
    return endpoint


def resolve_gateway() -> str:
    """gateway mode: read the ws debugger URL from the CDP gateway."""
    base = os.environ.get("ARCHONUM_CDP_BASE_URL", DEFAULT_CDP_BASE_URL).rstrip("/")
    username = os.environ.get("ARCHONUM_CDP_USERNAME")
    password = os.environ.get("ARCHONUM_CDP_PASSWORD")
    if not username or not password:
        raise SystemExit("set ARCHONUM_CDP_USERNAME and ARCHONUM_CDP_PASSWORD")

    version_url = _with_creds(f"{base}/json/version", username, password)
    print(f"fetching CDP version -> {_redact(version_url)}")
    body = _get_json(version_url)
    ws = body.get("webSocketDebuggerUrl")
    if not ws:
        raise SystemExit("CDP version metadata had no webSocketDebuggerUrl")
    print(f"  Browser={body.get('Browser', '?')}")
    return _with_creds(ws, username, password)


def resolve_endpoint() -> str:
    mode = os.environ.get("CDP_MODE")
    if not mode:
        mode = "browsers" if os.environ.get("ARCHONUM_TOKEN") else "gateway"
    print(f"mode: {mode}")
    return resolve_browsers() if mode == "browsers" else resolve_gateway()


def connect_with_retry(playwright, endpoint: str):
    """connect_over_cdp, retrying transient 502s while the browser spins up."""
    for attempt in range(1, CONNECT_RETRIES + 1):
        try:
            return playwright.chromium.connect_over_cdp(endpoint, timeout=CONNECT_TIMEOUT_MS)
        except Exception as e:  # noqa: BLE001 - retry only on transient gateway errors
            if "502" not in str(e) or attempt == CONNECT_RETRIES:
                raise
            wait = min(2 ** attempt, 8)
            print(f"  connect attempt {attempt} got 502, retrying in {wait}s...")
            time.sleep(wait)


def capture_panel(page, heading: str, clip: dict, out_path: Path) -> dict | None:
    """Find the card containing `heading`, scroll it to the top, screenshot that
    screenful, and pull the numbers out of the card's text. Generic: anchors on
    the leaf element whose own text is the heading, then climbs to the smallest
    ancestor holding the panel's "Total Collectors" summary."""
    handle = page.evaluate_handle(
        """(heading) => {
            const want = heading.toLowerCase();
            const node = [...document.querySelectorAll('*')].find(e =>
                e.childElementCount === 0 &&
                (e.textContent || '').trim().toLowerCase() === want);
            if (!node) return null;
            let el = node;
            while (el.parentElement && !/Total Collectors/i.test(el.textContent || ''))
                el = el.parentElement;
            return el;
        }""",
        heading,
    )
    element = handle.as_element()
    if not element:
        return None
    text = element.inner_text()
    element.evaluate("el => el.scrollIntoView({block: 'start'})")
    page.wait_for_timeout(500)
    page.screenshot(path=str(out_path), animations="disabled", clip=clip)

    def num(label_re: str):
        m = re.search(label_re, text, re.I)
        return m.group(1) if m else None

    return {
        "coverage": num(r"([\d.]+)%\s+Coverage"),
        "successful": num(r"(\d+)\s+Successful"),
        "failed": num(r"(\d+)\s+Failed"),
        "skipped": num(r"(\d+)\s+Skipped"),
        "total_collectors": num(r"(\d+)\s+Total Collectors"),
        "total_time": num(r"([\d.]+ms)\s+Total Time"),
        "avg_per_attempt": num(r"([\d.]+ms)\s+Avg"),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    endpoint = resolve_endpoint()

    with sync_playwright() as playwright:
        print(f"connecting over CDP -> {_redact(endpoint)}")
        browser = connect_with_retry(playwright, endpoint)

        # The remote browser already has a context + page open; reuse them.
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()

        print(f"navigating -> {TARGET_URL}")
        page.goto(TARGET_URL, wait_until="load", timeout=CONNECT_TIMEOUT_MS)
        page.wait_for_timeout(PAGE_SETTLE_MS)

        title = page.title()
        body_text = page.evaluate("() => document.body.innerText.slice(0, 500)")
        print(f"  title -> {title}")
        print(f"  body  -> {body_text.strip()}")

        # The remote browser is a mobile device whose layout viewport is larger
        # than the physical screen, so a default capture tiles the page. Clip to
        # the device screen to get one clean screenful.
        vp = page.evaluate(
            "() => ({iw: innerWidth, ih: innerHeight, sw: screen.width, sh: screen.height})"
        )
        print(f"  viewport -> inner={vp['iw']}x{vp['ih']} screen={vp['sw']}x{vp['sh']}")
        clip = {"x": 0, "y": 0, "width": vp["sw"], "height": vp["sh"]}

        shot = OUTPUT_DIR / "screenshot.png"
        page.screenshot(path=str(shot), animations="disabled", clip=clip)
        print(f"  shot  -> {shot}")

        # On the creepjs checker, grab the "Collector Coverage" summary panel.
        coverage = None
        if "creepjs" in TARGET_URL.lower():
            cov_shot = OUTPUT_DIR / "collector-coverage.png"
            coverage = capture_panel(page, "Collector Coverage", clip, cov_shot)
            if coverage:
                print(f"  coverage -> {coverage}")
                print(f"  panel    -> {cov_shot}")
            else:
                print("  Collector Coverage panel not found")

        result = {
            "endpoint": _redact(endpoint),
            "target": TARGET_URL,
            "url": page.url,
            "title": title,
            "body": body_text.strip(),
            "screenshot": str(shot),
            "collector_coverage": coverage,
        }
        (OUTPUT_DIR / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(f"saved -> {OUTPUT_DIR / 'result.json'}")

        browser.close()


if __name__ == "__main__":
    main()
