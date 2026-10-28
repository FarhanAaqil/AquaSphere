"""
Browser smoke tests for the web frontend (Playwright, Chromium).

Starts the real API on a spare port and checks that the app loads, every tab renders,
data views carry a provenance badge, a 503 becomes a visible "Data unavailable" state,
the app still loads with the API unreachable, and offline demo mode is clearly labelled.

    pytest tests/e2e -q -p no:cacheprovider --no-cov
    (needs: pip install playwright && playwright install chromium)
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]
TABS = ["overview", "predict", "explorer", "cube", "uncertainty", "ablation", "experiments", "explain", "cards"]
API_PATH = re.compile(r"^https?://[^/]+/(health|ready|meta|predict|predict_batch|grid|explain|validation(/profile)?)(\?.*)?$")
PREDICT_PATH = re.compile(r"^https?://[^/]+/predict\?.*$")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "aquasphere.serve.app:app", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")},
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(f"{url}/health", timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        else:
            pytest.skip("API server did not start")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


# Module scope: the sync Playwright API runs an event loop for as long as it is open, which
# would break async tests elsewhere in the suite if it stayed alive for the whole session.
@pytest.fixture(scope="module")
def browser() -> Iterator[object]:
    with playwright_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        except Exception as exc:  # browsers not installed
            pytest.skip(f"Chromium not available: {exc}")
        yield b
        b.close()


@pytest.fixture()
def page(browser: object) -> Iterator[object]:
    ctx = browser.new_context(viewport={"width": 1366, "height": 860}, reduced_motion="reduce")  # type: ignore[attr-defined]
    pg = ctx.new_page()
    pg.errors = []  # type: ignore[attr-defined]
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))  # type: ignore[attr-defined]
    yield pg
    ctx.close()


def _open(page: object, base_url: str, tab: str) -> None:
    page.goto(f"{base_url}/#/{tab}")  # type: ignore[attr-defined]
    page.wait_for_selector(f'.page[data-tab="{tab}"]', timeout=15000)  # type: ignore[attr-defined]


def test_app_loads(page: object, base_url: str) -> None:
    _open(page, base_url, "overview")
    assert page.title() == "AquaSphere"  # type: ignore[attr-defined]
    assert page.locator("#nav a").count() == len(TABS)  # type: ignore[attr-defined]
    page.wait_for_selector('#status-pill[data-state="ok"]', timeout=15000)  # type: ignore[attr-defined]
    page.wait_for_selector("#date-picker:not([disabled])", timeout=15000)  # type: ignore[attr-defined]
    assert not page.errors  # type: ignore[attr-defined]


@pytest.mark.parametrize("tab", TABS)
def test_each_tab_renders(page: object, base_url: str, tab: str) -> None:
    _open(page, base_url, tab)
    page.wait_for_timeout(1500)  # type: ignore[attr-defined]
    assert page.locator("text=This view failed to load").count() == 0  # type: ignore[attr-defined]
    assert page.locator(f'.nav__link[data-id="{tab}"][aria-current="page"]').count() == 1  # type: ignore[attr-defined]
    assert not page.errors, page.errors  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("tab", "selector"),
    [
        ("overview", '.badge[data-source="results"]'),
        ("predict", '.card .badge[data-source]:not([data-source="pending"])'),
        ("explorer", '.card__meta .badge[data-source]'),
        ("ablation", '.badge[data-source="results"]'),
        ("experiments", '.badge[data-source="results"]'),
        ("experiments", '.badge[data-source="pending"]'),
        ("cards", '.badge[data-source="results"]'),
    ],
)
def test_source_badges_present(page: object, base_url: str, tab: str, selector: str) -> None:
    _open(page, base_url, tab)
    page.wait_for_selector(selector, timeout=30000)  # type: ignore[attr-defined]


def test_503_shows_data_unavailable(page: object, base_url: str) -> None:
    detail = {"detail": "Surface satellite observation unavailable (test)."}
    page.route(PREDICT_PATH, lambda r: r.fulfill(status=503, content_type="application/json", body=json.dumps(detail)))  # type: ignore[attr-defined]
    _open(page, base_url, "predict")
    page.wait_for_selector('.state--error[data-error-kind="unavailable"]', timeout=15000)  # type: ignore[attr-defined]
    assert page.locator("text=Data unavailable").count() >= 1  # type: ignore[attr-defined]
    assert page.locator('.badge[data-source="unavailable"]').count() >= 1  # type: ignore[attr-defined]
    # nothing filled in: no stat tiles rendered
    assert page.locator('[data-ref="stats"] .stat__value').count() == 0  # type: ignore[attr-defined]


def test_loads_with_api_unreachable(page: object, base_url: str) -> None:
    page.route(API_PATH, lambda r: r.abort())  # type: ignore[attr-defined]
    _open(page, base_url, "overview")
    page.wait_for_selector('#status-pill[data-state="down"]', timeout=15000)  # type: ignore[attr-defined]
    page.goto(f"{base_url}/#/predict")  # type: ignore[attr-defined]
    page.wait_for_selector('.state--error[data-error-kind="offline"]', timeout=20000)  # type: ignore[attr-defined]
    assert not page.errors  # type: ignore[attr-defined]


def test_offline_demo_is_labelled(page: object, base_url: str) -> None:
    page.route(API_PATH, lambda r: r.abort())  # type: ignore[attr-defined]
    page.add_init_script("localStorage.setItem('aquasphere.prefs', JSON.stringify({demo: true}))")  # type: ignore[attr-defined]
    _open(page, base_url, "predict")
    page.wait_for_selector('.badge[data-source="demo_synthetic"]', timeout=15000)  # type: ignore[attr-defined]
    assert page.locator("#demo-banner").is_visible()  # type: ignore[attr-defined]
    assert page.locator("#demo-badge").is_visible()  # type: ignore[attr-defined]
