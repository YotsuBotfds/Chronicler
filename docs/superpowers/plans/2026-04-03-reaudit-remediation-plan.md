# 2026-04-03 — Re-Audit Remediation Plan

> All findings verified against current source (commit `e5ada7e`).
> Items marked DEFER are design-level changes that need spec/plan work, not mechanical fixes.

---

## Verification Summary

| Severity | Found | Verified | Clean agents |
|----------|-------|----------|-------------|
| High     | 13    | 13       | action_engine, rust-signals, rust-tick |
| Medium   | 10    | 10       | |
| Low/Dead | 32    | 32       | |
| Test     | 7     | 7        | |
| **Total**| **62**| **62**   | **3 clean** |

---

## Workstream 1: Correctness Bugs (Mechanical Fixes)

### Task 1.1 — Stalemate treated as war loss in factions
**File:** `factions.py:308-328`
**Bug:** War events with "stalemate" in description fall into the else (loss) branch. Both combatants get loss penalties.
**Fix:** Add stalemate check before the else:
```python
                if (is_attacker and "attacker_wins" in event.description) or \
                   (not is_attacker and "defender_wins" in event.description):
                    # War win ...
                elif "stalemate" in event.description:
                    pass  # No faction shift for stalemates
                else:
                    # War loss ...
```

### Task 1.2 — `_total_great_persons` counts inactive/dead GPs
**File:** `great_persons.py:103-104`
**Bug:** `sum(len(c.great_persons) for c in world.civilizations)` includes GPs with `active=False`.
**Fix:** Filter by active: `sum(1 for c in world.civilizations for gp in c.great_persons if gp.active)`

### Task 1.3 — GP ascended_to_leadership never moved to retired_persons
**File:** `factions.py:659-662`
**Bug:** When GP ascends, `active=False, alive=False` set but GP stays in `civ.great_persons`.
**Fix:** After setting flags, remove from civ list and append to retired:
```python
if gp in civ.great_persons:
    civ.great_persons.remove(gp)
world.retired_persons.append(gp)
```

### Task 1.4 — Long peace richest/poorest can be same civ
**File:** `politics.py:1499-1511`
**Bug:** When all economies equal, `max()` and `min()` return same civ. Net penalty applied.
**Fix:** Add guard: `if richest is poorest: continue` (or skip the block).

### Task 1.5 — Resource discovery doesn't init effective yields
**File:** `emergence.py:518-523`
**Bug:** `resource_base_yields[slot]` set but `resource_effective_yields[slot]` stays 0.0.
**Fix:** After line 522, add: `region.resource_effective_yields[slot] = region.resource_base_yields[slot]`

### Task 1.6 — Famine drain return value ignored
**File:** `ecology.py:133-134`
**Bug:** `drain_region_pop` returns actual drain (may be < requested if low pop). `per_neighbor` on line 154 uses full `famine_pop`, creating population.
**Fix:** `actual_drain = drain_region_pop(region, famine_pop)` then use `actual_drain` for `per_neighbor` calculation.

### Task 1.7 — Rust dissolution events overwritten by Python-side
**File:** `simulation.py:1822`
**Bug:** `world.dissolved_edges_by_turn[world.turn] = dissolved` overwrites any Rust-side entries from line 1106-1108.
**Fix:** Extend instead of replace:
```python
existing = world.dissolved_edges_by_turn.get(world.turn, [])
existing.extend(dissolved)
world.dissolved_edges_by_turn[world.turn] = existing
```

### Task 1.8 — Viewer chronicle_entries dropped for legacy format
**File:** `viewer/src/hooks/useLiveConnection.ts:216`
**Bug:** Init defaults `chronicle_entries` to `{}` (object). `narration_complete` handler checks `Array.isArray()` — fails for `{}`.
**Fix:** Change line 216: `chronicle_entries: msg.chronicle_entries || [],`

### Task 1.9 — Unsafe dict indexing in decompose_trade_routes
**File:** `economy.py:627`
**Bug:** `region_map[region_name]` — KeyError if stale region name.
**Fix:** `region = region_map.get(region_name)` + `if region is None: continue`

### Task 1.10 — Federation trade routes bypass embargo
**File:** `resources.py:218-224`
**Bug:** Federation members get trade routes without checking `embargo_set`.
**Fix:** Add embargo check:
```python
if pair not in routes and pair not in embargo_set:
    routes.add(pair)
```
(The `embargo_set` is already computed at line 155.)

