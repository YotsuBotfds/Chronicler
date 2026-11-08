## 06 Livelihoods, workshops, payroll, apprenticeship, guilds

**Map**
- 11 modules named in the brief total about 8,800 lines (livelihoods.py 1,255; apprenticeship.py 1,543; workshop_economics.py 1,024; workshop_payroll.py 863; guilds.py 781). Their 59 `*_state.py` siblings total about 8,945 lines in the package.
- `livelihoods.py` is the switch registry and wiring: `LIVELIHOODS_SWITCHES` (line ~130 of livelihoods_state.py), argparse (~600), `_check_prerequisites` (707-955), `configure_livelihoods` (961). Every switch calls `set_<name>_enabled`.
- Turn-loop hooks: `prepare_phase2`/`finish_phase2`/`rollback_phase2` in workshops.py (411, 551, 598); `before_crews` seams (workshops.py 248-260) feed the native crew planner; `phase10` in apprenticeship.py:1452 and adaptive_livelihoods.py:~398.
- Labour arbiter: `labour_reservations.booked()` (labour_reservations.py:71) is a read-only union of who already holds work. Only epidemic_care.py:418 and public_health.py:480 call it.
- Native authority: `workshop_work.rs` (`reserve`, line 100) and the Python `*_state` containers. Python never writes registry state directly except through `reserve_work` and `extend_paid_work`.

**Findings**

**(a) Dependency graph and validation.** Dependencies are real but partly enforced.
1. [med] bug — Saved-state prerequisite checks are inconsistent. Older switches check only an explicit request, e.g. `values["workshop_payroll"] is True` (livelihoods.py:754), `values["apprenticeship"] is True` (770), `values["operating_wear"] is True` (792), `values["repair_projects"] is True` (775), `values["recovery_crews"]` (785), `values["maintenance_obligation"]` (788). Newer ones use `_on()`, which also covers saved state (e.g. guild_leagues 881, timber_supply 800, reform_services 868). So resuming a saved world with `--no-workshops` or `--no-repair-projects` while apprenticeship or recovery crews stay saved is not refused. Whether the dependent goes inert or keeps running is unverified. Action: use `_on()` everywhere and add a resume test per prerequisite edge.
2. [low] `--workshop-payroll` checks workshops mode, but `--workshop-economics` (line 809) and `--apprenticeship` (771) use `_workshops_operate`, which has a different default for mode. Both are correct today, but the rule lives in three places.
3. Valid combinations are checked at config time with clear messages. Message text is pinned in places (e.g. tests/test_workshop_economics.py references the `--workshop-economics` refusal text), so reword with care.

**(b) The `*_state.py` pattern (duplication).** Counted by grep across src/chronicler:
- `def _bump(` is defined in 39 modules (e.g. adaptive_livelihoods.py:58, guilds.py:175, workshop_payroll.py:202). `def _state(` accessor in 39 modules.
- `__setstate__` in 29 state modules; `__getstate__` in 21; `PrivateAttr` in 39.
- `exclude_if=_is_none` pattern repeated 36 times in livelihoods_state.py.
- Four samples: livelihoods_state.py 157 lines (36 optional fields plus pickle hooks), workshops_state.py 100, operating_wear_state.py 57, adaptive_livelihoods_state.py 35 (its `__setstate__` re-fills defaults by hand).
- A shared `SwitchState(BaseModel)` base could hold `enabled`, `schema_version`, a `bump()` over a fixed counter key set, default-fill `__setstate__`, and the optional-field exclusion. Estimated saving 15–20 lines per module, roughly 600–800 lines. Constraint: pickle and dump key order must not change (see the streamlining table).

**(c) Labour double-booking.** The design is sound at the native layer and inconsistent at the Python layer.
4. [med] fragile — Native refusal is a hard exception. `workshop_work.rs:119` returns "agent already holds work this turn", and `reserve_work` (ffi/mod.rs:408) is all-or-none. Python pre-checks are per package: `labour_reservations.booked` (used by C2 and public health), `recovery_crews._excluded` (recovery_crews.py:238), and apprenticeship.py:467 and 1097. A new consumer that skips its check crashes the turn rather than skipping the person. No shared gate enforces the check.
5. [med] duplication/label — Native category 3 "repair" is shared by five consumers: RS2 repair (repair_projects.py:126), PL1 woodcutters (timber_supply.py:153, 595), PL3 crews (recovery_crews.py:422), C2 carers (epidemic_care.py:98, 510) and customs guards (public_health.py:532). `REASONS` in labour_reservations.py labels woodcutters and guards as `registry_repair`. Exclusion is correct (it is by person), but diagnostics misattribute the holder.
6. [low] Observe mode reserves nothing (workshops.py `prepare_phase2`: `reserve_turn = None if state.mode == "observe"`). Observe-mode crews therefore overlap C2 carers and guards in the same turn. This is documented as intentional; a check that observe crews never affect outcomes is missing.
7. [med] unverified — Farm time is removed by two mechanisms. The native `farm_labor_factor` already removes the diverted urban share (workshop_work.rs:19). C2 carers and guards also subtract farmer-equivalents per region with `remove_farm_time` (recovery_crews.py:585). That subtraction is aggregate, not per person, so an urban farmer's diverted share could be counted twice. Not verified against native output.

