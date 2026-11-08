# Turn-Loop Consolidation — Design Spec
> **Status:** Proposed (not started)
> **Date:** 2026-11-08
> **Tasks:** CON-3, CON-4, CON-11 (plus COR-10)
> **Depends on:** PIN-1 (DEC-1 option A) for every edit to `simulation.py`, `agent_bridge.py`, `grain_reserves.py`, `grain_storage.py`, `finance.py`; DEC-7 (delete the formation fallback)
> **Feeds:** DEP-6 (closed money supply), CON-1 (gate column), FIX-3, FIX-7, CON-10
> **Source:** docs/superpowers/audits/2026-11-08-streamlining-scout.md (+ scouts 01, 03, 04, 09, 22)

## 1. Goal and scope
Three behaviour-preserving refactors of the turn loop. All stay default-off-neutral and change no outcome.
- **CON-3:** one treasury seam (`treasury.py`) replacing the `if acc is not None: acc.add(...) else: civ.treasury ±= …` pair, and one public accumulator reader replacing five private-field readers.
- **CON-4:** an ordered hook table for the feature calls in `run_turn_result`.
- **CON-11:** delete the Python relationship-formation fallback.

Not in scope: the core `phase_*` calls, the economy transaction block (`try … except BaseException`), the learning/livelihoods `tick_agents` wrappers, `apply_asabiya_dynamics` routing (scout 01 finding 8), any change to fiat sources, and moving `_treasury_tax_carry`.

## 2. Current behaviour (verified)
- `run_turn_result` is `simulation.py:1891-2772`. Gated feature calls: 25 outside the economy transaction (my count). 17 are `_emit(tick_X(...))`; the rest are observers or `acc` writers with no emit. Gates are `_X_on(world)` (simulation.py:83-110, 2543), `getattr(world,"livelihoods"|"finance") is not None`, and the plain attributes `world.campaigns_enabled` and `world.mutual_aid_enabled`. Gates use `isinstance` on real state objects, so mocks read as off (maritime.py:136, contact_ledger.py:193).
- Six Phase-10 hooks evaluate `world.events_timeline[_hazard_timeline_start:] + turn_events[_pre_phase10_count:]` **at call time** (simulation.py:2454-2510). Each therefore sees events emitted by earlier hooks. A registry must keep that lazy.
- Phase 10 order matters and interleaves livelihoods with grain reserves: livelihoods-before-reserves (2526) → grain reserves (2530) → livelihoods phase 10 (2535) → ritual gatherings (2543).
- Both `except BaseException` handlers re-raise (simulation.py:2134-2140, 2326-2333). The audit's "re-raise not verified" is resolved: they do. Leave them.
- Off/shadow/demographics-only turns pass `phase10_acc = None` (simulation.py ~2433), so the `else:` direct-write branch of every Phase-10 dual path **is a production path**, not test-only. The two branches are not equivalent: the `acc` path floors treasury at 0 and casts via `type(current)(…)` in `apply` (accumulator.py:145-156); direct writes do not floor (`civ.treasury -= x`), except at sites that spell `max(0, …)` (action_engine.py:835-836, grain_reserves.py:668, finance.py:427).
- Treasury writes: the regex `\.treasury\s*[-+*]?=[^=]` has 55 hits in `src/chronicler`, of which 2 are false positives (`self.treasury` at wealth_accounting.py:355 and grain_reserves.py:915); 53 are civ writes. By AST, 107 `if acc is [not] None … else` blocks exist, 48 of them touching treasury (scout said ~40). Restores and overrides (scenario.py:623, politics_bridge.py:1013, politics.py:1259) are not flows.
- **Five divergent "projected treasury" folds** read `acc._changes` privately: `war/common.py:203-213` (unfloored, watermark), `diplomacy.py:324-333` (unfloored, watermark), `clearing_protection.py:189-203` (floored, casts, all categories in off mode), `mutual_aid.py:133-141` (floored, watermark), `finance.py:370-381` (floored, watermark). A sixth, `gp_agendas.py:303-308`, **ignores the watermark** and re-counts already-applied keep changes in hybrid Phase 10 (suspected double count; not run) → **COR-10**, a correction candidate, not fixed here.
- `WEALTH_WRITERS` (wealth_accounting_state.py:121) and its test (`tests/test_wealth_accounting.py:~755`, `scan_wealth_writers`) cover only native agent-wealth payer calls (`transfer_wealth`, `remit_wealth`, `pay_from_firm`, `settle_pairs`). They never see `civ.treasury`. A treasury helper that calls none of those names does not touch that registry. `money._move_treasury` (money.py:499-506) is the same dual path.
- `_treasury_tax_carry` is a private world attribute (simulation.py:1810-1823). It round-trips in run checkpoints (tests/test_run_checkpoint.py:141-146) and `checkpoint_replay.py:173` rejects a non-empty one. Scout 04 finding 7 is answered: leave it.
- `agent_bridge.py:1290` sets `rust_owns_formation = True`; nothing else assigns it. The only reader is `simulation.py:2576`. Rust runs the formation scan every agent-mode tick (`chronicler-agents/src/tick.rs:1454-1470`) and dissolutions reach `world.dissolved_edges_by_turn` through `agent_bridge.py:1735-1741`. Verdict: the fallback is dead in production. **But** `tests/test_turn_artifact_lifecycle.py:123` and `tests/test_regional_population.py:188` use `False` as a probe: the fallback is the only caller of the post-politics `get_snapshot()` (asserted at lifecycle `:~215` as the `post_politics` stage, and at regional_population `:~207` as `calls == ["snapshot","snapshot"]`). The audit missed that; those tests must be rewritten, not just un-set.

