"""Tiny JSON disk cache + HTTP helper shared by the RxNorm and openFDA clients.

Every lookup is cached under data/cache/, so a demo replays offline and the public
APIs (openFDA allows ~1000 unauthenticated calls/day per IP) are hit at most once
per drug. Set MEDSCAN_OFFLINE=1 to forbid network access and use the cache only.
"""
import json
import os
import time
from pathlib import Path

import requests

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


class SourceUnavailable(RuntimeError):
    """The public data source could not be reached (or offline with a cache miss)."""


class Cache:
    def __init__(self, name: str):
        self.path = CACHE_DIR / f"{name}.json"
        try:
            self.data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value

    def save(self):
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=1, sort_keys=True))
        except OSError:
            pass  # read-only filesystem: the in-memory copy still works


def offline() -> bool:
    return os.environ.get("MEDSCAN_OFFLINE") == "1"


def get_json(url: str, params: dict | None = None, retries: int = 2) -> dict | None:
    """GET -> parsed JSON. Returns None on 404 (openFDA's 'no results').
    Raises SourceUnavailable for anything else that goes wrong."""
    if offline():
        raise SourceUnavailable("offline mode and not in cache")
    err = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 404:
                return None
            if r.status_code == 429:
                err = "rate limited"
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            err = str(e)
            time.sleep(0.5 * (attempt + 1))
    raise SourceUnavailable(f"{url.split('?')[0]}: {err}")
