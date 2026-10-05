"""Local Chromium smoke test. Requires Python Playwright and a running Vite server.

Run: python scripts/qa_region_history.py
No simulation, paid service, hosting, or external artifact transfer is involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    parser.add_argument("--screenshots", type=Path, default=Path("/tmp/chronicler-region-qa"))
    args = parser.parse_args()
    if urlparse(args.url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Browser QA is restricted to a local server")
    fixture = Path(__file__).resolve().parents[1] / "src/__fixtures__/region_inspection_bundle.json"
    raw = fixture.read_bytes()
    args.screenshots.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=shutil.which("chromium"), headless=True, args=["--no-sandbox"]
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.goto(args.url)
        page.locator('input[type="file"]').first.set_input_files(fixture)
        disclosure = page.get_by_text("Inspect region history", exact=True)
        expect(disclosure).to_be_visible()
        expect(page.get_by_role("region", name="Region history inspector")).to_have_count(0)
        disclosure.click()
        panel = page.get_by_role("region", name="Region history inspector")
        expect(panel).to_be_visible()
        expect(panel.get_by_text(f"SHA-256: {hashlib.sha256(raw).hexdigest()}", exact=True)).to_be_visible()
        expect(panel.get_by_role("status")).to_contain_text("2 recorded values · 1 missing values · 2 turns without observations")
        expect(panel.get_by_role("table", name="Region history events").get_by_role("row")).to_have_count(2)
        panel.get_by_label("Include controller event context").check()
        expect(panel.get_by_text("Controller context; region unrecorded", exact=True)).to_have_count(2)
        panel.get_by_label("From turn").fill("3")
        panel.get_by_label("Through turn").fill("3")
        expect(panel.get_by_role("status")).to_contain_text("1 recorded values · 0 missing values")
        panel.get_by_label("Metric", exact=True).select_option("ecology:water")
        expect(panel.get_by_text("Metric not recorded", exact=True)).to_be_visible()
        panel.get_by_label("Region", exact=True).select_option("Upland")
        expect(panel.get_by_text("Upland trade: A different region.", exact=True)).to_be_visible()
        panel.get_by_label("Event type").select_option("drought")
        expect(panel.get_by_text("No events in this window.", exact=True)).to_be_visible()
        panel.get_by_label("Region", exact=True).select_option("Delta/~east")
        panel.get_by_label("From turn").fill("5")
        panel.get_by_label("Through turn").fill("5")
        panel.get_by_label("Metric", exact=True).select_option("stockpile:salt")
        expect(panel.get_by_role("status")).to_contain_text("1 recorded values · 1 missing values")
        expect(panel.get_by_text("7", exact=True)).to_be_visible()
        expect(panel.get_by_text("/world_state/regions/0/stockpile/goods/salt", exact=True)).to_be_visible()
        panel.get_by_role("button", name="Inspect turn 5").last.click()
        expect(page.locator(".phase75-topbar")).to_contain_text("5 / 5")
        panel.get_by_label("Metric", exact=True).select_option("stockpile:grain")
        expect(panel.get_by_text("0", exact=True)).to_be_visible()
        panel.get_by_label("From turn").fill("6")
        expect(panel.get_by_role("alert")).to_be_visible()
        expect(panel.get_by_role("table")).to_have_count(0)

        # A second artifact has the same run metadata but a different raw identity.
        bom_raw = b"\xef\xbb\xbf" + raw
        page.locator('input[type="file"]').first.set_input_files(
            {"name": "fixture-bom.json", "mimeType": "application/json", "buffer": bom_raw}
        )
        expect(panel.get_by_text(f"SHA-256: {hashlib.sha256(bom_raw).hexdigest()}", exact=True)).to_be_visible()
        expect(panel.get_by_role("status")).to_contain_text("2 recorded values · 1 missing values")
        panel.screenshot(path=str(args.screenshots / "desktop.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        panel.scroll_into_view_if_needed()
        assert panel.bounding_box()["x"] + panel.bounding_box()["width"] <= 391
        expect(panel.get_by_label("Region", exact=True)).to_be_visible()
        # Wide tables scroll within the panel rather than shrinking source paths.
        table_scroll = panel.locator(".region-history-table").first
        assert table_scroll.evaluate("el => el.scrollWidth > el.clientWidth")
        table_scroll.evaluate("el => el.scrollLeft = el.scrollWidth")
        expect(panel.get_by_text("/history/0/ecology/Delta~1~0east/soil", exact=True)).to_be_visible()
        table_scroll.evaluate("el => el.scrollLeft = 0")
        panel.screenshot(path=str(args.screenshots / "mobile.png"))

        # Intercepted local stream exercises the actual App/live connection path.
        live_page = browser.new_page()
        live_page.on("pageerror", lambda error: errors.append(str(error)))
        init = json.loads(raw)
        init.update({"type": "init", "state": "running"})
        init["history"] = init["history"][:2]
        init["metadata"]["total_turns"] = 100
        sockets = []

        def stream(route):
            sockets.append(route)
            route.send(json.dumps(init))

        live_page.route_web_socket("**/qa-stream", stream)
        live_page.goto(args.url + "/?ws=ws://127.0.0.1:5173/qa-stream")
        expect(live_page.locator(".phase75-topbar")).to_contain_text("3 / 100")
        expect(live_page.get_by_text("Inspect region history", exact=True)).to_have_count(0)
        sockets[-1].send(json.dumps({"type": "turn", **json.loads(raw)["history"][2]}))
        expect(live_page.locator(".phase75-topbar")).to_contain_text("5 / 100")
        assert not errors, errors
        browser.close()
        print("PASS: local Chromium desktop/mobile, original-byte SHA-256 including BOM, collapsed default, "
              "region/metric/time/event filters, zeros/missing/final-only goods, exact endpoint navigation, "
              "invalid ranges, artifact reset, live inspector exclusion/received-turn following; no page or console errors.")


if __name__ == "__main__":
    main()
