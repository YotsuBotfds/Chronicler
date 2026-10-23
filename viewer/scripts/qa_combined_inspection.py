"""Local-only Chromium QA for the isolated combined synthetic fixture."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5173/combined-inspection-demo.html")
    parser.add_argument("--evidence", type=Path, default=Path("/tmp/chronicler-combined-qa"))
    args = parser.parse_args()
    if urlparse(args.url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("QA is restricted to a local server")
    args.evidence.mkdir(parents=True, exist_ok=True)
    checks: list[str] = []
    errors: list[str] = []
    screenshots: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which("chromium"), headless=True, args=["--no-sandbox"])
        for device, viewport in [("desktop", {"width": 1440, "height": 1080}), ("mobile", {"width": 390, "height": 844})]:
            page = browser.new_page(viewport=viewport)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.goto(args.url)
            slider = page.get_by_role("slider", name="Requested turn")
            shared_civ = page.get_by_label("Example civilization")
            ledger = page.get_by_role("region", name="Event ledger")
            inspector = page.locator("section").filter(has=page.get_by_role("combobox", name="Settlement", exact=True))

            def scrub(turn: int) -> None:
                slider.focus()
                slider.press("Home")
                for _ in range(turn - 1):
                    slider.press("ArrowRight")
                expect(slider).to_have_value(str(turn))
                expect(slider).to_be_focused()

            def population(value: str) -> None:
                row = inspector.locator("dl > div").filter(has=page.locator("dt", has_text="Population estimate"))
                expect(row.locator("dd")).to_have_text(value)

            def expand() -> None:
                for button in ledger.get_by_role("button", name=re.compile("events on this page")).all():
                    if button.get_attribute("aria-expanded") == "false":
                        button.click()
                    expect(button).to_have_attribute("aria-expanded", "true")

            def screenshot(name: str) -> None:
                path = f"{device}-{name}.png"
                page.screenshot(path=str(args.evidence / path), full_page=True)
                screenshots.append(path)

            def no_future() -> None:
                expect(ledger.get_by_text(re.compile("FUTURE SENTINEL|Future civilization|future_sentinel"))).to_have_count(0)

            expect(page.get_by_text(re.compile("Synthetic / nonproduction preview"))).to_be_visible()
            expect(ledger.get_by_label("Civilization", exact=True)).to_be_disabled()
            population("23")
            expect(inspector.get_by_role("status")).to_contain_text("source turn 2 · observation age 1 turns")
            screenshot("01-combined-stale")
            seen: list[int] = []
            for index in range(3):
                expand()
                seen.extend(int(value) for value in ledger.locator("[data-source-index]:visible").evaluate_all("rows => rows.map(row => row.dataset.sourceIndex)"))
                population("23")
                expect(ledger.get_by_text(re.compile("Beta migration|Actorless weather"))).to_have_count(0)
                if index == 0:
                    screenshot("02-expanded-page")
                if index < 2:
                    ledger.get_by_role("button", name="Next events", exact=True).click()
            assert seen == list(range(2, 57)) + [65, 1, 0], seen
            assert len(set(seen)) == 58
            no_future()
            checks.append(f"{device}: all 58 Alpha records exactly once, source order preserved across three expanded pages")

            # Native button keyboard navigation keeps focus on an available boundary control.
            previous = ledger.get_by_role("button", name="Previous events", exact=True)
            previous.focus(); previous.press("Enter"); previous.press("Enter")
            expect(ledger.get_by_role("button", name="Next events", exact=True)).to_be_focused()
            shared_civ.focus(); shared_civ.press("ArrowDown")
            expect(shared_civ).to_have_value("Beta")
            expect(shared_civ).to_be_focused()
            population("71"); expand()
            expect(ledger.get_by_role("status")).to_contain_text("1–9 of 9 events")
            expect(ledger.get_by_text(re.compile("Alpha migration"))).to_have_count(0)
            screenshot("03-beta-keyboard")
            shared_civ.select_option("Nobody")
            expect(ledger.get_by_role("status")).to_contain_text("0–0 of 0 events")
            expect(inspector.locator("dl")).to_have_count(0)
            shared_civ.select_option("Alpha")
            checks.append(f"{device}: keyboard page-boundary focus and shared civilization selection; no unrelated actor backfill")

            for repeat in range(4):
                for turn in [1, 2, 3, 4, 5, 4, 3, 2]:
                    scrub(turn)
                    status = inspector.get_by_role("status")
                    expect(status).to_contain_text(f"As of turn {turn}.")
                    expect(ledger.get_by_role("status")).to_contain_text(f"of {1 if turn == 1 else 2 if turn == 2 else 59 if turn == 5 else 58} events")
                    if turn in {2, 3}:
                        population("23")
                        expect(status).to_contain_text("Same-turn source timestamp" if turn == 2 else "source turn 2 · observation age 1 turns")
                    else:
                        expect(inspector.locator("dl")).to_have_count(0)
                        expect(status).to_contain_text("not listed" if turn == 1 else "No historical snapshot" if turn == 4 else "Dissolution recorded")
                scrub(3)
                ledger.get_by_role("button", name="Next events", exact=True).click(); expand()
                ledger.get_by_label("Event type", exact=True).select_option(json.dumps("weather"))
                expect(ledger.get_by_role("status")).to_contain_text("0–0 of 0 events")
                population("23")
                shared_civ.select_option("Beta")
                expect(ledger.get_by_label("Event type", exact=True)).to_have_value("")
                population("71")
                page.get_by_role("button", name="Close experimental panels", exact=True).click()
                scrub(5); shared_civ.select_option("Alpha")
                page.get_by_role("button", name="Open experimental panels", exact=True).click()
                expect(inspector.get_by_role("status")).to_contain_text("Dissolution recorded")
                expect(ledger.get_by_role("status")).to_contain_text("Page 1 of 3")
                if repeat == 0:
                    screenshot("04-dissolved-reopened")
                page.get_by_role("button", name="Reload synthetic fixture", exact=True).click()
                expect(slider).to_have_value("3")
                population("23")
            checks.append(f"{device}: four repeated/interrupted scrub/filter/page/scope/close/reopen/reload sequences")

            scrub(25)
            page.get_by_role("combobox", name="Settlement", exact=True).select_option("9")
            population("40")
            expect(inspector.get_by_role("status")).to_contain_text("source turn 23 · observation age 2 turns")
            history = inspector.locator("summary", has_text="Recorded population history")
            history.focus(); history.press("Enter")
            provenance = inspector.locator("summary", has_text="Source provenance")
            provenance.focus(); provenance.press("Space")
            expect(inspector.get_by_text("/history/23/active_settlements/0/population_estimate", exact=True)).to_be_visible()
            table = inspector.get_by_role("table")
            sample_turns = [int(value) for value in table.locator("tbody tr td:first-child").all_text_contents()]
            next_samples = inspector.get_by_role("button", name="Next samples", exact=True)
            previous_samples = inspector.get_by_role("button", name="Previous samples", exact=True)
            next_samples.focus(); next_samples.press("Enter")
            expect(previous_samples).to_be_focused()
            sample_turns += [int(value) for value in table.locator("tbody tr td:first-child").all_text_contents()]
            assert sample_turns == [value for value in range(1, 26) if value != 4], sample_turns
            previous_samples.press("Enter")
            expect(next_samples).to_be_focused()
            screenshot("05-stale-history-provenance")
            scrub(24)
            expect(inspector.get_by_role("status")).to_contain_text("source turn 23 · observation age 1 turns")
            seek = inspector.get_by_role("button", name="Inspect settlement at turn 2", exact=True)
            seek.focus(); seek.press("Enter")
            expect(slider).to_have_value("2")
            expect(slider).to_be_focused()
            population("40")
            expect(ledger.get_by_role("status")).to_contain_text("1–2 of 2 events")
            scrub(6)
            population("Unavailable — Not recorded")
            expect(inspector.get_by_role("status")).to_contain_text("Observation age unavailable")
            page.get_by_role("combobox", name="Settlement", exact=True).select_option("")
            expect(inspector.locator("dl")).to_have_count(0)
            checks.append(f"{device}: source-turn labels scrub both ways, 24 sample rows exactly once, keyboard disclosures and shared seek, missing fields/selection")

            scrub(32); no_future()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), device
            page.get_by_role("button", name="Reload synthetic fixture", exact=True).click()
            slider.focus(); slider.press("Tab")
            expect(shared_civ).to_be_focused()
            shared_civ.press("Tab")
            expect(page.get_by_role("button", name="Close experimental panels", exact=True)).to_be_focused()
            checks.append(f"{device}: future sentinel/type/actor hidden at maximum turn; no document overflow; shared-control keyboard Tab order")
            page.close()
        version = browser.version
        browser.close()
    assert not errors, errors
    result = {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "browser": f"Chromium {version}", "url": args.url, "checks": checks,
              "screenshots": screenshots, "console_errors": errors, "scope": "synthetic isolated composition; no M61b acceptance"}
    (args.evidence / "browser-results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
