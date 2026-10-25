# Viewer panels and map layers for the simulation systems

Two rounds on branch `feat/viewer-systems`:

1. From `integrate/wave-4` (`1a6cacb`, merged as `893ec1c`): panels for
   epidemiology, money and credit, diplomacy, techniques and the maritime
   layer, plus two additive snapshot fields (`diplomacy.pairs`,
   `techniques.regions`). Details under [First round](#first-round).
2. From `main` `6e6fae6` (Wave 6 and languages): an audit of every system
   against the bundle and the viewer, panels for the systems that had none
   (campaign warfare, food, nomads, great-person agendas, governance, the
   contact ledger), thematic map layers, and two viewer-only snapshot fields
   (`food`, `migration`).

Code: `viewer/src/lib/systems.ts` (registry and the first five systems),
`viewer/src/lib/food.ts`, `wars.ts`, `polity.ts`, `mapLayers.ts`;
`viewer/src/components/systems/` (one panel per system);
`viewer/src/components/phase75/MapLayerMarks.tsx` and the map in `AppShell.tsx`;
`src/chronicler/mutual_aid.py` (`snapshot_summary`) and `src/chronicler/main.py`
(`_food_snapshot_fields`, `_migration_snapshot_fields`).

## Audit

Bundles checked: four runs on `main` `6e6fae6` (fresh native build, Linux,
Python 3.13): procedural 48 regions x 10 civs seed 42, 200 hybrid turns, and
template 10 regions x 5 civs seed 7, 200 hybrid turns, both with
`--maritime --nomads --gp-agendas` (every other system is on by default);
and the defaults alone on template seed 42 (150 hybrid turns) and procedural
30 x 8 seed 7 (150 hybrid turns). "Before" is the viewer on `main`; "after"
is this branch. Every bundle field named here is per snapshot
(`history[n]`) unless it says `world_state` or top level.

| System | Bundle data | Viewer before | Viewer after |
| --- | --- | --- | --- |
| Epidemiology (SEIRS) | `epidemics` (outbreaks by region and pathogen, deaths, quarantines, strains), `pandemic_regions`; events | Epidemics tab; region inspector block | + **Epidemics map layer**: each region's strongest outbreak, fill strength by prevalence, quarantine in the hover |
| Money and credit | `finance` (per civ debt, revenue, prices, coin, stress, defaults); events | Finance tab | Unchanged |
| Diplomacy | `diplomacy` (treaties, subjects and ladder stage, pair memory, top grievances); events | Diplomacy tab | Unchanged |
| Techniques | `techniques` (known, practised, regional practice); events | Techniques tab; region block | + **Techniques map layer**: practice share of a chosen technique per region (opens on the one spreading most) |
| Maritime | `maritime` (zones, fleets, blockades, counters); `world_state.maritime` zone ports and lanes; `world_state.geography.sea_zones` positions | Maritime tab (tables and strips; "the map has no sea geometry") | + **Sea map layer**: zones at their procedural positions (template: between their ports) with spokes to the ports, the holder's colour, ships, a red ring under blockade |
| Nomads | `nomads` (modes, herds per civ, tributes, hordes, counters); events | None | **Nomads tab**: ways of life over time, herds per civ, hordes and tribute, counters, raid/horde/dzud events; raids on the Wars layer |
| Great-person agendas | `gp_agendas` (open vows with civ index and target, bonds, totals); events | None | **Agendas tab**: running totals declared/fulfilled/failed, open vows in the simulation's phrasing with targets resolved, bonds, events |
| Historiography | top-level `historiography`; chronicle entries' `accounts` | In-world accounts of a pinned event | Unchanged |
| Languages | top-level `languages` | Languages inspector | Unchanged |
| Contact ledger | `contact` (edges, contact and trade pairs, inflow and stock by channel, top trade pairs with dependence); final `world_state.contact_ledger` | None | **Contact tab**: pairs in contact and trading over time, largest partnerships with each side's dependence, embargoes |
| Causal provenance | events' `event_id`, `causes`, `region`, `episode`, `duration`; chronicle `causal_chains` | Inspector "Because" / "Led to" | Unchanged; famine spans are read from `region` and `episode` |
| Fisheries and mutual aid | `fishery_collapse`/`fishery_recovery` and `mutual_aid` events; final `world_state` fish stocks, `mutual_aid_state`, last turn's transfers | None (event log only) | New **`food`** field (regional sufficiency, relief convoys); fishery and relief events in the Food tab; convoys on the Food layer |
| Food balance and logistics | `famine` (onset, repeats) and `famine_ended` events with region and duration; `supply_shock` | Event log only | **Food tab**: famine spans by region, regions short of food and in famine over time, hungry regions with food ÷ need; **Food map layer**; food block in the region inspector |
| Governance | `civ_stats[civ].governance` (form, cycle, regime, legitimacy, PSI, institutions, elites, revolts) | None | **Governance tab**: forms of government over time with PSI-crisis marks, PSI per civ, realms at the turn, reform and crisis events |
| Campaign warfare | `campaign` (armies, the turn's battles, occupations, wars with score); events | Typed only; the Campaign surface drew disposition links | **Wars tab**: wars over time coloured by the side ahead, wars, armies, occupations and battles at the turn; **Wars map layer** (default on the Campaign surface); war block in the region inspector |
| Procedural geography | regions' `x`/`y` and `geo`; `world_state.geography` sea zones and lanes | Pins scaled to the canvas, but a world using part of the 0-100 map sat in its middle | The atlas fits the pins' bounds (and sea zones); elevation, moisture and biome are still not drawn |
| Migration | agent moves only in the `agent_events.arrow` sidecar; `mass_migration` and `notable_migration` events | None | New **`migration`** field; **Migration map layer** (moves summed over the last 10 recorded turns, arrow width by people) |

## What changed in the viewer

* **Map layers.** A "Map layer" chip row under the overlay chips (shown when
  the bundle has data for a layer): Control (the default, unchanged), Food,
  Epidemics, Wars, Migration, Techniques, Sea. One layer at a time; each
  recolours the region nodes, adds its marks and a legend with one line on
  what it shows, and every node and mark has hover text. Layers with marks
  (Wars, Migration, Sea) keep the controller colours dimmed underneath. The
  decorative fog mask and the named-event dots are hidden while a layer is
  drawn, so they cannot be read as data. The Campaign surface opens on the
  Wars layer.
* **Atlas fit.** Region pins are fitted to their own bounding box
  (`pinFrame`/`atlasPoint` in `appShellHelpers.ts`, replacing `pinScale`),
  so procedural worlds fill the canvas. The map column no longer stretches
  its rows when the inspector is long (the civ chips were drawn as tall
  pills).
* **Panels.** The systems panel (now "Systems recorded in this run") gains
  Food, Wars, Nomads, Agendas, Governance and Contact tabs, in that order
  around the first five; a tab appears only when the bundle records the
  system. Each tab answers one question (where food is short; who is
  fighting and who is ahead; who lives by herds; what great persons vowed;
  how close each realm is to breaking; who depends on whom for trade) with
  tiles, one strip or chart, the scrubbed turn's table and the system's
  events, which pin in the inspector as before.
* **Region inspector.** With a region selected: its food ÷ need and famine
  (since when), and the armies in it or its occupier, next to the existing
  epidemic and technique blocks.
* **Live mode.** `useLiveConnection` passes `contact`, `gp_agendas`,
  `nomads`, `food` and `migration` through.

The synthetic demonstration pages are unchanged; nothing here is synthetic.

## Bundle contract

All new fields are optional and the bundle version stays 5; older bundles
load and show what they carry. Types are in `viewer/src/types.ts`
(`ContactSnapshot`, `GpAgendasSnapshot`, `NomadsSnapshot`, `FoodSnapshot`,
`MigrationFlow`, `GovernanceSnapshot`, `WorldState.geography`).

Two fields were added because the data existed in the simulation but was
not in the bundle. Both are viewer-only, read after the turn from state the
simulation keeps, touch no state or RNG, and are omitted while `None`:

| Field | Shape | Written when | Source |
| --- | --- | --- | --- |
| `history[n].food` | `{"sufficiency": [per region index: food on hand ÷ the turn's need, 0-2, two decimals, or null], "aid": [[donor, recipient, food delivered], ...]}` | mutual aid runs on an agent-backed economy (default on in agent modes) | `world.mutual_aid_state` observed in the completed turn; `world.mutual_aid_last_transfers` of that turn |
| `history[n].migration` | `[[from region index, to region index, agents], ...]`, sorted | `--agents hybrid` or `shadow` | the completed turn's `migration` agent events, through the exact history index |

Without `food`, the Food tab and layer show famines only and say so; without
`migration` there is no Migration layer. Famine spans need events with
`region` and `episode` (bundle version 4+); older bundles get no Food tab.

### Size

* Bundle-size guard world (`tests/test_bundle.py::TestBundleSize`: seed 1,
  5 civs, 10 regions, 500 turns, agents off): **18,519,396 bytes (17.66 MB)
  on both `main` and this branch, byte-identical**. Neither field is written
  with agents off, so the no-Rust guard (18.28 MB) cannot change; it was not
  re-measured.
* The same world in hybrid, 300 turns: 11,192,915 to 11,226,728 bytes
  (+33.8 KB, +0.30%).
* Audit runs: procedural 48 x 10 all on, 200 turns +72.4 KB (+0.36%);
  template 10 x 5 all on, 200 turns +22.8 KB (+0.30%); template defaults,
  150 turns +15.7 KB (+0.37%); procedural 30 x 8 defaults, 150 turns
  +35.8 KB (+0.27%).

## Evidence

Linux, Python 3.13.17, a fresh `maturin develop --release` build of the
unchanged Rust tree (compiled `AgentSimulator`, `EcologySimulator`,
`PoliticsSimulator` verified), Node 22.

**Identity** (`scripts/viewer_systems_identity.py`, base `6e6fae6` source on
`PYTHONPATH` against this branch, same interpreter and extension,
`PYTHONHASHSEED=0`):

| Run | Mode | Files | Differences |
| --- | --- | --- | --- |
| guard world, agents off, 500 turns | `compare` | 10 | 0 |
| guard world, hybrid, 300 turns | `compare-additive` | 11 | 0 |
| procedural 48 x 10 seed 42, hybrid, 200 turns, all on | `compare-additive` | 16 | 0 |
| template 10 x 5 seed 7, hybrid, 200 turns, all on | `compare-additive` | 11 | 0 |
| template seed 42, hybrid, 150 turns, defaults | `compare-additive` | 10 | 0 |
| procedural 30 x 8 seed 7, hybrid, 150 turns, defaults | `compare-additive` | 14 | 0 |

`compare` is byte identity of every output (bundle without
`metadata.generated_at`): states, memories, agent events, chronicles,
historiography and languages sidecars. `compare-additive` removes only
`history[n].food` and `history[n].migration` from the branch bundle (and
requires the base bundle to lack them).

**Tests**: see the ledger entry (`docs/superpowers/progress/phase-6-progress.md`).
Python: `tests/test_viewer_snapshot_fields.py` (the two fields' contents,
turn scoping, omission, agents-off bundles, a native hybrid bundle);
`TestViewerFixtureContract` checks the fixture carries every field and that
its later-system fields still have the shape a fresh run writes. Viewer:
`lib/__tests__/food.test.ts`, `polity.test.ts`, `mapLayers.test.ts`, the new
panels in `SystemsPanel.test.tsx`, `AppShell.mapLayers.test.tsx`.

**Fixture.** `viewer/src/__fixtures__/systems_bundle.json` is regenerated by
`scripts/build_viewer_systems_fixture.py` from procedural 48 x 10 seed 42,
120 hybrid turns, all systems on, on this branch: every 10th snapshot and
the last (14), every system field as exported, the governance keys the panel
reads, famines in the first eight regions (whole spans) and the first 12
events of every other system type, plus the events they cite. 685 KB (was
437 KB).

**Browser.** The production build (`vite preview`) driven by headless
Chromium (Playwright) on the audit bundles: every new tab, each map layer,
the region inspector and the default-flag Campaign surface, with no console
errors or warnings.
Screenshots stay outside the repository with the run outputs.

## Cut and remaining gaps

* **Per-turn region population, fish stocks and merchant food deliveries**
  are not in the snapshot; the Food layer shows sufficiency and relief
  convoys, not where merchants carried food.
* **Nomad herds per region** are per civ in the snapshot (the final state
  has them per region), so there is no herd map layer.
* **Geography detail.** Elevation, moisture, biome and the land outline are
  not drawn; the "borders" overlay still links regions within a controller,
  not real adjacency.
* **Colour collisions.** Faction colours are hashed hues, so two civs can
  share one; strips and tables name civs, the map layers do in hover text.
* The fixture keeps every 10th snapshot, so its migration window and battle
  list are thinner than a real bundle's.
* Phone layout is not tuned (the shell is a desktop layout).

## First round

Branch `feat/viewer-systems` from `integrate/wave-4` at `1a6cacb`. Panels for
epidemics, finance, diplomacy, techniques and maritime; the region
inspector's epidemic and technique blocks; event rows that pin in the
inspector so causal provenance explains them; live-mode pass-through. Two
additive fields, written only with the system on:

| Field | Shape | Why |
| --- | --- | --- |
| `history[n].diplomacy.pairs` | holder -> target -> `[trust, total grievance]`, one decimal, every directed pair of living civilizations with a memory | `top_grievances` covers five pairs only |
| `history[n].techniques.regions` | region -> technique key -> practice share, two decimals, rows at or above 0.03 | known/practised are per civilization |

Size then: template seed 42 hybrid 120 turns +55 KB (1.5%), procedural
48 x 10 +183 KB (2.1%). Identity was proven with the same script (then
stripping these two fields): every output identical over six runs. Tests
then: `pytest -m "not slow" -n 2` 5,699 passed, 3 skipped; viewer 25 files,
197 tests.