## 3. Design
### CON-3 treasury seam
New `src/chronicler/treasury.py` (unpinned):
```python
def treasury_delta(world, acc, civ, delta, *, reason, civ_idx=None, floor0=False) -> None:
    if acc is not None:                       # never skip delta == 0: the change list is index-addressed
        acc.add(civ_idx if civ_idx is not None else civ_index(world, civ.name), civ, "treasury", delta, "keep")
    elif floor0: civ.treasury = max(0, civ.treasury + delta)
    else:        civ.treasury += delta
```
- The index is computed lazily, exactly where each site computes it now. The `acc` path is unchanged, so `StatChange.stat_at_time` and list indices are identical.
- `reason` is a required literal from `TREASURY_REASONS` (table: fiat source / spend sink / transfer, with the 48 sites classified). It has no runtime effect today. It exists so an AST test can inventory every flow and DEP-6 can attach a flow record without another sweep. Fiat labels follow scout 04 finding 1.
- Stat-neutral callers keep their guards (`money._move_treasury` keeps `if not units: return`).
- `StatAccumulator` gains `queued_changes(civ_idx, stat, category="keep", *, unapplied_only=True)` (generator) and `_apply_change` (shared by `apply`/`apply_keep`, scout 01 finding 10). The five folds keep their own floor/cast rules and only swap the private read. No semantic harmonisation.
- A guard test fails on any new `civ.treasury ±=` outside an allowlist (restores, scenario, politics_bridge restore, `treasury.py`).
- Order: helper with zero call-site changes → unpinned call sites → pinned call sites.

