# Behaviour Corrections (COR-3 to COR-8) — Design Spec
> **Status:** Proposed (not started)
> **Date:** 2026-11-08
> **Tasks:** COR-3, COR-4, COR-5, COR-6, COR-7, COR-8
> **Depends on:** DEC-4 (D4 provenance reads), DEC-5 (D5 health crowding), DEC-7 (D7 era-advance cost rule); PIN-1 (D1) for any enforced file
> **Feeds:** CON-5 (shared Python/Rust constants), CON-1, DEP-2, DEP-3
> **Source:** docs/superpowers/audits/2026-11-08-streamlining-scout.md (+ scout reports 14, 10, 15, 09, 08, 02, 12, 21, 29)

## 1. Goal and scope
Six separate corrections, one PR each (COR-5 is five PRs). Each fixes a verified defect and each
changes something observable. Every PR needs a baseline, a CONTINUATION entry and, where a DEC
applies, owner sign-off before it merges. This spec also records where an audit claim was wrong,
because three of the six are smaller than the audit says.

Not in scope: the RNG hygiene correction (COR-1), the governance default (COR-2), closed money
supply (DEP-6), and deleting the legacy war model.

## 2. Current behaviour (verified)
**COR-3.** `tech.check_tech_advancement` emits `capability_scholarship` at `src/chronicler/tech.py:101-106`,
before the culture/economy/treasury gate at `:108`. A civ on the scholarship focus that cannot afford the
advance therefore logs the event every turn. The literal `0.8` is at `:101`. `techniques.SCHOLARSHIP_COST = 0.8`
is at `src/chronicler/techniques.py:106`. Only `simulation.phase_technology` (`simulation.py:1579`) calls this
function, and it runs only when techniques are off (`simulation.py:2205-2212`). New worlds default techniques on
(`main.py:1699-1704`, `DEFAULT_ENABLED_FOR_NEW_WORLDS` is True). **Audit claim corrected:** under techniques,
era advance is not free. `_invent` (`techniques.py:539-578`) charges `era_cost / INVENTIONS_PER_ERA / rate`
(x0.8 for scholarship) per invention, with the capability event emitted after the charge. `_advance`
(`techniques.py:789`) charges nothing because the cost was already paid per invention. Techniques per tier
are 6, 5, 5, 6, 4, 3, 1 (probed), against `INVENTIONS_PER_ERA = 2`, so the total cost per era is a different
quantity from the legacy single charge.

**COR-4.** `PublicHealthState.crowding` defaults to `legacy_displacement` (`public_health_state.py:46`).
The setter `set_public_health_enabled` creates the state with `PublicHealthState()` when none exists
(`public_health.py:36-39`) and sets `crowding` only if `args.public_health_crowding` is given. The legacy mode
multiplies susceptibility by `1.0 + DISPLACEMENT_CROWDING * displaced` (`public_health.py:427`). `check_request`
(`public_health.py:52-58`) and `livelihoods._check_prerequisites` (`livelihoods.py:1056-1066`) reject a given
value that differs from a saved one. Tests pin the current behaviour at `tests/test_residence_exposure.py:445-466`.
The help text says "unchanged default" (`livelihoods.py:244`).

**COR-5.** `tests/test_provenance_decision_guard.py:176-193` lists seven reads (the pointer said "one more": it is
`scholarship._sack_cause`). Detail is in section 3. Scholarship is opt-in (`expansion_features.py`);
the other four are on the default path.

**COR-6.** (a) `war/runtime.py:107-115`: the truce and `can_raise` early returns skip `world.events_timeline.extend(ctx.events)`
and `flush_military_losses(ctx)` (`:139-140`). `reconcile_wars` can have emitted `war_ended`/`war_declared`
into `ctx.events` (`war/peace.py:313`, `:90`), and `emit` has already called `provenance.observe_now`
(`war/common.py:249`), so those events keep ids but never reach the timeline. (b) `war/armies.py:340-343`: the
non-roster branch ignores the return value of `drain_population`, so `army.soldiers` and `army.casualties` fall
by `count` even when no region could supply it. (c) `reconcile_rosters` adds roster losses from natural deaths
to `army.casualties` (`war/armies.py:447`). `army.casualties` also decides "destroyed" or "demobilized"
(`war/runtime.py:208`) and the attribution closure (`attribution_records.py:619`). The 17% figure comes from
`docs/superpowers/roadmaps/connected-world-program.md:420`; I did not re-measure it.

