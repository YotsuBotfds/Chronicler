"""Bounded local Chromium QA of the isolated settlement fixture (no AppShell).

Run against npm run dev: python scripts/qa_settlement_inspector.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5173/settlement-inspector-demo.html")
    parser.add_argument("--evidence", type=Path, default=Path("/tmp/chronicler-settlement-qa"))
    args = parser.parse_args()
    if urlparse(args.url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("QA is restricted to a local server")
    args.evidence.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    checks: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which("chromium"), headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1280, "height": 1200})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.goto(args.url)
        status = page.get_by_role("status")
        slider = page.get_by_role("slider", name="Requested turn")

        def population(value: str) -> None:
            row = page.locator("dl > div").filter(has=page.locator("dt", has_text="Population estimate"))
            expect(row.locator("dd")).to_have_text(value)

        def screenshot(name: str) -> None:
            page.screenshot(path=str(args.evidence / f"{name}.png"), full_page=True)

        population("23")
        expect(page.get_by_text("1.25", exact=True)).to_be_visible()
        expect(page.get_by_text("-2.75", exact=True)).to_be_visible()
        screenshot("01-founded-desktop")
        slider.focus()
        slider.press("ArrowRight")
        expect(status).to_contain_text("Stale summary · source turn 2 · observation age 1 turns")
        population("31")
        screenshot("02-stale-keyboard")
        slider.press("ArrowRight")
        expect(status).to_contain_text("No historical snapshot recorded")
        expect(page.locator("dl")).to_have_count(0)
        screenshot("03-gap")
        slider.press("ArrowRight")
        expect(status).to_contain_text("Dissolution recorded")
        expect(page.locator("dl")).to_have_count(0)
        screenshot("04-dissolved")
        slider.press("Home")
        expect(status).to_contain_text("not listed in this snapshot")
        expect(page.get_by_role("heading", name="River Quay")).to_have_count(0)
        screenshot("05-before-founding")
        slider.press("ArrowRight")
        population("23")
        checks.append("keyboard scrub forward/back: founding, stale source/age, gap, recorded dissolution, before founding")

        select = page.get_by_role("combobox", name="Settlement")
        select.focus()
        select.press("ArrowDown")
        expect(select).to_have_value("9")
        expect(page.get_by_role("heading", name="Upper Ferry")).to_be_visible()
        population("40")
        select.press("ArrowUp")
        expect(select).to_have_value("7")
        select.press("Home")
        expect(select).to_have_value("")
        expect(status).to_contain_text("Select a positive whole settlement ID")
        select.press("ArrowDown")
        expect(select).to_have_value("7")
        checks.append("native keyboard selection, changed settlement identity/value, cleared selection")

        provenance = page.locator("summary", has_text="Source provenance")
        provenance.focus()
        provenance.press("Enter")
        expect(page.get_by_text("/history/1/active_settlements/0/population_estimate", exact=True)).to_be_visible()
        screenshot("06-provenance-keyboard")
        provenance.press("Space")
        expect(page.get_by_text("/history/1/active_settlements/0/population_estimate", exact=True)).not_to_be_visible()
        samples = page.locator("summary", has_text="Recorded population history")
        samples.focus()
        samples.press("Enter")
        expect(page.get_by_role("table", name="Settlement population observations")).to_be_visible()
        seek = page.get_by_role("button", name="Inspect settlement at turn 1")
        seek.focus()
        seek.press("Enter")
        expect(status).to_contain_text("As of turn 1")
        checks.append("keyboard Enter/Space on disclosures, provenance pointers, Enter on historical seek")

        # Rapid controlled updates and interrupt/reopen exercise state retention/reset.
        slider.focus()
        slider.press("ArrowRight")
        for _ in range(4):
            select.select_option("9")
            slider.focus()
            slider.press("End")
            expect(status).to_contain_text("Observation age unavailable")
            population("Unavailable — Not recorded")
            slider.press("Home")
            slider.press("ArrowRight")
            population("40")
            select.select_option("9")
            population("40")
            select.select_option("7")
            population("23")
        close = page.get_by_role("button", name="Close settlement inspector")
        close.focus()
        close.press("Enter")
        expect(page.get_by_role("status")).to_have_count(0)
        slider.focus()
        slider.press("ArrowRight")
        opener = page.get_by_role("button", name="Open settlement inspector")
        opener.focus()
        opener.press("Enter")
        population("31")
        expect(status).to_contain_text("source turn 2")
        page.reload()
        population("23")
        checks.append("four repeated scrubs/selections, close while changing turn, keyboard reopen, reload")

        slider.focus()
        select.select_option("9")
        slider.press("End")
        population("Unavailable — Not recorded")
        expect(status).to_contain_text("Observation age unavailable")
        screenshot("07-missing-timestamp-fields")
        slider.press("Home")
        slider.press("ArrowRight")
        slider.press("ArrowRight")
        select.select_option("7")
        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.get_by_role("combobox", name="Settlement")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Page overflows mobile viewport"
        population("31")
        screenshot("08-stale-mobile")
        provenance = page.locator("summary", has_text="Source provenance")
        provenance.click()
        expect(page.get_by_text("/history/2/active_settlements/0/population_estimate", exact=True)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Provenance overflows mobile viewport"
        screenshot("09-provenance-mobile")
        checks.append("390px mobile viewport, exact values and long source paths with no page overflow")
        # Native controls remain reachable using real browser Tab navigation.
        page.keyboard.press("Control+Home")
        slider.focus()
        page.keyboard.press("Tab")
        expect(page.get_by_role("button", name="Previous turn")).to_be_focused()
        page.keyboard.press("Tab")
        expect(page.get_by_role("button", name="Next turn")).to_be_focused()
        page.keyboard.press("Tab")
        expect(page.get_by_role("button", name="Close settlement inspector")).to_be_focused()
        page.keyboard.press("Tab")
        expect(select).to_be_focused()
        checks.append("native Tab order across timeline, close and settlement selector")
        assert not errors, errors
        browser.close()
    result = {"result": "PASS", "checks": checks, "page_console_errors": errors,
              "screenshots": sorted(p.name for p in args.evidence.glob("*.png")),
              "coverage_gaps": ["No AppShell production mounting or map selection", "No M61b scale fixture or budget benchmark",
                                "Chromium only; no screen-reader or Firefox/WebKit run", "Timestamp cannot prove detection freshness"]}
    (args.evidence / "browser-qa.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
