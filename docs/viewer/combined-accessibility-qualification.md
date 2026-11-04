# Bounded combined-preview accessibility qualification

The isolated synthetic combined viewer retains its existing data, source order,
requested-turn/civilization controls, and production gate. This qualification does
not establish M61b acceptance or authorize mounting the production AppShell.

Targeted repairs:

- Empty From/Through turn fields used a translucent boundary with approximately
  2.53:1 rendered contrast against the panel. Only these number-field boundaries
  now use the existing solid gold token (approximately 7.99:1 on the tested panel).
- Population sample pagination now updates an atomic polite live region with the
  complete visible row range and total. This is DOM announcement semantics;
  actual screen-reader speech and usability have not been tested.
- Event count status explicitly requests an atomic announcement.
- The settlement section uses a level-two heading alongside the event section;
  its subsections use level-three headings. The title's existing styling is kept.

Run the existing combined regression and the new bounded qualification against
an entirely local preview. Python Playwright and Pillow are required. Install
Deque's pinned axe package into a separate tooling directory; the viewer lockfile
and application dependencies are unchanged.

```sh
npm install --prefix /tmp/chronicler-axe axe-core@4.11.1
npm run dev -- --host 127.0.0.1
python scripts/qa_combined_inspection.py --evidence /tmp/chronicler-combined-regression
python scripts/qa_combined_accessibility.py \
  --axe /tmp/chronicler-axe/node_modules/axe-core/axe.min.js \
  --evidence /tmp/chronicler-combined-accessibility
npm test
npx tsc -b --force
npm run build
npm run lint
```

The script uses system Chromium. Desktop 1440, mobile 390, reflow 320, and real 200%
Chromium zoom cover focus after filtering, invalid ranges, pagination and reset,
shared turn/civilization changes, empty results, expanded groups, founding,
dissolution, missing snapshot/fields, stale source text, history disclosures,
sample boundaries and row seeks. The original regression also proves the fixture's
58 Alpha records appear exactly once in the documented newest-turn/group/source-position
order, and 24 history rows appear exactly once in input order.

Real browser zoom uses a newly created temporary profile and Chromium's default
zoom preference. It checks DPR 2, visual viewport scale 1, and a CSS viewport half
its outer width; CSS zoom or pinch scaling is not substituted. Initial/expanded
states are checked for document overflow and controls outside the CSS viewport.

Axe scans record violations and all incomplete results. Gradient backgrounds make
some color-contrast checks incomplete; zero axe violations is not a complete
accessibility certification. Rendered boundary measurements and separate
conservative text/focus contrast checks supplement the scans. The evidence report
records their exact scope and limits. The script saves Chromium ARIA DOM snapshots;
these are not assistive-technology sessions.

Firefox and WebKit installation was attempted through normal Playwright tooling.
Both received 403 `Domain forbidden`; those browsers remain unrun. No restricted
mirror, security bypass, production activation, external hosting or GitHub writes
are involved. Review and final verification evidence is supplied separately with
exact source HEAD/tree and package identities.

Primary tooling/criterion references:
[Deque axe-core](https://github.com/dequelabs/axe-core),
[Playwright browsers](https://playwright.dev/python/docs/browsers),
[W3C non-text contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html).
