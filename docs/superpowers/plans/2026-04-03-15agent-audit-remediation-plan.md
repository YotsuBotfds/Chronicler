# 2026-04-03 — 15-Agent Audit Remediation Plan

> All findings below are **verified against current source** (commit `011fd8e`).
> Rejected/retracted findings from the raw audit are not included.

---

## Verification Summary

| Severity | Found | Verified | Rejected |
|----------|-------|----------|----------|
| High     | 15    | 15       | 0        |
| Medium   | 16    | 16       | 0        |
| Low      | 20    | 20       | 0        |
| Test     | 8     | 8        | 0        |
| **Total**| **59**| **59**   | **0**    |

---

## Workstream 1: Severity Multiplier Consistency

**Goal:** All negative stat changes go through M18 severity multiplier (except treasury, ecology).

### Task 1.1 — War military losses missing severity (H1)
**File:** `action_engine.py:614-729`
**Fix:** Apply `mult` to `winner_mil_loss` and `loser_mil_loss` in:
- Vassalization attacker_wins (lines 616-617, 620-621)
- Absorption attacker_wins (lines 702-704, 707-708)
- Defender_wins (lines 717-718, 721-722)

Pattern: `acc.add(att_idx, attacker, "military", -int(winner_mil_loss * mult), "guard-action")`
Same for else branches: `attacker.military = clamp(attacker.military - int(winner_mil_loss * mult), ...)`

**Note:** Stalemate path (726-729) already correct — use as reference.

### Task 1.2 — Twilight population drain missing severity (H5)
**File:** `politics.py:1296-1299`
**Fix:** Multiply `twilight_pop` by `mult` (already computed on line 1301 — move it before the pop drain block):
```python
mult = get_severity_multiplier(civ, world)
twilight_pop_scaled = int(twilight_pop * mult)
```
Apply to both acc path and else path.

### Task 1.3 — Injected plague missing severity on population (H12)
**File:** `simulation.py:930-935`
**Fix:** Replace `-10` with `-int(10 * mult)` on line 930 (acc path) and `drain_region_pop(target_r, int(10 * mult))` on line 935 (else path). `mult` is already computed on line 927.

---

## Workstream 2: Population Conservation & Mode Parity

### Task 2.1 — Famine refugee population conservation (H6)
**File:** `ecology.py:133-151`
**Bug:** Drains 5 from famine region, adds 5 to EACH adjacent foreign neighbor (N×5 created from 5).
**Fix:** Distribute `famine_pop` across eligible neighbors proportionally:
```python
eligible = [list of (adj, neighbor) pairs]
if eligible:
    per_neighbor = max(1, famine_pop // len(eligible))
    for adj, neighbor in eligible:
        add_region_pop(adj, per_neighbor)
```

### Task 2.2 — Twilight population/region desync in acc path (H4)
**File:** `politics.py:1294-1300`
**Bug:** acc path subtracts from `civ.population` but not from any region.
**Fix:** Both paths should drain from the highest-population region:
```python
target_r = max(civ_regions, key=lambda r: r.population)
drain_region_pop(target_r, twilight_pop_scaled)
sync_civ_population(civ, world)
if acc is not None:
    # population already drained directly; no acc.add for population
    pass
```
(Same pattern as the C-3 famine fix — direct mutation for population, acc only for non-population stats.)

### Task 2.3 — Pandemic/supervolcano population silently dropped in hybrid (H7)
**Files:** `emergence.py:334, 453`
**Bug:** Population loss routed as `"guard"` — skipped in agent mode. Agents don't model pandemic/volcano deaths.
**Fix:** Same pattern as C-3 famine fix — direct mutation for catastrophic population loss:
```python
# Replace acc.add(..., "guard") with direct drain
distribute_pop_loss(affected_regions, pop_loss)
sync_civ_population(civ, world)
```
Keep stability/economy as `"signal"`.

### Task 2.4 — Injected plague uses single-region drain (H13)
**File:** `simulation.py:932-936`
**Fix:** Replace single-region `drain_region_pop` with `distribute_pop_loss(civ_regions, int(10 * mult))` + `sync_civ_population(civ, world)`, matching the natural plague path.

### Task 2.5 — Dead civ stats not zeroed in hybrid write-back (M4)
**File:** `agent_bridge.py:2251-2253`
**Fix:** After `civ.population = 0`, also zero `civ.military`, `civ.economy`, `civ.culture`, `civ.stability`.

---

## Workstream 3: Accumulator Routing Gaps

### Task 3.1 — `tick_hostages` not wired to accumulator (H9)
**Files:** `relationships.py:476, 512-513` + `simulation.py:482`
**Fix:**
1. Add `acc=None` param to `tick_hostages` and `release_hostage` signatures
2. Route `origin.treasury -= 10` through `acc.add(origin_idx, origin, "treasury", -10, "keep")`
3. Update call site in `simulation.py:482` to pass `acc=acc`

