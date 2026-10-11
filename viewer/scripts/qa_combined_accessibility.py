"""Bounded local Chromium accessibility/zoom qualification; no assistive technology claim.

Install axe-core@4.11.1 outside the viewer, then pass its axe.min.js path.
Browser zoom uses a new temporary Chromium profile, never an existing user profile.
"""
from __future__ import annotations
import argparse
import json
import math
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import urlparse
from playwright.sync_api import expect, sync_playwright
from PIL import Image


def luminance(rgb):
    channels = [v / 255 for v in rgb]
    return sum((v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4) * w
               for v, w in zip(channels, [.2126, .7152, .0722]))


def contrast(a, b):
    low, high = sorted([luminance(a), luminance(b)])
    return (high + .05) / (low + .05)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:5173/combined-inspection-demo.html')
    parser.add_argument('--axe', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true', help='Record original defects without asserting repairs')
    args = parser.parse_args()
    if urlparse(args.url).hostname not in {'127.0.0.1', 'localhost', '::1'}:
        parser.error('Only local preview URLs allowed')
    args.evidence.mkdir(parents=True, exist_ok=True)
    checks, scans, boundaries, screenshots, errors, text_contrast = [], [], [], [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=shutil.which('chromium'), args=['--no-sandbox'])
        version = browser.version
        for mode, viewport in [('desktop', {'width': 1440, 'height': 1080}),
                               ('mobile', {'width': 390, 'height': 844}),
                               ('reflow320', {'width': 320, 'height': 844}), ('zoom200', None)]:
            temporary = None
            if mode == 'zoom200':
                temporary = tempfile.TemporaryDirectory(prefix='chronicler-zoom-')
                profile = Path(temporary.name) / 'Default'
                profile.mkdir()
                (profile / 'Preferences').write_text(json.dumps({'partition': {'default_zoom_level': {'x': math.log(2) / math.log(1.2)}}}))
                context = p.chromium.launch_persistent_context(temporary.name, executable_path=shutil.which('chromium'),
                    headless=True, viewport=None, args=['--no-sandbox', '--window-size=1440,1080'])
            else:
                context = browser.new_context(viewport=viewport)
            page = context.new_page()
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
            page.goto(args.url)
            expect(page.get_by_role('heading', level=1)).to_be_visible()
            metrics = page.evaluate('({innerWidth,outerWidth,dpr:devicePixelRatio,scale:visualViewport.scale})')
            if mode == 'zoom200':
                assert metrics['dpr'] == 2 and metrics['scale'] == 1 and abs(metrics['innerWidth'] * 2 - metrics['outerWidth']) <= 2, metrics
            slider = page.get_by_role('slider', name='Requested turn')
            civ = page.get_by_role('combobox', name='Example civilization', exact=True)
            ledger = page.get_by_role('region', name='Event ledger')
            inspector = page.locator('section').filter(has=page.get_by_role('combobox', name='Settlement', exact=True))
            select = page.get_by_role('combobox', name='Settlement', exact=True)

            def scrub(turn):
                slider.focus(); slider.press('Home')
                for _ in range(turn - 1): slider.press('ArrowRight')
                expect(slider).to_have_value(str(turn)); expect(slider).to_be_focused()

            def shot(name):
                path = f'{mode}-{name}.png'
                page.screenshot(path=str(args.evidence / path), full_page=True)
                screenshots.append(path)
                return args.evidence / path

            def axe(name):
                page.add_script_tag(path=str(args.axe.resolve()))
                result = page.evaluate('async () => await axe.run()')
                (args.evidence / f'{mode}-axe-{name}.json').write_text(json.dumps(result, indent=2))
                scans.append({'mode': mode, 'state': name, 'violations': [v['id'] for v in result['violations']],
                              'incomplete': [{'id': v['id'], 'nodes': len(v['nodes'])} for v in result['incomplete']]})
                assert not result['violations'], scans[-1]

            def reflow():
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), mode
                # Scrollable tables may scroll internally; their containing page must reflow.
                for control in page.locator('input,select,button,summary').all():
                    if control.is_visible():
                        box = control.bounding_box()
                        assert box['x'] >= 0 and box['x'] + box['width'] <= metrics['innerWidth'] + 1, (mode, box)

            expect(page.get_by_role('main')).to_have_count(1)
            expect(ledger.get_by_role('heading', level=2)).to_have_text('Event ledger')
            if not args.baseline:
                expect(inspector.get_by_role('heading', level=2)).to_have_text('River Quay')
            page.get_by_role('slider').focus()
            focus = slider.evaluate('(x)=>({width:getComputedStyle(x).outlineWidth,color:getComputedStyle(x).outlineColor,style:getComputedStyle(x).outlineStyle})')
            assert focus['width'] == '2px' and focus['style'] == 'solid', focus
            shot('initial-focus'); axe('initial'); reflow()
            # Preserve computed DOM structure without claiming spoken output.
            (args.evidence / f'{mode}-initial-aria.txt').write_text(page.locator('main').aria_snapshot())
            # Conservative upper bound for authored dark surfaces in this fixture:
            # max shell gradient -> .92 panel + .018 highlight -> .02 card -> .026 button.
            # Each channel is <=41; use [41,41,41] for all text and focus comparisons.
            if mode == 'desktop':
                colors = page.locator('main *').evaluate_all('xs => [...new Set(xs.filter(x => x.childNodes.length && [...x.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) && x.getClientRects().length && !x.closest("[hidden]" ) && !x.matches(":disabled,option")).map(x => getComputedStyle(x).color))]')
                for color in colors:
                    rgb = [float(v) for v in re.findall(r'[\d.]+', color)[:3]]
                    value = contrast(rgb, [41, 41, 41])
                    text_contrast.append({'foreground': color, 'conservative_background_bound': [41,41,41], 'ratio': value})
                    assert value >= 4.5, text_contrast[-1]
                assert contrast([191,227,229], [41,41,41]) >= 3
            path = shot('control-boundaries')
            if mode == 'desktop':
                img = Image.open(path).convert('RGB')
                for name in ['From turn', 'Through turn']:
                    field = ledger.get_by_role('spinbutton', name=name, exact=True)
                    box = field.bounding_box(); x = int(box['x']); y = int(box['y'] + box['height'] / 2)
                    edge, outside = img.getpixel((x, y)), img.getpixel((x - 2, y))
                    item = {'label': name, 'edge': edge, 'outside': outside, 'ratio': contrast(edge, outside),
                            'css': field.evaluate('(x)=>({border:getComputedStyle(x).borderColor,background:getComputedStyle(x).backgroundColor})')}
                    boundaries.append(item)
                    if not args.baseline: assert item['ratio'] >= 3, item

            # Controls survive filtering, invalid range, reset, and page reset.
            next_events = ledger.get_by_role('button', name='Next events', exact=True)
            next_events.focus(); next_events.press('Enter')
            field = ledger.get_by_role('combobox', name='Event type', exact=True)
            field.focus(); field.select_option(json.dumps('weather'))
            expect(field).to_be_focused(); expect(ledger.get_by_role('status')).to_contain_text('0–0 of 0 events · Page 1 of 1')
            if mode == 'desktop': axe('empty-filter')
            reset = ledger.get_by_role('button', name='Reset filters', exact=True)
            reset.focus(); reset.press('Enter'); expect(reset).to_be_focused()
            from_turn = ledger.get_by_role('spinbutton', name='From turn', exact=True)
            from_turn.focus(); from_turn.fill('5'); expect(from_turn).to_be_focused()
            ledger.get_by_role('spinbutton', name='Through turn', exact=True).fill('2')
            expect(ledger.get_by_role('alert')).to_be_visible()
            expect(from_turn).to_have_attribute('aria-invalid', 'true')
            if mode == 'desktop': axe('invalid-range')
            reset.click(); expect(ledger.get_by_role('alert')).to_have_count(0)
            group = ledger.get_by_role('button', name='Turn 3 · migration · 24 events on this page')
            group.focus(); group.press('Enter'); expect(group).to_be_focused(); expect(group).to_have_attribute('aria-expanded', 'true')
            if mode == 'desktop': axe('expanded-group')
            reflow()
            civ.focus(); civ.select_option('Nobody'); expect(civ).to_be_focused()
            expect(ledger.get_by_role('status')).to_contain_text('0–0 of 0 events')
            if mode == 'desktop': axe('nobody')
            civ.select_option('Beta'); expect(civ).to_be_focused(); expect(inspector.get_by_role('status')).to_contain_text('As of turn 3')
            civ.select_option('Alpha')
            for turn, phrase in [(1, 'not listed'), (2, 'Same-turn source timestamp'), (3, 'Stale summary'), (4, 'No historical snapshot'), (5, 'Dissolution recorded')]:
                scrub(turn); expect(inspector.get_by_role('status')).to_contain_text(phrase); reflow()
                if mode == 'desktop': axe(f'turn-{turn}')
            scrub(6); select.select_option('9'); expect(inspector.get_by_role('status')).to_contain_text('Observation age unavailable')
            if mode == 'desktop': axe('missing-fields')
            scrub(25)
            expect(inspector.get_by_role('status')).to_contain_text('Stale summary · source turn 23 · observation age 2 turns')
            select.focus(); select.select_option('9'); expect(select).to_be_focused()
            history = inspector.locator('summary', has_text='Recorded population history')
            history.focus(); history.press('Enter'); expect(history).to_be_focused()
            provenance = inspector.locator('summary', has_text='Source provenance')
            provenance.focus(); provenance.press('Space'); expect(provenance).to_be_focused()
            next_samples = inspector.get_by_role('button', name='Next samples', exact=True)
            previous_samples = inspector.get_by_role('button', name='Previous samples', exact=True)
            count = inspector.get_by_text('1–20 of 24 historical samples', exact=True)
            before = count.evaluate('(x)=>({live:x.getAttribute("aria-live"),atomic:x.getAttribute("aria-atomic")})')
            next_samples.focus(); next_samples.press('Enter'); expect(previous_samples).to_be_focused()
            expect(inspector.get_by_text('21–24 of 24 historical samples', exact=True)).to_be_visible()
            if not args.baseline: assert before == {'live': 'polite', 'atomic': 'true'}, before
            shot('history-page2'); reflow(); axe('history-page2')
            previous_samples.press('Enter'); expect(next_samples).to_be_focused()
            seek = inspector.get_by_role('button', name='Inspect settlement at turn 2', exact=True)
            seek.focus(); seek.press('Enter'); expect(slider).to_be_focused(); expect(slider).to_have_value('2')
            expect(ledger.get_by_role('status')).to_contain_text('Page 1 of 1')
            scrub(25); expect(inspector.get_by_text('1–20 of 24 historical samples', exact=True)).to_be_visible()
            select.focus(); select.select_option(''); expect(select).to_be_focused(); expect(inspector.locator('dl')).to_have_count(0)
            checks.append({'mode': mode, 'metrics': metrics, 'focus': focus, 'sample_count_DOM_before_pagination': before,
                           'pass': ['landmarks/form names','filter/invalid-range/reset focus','expanded group keyboard','civilization/empty results',
                                    'turn/founding/stale/gap/dissolution/missing fields','sample boundaries/seek focus','pagination reset',
                                    'non-color stale explanation','reflow initial/expanded/state transitions']})
            context.close()
            if temporary: temporary.cleanup()
        browser.close()
    assert not errors, errors
    result = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'tree': subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], text=True).strip(),
              'browser': f'Chromium {version}', 'axe': '4.11.1', 'checks': checks, 'axe_scans': scans,
              'input_boundary_contrast': boundaries, 'conservative_text_contrast': text_contrast, 'screenshots': screenshots, 'console_errors': errors,
              'limitations': ['No actual screen reader testing or spoken-output verification',
                              'Axe gradient contrast incomplete; inspect raw incomplete results',
                              'Firefox/WebKit unrun: normal installer received403 Domain forbidden',
                              'Synthetic fixture only; no production or M61b acceptance']}
    (args.evidence / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