**(d) Dead modes and adaptive controls.**
8. [med] Adaptive oscillation. `_declines` (adaptive_livelihoods.py:~97-109) refuses a kind for `WORK_WINDOW = 10` turns after a window net of `net_milli <= 0`. A refusal is not written as a memory row: `accepts_offer` (128-150) appends only to `state.offers`. Once the window empties, the agent accepts again, so a persistently loss-making job gives an apparent limit cycle of about 11 turns. Migration has the same shape: `penalty_rows` (76-84) decays linearly and the total is clamped at `P_CAP` three times (84, 311, 381). There is no hysteresis. Predicted, not run; action: write a declined-memory row, or add a hysteresis band, and test a 30-turn trace.
9. [med] Inconsistent gap resets. `_work_index` (adaptive_livelihoods.py:88-91) clears memory and work on a gap. `before_agent_tick` (284-288) clears memory, work, known_residences and trade_experience. `on_pool_reset` (~455) clears a third set. A planner probe can trigger the first reset during Phase 2. Action: one reset helper with one definition of "gap".
10. [low] Shuffled-mode permutation is copy-pasted (adaptive_livelihoods.py:316-330 and 359-376). The rules-2 and rules-3 paths can drift.
11. [low] `after_agent_tick` raises `RuntimeError` when the native receipt is missing (adaptive_livelihoods.py:~415). This is intended, but it is a hard stop.
12. Dead modes: adaptive `rules "1"` and `mode "shuffled"` are retained for saved runs (not dead). `record_only` still computes penalties and then discards them (adaptive_livelihoods.py:~305-307). No fully dead mode found in this area.

**Other duplication**
13. [low] `_health_holders` is copied verbatim in apprenticeship.py:1191 and recovery_crews.py:226.
14. [low] `_lane_active` is copied five times: recovery_crews.py:158, workshops.py:232, repair_projects.py:292, timber_supply.py:247, labour_reservations.py:42.

**Simulation depth**
- Crew choice is ascending stable id (workshop_work.rs header, lines 14-16). Lowest ids are staffed first, with no use of the age, household or skill fields already in the pool. Rank by a per-person attribute, or sample with the RNG.
- Workshop labour is a fixed rank share `1 - URBAN_FARM_LABOR[rank]` (workshops.py:139-141) for every farmer in a city. Tie it to seasonal demand or to the city's real craft gap.
- Labour booking follows code order (C2 before public health, learning before crews). A demand queue would make the competition for labour explicit.
- The adaptive controls have no learning rate or memory weight. Adding one would give a tunable, testable speed of adjustment.

**Confidence** Verified by reading and grep: the switch validation, reservation exclusions, categories, the duplicate helper counts and the native refusal. Inferred: the oscillation period, the double-count in finding 7, and the inert-dependent behaviour in finding 1, which need a run to confirm.

**Streamlining candidates**

| Candidate (path or symbol) | Action (delete / merge into X / extract / rewrite) | Lines saved (approx) | Breaks or blocks (tests, pins, CLI flags, saved-bundle compat) | Risk (low/med/high) |
|---|---|---|---|---|
| `_bump` in 39 state-owning modules | extract into a shared `SwitchState.bump` | ~120 | Counter dict key sets are dumped; key order and float vs int types must match. No CLI flag. | med |
| `_state(world)` accessor in 39 modules | extract `lane_state(world, name)` | ~100 | None public; some modules name it `_state` in tests via monkeypatch (unverified) | low |
| `_lane_active` (recovery_crews.py:158, workshops.py:232, repair_projects.py:292, timber_supply.py:247, labour_reservations.py:42) | merge into one helper in a leaf module | ~40 | None; cycle risk if put in a module that imports the lanes | low |
| `_health_holders` apprenticeship.py:1191 | delete, import recovery_crews' copy | ~10 | Docstring cites the other copy; no CLI flag | low |
| Shuffle block adaptive_livelihoods.py:316-330 and 359-376 | extract `_shuffle_rows` | ~15 | Rules-2 saved runs must stay byte-identical; check against a checkpoint | med |
| `__setstate__` default-fill in 29 state modules | move into a base class | ~150 | Pickle compat: exact restoration depends on it; saved bundles and checkpoints must load unchanged | med |
| `labour_reservations.booked` vs `recovery_crews._excluded` (recovery_crews.py:238) | merge; delete `_excluded` | ~14 | recovery_crews.py docstring keeps `_excluded` unchanged so PL3 outputs stay the same; a test checks the two agree | med |
| `_check_prerequisites` repeated saved-or-explicit checks (livelihoods.py:707-955) | table-driven rules, with `_on` everywhere (fixes finding 1) | ~60 | Refusal messages are pinned in tests (e.g. `--workshop-economics`); `LivelihoodsRefusal` vs `ValueError` split must be kept | med |

**Pinned or compat notes:** `scripts/testing/native_shards_manifest.json` and the source-witness fixtures were not checked for these files (not in brief scope); run `scripts/refactor_preflight.py` before moving any of them. Saved-bundle compatibility: every `*_state` field is part of a pickle or dump; deleting a field is not safe without a migration.