### Task 3.2 — Missing `_require_acc_for_hybrid` guard in `check_federation_dissolution` (M15)
**File:** `politics.py:677`
**Fix:** Add `_require_acc_for_hybrid(acc, world)` at function entry, matching `check_secession` pattern.

### Task 3.3 — Absorption defender stability uses wrong routing (M16)
**File:** `action_engine.py:705`
**Fix:** Change `"signal"` to `"guard-shock"` to match the vassalization path (line 618). Same for defender_wins line 719.

---

## Workstream 4: Logic Bugs

### Task 4.1 — Non-militant faiths get conquest conversion boost (H2)
**File:** `action_engine.py:700`
**Fix:** Indent `contested.conquest_conversion_boost = 1.0` inside the `if is_militant:` block.

### Task 4.2 — Congress `war_start_turns` cleanup too broad (H3)
**File:** `politics.py:935`
**Fix:** Change `or` to `and`:
```python
if parts[0] in participants and parts[1] in participants:
```
(Match the `active_wars` filter on line 931.)

### Task 4.3 — Persecution counted as clergy win for victims (H10)
**File:** `factions.py:168-169`
**Fix:** Check event actors to distinguish persecutor from victim. Persecution events should have the persecutor as actors[0]:
```python
if event_type_lower == "persecution":
    # Only count as win if this civ is the persecutor (actors[0]), not victim
    return len(event.actors) >= 1 and civ.name == event.actors[0]
```
Verify event actor ordering in the persecution generation code first.

### Task 4.4 — `tech_advanced` counter reset regardless of cooldown (H11)
**File:** `simulation.py:1257` + `great_persons.py:207-217`
**Fix:** Only reset `tech_advanced` when a scientist actually spawns. Move reset inside the `if tech_trigger or economy_trigger:` block in `check_great_person_generation`, after successful spawn:
```python
if tech_trigger or economy_trigger:
    _enforce_cap(civ, world)
    gp = _create_great_person("scientist", civ, world)
    _set_cooldown(civ.name, "scientist", world)
    civ.event_counts[_TECH_ADVANCE_KEY] = 0  # reset HERE
    spawned.append(gp)
```
Remove the unconditional reset at `simulation.py:1257`.

### Task 4.5 — `DOMAIN_PERSONALITY_MAP` keys don't match domain strings (H8)
**File:** `agent_bridge.py:71-75`
**Fix:** Update keys to match actual domain strings from `world_gen.py`:
```python
DOMAIN_PERSONALITY_MAP = {
    "warfare":    (0.10, 0.0,  0.0),
    "commerce":   (0.0,  0.10, 0.0),
    "maritime":   (0.0,  0.10, 0.0),
    "scholarship":(0.0,  0.0,  0.10),
    "faith":      (0.0,  0.0,  0.10),
}
```
Grep `world_gen.py` for actual domain strings and map appropriately.

### Task 4.6 — Dynasty member KeyError crash (H14)
**File:** `narrative.py:352`
**Fix:** Use `.get()`:
```python
living_count = sum(1 for m in dynasty.members if m in gp_by_agent_id and gp_by_agent_id[m].alive)
```

### Task 4.7 — None-relationship blocks merchant edges (H15)
**File:** `economy.py:1015-1016`
**Fix:** Change `continue` to assign neutral disposition when relationship is None:
```python
disp_ab = _DISP_NUMERIC.get(rel_ab.disposition.value, 0) if rel_ab else 2  # neutral
disp_ba = _DISP_NUMERIC.get(rel_ba.disposition.value, 0) if rel_ba else 2
if disp_ab < 2 or disp_ba < 2:
    continue
```

---

## Workstream 5: Crash Prevention

### Task 5.1 — `LocalClient.complete` None content crash (M1)
**File:** `llm.py:115`
**Fix:** `return (response.choices[0].message.content or "").strip()`

### Task 5.2 — `GeminiClient.complete` None text crash (M2)
**File:** `llm.py:268`
**Fix:** `return (response.text or "").strip()`

### Task 5.3 — `shock_category` None in ShockContext (M3)
**File:** `narrative.py:539-548`
**Fix:** Add `and ev.shock_category is not None` to the filter condition.

---

## Workstream 6: Analytics & Reporting Fixes

### Task 6.1 — Politics firing rate key mismatch (M8)
**File:** `analytics.py:1427`
**Fix:** Update the key list to match `extract_politics` output:
```python
for key in ["war_rate", "secession_rate", "federation_formed_rate",
            "vassal_imposed_rate", "mercenary_spawned_rate", "twilight_absorption_rate"]:
```

### Task 6.2 — `extract_stockpiles` reads wrong path (M9)
**File:** `analytics.py:309`
**Fix:** `_snapshot_at_turn` returns TurnSnapshot dicts which have `civ_stats` but not `world_state.regions`. Since stockpile data isn't captured in TurnSnapshots, either:
- Mark function as dead code with `# TODO: wire stockpile data into TurnSnapshot`, or
- Remove the function if no caller exists.

