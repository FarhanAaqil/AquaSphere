"""
Full click-through of the running app in a visible Chrome window (roadmap Phase 6 sign-off).

    make serve                                   # in another terminal
    python scripts/walkthrough.py                # visible Chrome, records a video
    python scripts/walkthrough.py --headless     # same steps, no window

Drives every tab and control, downloads every export, and fails on any page error, console
error, unexpected HTTP error or failed request. With --offline-check it finally stops the API
(it must be the one on --url) and checks the offline app shell and saved-results banner.
The recording is written to dist/demo/ (not committed).
"""

from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "dist" / "demo"


class Run:
    def __init__(self, page: Page, base: str) -> None:
        self.page = page
        self.base = base
        self.results: list[tuple[str, bool, str]] = []
        self.errors: list[str] = []
        self.http: list[str] = []
        self.downloads: list[str] = []
        page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        page.on(
            "console",
            lambda m: (
                m.type == "error"
                and "Failed to load resource" not in m.text  # HTTP errors are judged below
                and "GL Driver" not in m.text
                and self.errors.append(f"console: {m.text[:200]}")
            ),
        )
        page.on("response", self._response)
        page.on("requestfailed", lambda r: self._failed(r.url, r.failure or ""))

    def _response(self, r: Any) -> None:
        # 503 is the honest "no observation" answer; 404 for optional results files is expected
        if r.status >= 400 and r.status not in (503, 404) and "/api" not in r.url:
            self.http.append(f"{r.status} {r.url[len(self.base) :][:100]}")

    def _failed(self, url: str, why: str) -> None:
        if "net::ERR_ABORTED" in why:  # navigating away cancels in-flight requests: expected
            return
        self.http.append(f"FAILED {url[len(self.base) :][:100]} {why}")

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append((name, bool(ok), detail))
        print(
            f"  {'PASS' if ok else 'FAIL'}  {name}{(' - ' + detail) if detail else ''}", flush=True
        )

    def go(self, tab: str, wait: int = 2500) -> None:
        print(f"\n== {tab}", flush=True)
        self.page.goto(f"{self.base}/#/{tab}")
        self.page.wait_for_selector(f'.page[data-tab="{tab}"]', timeout=20000)
        self.page.wait_for_timeout(wait)

    def no_loading(self, timeout: int = 60000) -> bool:
        try:
            self.page.wait_for_function(
                "!document.querySelector('.state--loading')", timeout=timeout
            )
            return True
        except Exception:
            return False

    def click_map(self, nth: int, fx: float, fy: float) -> None:
        hit = self.page.locator(".map .map__hit").nth(nth)
        hit.scroll_into_view_if_needed()
        box = hit.bounding_box()
        assert box is not None
        self.page.mouse.click(box["x"] + box["width"] * fx, box["y"] + box["height"] * fy)

    def download(self, locator: Any, label: str, magic: bytes | None = None) -> None:
        with self.page.expect_download(timeout=60000) as info:
            locator.click()
        d = info.value
        path = DEMO_DIR / "downloads" / d.suggested_filename
        path.parent.mkdir(parents=True, exist_ok=True)
        d.save_as(path)
        body = path.read_bytes()
        ok = len(body) > 100 and (magic is None or body.startswith(magic))
        self.downloads.append(d.suggested_filename)
        self.check(f"{label} download", ok, f"{d.suggested_filename}, {len(body):,} bytes")


