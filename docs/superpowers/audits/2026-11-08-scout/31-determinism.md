## 31 Determinism and RNG
**Map**
- RNG is almost entirely per-call `random.Random(...)` instances; there is no world-level RNG object (no `world.rng`), no numpy RNG and no module-global `random.seed` in `src/chronicler/`. About 88 construction sites; about 67 key on `stable_hash_int(namespace, seed, turn, ...)` (utils.py:38, sha256 over a stable serialisation, sets sorted at utils.py:24-26).
- The turn loop draws through `simulation.py` (black swans via `emergence.check_black_swans`, env hazards at simulation.py:216, leader death/crisis at simulation.py:955/1005, artifact gate at simulation.py:1065-1066).
- Batch: `batch.py:95-135` (sequential and `multiprocessing.Pool`), summary at `batch.py:~225` (`_write_summary`).
- Exact-run guard: `what_if.py:224-228` (`require_hash_seed`).
- Scope: Python package only. Rust `chronicler-agents` RNG not audited.

**Findings**
1. [high] bug: `war_requisition.py:183-188` greedily debits food goods by iterating `FOOD_GOODS`, a `frozenset[str]` (economy.py:51). Iteration order depends on PYTHONHASHSEED. Verified with `.venv/bin/python -I` on the frozenset: seeds 0-4 give five different orders. Which good is drawn down first changes the stockpile outcome. Gated to hybrid mode with `--war-requisition` (livelihoods.py:895). Action: iterate a fixed tuple; this is an intentional outcome correction and must be documented, with pinned baselines checked. Tests in tests/test_war_requisition.py do not vary hash seed.
2. [med] bug: `action_engine.py:198` `rng = random.Random(world.turn * 1000 + civ_idx)` ignores `world.seed`. The EXPAND target at `action_engine.py:215` (`rng.choice(unclaimed)`) draws the same uniform stream for every seed. Deterministic, but the choice is correlated across seeds and cannot be varied by seed. Action: `stable_hash_int("expand", world.seed, world.turn, civ.name)`.
3. [med] fragile: additive integer seeds collide across systems that share a stream value. `agent_bridge.py:2244` (`seed+turn+agent_id`) and `artifacts.py:654` via `simulation.py:1067` (`seed+turn+civ_idx`) produce identical `random.Random` streams whenever agent_id equals civ_idx in the same turn. `simulation.py:1066` (`seed+turn+civ_idx+8888`) collides with `agent_id` values near 8888. Also `emergence.py:226,257,396,514,603,650` and `simulation.py:2005` use `seed + turn*K` with distinct K. Those collide only at turn >= K, but the scheme is fragile. Action: route all of them through `stable_hash_int` with a namespace. Changing them alters outcomes, so do it with a baseline.
4. [med] latent str-hash dependence: `economy.py:442-450` sums `clamp_floor_loss` in set-iteration order of `all_keys`. Float addition is order-sensitive in the last bits. The value is returned to `economy.py:2019` (`conservation["clamp_floor_loss"]`) and read at `analytics.py:2211`. It is nonzero only when the clamp fires. Action: iterate `sorted(all_keys)` or use `math.fsum`.
5. [med] test-gap: `batch.py:122` uses real `multiprocessing.Pool` with no `set_start_method`. Linux forks, and macOS spawns, where children do not inherit the parent's hash secret unless PYTHONHASHSEED is set in the environment. Nothing sets it: `batch_manifest.py:192` only records it. Outputs are order-stable: results are appended in submission order (`batch.py:126-133`), and `_write_summary` uses a stable sort. The only parallel-vs-sequential test, `tests/test_batch.py:153`, uses `_InlinePool` (line 115-117) and never exercises real processes or a second hash seed.
6. [low] fragile: `live.py:1282-1287` (`resolve_start_seed`) uses the module-global `random.randint` when a start has no seed. This is the only module-global `random` call in `src/`. It is an input, not a stream; whether the resolved seed is written into bundle metadata is unverified.
7. [low] test-gap: feature-off tests (e.g. tests/test_gp_agendas.py:933, tests/test_epidemiology.py:156) assert that the feature's code never runs. No test checks that toggling feature A leaves feature B's draws unchanged. No guard forbids module-level `random` or additive seeds. tests/test_action_engine.py:461 pins one `stable_hash_int` stream.
8. [low] dead-code (used only by tests): `events.py:208` `roll_for_event`, "no longer used by the turn loop" (docstring). Grep: src/ has no caller. tests/test_events.py:16-33 calls it. Used only by tests; no CLI flag.
9. [low] clock: none affects outcomes. `narrative.py:1752-1755` is ETA telemetry. `what_if.py:513-520` (ARM_TIMEOUT) can abort an arm, which affects whether a pair is produced, not its contents. Timestamps are output metadata (`bundle.py:93`, `analytics.py:1312`, `live.py:556`, `bundle_codec.py:382-454` timings). `validation_io.py:69` SCRUB_KEYS scrubs only `generated_at`, so the `analytics.py:1312` timestamp is not scrubbed in comparisons (unverified whether it is compared).
10. [low] fine: max/min ties are resolved by id (`religion.py:211-216`, `257-263`); `sorted` calls are keyed on ints/strings. Enum frozensets (institutions.py:130-136, ecology.py:1032) are used for membership only.

