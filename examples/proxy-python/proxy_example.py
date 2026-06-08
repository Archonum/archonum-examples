"""
Route HTTP requests through an Archonum proxy (Python + requests).

Archonum hands out per-country HTTP proxies. We ask the API for one, then make
a normal request through it — the exit IP comes out in the chosen country.

  GET {ARCHONUM_BASE_URL}/api/v1/proxies/?country=..&session=..
    Authorization: Token {ARCHONUM_TOKEN}
  -> { host, http_port, username, password, country, session }

Needs: ARCHONUM_TOKEN, ARCHONUM_COUNTRY
"""

import json
import os

import requests

DEFAULT_BASE_URL = "https://app.archonum.com"
TARGET_URL = os.environ.get("TARGET_URL", "https://api.ipify.org?format=json")
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT_MS", "15000")) / 1000


def fetch_proxy() -> dict:
    """Ask the Archonum API for a per-country HTTP proxy."""
    token = os.environ.get("ARCHONUM_TOKEN")
    country = (os.environ.get("ARCHONUM_COUNTRY") or "").lower()
    if not token or not country:
        raise SystemExit("set ARCHONUM_TOKEN and ARCHONUM_COUNTRY")
    base = os.environ.get("ARCHONUM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    session = os.environ.get("ARCHONUM_SESSION", "example")

    url = f"{base}/api/v1/proxies/?country={country}&session={session}"
    print(f"fetching Archonum proxy -> {url}")
    res = requests.get(url, headers={"Authorization": f"Token {token}"}, timeout=HTTP_TIMEOUT)
    res.raise_for_status()
    body = res.json()
    if "error" in body:
        raise SystemExit(f"Archonum returned no proxy for {country}: {body['error']}")
    print(f"  proxy {body['host']}:{body['http_port']} country={body['country']}")
    return body


def proxy_url(proxy: dict) -> str:
    return f"http://{proxy['username']}:{proxy['password']}@{proxy['host']}:{proxy['http_port']}"


def main() -> None:
    proxy = fetch_proxy()
    proxies = {"http": proxy_url(proxy), "https": proxy_url(proxy)}

    print(f"requesting {TARGET_URL} through the proxy...")
    res = requests.get(TARGET_URL, proxies=proxies, timeout=HTTP_TIMEOUT)
    res.raise_for_status()
    print(f"  status -> {res.status_code}")
    print(f"  body   -> {res.text.strip()}")


if __name__ == "__main__":
    main()
