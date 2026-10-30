"""Offline app shell: the service worker and manifest are served correctly and the precache
list only names files that exist."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from aquasphere.serve.app import app

WEB = Path(__file__).resolve().parents[2] / "web"
client = TestClient(app)


def test_service_worker_is_served_from_the_root_and_revalidated() -> None:
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/javascript")
    assert r.headers["cache-control"] == "no-cache"
    assert r.headers["service-worker-allowed"] == "/"
    # health and readiness must never come from a saved copy
    assert "LIVE_ONLY" in r.text and "health|ready" in r.text


def test_manifest_is_installable() -> None:
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200
    m = r.json()
    assert m["display"] == "standalone" and m["icons"] and m["start_url"]


def test_precache_lists_existing_files_only() -> None:
    path = WEB / "data" / "precache.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["files"][0] == "index.html" and len(manifest["version"]) == 16
    missing = [f for f in manifest["files"] if not (WEB / f).is_file()]
    assert missing == []
    assert "sw.js" not in manifest["files"]


def test_precache_version_matches_the_current_files() -> None:
    """A stale version would leave returning visitors on old cached files: rebuild with
    `make ui-data` (scripts/build_web_data.py) after changing anything under web/."""
    import sys

    sys.path.insert(0, str(WEB.parent / "scripts"))
    from build_web_data import precache

    committed = json.loads((WEB / "data" / "precache.json").read_text(encoding="utf-8"))
    assert committed == precache()
