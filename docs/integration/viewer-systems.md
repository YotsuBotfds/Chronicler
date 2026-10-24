# Viewer panels for the default-off systems

Branch `feat/viewer-systems`, based on `integrate/wave-4` at `1a6cacb`
(epidemiology, money and credit, diplomacy, techniques and the maritime
layer, all default off, plus causal provenance). Code: `viewer/src/lib/systems.ts`
(read-only helpers), `viewer/src/components/systems/` (panels), two additive
snapshot fields in `src/chronicler/diplomacy.py` and `src/chronicler/techniques.py`.

The production viewer (the phase 7.5 `AppShell`) now shows each system when a
bundle records it, and nothing new when it does not: a bundle without any
`history[n].epidemics`, `.finance`, `.diplomacy`, `.techniques` or `.maritime`
renders pixel-identically to the base viewer (see [Evidence](#evidence)).
The synthetic demonstration pages are unchanged.

## Where it lives

* **Simulation systems panel.** A full-width panel below the map workspace on
  the Overview, Character, Trade and Campaign surfaces, with one tab per
  recorded system (absent systems have no tab). It opens on the system that
  fits the surface (Trade: finance; Campaign: diplomacy, then maritime;
  Character: techniques; otherwise the first present) until the viewer picks
  one. Every value is the bundle's own record for the snapshot the shell shows
  at the scrubbed turn (the latest at or before it); gaps stay gaps.
* **Events.** Each panel lists its system's events up to the scrubbed turn as
  the shell's event rows. Selecting one pins it in the right inspector and
  seeks to its turn, so the existing causal-provenance rows ("Because" and
  "Led to") explain it; provenance is not re-implemented.
* **Region inspector.** With a region selected, the inspector's selection
  block adds the region's outbreaks (pathogen, prevalence, immunity, new
  cases, deaths, virgin soil), whether its controller is in quarantine, its
  practised techniques with their share of the population, and how many
  techniques the controller knows. Each block appears only when the snapshot
  carries that system. Panel tables name regions and civilizations as links
  that select them.
* **Live mode.** `useLiveConnection` passes the five fields through from the
  live server's turn messages.

| Tab | Shows |
| --- | --- |
| Epidemics | Active outbreaks, deaths this turn and so far, quarantined states; a strip with one row per region and pathogen across the run (hover: peak prevalence, deaths, virgin soil; click a row to select the region); the scrubbed turn's outbreak table, quarantines and mutated strains; arrival, epidemic, mutation and quarantine events. |
| Finance | Open credit lines and the world ledger (lent, repaid, written off, seigniorage); two charts per civilization, debt in turns of smoothed revenue and the price index (one measure per chart); the scrubbed turn's public-finance table (debt, foreign debt, revenue, prices, coin fineness, fiscal stress, arrears, defaults, debasements); loans, defaults (with write-offs) and debasements as a filterable event list. |
| Diplomacy | Treaties in force (kind, parties, start, expiry); the vassal ladder (client, vassal, union) with the subjects at the scrubbed turn and a strip of every overlord-subject pair's stage over the run; trust and total grievance matrices between living civilizations at the scrubbed turn, plus the five largest grievances by kind; treaty and ladder events. |
| Techniques | Known techniques per civilization over time; the era timeline (eras derived from practised techniques), one strip row per civilization with the era named in the bar; the scrubbed turn's known and widely practised counts per civilization; regional practice per technique (regions practising it, where it is strongest); inventions, adoptions ("learned X from Y's merchants"), losses, advances and regressions. |
| Maritime | Fleets, ships, controlled and contested zones, blockades and closed lanes; a sea-zone control strip (controller's colour and initials, contested grey, a red line under blockaded turns); zones with status, ships by civilization, pirate pressure, sea trade, piracy and ports; fleets and blockades at the scrubbed turn; run counters; naval events. A world without sea zones says the layer is idle. |

The map draws regions only (no sea geometry, and Geography 2.0's sea zones
are not projected onto it), so sea zones are tables and strips rather than a
map layer.

## Bundle contract

`viewer/src/types.ts` types every field as optional on `TurnSnapshot`
(`EpidemicSnapshot`, `FinanceSnapshot`, `DiplomacySnapshot`,
`TechniquesSnapshot`, `MaritimeSnapshot`) after each system's
`snapshot_summary()`. The viewer also reads the final
`world_state.maritime.zones[i].ports` (zones and ports are fixed once built).

Two fields were missing for the panels and are added, optional and additive,
only when the system is on:

| Field | Shape | Why |
| --- | --- | --- |
| `history[n].diplomacy.pairs` | holder -> target -> `[trust, total grievance]`, one decimal, every directed pair of living civilizations that has a memory, in civilization index order | `top_grievances` covers only five pairs, so trust and grievance between all pairs at a turn were not recorded |
| `history[n].techniques.regions` | region -> technique key -> practice share, two decimals, rows at or above `LOSE_LEVEL` (0.03), in practice-table order | `known`/`practised` are per civilization, so per-region technique state at a turn was not recorded |

Both are read-only: no RNG, no state or cache is touched. With the switches
off nothing changes (the summaries are not called). Size with every system on:
the template seed-42 hybrid 120-turn bundle grows by 55 KB (3.55 to 3.60 MB,
1.5%), the procedural 48-region 10-civ bundle by 183 KB (8.91 to 9.10 MB, 2.1%).

The bundle version stays 4: every new field is optional, and v3 and v4
bundles load as before. Bundles written before these fields fall back
honestly: the trust and grievance view shows the five recorded grievances and
says the other pairs are not recorded; the region inspector and the
techniques tab say regional practice is not exported.

## Evidence

Linux, Python 3.13, a fresh `maturin develop --release` build of the
unchanged Rust tree (compiled `AgentSimulator`, `EcologySimulator`,
`PoliticsSimulator` verified), Node 22.

**Python identity** (`scripts/viewer_systems_identity.py`, base `1a6cacb`
on `PYTHONPATH` against this branch, same interpreter and extension,
`PYTHONHASHSEED=0`):

| Run | Mode | Files | Differences |
| --- | --- | --- | --- |
| template seed 42, hybrid, 120 turns, default (systems off) | `compare` | 8 | 0 |
| template seed 7, off, 150 turns, default | `compare` | 7 | 0 |
| procedural 48 regions x 10 civs, seed 42, hybrid, 120 turns, default | `compare` | 14 | 0 |
| template seed 42, hybrid, 120 turns, `--no-diplomacy --no-techniques` | `compare` | 8 | 0 |
| template seed 42, hybrid, 120 turns, all five systems on | `compare-additive` | 8 | 0 |
| procedural 48 x 10, seed 42, hybrid, 120 turns, all five on | `compare-additive` | 14 | 0 |

`compare` is byte identity of every output (bundles without
`metadata.generated_at`). `compare-additive` removes only the two new fields
from the branch bundle (and requires the base bundle to lack them): with every
system on, all outputs, states, agent events and the rest of every bundle are
identical, so no simulation outcome changed.

**Tests.** `pytest -m "not slow" -n 2`: 5,699 passed, 3 skipped (base about
5,697; the two new tests extend `TestViewerFixtureContract`). The diplomacy and
techniques bundle tests now pin the new keys and check them against the final
world state. Viewer: 25 test files, 197 tests (base 22 files, 166 tests),
ESLint clean, `tsc -b && vite build` passes with the existing large-chunk
warning.

* `viewer/src/lib/__tests__/systems.test.ts`: segments, rows, series gaps,
  the pair-matrix fallback, colour scales, event ordering, surface preference.
* `viewer/src/components/systems/__tests__/SystemsPanel.test.tsx`: each panel
  renders from the real-shaped fixture; tabs exist only for recorded systems;
  the panel renders nothing for `sample_bundle.json`; older-bundle fallbacks;
  the sealess maritime message; the region inspector block.
* `viewer/src/components/phase75/__tests__/AppShell.systems.test.tsx`: no
  panel and no region block for a systems-off bundle; region selection from a
  panel; a panel event pinned in the inspector with its recorded causes.
* `useLiveConnection`: the five fields pass through live turn messages.

`viewer/src/__fixtures__/systems_bundle.json` is the procedural all-on run
above, trimmed by `scripts/build_viewer_systems_fixture.py` (every 8th
snapshot and the last, system fields as exported, system events and the events
they cite). `tests/test_bundle.py::TestViewerFixtureContract` checks it carries
the viewer contract and that its system fields still have the shape a fresh
all-on run writes.

**Browser.** The production build served by `vite preview`, driven by
headless Chromium (Playwright): every tab of both all-on bundles, a 300-turn
all-on bundle (eras move), the region inspector and an inspector-pinned
finance event were captured with no console errors or warnings. The base
viewer build (`1a6cacb`) and this build render three systems-off bundles
(template seed 42 hybrid, procedural 48 x 10 hybrid, `sample_bundle.json`)
pixel-identically on the Overview, Trade and Campaign surfaces with a region
selected (9 of 9 screenshots byte-equal). Screenshots stay outside the
repository with the run outputs.

## Cut

* **Map layers.** No sea-zone, fleet, blockade or outbreak overlay: the map
  has no sea geometry. Sea zones are tables and strips instead. The existing
  `pandemic_regions` field (which epidemiology also fills) is still not drawn.
* **Contact ledger panel.** `history[n].contact` already existed and is not
  one of the five systems; it has no panel.
* **Per-lender loan book.** The finance snapshot records the number of credit
  lines and per-civilization debt, not each line; loans, defaults and
  debasements are listed from their events (amounts and lenders are in the
  descriptions). No snapshot field was added for it.
* **Technique names per civilization over time** (the snapshot has counts) and
  per-pathogen death charts.
* **Legacy `Layout`** (not used by the app) and the synthetic demo pages are
  untouched.
* **Phone layout.** The shell is a desktop layout; the panel collapses to one
  column below 1,100 px but was not tuned for phones.

## Known gaps

* Faction colours are the viewer's hashed hues, so two civilizations can share
  a colour (two greens in the procedural run). Strips name controllers in the
  bar and tables name civilizations; the palette itself is unchanged.
* Pre-existing, unchanged: for generated worlds (template and procedural
  alike) the shell's map places region nodes far outside the canvas (their
  `x`/`y` run 0-100 while `computeAtlasLayout` expects 0-1), so regions cannot
  be clicked on the map. The panels' region links select regions for the
  inspector regardless.