### CON-4 hook table
New `src/chronicler/turn_hooks.py`:
```python
@dataclass(frozen=True)
class TurnHook: slot: str; order: int; key: str; gate: str; target: str  # "module:attr", imported at call
HOOKS: tuple[TurnHook, ...]   # one literal, written in execution order
def run_hooks(slot, ctx) -> None
```
- `GATES: dict[str, Callable]` holds the existing predicates. `ctx` (`TurnContext`) carries `world, acc, phase10_acc, artifacts, agent_bridge, economy_result, emit, recent_events()`; `recent_events()` recomputes the slice per call.
- Slots (in order): `p1.environment`, `p1.off_observers`, `p2.dues`, `p3b.finance`, `p5.after_action`, `p5.war_sync`, `p9.before_ecology`, `p9.after_ecology`, `p10.after_politics`, `p10.pre_flush`, `post.close`. `order` is an explicit integer, asserted strictly increasing within a slot; nothing is sorted by name. This resolves scout 01 finding 13 (phase table in one place).
- Targets are strings resolved with `importlib` at each call, so `monkeypatch.setattr(runtime, "tick_campaigns", …)` (tests/test_war_integration.py:120, test_nomads.py:890, test_ritual_gatherings_native.py:141) keeps working and import cost stays lazy.
- Adapters in `turn_hooks.py` keep the irregular blocks verbatim: scholarship with learning services (2505-2521), campaigns' `end_of_turn_sync`, finance's `update_money`.
- Stays inline: the core `phase_*` calls (tests patch them on the `sim` namespace, `tests/test_turn_artifact_lifecycle.py:54-66`), the economy transaction (8 livelihoods/health/storage calls inside the rollback block), `with_economy_columns`, `filter_boundary_batch`, the `tick_agents` wrappers, the techniques/phase_technology branch, the tech-regression branch, and the off-mode transient clears (FIX-3 owns those, `:2379-2387`).
- New systems register one `TurnHook` row plus a gate entry. No RNG moves: the dispatcher draws nothing.

### CON-11 formation fallback (decision DEC-7, delete)
Remove `simulation.py:2576-2602` (the whole `if not rust_owns_formation` branch), the `rust_owns_formation` attribute, and from `relationships.py` `compute_belief_data`, `dissolve_edges`, `check_*_formation`, `CORELIGIONIST_MINORITY_THRESHOLD`, `form_and_sync_relationships`, `_sync_relationship_edges`, `_edge_op_type`, the `REL_OP_*` constants and `_LEGACY_REL_SENTIMENT`. Keep `REL_RIVAL`/`REL_MARRIAGE` (used at simulation.py:2611, 2628) and the hostage code (`capture_hostage`, `tick_hostages`, `release_hostage` and their `_*hostage*` helpers). The explicit test-flag option is rejected: it keeps ~350 lines and a branch that only tests execute. Git history is the archive. This also removes the unlogged `get_snapshot()` failure swallow (scout 01 finding 2) with it.

## 4. Compatibility
Saved bundles and checkpoints are unchanged: no field is added or removed (`dissolved_edges_by_turn` stays, written by `agent_bridge.py:1735`). No CLI flag changes. Old bundles import unchanged. A bridge object that still sets `rust_owns_formation` is harmless (attribute ignored).

## 5. Pins and preflight (run 2026-11-08)
| File | Level |
|---|---|
| `simulation.py` | ENFORCED, 11 chained witness fixtures; needs PIN-1 |
| `agent_bridge.py` | ENFORCED, 7 fixtures; needs PIN-1 (one line) |
| `grain_reserves.py` 9, `grain_storage.py` 2, `finance.py` 2 | ENFORCED; needs PIN-1 (one site each) |
| `economy.py` | ENFORCED (7) but **not touched** by these tasks |
| `money.py`, `accumulator.py`, `relationships.py`, `politics.py`, `action_engine.py`, `culture.py`, `factions.py`, `war/common.py`, `wealth_accounting.py` | unpinned (historical provenance hashes only) |
| `tests/test_turn_artifact_lifecycle.py`, `test_regional_population.py`, `test_relationships.py`, `test_m50a_relationships.py`, `test_audit_batch_e.py` | shard-manifest owners: edit bodies, keep node IDs of kept tests, update the manifest only for deleted nodes (reviewed) |