### Task 1.11 — Proxy wars stale treasury in hybrid mode
**File:** `politics.py:789-805`
**Bug:** In acc path, `sponsor.treasury` isn't mutated, so bankruptcy check sees original balance for all proxy wars.
**Fix:** Track cumulative deductions:
```python
# Before the loop:
treasury_deducted = defaultdict(int)
# Inside loop, acc path:
treasury_deducted[sponsor.name] += pw.treasury_per_turn
prospective = sponsor.treasury - treasury_deducted[sponsor.name]
```

### Task 1.12 — Vassalization missing trade route cache invalidation
**File:** `politics.py:453-458`
**Fix:** Add `world.invalidate_trade_route_cache()` after the war removal block (after line 458).

---

## Workstream 2: Dead Code Cleanup

Single batch commit. All verified as unused.

- `factions.py:277` — Remove dead `snapshot` param from `compute_tithe_base`
- `factions.py:282` — Remove dead `getattr(civ, 'trade_income', 0)` fallback
- `great_persons.py:336` — Remove dead `belief_registry` param from `check_pilgrimages`
- `narrative.py:1196` — Remove dead `agent_ctx` variable
- `narrative.py:1183` — Remove dead `gp_by_name` param from `_narrate_sequential`
- `narrative.py:42` — Remove dead `_update_arc_summary` function (or keep for M45)
- `narrative.py:1078` — Remove redundant `_closest_snap` call
- `llm.py:241` — Remove redundant `import time` inside `GeminiClient.complete`
- `infrastructure.py:17-18` — Remove dead `K_MAX_TEMPLES_PER_REGION`, `K_TEMPLE_CONVERSION_BOOST` imports
- `emergence.py:958-982` — Remove dead `clear_expired_capacity_modifier` function
- `resources.py:6` — Remove unused `Disposition` import
- `resources.py:308-319` — Remove dead `SEASON_MOD` table
- `resources.py:335-347` — Remove dead `resource_class_index()` function
- `ecology.py:18` — Remove unused `K_FAMINE_REFUGEE_POP` import
- `simulation.py:61` — Remove unused `sync_all_populations` import
- `simulation.py:1410` — Remove unreachable comment after return

---

## Workstream 3: Minor Fixes

### Task 3.1 — Ecology raw string instead of tuning constant
**File:** `ecology.py:136`
**Fix:** Replace `"stability.drain.famine_immediate"` with `K_FAMINE_STABILITY` (import if needed).

### Task 3.2 — Stale phase docstring in simulation.py
**File:** `simulation.py:3-14`
**Fix:** Update phase numbering to match actual execution order per CLAUDE.md.

### Task 3.3 — Fortification spurious event on completion turn
**File:** `infrastructure.py:134-142`
**Fix:** Guard event emission: `if infra.turns_remaining > 0:` before emitting capability_fortification.

### Task 3.4 — Inconsistent event routing in tick_infrastructure
**File:** `infrastructure.py:138`
**Fix:** Append to local `events` list instead of directly to `world.events_timeline`.

### Task 3.5 — Redundant length check in climate migration
**File:** `climate.py:229`
**Fix:** Remove `if len(eligible) > 0` guard (already inside `if eligible:`).

### Task 3.6 — Missing hills terrain cost
**File:** `economy.py:45-52`
**Fix:** Add `"hills": 1.3` to `TERRAIN_COST` dict.

---

## DEFERRED (design-level, need spec)

These are real issues but require design decisions, not mechanical fixes:

- **Narrative agent-context disconnected** — `narrate_batch` accepts social_edges/gini/displacement/economy_result but no caller passes them. This is M45+ wiring work.
- **Dynasty context never reaches narration** — `dynasty_registry` never passed to `build_agent_context_for_moment`. Same scope as above.
- **GP deeds show current region not deed region** — Needs deed model to store region per deed.
- **Hostage capture/release never syncs Rust agent civ** — Needs bridge parameter threading from war resolver. Design question about when/how to sync.
- **Dissolution event tuple schema mismatch** — Needs Rust AgentEvent to carry target_id. Blocked by Rust struct change.
- **Dead nested test in test_ecology.py** — `test_mining_collapse_and_recovery` accidentally nested. Needs manual review of intended scope.

---

## Execution Order

1. **Workstream 1** (12 correctness fixes) — dispatch as parallel agents by file
2. **Workstream 2** (dead code) — single batch agent
3. **Workstream 3** (6 minor fixes) — single batch agent
4. Full test suite verification
5. Commit and push
