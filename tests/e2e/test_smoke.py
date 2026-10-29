"""
Browser smoke tests for the web frontend (Playwright, Chromium).

Starts the real API on a spare port and checks that the app loads, every tab renders,
data views carry a provenance badge, a 503 becomes a visible "Data unavailable" state,
the app still loads with the API unreachable, and offline demo mode is clearly labelled.

    pip install -e ".[e2e]" && playwright install chromium
    pytest tests/e2e -q --no-cov
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]
TABS = [
    "overview",
    "predict",
    "explorer",
    "cube",
    "uncertainty",
    "ablation",
    "experiments",
    "explain",
    "cards",
]
API_PATH = re.compile(
    r"^https?://[^/]+/(health|ready|meta|predict|predict_batch|grid|explain|validation(/profile)?)(\?.*)?$"
)
PREDICT_PATH = re.compile(r"^https?://[^/]+/predict\?.*$")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "aquasphere.serve.app:app",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        # Offline: tests must not depend on NOAA being reachable from the CI runner
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "AQUASPHERE_OFFLINE": "1"},
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
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # still busy with a request: don't hang the suite
            proc.kill()
            proc.wait(timeout=10)


# Module scope: the sync Playwright API runs an event loop for as long as it is open, which
# would break async tests elsewhere in the suite if it stayed alive for the whole session.
@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(
                args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
            )
        except Exception as exc:  # browsers not installed
            pytest.skip(f"Chromium not available: {exc}")
        yield b
        b.close()


@pytest.fixture()
def page(browser: Browser) -> Iterator[Page]:
    ctx = browser.new_context(viewport={"width": 1366, "height": 860}, reduced_motion="reduce")
    pg = ctx.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.errors = errors  # type: ignore[attr-defined]
    yield pg
    ctx.close()


def _errors(page: Page) -> list[str]:
    return list(getattr(page, "errors", []))


def _open(page: Page, base_url: str, tab: str) -> None:
    page.goto(f"{base_url}/#/{tab}")
    page.wait_for_selector(f'.page[data-tab="{tab}"]', timeout=15000)


def test_app_loads(page: Page, base_url: str) -> None:
    _open(page, base_url, "overview")
    assert page.title() == "AquaSphere"
    assert page.locator("#nav a").count() == len(TABS)
    # "degraded" = API up but no trained checkpoint (CI): honest, and still a working app
    page.wait_for_selector(
        '#status-pill[data-state="ok"], #status-pill[data-state="degraded"]', timeout=15000
    )
    page.wait_for_selector("#date-picker:not([disabled])", timeout=15000)
    assert not _errors(page)


@pytest.mark.parametrize("tab", TABS)
def test_each_tab_renders(page: Page, base_url: str, tab: str) -> None:
    _open(page, base_url, tab)
    page.wait_for_timeout(1500)
    assert page.locator("text=This view failed to load").count() == 0
    assert page.locator(f'.nav__link[data-id="{tab}"][aria-current="page"]').count() == 1
    assert not _errors(page), _errors(page)


@pytest.mark.parametrize(
    ("tab", "selector"),
    [
        ("overview", '.badge[data-source="results"]'),
        ("predict", '.card .badge[data-source]:not([data-source="pending"])'),
        ("explorer", ".card__meta .badge[data-source]"),
        ("ablation", '.badge[data-source="results"]'),
        ("experiments", '.badge[data-source="results"]'),
        ("experiments", '.badge[data-source="pending"]'),
        ("cards", '.badge[data-source="results"]'),
    ],
)
def test_source_badges_present(page: Page, base_url: str, tab: str, selector: str) -> None:
    _open(page, base_url, tab)
    page.wait_for_selector(selector, timeout=30000)


def test_503_shows_data_unavailable(page: Page, base_url: str) -> None:
    body = json.dumps({"detail": "Surface satellite observation unavailable (test)."})
    page.route(
        PREDICT_PATH,
        lambda r: r.fulfill(status=503, content_type="application/json", body=body),
    )
    _open(page, base_url, "predict")
    page.wait_for_selector('.state--error[data-error-kind="unavailable"]', timeout=15000)
    assert page.locator("text=Data unavailable").count() >= 1
    assert page.locator('.badge[data-source="unavailable"]').count() >= 1
    # nothing filled in: no stat tiles rendered
    assert page.locator('[data-ref="stats"] .stat__value').count() == 0


def test_loads_with_api_unreachable(page: Page, base_url: str) -> None:
    page.route(API_PATH, lambda r: r.abort())
    _open(page, base_url, "overview")
    page.wait_for_selector('#status-pill[data-state="down"]', timeout=15000)
    page.goto(f"{base_url}/#/predict")
    page.wait_for_selector('.state--error[data-error-kind="offline"]', timeout=20000)
    assert not _errors(page)


AXE = Path(__file__).parent / "vendor" / "axe.min.js"  # axe-core 4.10.2, vendored for offline CI
AXE_RUN = """async () => {
  const r = await axe.run(document, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
  });
  return r.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id} (${v.impact}) x${v.nodes.length}: ${v.nodes[0].target.join(' ')}`);
}"""


def _axe_violations(page: Page) -> list[str]:
    page.add_script_tag(path=str(AXE))
    return list(page.evaluate(AXE_RUN))


@pytest.mark.parametrize("tab", TABS)
def test_no_serious_accessibility_violations(page: Page, base_url: str, tab: str) -> None:
    _open(page, base_url, tab)
    page.wait_for_timeout(2500)  # let async cards and charts render
    assert _axe_violations(page) == []


def test_offline_state_is_accessible(page: Page, base_url: str) -> None:
    page.route(API_PATH, lambda r: r.abort())
    _open(page, base_url, "predict")
    page.wait_for_selector('.state--error[data-error-kind="offline"]', timeout=20000)
    assert _axe_violations(page) == []


def test_shareable_link_restores_the_view(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/#/predict?lat=18.50&lon=88.25&mode=nowcast")
    page.wait_for_selector('.page[data-tab="predict"]', timeout=15000)
    page.wait_for_function(
        "document.querySelector('[data-ref=sub]').textContent.includes('18.50')", timeout=15000
    )
    assert page.get_attribute('#mode-switch [aria-checked="true"]', "data-mode") == "nowcast"
    assert "lat=18.50" in page.url and "mode=nowcast" in page.url


def test_invalid_link_parameters_are_ignored(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/#/predict?lat=99&lon=88&date=2031-01-01")
    page.wait_for_selector('.page[data-tab="predict"]', timeout=15000)
    page.wait_for_timeout(1500)
    assert "lat=99" not in page.url
    assert "2031-01-01" not in page.url
    assert not _errors(page)


def test_offline_demo_is_labelled(page: Page, base_url: str) -> None:
    page.route(API_PATH, lambda r: r.abort())
    page.add_init_script("localStorage.setItem('aquasphere.prefs', JSON.stringify({demo: true}))")
    _open(page, base_url, "predict")
    page.wait_for_selector('.badge[data-source="demo_synthetic"]', timeout=15000)
    assert page.locator("#demo-banner").is_visible()
    assert page.locator("#demo-badge").is_visible()