**COR-7.** Rust `step_forced_collapse` (`chronicler-agents/src/politics.rs:2888-3025`) emits ops with step 11. Python
drops them (`simulation.py:1434-1440`) and runs its own collapse after `apply_asabiya_dynamics`
(`simulation.py:1446-1486`). The copies differ: Python applies the severity multiplier (`:1465`) and reads
post-aggregation asabiya; Rust uses neither. Step 11 is the last step, so nothing downstream reads its
`live_civs` mutation. Tests assert step 11: `chronicler-agents/tests/test_politics.rs:1147-1220`, `:1610`,
`tests/test_politics_parity.py:700-715`, `tests/test_politics_bridge.py:1603-1606`.

**COR-8.** **Audit claim largely wrong for `hills`.** `ffi_constants.TERRAIN_MAP` maps `hills` (and `river`) to 0 =
plains on purpose (`ffi_constants.py:12-26`). Python `.get(region.terrain, ["plains"])` (`ecology.py:475`, `:1310`,
`climate.py:315`) therefore matches Rust `TERRAIN_CAPS[plains]` (`ecology.rs:85`, `:417-421`). `TERRAIN_ECOLOGY_DEFAULTS`
is read only with literal keys `"plains"`/`"forest"` (`ecology.py:636-639`, `timber_stock.py:104`). The gap is
a missing explicit row and a missing test. **Unread tuning keys confirmed:** the eight constants
(`K_TWILIGHT_STABILITY`, `K_FAMINE_WATER_THRESHOLD`, `K_DISEASE_BASELINE_FEVER/CHOLERA/PLAGUE`,
`K_FAMINE_REFUGEE_POP`, `K_MAX_TEMPLES_PER_REGION`, `K_TEMPLE_CONVERSION_BOOST`) appear only in `tuning.py`
(lines 29, 47, 57-59, 110, 199, 201, and `KNOWN_OVERRIDES` at 293-323); equivalent behaviour uses module
constants (`infrastructure.py:37-39`, `world_gen.py:467-480`). **`TITHE_RATE` claim corrected:** there is no
tuning key for it (`tuning.py` has no tithe entry), so no override can desync. The hazard is two literals,
`factions.py:35` and `economy.rs:113` (`EconomyConfig` has `tax_rate` but no tithe field, `economy.rs:128-163`).

## 3. Design
**COR-3 (needs DEC-7).** Event-order fix, no owner choice needed: emit `capability_scholarship` only when the
advance is paid (after the gate, next to the charge). Import the multiplier from one place: define
`SCHOLARSHIP_COST_MULTIPLIER = 0.8` in `tech.py` and have `techniques.py` re-export it as `SCHOLARSHIP_COST`
(`techniques.py` already imports `tech` lazily). Cost-rule options for the owner:
- **A (recommended):** keep both rules. Legacy = one charge per advance; techniques = per-invention charge. Document it in `docs/integration/techniques.md`. No outcome change on the default path.
- **B:** also charge at `_advance`. Double-charges; reject.
- **C:** calibrate invention cost so the expected total per era approximates the legacy charge (for example `era_cost / len(_BY_TIER[tier])` with a cap). Default-path outcome change; needs the 200-seed gate.
- **D:** remove the legacy charge. Reject: `--no-techniques` worlds and old saved worlds need it.

**COR-4 (needs DEC-5).** In `set_public_health_enabled`, when no state exists create
`PublicHealthState(crowding="density_only")`; an explicit `--public-health-crowding` still wins. Do not change the
pydantic field default or `__setstate__` handling, so saved JSON and pickles keep their recorded mode.
A state that already exists (enabled or later disabled) is never changed. Update the `livelihoods.py:244` text.
A world saved with public health never enabled has no state, so its first enable becomes `density_only`:
that is the intended "new enable" case.

