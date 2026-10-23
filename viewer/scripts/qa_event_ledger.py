"""Isolated local Chromium QA; no production activation or external writes."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5173/event-ledger-demo.html")
    parser.add_argument("--evidence", type=Path, default=Path("/tmp/chronicler-ledger-qa"))
    args = parser.parse_args()
    if urlparse(args.url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("QA requires a local server")
    args.evidence.mkdir(parents=True, exist_ok=True)
    checks: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which("chromium"), headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.goto(args.url)
        panel = page.get_by_role("region", name="Event ledger")
        expect(panel.get_by_role("status")).to_have_text("1–24 of 61 events · Page 1 of 3")
        page.screenshot(path=str(args.evidence / "desktop-collapsed.png"))
        seen: list[int] = []
        for number in range(1, 4):
            for button in panel.get_by_role("button", name="events on this page").all():
                button.focus()
                for _ in range(3):
                    page.keyboard.press("Enter")
                    expect(button).to_have_attribute("aria-expanded", "true")
                    expect(button).to_be_focused()
                    page.keyboard.press("Space")
                    expect(button).to_have_attribute("aria-expanded", "false")
                page.keyboard.press("Enter")
            records = panel.locator("li[data-source-index]:visible")
            seen.extend(int(value) for value in records.evaluate_all("els => els.map(el => el.dataset.sourceIndex)"))
            assert records.count() <= 24
            if number < 3:
                next_button = panel.get_by_role("button", name="Next events")
                next_button.focus()
                page.keyboard.press("Enter")
                expect(next_button if number == 1 else panel.get_by_role("button", name="Previous events")).to_be_focused()
        assert len(seen) == 61 and set(seen) == set(range(61))
        expect(panel.get_by_role("button", name="Next events")).to_be_disabled()
        checks.append("61 historical records exactly once across three pages; each page bounded at 24; duplicate-looking records survive")
        checks.append("three repeated Enter/Space expand-collapse cycles on each group; pagination retains keyboard focus")

        # Interrupt the late-page expansion with an exact actor query.
        panel.get_by_label("Civilization", exact=True).select_option(label="Beta")
        expect(panel.get_by_role("status")).to_have_text("1–4 of 4 events · Page 1 of 1")
        panel.get_by_role("button", name="events on this page").click()
        assert panel.locator("li[data-source-index]:visible").count() == 4
        for item in panel.locator("li[data-source-index]:visible").all():
            expect(item).to_contain_text("Beta")
        panel.screenshot(path=str(args.evidence / "desktop-focused.png"))
        expect(panel).not_to_contain_text("Migration record")
        expect(panel).not_to_contain_text("FUTURE MUST NOT LEAK")
        expect(panel.get_by_label("Event type")).not_to_contain_text("future_secret")
        panel.get_by_label("Civilization", exact=True).select_option(label="Nobody")
        expect(panel.get_by_role("status")).to_have_text("0–0 of 0 events · Page 1 of 1")
        panel.get_by_role("button", name="Reset filters").click()
        expect(panel.get_by_role("status")).to_have_text("1–24 of 61 events · Page 1 of 3")
        checks.append("late-page actor query resets; Beta has exactly four matching events; empty focus never backfills; no future record or option leaks")

        for label, value in [("Event type", "migration"), ("From turn", "3"), ("Through turn", "4")]:
            panel.get_by_role("button", name="Next events").click()
            if label == "Event type":
                panel.get_by_label(label).select_option(label=value)
            else:
                panel.get_by_label(label).fill(value)
            expect(panel.get_by_role("status")).to_contain_text("Page 1 of 3")
        panel.get_by_label("From turn").fill("5")
        expect(panel.get_by_role("alert")).to_be_visible()
        expect(panel.get_by_label("From turn")).to_have_attribute("aria-invalid", "true")
        expect(panel.locator("li[data-source-index]:visible")).to_have_count(0)
        panel.get_by_role("button", name="Reset filters").click()
        checks.append("type and both turn filters reset later pages; invalid reversed range hides all records and announces an error")

        for _ in range(3):
            panel.get_by_role("button", name="Next events").click()
            panel.get_by_role("button", name="events on this page").click()
            panel.get_by_role("button", name="Inspect source event #25", exact=True).click()
            expect(page.get_by_role("complementary", name="Source inspection")).to_contain_text("turn 4")
            page.get_by_role("button", name="Rewind to turn 3").click()
            expect(page.get_by_role("complementary", name="Source inspection")).not_to_contain_text("turn 4")
            expect(panel.get_by_role("status")).to_have_text("1–3 of 3 events · Page 1 of 1")
            panel.get_by_role("button", name="events on this page").click()
            expect(panel.get_by_text("Actors: No actors recorded.", exact=False)).to_have_count(2)
            page.get_by_role("button", name="Return to turn 4").click()
            expect(panel.get_by_role("status")).to_have_text("1–24 of 61 events · Page 1 of 3")
            page.get_by_role("button", name="Close ledger").click()
            expect(panel).to_have_count(0)
            page.get_by_role("button", name="Open ledger").click()
            expect(panel.get_by_role("status")).to_contain_text("Page 1 of 3")
        checks.append("three interrupted inspect/rewind/return and close/reopen cycles; prior future inspection cleared; missing and empty actors displayed truthfully")

        panel.get_by_role("button", name="Next events").click()
        page.get_by_role("button", name="Reload fixture").click()
        expect(panel.get_by_role("status")).to_contain_text("Page 1 of 3")
        toggle = panel.get_by_role("button", name="events on this page")
        toggle.focus()
        page.keyboard.press("Enter")
        page.keyboard.press("Tab")
        expect(panel.get_by_role("button", name="Inspect source event #1", exact=True)).to_be_focused()
        page.keyboard.press("Enter")
        expect(page.get_by_role("complementary", name="Source inspection")).to_contain_text("Original event #1")
        panel.screenshot(path=str(args.evidence / "desktop-expanded.png"))
        checks.append("artifact reload resets query; Tab reaches first source action and Enter inspects its original source position")

        page.set_viewport_size({"width": 390, "height": 844})
        panel.get_by_role("button", name="events on this page").click()
        box = panel.bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= 390
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=str(args.evidence / "mobile-collapsed.png"))
        # Native selects support keyboard selection, including the empty-query option.
        civ = panel.get_by_label("Civilization", exact=True)
        civ.focus()
        page.keyboard.press("Home")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        expect(civ).to_have_value(json.dumps("Alpha"))
        expect(panel.get_by_role("status")).to_contain_text("of 56 events")
        toggle = panel.get_by_role("button", name="events on this page")
        toggle.focus()
        page.keyboard.press("Space")
        expect(toggle).to_have_attribute("aria-expanded", "true")
        panel.screenshot(path=str(args.evidence / "mobile-expanded.png"))
        checks.append("390px viewport has no horizontal page overflow; native select keyboard query and Space expansion succeed")
        assert not errors, errors
        (args.evidence / "browser-results.json").write_text(json.dumps({"browser": browser.version,
            "checks": checks, "console_errors": errors, "source_indices": seen,
            "coverage_gaps": ["Chromium only; no Firefox/WebKit", "No screen-reader or automated contrast audit", "Synthetic legacy Event fixture; no M61b-scale production mount or general entity IDs"]}, indent=2) + "\n")
        browser.close()


if __name__ == "__main__":
    main()