**Simulation depth**
- Per-region and per-route draws are already keyed (`geography.py:209`, `resources.py:59`); extend the same namespace pattern to expansion (finding 2) so seed sweeps vary expansion targets.
- A single `system_rng(system, namespace, world, *parts)` helper would make the stream contract auditable and allow a per-feature stream census.
- Hash-seed sweeps (PYTHONHASHSEED 0..N) in CI would catch finding 1 and similar drift automatically.

**(a) RNG source table**
| Stream / owner | Seeded how | Draws from it |
|---|---|---|
| Per-system namespaced `Random` (`_rng` helpers) | `stable_hash_int(ns, seed, turn, ...)` | war/common.py:88, diplomacy.py:248, maritime.py:412, guilds.py:171, cities.py:241, nomads.py:243, agent_movements.py:263, scholarship.py:165, gp_agendas.py:241, governance_runtime.py:312, grain_convoys.py:473, epidemiology.py:299, techniques.py:209, harvest_forecasts.py:294, scientific_claims.py:300, geography.py:268 |
| Politics/leader/succession | `stable_hash_int("successor"/"congress"/..., seed, turn, civ)` | politics.py (19 sites), politics_bridge.py, succession.py, leaders.py:292, factions.py:656/728 |
| Raw int seeds | `seed + turn*K`, `seed + turn + id`, `seed ^ ...` | emergence.py:226-1033, agent_bridge.py:2244/2275, simulation.py:1066/2005, religion.py:138, politics_bridge.py:1193 |
| Turn-indexed, not world-seeded | `turn*1000 + civ_idx` | action_engine.py:198 (EXPAND) |
| Pass-through seed | caller-supplied | action_engine.py:760 (resolve_war), artifacts.py:131/657, events.py:220 (legacy), world_gen.py:87/114/454, intelligence.py:209 (sha256) |
| Module-global `random` | none seeded | live.py:1286 (start with no seed) |
| numpy RNG | none in src | (np used for arrays only) |
| `hash()` builtin | none | PYTHONHASHSEED enters only via set/frozenset/enum iteration (findings 1, 4) |
| uuid | uuid4 | what_if.py:369 (output dir name) |
| secrets | token | artifact_io.py:105 (temp name), live.py:181 (session token) |
| os.urandom | none | - |

**(b) Per-feature streams**: no shared RNG object exists. Systems derive their own `Random` per call from `stable_hash_int(namespace, ...)`, so one system's draw count cannot shift another's. The exceptions are the raw-int seeds (finding 3), where two systems can share one stream value. Feature-off identity can still differ through world state: a feature that changes agent creation changes `agent_id`, which changes the `agent_bridge.py:2244` stream. That is state coupling, not stream sharing.

**(c) Set iteration**: the audit was sampled, not exhaustive over ~67 set/frozenset sites. Confirmed findings 1 and 4 (order-sensitive). `household_retail.py:1994-2002` (`next(iter(homes))` only when len==1), `techniques.py:780`, `agent_bridge.py:2154` (dict build) are order-safe.

**(d) PYTHONHASHSEED**: the requirement (`what_if.py:227`; tests in tests/test_what_if*.py) is consistent with finding 1 (`war_requisition.py:183`) and finding 4. A pydantic `__pydantic_fields_set__` order issue (tests/test_grain_storage.py:93) affects serialisation only. Removal: convert both sites to ordered iteration, then audit the remaining set/frozenset iteration before relaxing `require_hash_seed`. The change would alter seed-0 outcomes for the war-requisition path, so it needs a documented correction.

**(e) Clock**: see finding 9. No clock influences outcomes.

**(f) Parallel order**: results and summary are order-stable (see finding 5). Real multiprocessing with varied hash seeds is untested.

**(g) Tests**: good coverage. Same-seed determinism, save/load continuation and hash-seed-varied subprocess tests exist (tests/test_checkpoint_replay.py:349-372, tests/test_run_checkpoint.py:218, tests/test_governance_measurements.py:1039, tests/test_experiment_receipt_inspector.py:321). Gaps: no stream-isolation test, no seed-collision guard, no real parallel batch test, no hash-seed sweep of the war-requisition food debit.

**Streamlining candidates**
| Candidate (path or symbol) | Action (delete / merge into X / extract / rewrite) | Lines saved (approx) | Breaks or blocks (tests, pins, CLI flags, saved-bundle compat) | Risk (low/med/high) |
|---|---|---|---|---|
| events.py:roll_for_event (208-230) | delete | ~25 | tests/test_events.py:16-33 (no pins; no CLI flag; no bundle field) | low |
| `_rng` helpers in war/common.py:88, diplomacy.py:248, maritime.py:412, guilds.py:171, cities.py:241, nomads.py:243, agent_movements.py:263, scholarship.py:165, gp_agendas.py:241, epidemiology.py:299 | extract to one `system_rng(system, ns, world, *parts)` in utils.py | ~30 | hashed tuple must stay byte-identical (`stable_hash_int("<system>", ns, seed, turn, ...)`), or outcomes change; no pins known (unverified in fixtures) | med |
| Local re-imports `import random as _random` at simulation.py:992/1065/2004, factions.py:637, artifacts.py:130/656, agent_bridge.py:2191, live.py:1284, relationships.py:454 | merge into module-level `import random` | ~10 | none | low |
| tech_focus.py:237 `_tiebreak_hash` (sha256 of f-string) vs `utils.stable_hash_int` | merge into X | ~5 | changes tie-breaks, so outcomes change; needs baseline | high |
| economy.py:442-450 float sum over set | rewrite (sorted keys) | 0 | changes last-bit conservation diagnostic only | low |