**COR-5 (needs DEC-4).** Method for every read: add the replacement state first, run a shadow comparison
(old read equals new read on a seed batch), then switch and remove the guard entry. A shared new field helps three
reads: `Region.last_takeover: tuple[int, str] | None` (turn, "conquest"|"occupation"), written where the
events are emitted (`war/occupation.py:105`, `:164`, `action_engine.py:659`), `exclude_if=_is_none` so saved bytes
do not change. `Occupation.since_turn` (`models.py:895-902`) already covers occupation.

| # | Read | Decides | Replacement | Default path | Expected change |
|---|---|---|---|---|---|
| 1 | `cities._lord_change` recall conquest/occupation within 1 (`cities.py:570-580`) | sack vs peaceful lord change | `region.last_takeover` within 1 | yes | near zero if written at the same sites; differs only when a key was overwritten or forgotten |
| 2 | `diplomacy._aid_convoys` `ev.episode == "tick"` (`diplomacy.py:1759`) | skip famine ticks, so aid follows onsets and repeats | per-region famine state: `Region.famine_cooldown` (`models.py:441`) or a new onset flag | yes | unknown; episode gap rules are not equal to cooldown, so expect small shifts in aid timing |
| 3 | `epidemiology._reports` `open_episode(...) is None` (`epidemiology.py:905`) | arrival event and source reset | a persisted `reported`-since-onset flag on the epidemiology row | yes | unknown; row.reported is cleared when the outbreak subsides, the episode closes by gap, so they can differ |
| 4 | `nomads._herds` recall drought within 10 (`nomads.py:825`) | gates `pasture_drought` | active drought condition for the civ (`events.py:498` `has_condition`) with a remembered end turn | yes | event emission timing only (condition lasts fewer turns than the 10-turn recall) |
| 5 | `scholarship._in_famine` (`scholarship.py:750`) | blocks a founding | same famine state as #2 | no (opt-in) | none on defaults |
| 6 | `scholarship._newly_occupied` (`:389-391`) | strikes the seat | `Occupation.since_turn == turn` | no | none on defaults |
| 7 | `scholarship._sack_cause` (`:398-407`) | hostile lord change, blocks founding | `region.last_takeover` | no | none on defaults |

I have not measured any of these. "Expected change" is a hypothesis for the baseline to settle.

**COR-6.** Three independent PRs (the first two are cheap, the third needs a decision).
(a) In both early returns, extend the timeline with `ctx.events` and flush military losses before returning.
Stream-only plus any stat the flush applies. (b) `count = drain_population(...)` result clamps what dies when the
roster is empty; decide whether soldiers die only if people were drained (recommended: yes, it makes the army
shrink match the population ledger). (c) Add `Army.natural_deaths: int = 0` (default, omitted when 0), book
`reconcile_rosters` losses there, keep `army.casualties` for campaign deaths, and update the closure in
`attribution_records.py:619` to add both. This changes the "destroyed" vs "demobilized" verdict for armies whose only
losses were natural. Owner call: DEC-7 covers only the war-model keep decision; flag (c) separately.

**COR-7.** Recommend **delete Rust step 11** (option B). Rust-authoritative (option A) would change
outcomes (severity multiplier, asabiya timing) and need `simulation.py` edits (enforced pin). Deleting leaves Python
output byte-identical. Keep `CivOpType::StripToFirstRegion` and the `ffi/batch.rs:125` mapping, since removing the
enum variant is an FFI change. Keep `op[0] != 11` as a harmless filter until a later cleanup. Keep the Python oracle
fallback untouched. Update the module comment at `politics.rs:1-5` and delete or rewrite the tests listed above.