### Task 6.3 — `extract_legacy_chain_metrics` reads wrong location (M10)
**File:** `analytics.py:1998`
**Fix:** Same — bundle `metadata` doesn't have `great_persons`. Either fix the path to read from `world_state.civilizations[*].great_persons` or remove as dead code.

### Task 6.4 — `[local inference]` print for all modes (L3)
**File:** `main.py:313`
**Fix:** Conditionally show inference mode:
```python
mode_label = {"local": "local inference", "api": "Claude API", "gemini": "Gemini API"}.get(args.narrator, "local inference")
print(f"  Sim model: {sim_model} | Narrative model: {narr_model} [{mode_label}]")
```

---

## Workstream 7: Viewer Fixes

### Task 7.1 — In-place array mutation in useLiveConnection (M11)
**File:** `viewer/src/hooks/useLiveConnection.ts:232-240, 296-298`
**Fix:** Create new arrays before publishing:
```typescript
liveBundle.history = [...liveBundle.history, buildLiveTurnSnapshot(msg)];
liveBundle.events_timeline = [...liveBundle.events_timeline, ...((msg.events) || [])];
```
Same pattern for `chronicle_entries` and `named_events`.

### Task 7.2 — WebSocket reconnect timer leak (M12)
**File:** `viewer/src/hooks/useLiveConnection.ts:161-169`
**Fix:** Clear existing reconnect timer before scheduling new one:
```typescript
ws.onclose = () => {
  if (unmounted) return;
  setConnected(false);
  wsRef.current = null;
  if (reconnectRef.current) clearTimeout(reconnectRef.current);
  // ... schedule new timer
};
```

---

## Workstream 8: Data Quality & Bridge

### Task 8.1 — Dissolution events missing target agent (M5)
**File:** `agent_bridge.py:1106`
**Fix:** The Rust `AgentEvent` struct needs a `target_id` field for dissolution events. Until that's added, document the limitation. If Rust changes are in scope, add `target_id: u32` to dissolution events.

### Task 8.2 — River discount inconsistency (M6)
**File:** `economy.py:924-932`
**Fix:** Replace `_regions_share_river` with a lookup against `build_river_route_set`:
```python
river_routes = build_river_route_set(world.regions)
# In build_merchant_route_graph:
if frozenset({r1.name, r2.name}) in river_routes:
    edge_cost *= RIVER_DISCOUNT
```

### Task 8.3 — Type annotation: `extract_conservation_diagnostics` returns bool (L7)
**File:** `analytics.py:2129`
**Fix:** Change to `float(c.get("clamp_floor_loss", 0.0) > 0)` or update annotation to `dict[str, float | bool]`.

---

## Workstream 9: Dead Code Cleanup

All low-priority. Can be batched into a single commit.

- `ecology.py:355-356` — Remove unused `season_id` computation
- `ecology.py:213` — Remove unused `_TERRAIN_FROM_U8`
- `narrative.py:918` — Remove unused `gap_summaries` parameter
- `narrative.py:25,28` — Remove unused `Disposition`, `NarrationContext` imports
- `models.py:938-948` — Remove unused `NarrationContext` model (grep first to confirm no callers)
- `politics.py:1138` — Remove dead assignment before `check_restoration`
- `infrastructure.py:129,185,225,331,345` — Remove redundant local `Event` imports
- `economy.py:1558` — Remove dead `min()` clamp in tithe scale
- `emergence.py:696` — Remove dangling indented comment

---

## Workstream 10: Test Suite Hardening

### Task 10.1 — Fix tautological/weak tests
- `test_climate.py:310-331` — Rewrite mountain defense tests to call `resolve_war` from `action_engine.py`
- `test_action_engine.py:305-310` — Assert `result.outcome == "attacker_wins"` (not `in (all three)`)
- `test_relationships.py:614-655` — Add actual simulation turn or function call before asserting no events
- `test_factions.py:58-84` — Explicitly set CLERGY influence; add CLERGY-specific normalization assertion

### Task 10.2 — Fix over-mocking
- `test_economy.py:350-390` — Replace MagicMock world with real or stub objects that raise on unexpected attribute access

### Task 10.3 — Fix silent-skip tests
- `test_m57b_household.py:24-58` — Add `pytest.importorskip("chronicler_agents")` so test is properly marked as skipped rather than vacuously passing

---

## Execution Order

1. **Workstream 1** (severity multiplier) — 3 tasks, mechanical
2. **Workstream 2** (population conservation) — 5 tasks, requires care
3. **Workstream 3** (accumulator routing) — 3 tasks, mechanical
4. **Workstream 4** (logic bugs) — 7 tasks, most impactful
5. **Workstream 5** (crash prevention) — 3 tasks, one-liners
6. **Workstream 6** (analytics) — 4 tasks, isolated
7. **Workstream 7** (viewer) — 2 tasks, isolated
8. **Workstream 8** (bridge/data) — 3 tasks, mixed complexity
9. **Workstream 9** (dead code) — single batch commit
10. **Workstream 10** (tests) — 3 tasks, after source fixes

**Estimated total: ~45 discrete edits across ~25 files.**