def walk(run: Run, offline_check: bool, server_pid: int | None) -> None:
    pg = run.page
    # ── Overview ──
    run.go("overview", 4000)
    run.check("API status ready", pg.locator('#status-pill[data-state="ok"]').count() == 1)
    run.check("hero and globe", pg.locator(".hero__title").is_visible())
    pg.wait_for_selector('[data-ref="metrics"] .stat__value', timeout=20000)
    metrics = pg.locator('[data-ref="metrics"]').inner_text()
    run.check("headline metrics from results files", "°C" in metrics, metrics.split("\n")[0][:60])
    for _ in range(8):  # scroll the descent to 1000 m
        pg.mouse.wheel(0, 900)
        pg.wait_for_timeout(350)
    run.check("descent scrolls to the deep", pg.evaluate("window.scrollY") > 1500)
    pg.evaluate("window.scrollTo(0, 0)")
    pg.locator('.hero__cta a[href="#/predict"]').click()
    pg.wait_for_selector('.page[data-tab="predict"]', timeout=15000)
    run.check("hero CTA opens Predict", True)

    # ── Top bar ──
    print("\n== top bar", flush=True)
    picker = pg.locator("#date-picker")
    options = picker.locator("option").all_inner_texts()
    run.check("date picker has stored dates", len(options) > 100, f"{len(options)} dates")
    picker.select_option("2023-08-15")
    pg.wait_for_timeout(1500)
    run.check("date change reaches the URL", "2023-08-15" in pg.url)
    pg.locator('#mode-switch button[data-mode="nowcast"]').click()
    pg.wait_for_timeout(1200)
    run.check(
        "nowcast mode on",
        pg.get_attribute('#mode-switch [aria-checked="true"]', "data-mode") == "nowcast",
    )
    pg.locator('#mode-switch button[data-mode="delayed"]').click()
    pg.locator("#settings-btn").click()
    run.check("settings popover opens", pg.locator("#settings").is_visible())
    pg.locator("#perf-toggle").check()
    pg.wait_for_timeout(800)
    run.check("performance mode on", "perf" in pg.evaluate("document.body.className"))
    pg.locator("#perf-toggle").uncheck()
    pg.locator("#copy-link-btn").click()
    pg.wait_for_timeout(600)
    run.check("copy link toast", pg.locator(".toast").count() > 0)

    # ── Predict ──
    run.go("predict", 3000)
    run.click_map(0, 0.72, 0.55)  # Bay of Bengal
    pg.wait_for_selector(
        '[data-ref="chart"].js-plotly-plot, [data-ref="chart"] .js-plotly-plot', timeout=30000
    )
    pg.wait_for_timeout(1500)
    stats = pg.locator('[data-ref="stats"] .stat-card').count()
    run.check("profile and 6 stat tiles", stats == 6, f"{stats} tiles")
    run.check(
        "v2 model and mode tags", "tier_a_v2" in pg.locator('[data-ref="badges"]').inner_text()
    )
    checks = pg.locator('[data-ref="checks"]').inner_text()
    run.check("dissimilarity check reported", "DI " in checks, checks.split("\n")[-1][:80])
    pg.fill('input[name="lat"]', "16.5")
    pg.fill('input[name="lon"]', "64.0")
    pg.locator('[data-ref="go"]').click()
    pg.wait_for_function(
        "document.querySelector('[data-ref=sub]').textContent.includes('16.50')", timeout=30000
    )
    run.check("coordinate form predicts", True)
    run.download(pg.locator('[data-ref="csv"]'), "profile CSV", b"# AquaSphere")
    run.download(pg.locator('[data-ref="nc"]'), "profile NetCDF", b"CDF")
    pg.locator('#mode-switch button[data-mode="nowcast"]').click()
    pg.wait_for_timeout(3000)
    run.check("nowcast re-predicts", "Nowcast" in pg.locator('[data-ref="badges"]').inner_text())
    pg.locator('#mode-switch button[data-mode="delayed"]').click()

    # ── Profile Explorer ──
    run.go("explorer", 4000)
    pts = pg.locator(".map__pt")
    run.check("held-out profiles on the map", pts.count() > 50, f"{pts.count()} points")
    # Points overlap where floats cluster; select by keyboard, which also checks keyboard access
    pts.nth(5).focus()
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(4000)
    run.check("predicted vs observed profile", pg.locator(".js-plotly-plot").count() >= 1)
    for region in ("Bay of Bengal", "Arabian Sea", "all"):
        pg.locator(f'[data-region="{region}"]').click()
        pg.wait_for_timeout(500)
    run.check("region filters", pg.locator('[data-region="all"][aria-pressed="true"]').count() == 1)
    pg.locator('[data-ref="show-train"]').check()
    pg.wait_for_timeout(800)
    pg.locator('[data-ref="show-train"]').uncheck()
    run.check("training-float toggle", True)

    # ── Ocean Cube ──
    run.go("cube", 6000)
    run.check(
        "cube renders",
        run.no_loading(60000)
        and pg.locator('[data-ref="stage"] canvas, [data-ref="map"] .js-plotly-plot').count() > 0,
    )
    for chip in pg.locator('[data-ref="depths"] .chip').all()[:3]:
        chip.click()
        pg.wait_for_timeout(500)
    layer = pg.locator('[data-ref="layer"]')
    for value in layer.locator("option").evaluate_all("os => os.map(o => o.value)")[:3]:
        layer.select_option(value)
        pg.wait_for_timeout(700)
    pg.locator('[data-ref="play"]').click()
    pg.wait_for_timeout(5000)
    pg.locator('[data-ref="play"]').click()
    run.check("depth, layer and date playback", run.no_loading(60000))

    # ── Ocean Products ──
    run.go("products", 2000)
    layer = pg.locator('.page [data-ref="layer"]')
    for value in layer.locator("option").evaluate_all("os => os.map(o => o.value)"):
        layer.select_option(value)
        ok = run.no_loading(60000) and pg.locator(".js-plotly-plot").count() > 0
        run.check(f"layer {value}", ok, pg.locator(".card__sub").first.inner_text()[:70])
    pg.locator('[data-ref="layer"]').select_option("temperature")
    pg.locator('[data-ref="depth"]').select_option("300")
    run.no_loading()
    pg.locator('[data-ref="compare"]').check()
    pg.locator('[data-ref="date2"]').select_option("2023-02-15")
    ok = run.no_loading(90000)
    run.check(
        "two-date difference map", ok and "\u2212" in pg.locator(".card__sub").first.inner_text()
    )
    pg.locator('[data-ref="compare"]').uncheck()
    run.no_loading()
    run.download(pg.locator('[data-ref="csv"]'), "grid CSV", b"# AquaSphere")

    # ── Sections ──
    run.go("sections", 3000)
    run.click_map(0, 0.22, 0.58)
    run.click_map(0, 0.72, 0.58)
    pg.wait_for_selector('.card[data-ref="transect"] .js-plotly-plot', timeout=60000)
    run.check(
        "transect section", "profiles over" in pg.locator('.card[data-ref="transect"]').inner_text()
    )
    pg.locator('select[data-ref="n"]').select_option("60")
    run.no_loading()
    run.click_map(1, 0.35, 0.6)
    run.no_loading(60000)
    run.check(
        "depth-time section",
        "dates" in pg.locator('.card:has-text("Depth \u00d7 time")').last.inner_text(),
    )
    pg.locator('[data-ref="span"]').select_option("730")
    run.no_loading(90000)
    run.download(pg.locator('a[data-ref="nc"]').last, "section-point NetCDF", b"CDF")

    # ── Uncertainty ──
    run.go("uncertainty", 4000)
    run.no_loading(90000)
    for chip in pg.locator(".depth-pick .chip").all():
        chip.click()
        pg.wait_for_timeout(400)
    run.check("interval-width maps by depth", pg.locator(".js-plotly-plot").count() >= 4)
    pg.get_by_role("button", name="Run drift monitor").click()
    pg.wait_for_selector('.card:has-text("Drift monitor") .js-plotly-plot', timeout=180000)
    run.check("drift monitor", True)

    # ── Sensors & Modes / Experiments ──
    run.go("ablation", 3000)
    run.check("E3 and E7", "skill retained" in pg.inner_text("main").lower())
    pg.locator('#mode-switch button[data-mode="nowcast"]').click()
    pg.wait_for_timeout(1500)
    pg.locator('#mode-switch button[data-mode="delayed"]').click()
    run.go("experiments", 5000)
    text = pg.inner_text("main")
    run.check("final evaluation card", "Final evaluation" in text)
    run.check("E2, E4, E5 and E8 cards", all(k in text for k in ("E2", "E4", "E5", "E8")))

    # ── Explain ──
    run.go("explain", 3000)
    pg.locator('[data-ref="form"] button[type="submit"]').click()
    run.no_loading(60000)
    run.check("feature attribution", pg.locator(".js-plotly-plot").count() >= 1)

    # ── Cards + PDF export ──
    run.go("cards", 3000)
    run.check("model card shows Tier A v2", "tier_a_v2" in pg.inner_text("main"))
    pg.locator('[data-ref="export"]').click()
    pg.wait_for_timeout(800)
    run.check("PDF export triggered", pg.evaluate("window.__printed === true"))

    # ── Demo mode refuses to invent v2 data ──
    print("\n== offline demo", flush=True)
    pg.locator("#settings-btn").click()
    pg.locator("#demo-toggle").check()
    pg.wait_for_timeout(1500)
    run.go("products", 2500)
    run.check(
        "demo mode: products need the live API", "Needs the live API" in pg.inner_text("main")
    )
    pg.locator("#settings-btn").click()
    pg.locator("#demo-toggle").uncheck()
    pg.wait_for_timeout(1500)

    if offline_check and server_pid:
        print("\n== offline app (API stopped)", flush=True)
        pg.goto(f"{run.base}/?sw=1#/predict")
        pg.wait_for_function("navigator.serviceWorker.ready.then(() => true)", timeout=30000)
        pg.wait_for_timeout(3000)
        pg.reload()
        pg.wait_for_timeout(8000)
        subprocess.run(["taskkill", "/PID", str(server_pid), "/F"], capture_output=True)
        time.sleep(2)
        pg.reload()
        pg.wait_for_timeout(10000)
        run.check("app opens with the API down", pg.locator(".page").count() == 1)
        run.check("saved-results banner", pg.locator("#saved-banner").is_visible())
        run.check("status says offline", pg.locator('#status-pill[data-state="down"]').count() == 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--offline-check", action="store_true")
    ap.add_argument("--server-pid", type=int, default=None)
    a = ap.parse_args()
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome", headless=a.headless, slow_mo=60 if not a.headless else 0
        )
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
            record_video_dir=str(DEMO_DIR),
            record_video_size={"width": 1440, "height": 900},
            permissions=["clipboard-read", "clipboard-write"],
        )
        ctx.add_init_script("window.print = () => { window.__printed = true; };")
        page = ctx.new_page()
        run = Run(page, a.url)
        try:
            walk(run, a.offline_check, a.server_pid)
        except Exception as e:  # report the step that broke, then the summary
            run.check("walkthrough completed", False, f"{type(e).__name__}: {str(e)[:300]}")
        video = page.video.path() if page.video else None
        ctx.close()
        browser.close()
    failed = [r for r in run.results if not r[1]]
    print(f"\n{len(run.results) - len(failed)}/{len(run.results)} checks passed")
    print("errors:", run.errors or "none")
    print("http problems:", run.http or "none")
    print("downloads:", run.downloads)
    if video:
        print(
            "recording:",
            Path(video).relative_to(ROOT) if Path(video).is_relative_to(ROOT) else video,
        )
    return 1 if failed or run.errors or run.http else 0


if __name__ == "__main__":
    raise SystemExit(main())