**COR-8.** Three PRs. (a) `hills`: add explicit `hills` and `river` rows equal to the `plains` rows to both
tables, plus a test that every `TERRAIN_MAP` key resolves and that Python and Rust agree
(use `tests/test_ecology_parity.py`). Behaviour-preserving. (b) Unread keys: do not wire them; remove them from
`KNOWN_OVERRIDES` handling by moving them to a `DEPRECATED_UNREAD_KEYS` set. `load_tuning` warns
`"tuning key X is accepted but has no effect"` and still accepts the value. The constants stay for import
compatibility. (c) `TITHE_RATE`: add a parity test (Python `factions.TITHE_RATE` against the Rust constant, via a
tiny exported getter or a regex test on `economy.rs`); defer an `economy.tithe_rate` key to CON-5.

## 4. Compatibility
No saved-bundle field is removed. New fields (`last_takeover`, `Army.natural_deaths`) are optional and omitted when empty,
and old bundles load. Old pickles keep `legacy_displacement`. Tuning files naming deprecated keys still load.
Viewer and CLI flags are unchanged. COR-5 and COR-6 change event streams, so narration of existing seeds shifts.

## 5. Pins and preflight (ran `scripts/refactor_preflight.py`)
| File | Level | Handling |
|---|---|---|
| `simulation.py` | enforced (11 witnesses) | untouched by the recommended designs |
| `agent_bridge.py` | enforced (7) | untouched |
| `tuning.py` | enforced (4) | COR-8b needs PIN-1 or an inverse layer |
| `ecology.py` | enforced (2); `ecology.rs` enforced | COR-8a needs PIN-1; or leave the Python tables and add only the test (fallback) |
| `economy.py`, `economy.rs`, `ffi/mod.rs` | enforced | untouched (COR-8c is test-only) |
| `scholarship.py` | enforced | COR-5 #5-#7 need PIN-1 |
| `tech.py` | digest-recorded in `tests/fixtures/performance/corrected_*.json` and reference_baselines | COR-3 needs the digest owner test read first; do not rewrite the hash |
| `techniques.py`, `public_health*.py`, `livelihoods.py`, `war/*`, `cities.py`, `diplomacy.py`, `epidemiology.py`, `nomads.py`, `factions.py`, `politics.rs` | reference only | proceed with tests |
| `war/armies.py` | no pins | proceed |

## 6. Classification
All six are corrections. COR-8a and COR-7 (option B) are behaviour-preserving in effect and need only
`turn_speed_identity` byte identity plus the native/parity tests. COR-3 event move and COR-6a change the event stream only.
COR-4 changes only worlds that enable public health (default off), so identity cases do not move.
COR-5 #1-#4, COR-6b, COR-6c, and COR-3 option C change default-path outcomes.

## 7. Tests
`test_tech.py`, `test_techniques.py` (event order, constant identity); `test_residence_exposure.py` (flip the
default assertion, add explicit-legacy, saved-legacy and disable/enable cases), `test_public_health_integration.py`;
`test_provenance_decision_guard.py` (guard set shrinks per PR); one test file per decision read (`test_cities.py`,
`test_diplomacy.py`, `test_epidemiology.py`, `test_nomads.py`, `test_scholarship.py`); `test_war_armies.py`,
`test_war_integration.py`, `test_attribution_records*.py` (COR-6); `test_politics_parity.py`, `test_politics_bridge.py`,
`chronicler-agents/tests/test_politics.rs` (COR-7); `test_ecology_parity.py`, `test_tuning.py` (COR-8).

## 8. Risks and rollback
Shadow comparison may show #2 and #3 are not equal; then the owner chooses between keeping the grandfathered read
and accepting the shift. COR-7 needs a native rebuild into the separate venv. Each PR reverts independently.
Unverified: whether `live.py` reaches `set_public_health_enabled` with a crowding arg; how `apply_region_conquest`
sets `last_conquered_turn`.

## 9. Size
About +350/-250 lines across 14 PRs: COR-3 1, COR-4 1, COR-5 5 (reads 5-7 share a PR because they are opt-in and share one file), COR-6 3, COR-7 1, COR-8 3.