If PIN-1 slips, the fallback is a reviewed exact-inverse layer per pinned file (`scripts/testing/reviewed_main_witness.py`); that is 11 chained fixtures for `simulation.py` and is not recommended.

## 6. Classification
All three: **behaviour-preserving refactor**. Proof per change:
1. Golden `StatAccumulator.add` log (civ, stat, delta, category, stat_at_time, in order) plus final civ stats for 12 off-mode turns on 3 seeds, recorded on unmodified `main` (PR 1) and compared unchanged in every later PR.
2. Golden hook-call sequence per feature combination (§7), recorded before the registry.
3. `scripts/turn_speed_identity.py run … && compare`. Its `CASES` (turn_speed_identity.py:42-63) are 9 runs: off s42/s7, proc48 off s7 (3 off); hybrid s42/s7/s1234, proc48 hybrid s42, scaled22k, scaled52k (6 hybrid). They run the **default** feature resolution only. For default-off hooks run the matrix again with `--cli-arg`, one switch per run set (`--cities`, `--guilds`, `--scholarship`, `--grain-reserves`, `--nomads`, `--maritime`, `--diplomacy`, `--gp-agendas`, `--agent-movements`, `--finance`, `--contact-ledger`, `--epidemiology`, `--campaigns`; livelihoods and ritual gatherings have no argparse switch in `main.py`, so they are covered only by the call-sequence test: add an explicit `CASES` entry if the owner wants byte identity for them). Base tree is run with `--source-root`. Default-on features are listed by `main._configure_run` (CON-1; unverified here).
4. Oracle lane `scripts/run_python_oracle_checks.py`.

COR-10 (gp_agendas watermark) is a correction and needs its own baseline and CONTINUATION entry. It is excluded from every PR below.

## 7. Tests
- New `tests/test_treasury_seam.py`: helper equivalence table (acc/None × floor0 × zero delta × lazy index); AST inventory of `reason`; no-new-direct-write guard; `queued_changes` vs each of the five folds on randomized change lists.
- New `tests/test_turn_hooks.py`: table well-formed (unique keys, increasing order, targets importable); recorded sequence for ≥6 combinations (none; all-agent-off hooks; cities+guilds+scholarship; livelihoods+grain-reserves+ritual; finance+maritime+nomads+campaigns; hybrid fake-bridge all) via a harness `tests/support/turn_order_trace.py` that patches both `sim._X_on` (old) and `turn_hooks.GATES[...]` (new) and stubs each target to record `(slot, key)`. Golden JSON recorded in PR 1.
- Changed: lifecycle and regional_population (drop the `post_politics` probe and `rust_owns_formation`; assert snapshot count 2 and no extra fetch); delete the formation/dissolve cases in `test_relationships.py` (keep hostage and `test_war_result_*`), `test_m50a_relationships.py:251-295`, `test_audit_batch_e.py:326-366`; add a test that `AgentBridge` has no `rust_owns_formation`.

## 8. Risks, open questions, rollback
- Risk: a site's direct branch differs from `+=` (a `max(0, …)`, an `int()`); mitigated by `floor0` and by the golden log. Sites that cast (`politics_bridge.py:1352`) stay out.
- Risk: `emit` ordering through the registry; mitigated by the call-sequence golden and by keeping `_emit`.
- FIX-3 edits `:2379-2387` and FIX-7 edits livelihoods hooks; merge FIX-3 first or leave the block inline. COR-3 may rewrite `tech.py:115`; migrate it last or let COR-3 land first.
- Open: should `reason` be enforced at runtime? (Recommend no until DEP-6.)
- Rollback: each PR reverts cleanly; no data migrations.

## 9. Size
CON-3: +90 lines (helper, reader, tests) and about −150 net at call sites. CON-4: about −190 in `simulation.py`, +230 `turn_hooks.py`, +200 tests. CON-11: −27 simulation, −1 bridge, −345 `relationships.py`, about −600 in tests. Five PRs.
