# Static artifact region history inspector

This bounded addition to the existing React viewer inspects the public `edf7299`
legacy single-artifact export surface. It does not activate the dormant Phase 7.5
Tauri/Bundle v2 roadmap or make any claim about private `b665e198` science.

## Use

1. In `viewer/`, install locked dependencies with `npm ci`, then run `npm run dev`.
2. Choose **Open Existing** and open a local `chronicle_bundle.json`.
3. Expand **Inspect region history** in Overview, Character, Trade, or Campaign.
4. Choose a region, metric, inclusive turn window, and optional event type.
   **Use map selection** adopts a selected region without overriding manual filters.
5. Read raw values and their JSON pointers in the table. Turn buttons navigate the
   existing timeline; tables show 50 rows per page. Dots show recorded ecology
   observations without connecting lines. The main viewer starts at turn 1;
   observations outside its navigable range remain inspectable in the table.

The panel is closed by default. Existing reports, exports, simulation mechanisms,
and layered-bundle compatibility behavior are unchanged. Live streams do not show
this panel because their `world_state` is the initialization observation, not a
terminal state. Static sparse/resumed artifacts use their declared run endpoint
for navigation; live navigation uses the newest received snapshot turn.

## Evidence semantics

- Soil, water, and forest cover come only from `history[i].ecology[region]`.
  Missing fields, invalid numeric values, and unsampled turns have explicit labels.
  Zero stays zero. No forward-fill, terminal-state backfill, or resampling occurs.
- Controller labels come from the exact snapshot, with separate labels for
  uncontrolled and unrecorded. Region names include historic records, not just
  surviving terminal regions. Region joins follow the legacy name-based contract;
  stable entity IDs are deferred to Bundle v2.
- Stockpiles exist only in `world_state.regions[i].stockpile.goods`. Each good is
  shown separately at `world_state.turn`. Historic stockpiles are labeled absent;
  final values never populate history rows. An absent good is not assumed to be
  zero. A history snapshot and final-state observation can share a turn and remain
  separate records. There is no computed food or edible-food aggregate; salt is a
  separate named good. The viewer displays exported units without conversion.
- Regional events require `named_events[i].region` to match. Controller event
  context is opt-in and matches `events_timeline[i].actors` to an exact-turn
  controller record. It does not establish region attribution or causality.
  Controller-context events during snapshot gaps and Arrow agent-event sidecars
  cannot establish a regional association here. Explicit named-event region
  records remain inspectable even during a snapshot gap. “No events” means no matching
  exported records, not proof nothing occurred.
- Provenance includes original array indices and escaped JSON pointers. Missing
  fields show the expected field path or containing record alongside their
  availability label. Duplicate observations are retained, not silently deduped.
- File name, byte count, and SHA-256 identify the exact original bytes including
  whitespace and UTF-8 BOM. The hash is not derived from parsed/reserialized JSON.
  BOM-marked UTF-16 LE/BE files retain the previous loader's decoding compatibility;
  their hashes still identify the original bytes.
  If Web Crypto is unavailable, the UI labels the hash unavailable. Metadata is
  shown as run context, not as a substitute for content identity. Asynchronous
  file loads cannot overwrite a newer artifact with an older delayed hash.

## Deterministic fixture and checks

`viewer/src/__fixtures__/region_inspection_bundle.json` is synthetic seed 1701
with fixed timestamp, two regions, sampled turns 1/3/5, changing control, zero and
missing ecology, an exact-region event during a sample gap, unrelated events,
and separate terminal grain (0), salt (7), and timber (3) observations. It is an
inspection contract fixture, not scientific validation or empirical evidence.

Run `npm test`, `npm run build` (includes TypeScript checks), and `npm run lint`
from `viewer/`. Tests cover filtering, missing vs zero, unrecorded turns, source
escaping/index preservation, no input mutation, terminal-only goods, event scope,
pagination, original-byte identity, file-load races, and static/live navigation.

With Python Playwright and local Chromium available, start Vite and run
`python scripts/qa_region_history.py` from `viewer/`. It exercises the real app
on desktop and mobile viewports. Screenshots stay under
`/tmp/chronicler-region-qa` by default. No browser downloads or external services
are needed in this environment.

## Boundaries

This remains a browser inspector for a loaded legacy artifact. It scans the
already-loaded history; it does not claim large-layer indexing/performance gates,
discover raw Arrow sidecars, reconstruct absent resource history, or prove causal
mechanisms. UI tables are bounded, while the sample chart uses the selected
window. No simulation/export changes, paid services, Drive writes, hosting,
deployment, credential changes, or public promotion are part of this lane.
