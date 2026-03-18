# M45: Character Arc Tracking — Design Spec

> **Status:** Reviewed (Phoebe 2-pass, all blocking/near-blocking resolved)
> **Author:** Cici (Opus 4.6)
> **Date:** 2026-03-18
> **Prerequisites:** M39 (Family & Lineage), M40 (Social Networks), M37-M38b (Religion). M44 (API Narration) recommended but not required.

---

## Goal

Make the narrator aware of character arcs across the entire chronicle, enabling callbacks, thematic threading, and arc classification. Two independent systems:

1. **Arc classifier** (simulation-side, Phase 10): pattern-matches structured event data to assign trajectory states and archetype labels to named characters. Works in `--simulate-only` mode.
2. **Arc summaries** (narration-side, `narrate_batch()`): LLM-generated one-sentence narrative summaries that build up across moments, giving the narrator self-referential threading. API mode only (`--narrator api`).

A third deliverable — **deeds population** — fixes a long-standing gap where `gp.deeds` was defined but never populated, giving the narrator and classifier structured character history.

---

## Data Model Changes

### GreatPerson Fields (models.py)

```python
# Existing (M38b) — usage extended, M38b explicit set removed:
arc_type: str | None = None       # Complete archetype label

# New:
arc_phase: str | None = None      # Current trajectory state
arc_summary: str | None = None    # LLM-generated narrative summary (max 3 sentences)
arc_type_turn: int | None = None  # Turn when arc_type was (re)classified
```

**Field semantics:**

| Field | Mutability | Source | Available in --simulate-only |
|-------|-----------|--------|------------------------------|
| `arc_phase` | Re-derived from scratch every turn | Classifier (Phase 10) | Yes |
| `arc_type` | Persists, may be reclassified when a more complete archetype emerges | Classifier (Phase 10) | Yes |
| `arc_type_turn` | Updated on each (re)classification | Call site (Phase 10) | Yes |
| `arc_summary` | Appended after each narrated moment, truncated to 3 sentences | Follow-up LLM call in `narrate_batch()` | No — stays None |

All fields have `None` defaults. Existing Pydantic serialization carries them into `chronicle_bundle.json` via `world_state → civilizations → great_persons` and `retired_persons`. No bundle format changes.

### M38b Migration

`check_pilgrimages()` (great_persons.py:368) currently sets `gp.arc_type = "Prophet"` explicitly on pilgrimage return. M45 removes this — the classifier becomes the single authority for `arc_type`. Prophet detection is included in the classifier's pattern matching. The M38b check `if gp.arc_type == "Prophet"` (great_persons.py:387) that prevents repeat pilgrimages changes to check the classifier-set value, which produces the same result.

---

## Arc Classifier

### Module

New file: `src/chronicler/arcs.py`

### Core Function

```python
def classify_arc(
    gp: GreatPerson,
    events: list[Event],
    dynasty_registry: DynastyRegistry | None,
    current_turn: int,
) -> tuple[str | None, str | None]:
    """Classify a character's arc from their event history.

    Pure function — stateless re-derivation each turn.

    Args:
        gp: The character to classify.
        events: Full events_timeline (filtered internally by gp.name in e.actors).
        dynasty_registry: For Dynasty Founder detection. Sourced from
            AgentBridge.dynasty_registry; None in --agents=off mode.
        current_turn: Current simulation turn (for career-length calculations).

    Returns:
        (arc_phase, arc_type) — either or both may be None.
    """
```

### Event Filtering

The classifier filters `events` to character-specific events using `gp.name in e.actors`. This works because character lifecycle events include the character name in actors:

- `character_death`: `actors=[name, civ.name]`
- `exile_return`: `actors=[name]`
- `notable_migration`: `actors=[name]`
- `conquest_exile`: `actors=[gp.name, conquered_civ.name, conqueror_civ.name]`
- `secession_defection`: `actors=[gp.name, ...]`

Civ-level simulation events (war, trade, rebellion) use civ names only — the classifier does not match on these. All 8 archetypes are defined using character-level events and GreatPerson fields only. If a future archetype needs civ-level correlation, it would require a secondary `civ.name in e.actors` filter path — not M45 scope.

### Archetype Definitions

8 archetypes. Each has a partial match (→ `arc_phase` only) and a complete match (→ `arc_type`).

#### Rise-and-Fall

| | Condition |
|-|-----------|
| **Partial** | Active character + established career (`(current_turn - gp.born_turn) >= RISING_CAREER_THRESHOLD`) → phase `"rising"` |
| **Complete** | + `character_death` or `conquest_exile` event → type `"Rise-and-Fall"`, phase `"fallen"` |

`RISING_CAREER_THRESHOLD`: initial guess 20 turns. `[CALIBRATE]` for M47. Ensures only established characters (not just-promoted) are in a "rise" phase. Note: `born_turn` is the promotion turn, not biological birth (see CLAUDE.md). Calibration note: typical character lifespans are 20-30 turns (`_compute_lifespan` in great_persons.py), so a threshold of 20 means nearly all surviving characters match. M47 should check whether threshold should be 25-30, or whether a second partial condition is needed.

#### Exile-and-Return

| | Condition |
|-|-----------|
| **Partial** | `conquest_exile` event exists → phase `"exiled"` |
| **Complete** | + `exile_return` event after the exile → type `"Exile-and-Return"` |

#### Dynasty Founder

| | Condition |
|-|-----------|
| **Partial** | Dynasty exists in registry with `gp.agent_id` as founder → phase `"founding"` |
| **Complete** | + dynasty has 2+ members (2nd generation promoted) → type `"Dynasty-Founder"` |

Note: these conditions are degenerate in the current implementation. `DynastyRegistry` creates dynasties only when a 2nd-generation child is promoted (`dynasties.py:47`), so the dynasty starts with 2 members. Partial and complete always fire simultaneously — no character will have `arc_phase="founding"` without also having `arc_type="Dynasty-Founder"`. Accept as low-impact; the "founding" phase could become meaningful if dynasty creation logic changes (e.g., Phase 7 pre-founding detection).

#### Tragic Hero

| | Condition |
|-|-----------|
| **Partial** | `gp.trait == "bold"` and `gp.active` → phase `"embattled"` |
| **Complete** | `gp.trait == "bold"` + `gp.fate == "dead"` + `(gp.death_turn - gp.born_turn) < TRAGIC_HERO_LIFESPAN_THRESHOLD` → type `"Tragic-Hero"` |

Uses only GreatPerson fields — no event filtering. A bold character who burned bright and died fast is tragic regardless of cause. The narrator has deeds and event context for framing. Diverges from roadmap definition ("bold + rebellion + same-region death") — Decision 9 explains: no rebellion character-attribution exists. Roadmap should be updated when M45 lands.

`TRAGIC_HERO_LIFESPAN_THRESHOLD`: initial guess 30-40 turns. `[CALIBRATE]` for M47. Note: `born_turn` is the promotion turn (set to `world.turn` in `_process_promotions`), not biological birth. So `death_turn - born_turn` measures career length as a named character — a better signal for "burned bright and died fast" than biological age.

#### Wanderer

| | Condition |
|-|-----------|
| **Partial** | 2 `notable_migration` events → phase `"wandering"` |
| **Complete** | 3+ `notable_migration` events + `gp.region != gp.origin_region` → type `"Wanderer"` |

#### Defector

| | Condition |
|-|-----------|
| **Partial** | `gp.civilization != gp.origin_civilization` → phase `"defecting"` |
| **Complete** | + `secession_defection` or `conquest_exile` event with character name → type `"Defector"` |

Uses the field check as primary signal. Character-level events (`secession_defection`, `conquest_exile`) confirm the mechanism.

#### Prophet

| | Condition |
|-|-----------|
| **Partial** | Currently mid-pilgrimage (`gp.pilgrimage_return_turn is not None`) → phase `"converting"` |
| **Complete** | `pilgrimage_return` event exists in character's event history → type `"Prophet"` |

Note on timing: `check_pilgrimages()` clears pilgrimage fields (`pilgrimage_destination`, `pilgrimage_return_turn` → `None`) and emits the `pilgrimage_return` event within `phase_consequences()`, which runs BEFORE the classifier. So on the return turn: partial doesn't match (fields cleared), but complete matches (event emitted). On mid-pilgrimage turns: partial matches (fields still set), complete doesn't match yet. This is correct behavior.

Replaces the M38b explicit `gp.arc_type = "Prophet"` set. Classifier is the single authority.

#### Martyr

| | Condition |
|-|-----------|
| **Partial** | `gp.role == "prophet"` + displaced from origin (`conquest_exile` event with character name) → phase `"persecuted"` |
| **Complete** | `gp.role == "prophet"` + `gp.fate == "dead"` + `(gp.death_turn - gp.born_turn) < MARTYR_LIFESPAN_THRESHOLD` → type `"Martyr"` |

Redefined from the roadmap's "persecution → death → posthumous conversion spike." Persecution events (`religion.py`) use `actors=[civ.name]` — no character names in actors, so the `gp.name in e.actors` filter can never match them (Decision 11). The field-based definition captures the narrative archetype: a prophet who died before establishing influence. Distinguished from Tragic Hero by role (`"prophet"` vs `"bold"` trait) — different narrative meaning (faith dimension vs personality dimension).

`MARTYR_LIFESPAN_THRESHOLD`: initial guess 30-40 turns. `[CALIBRATE]` for M47. Same note as Tragic Hero: `born_turn` is promotion turn, measuring career length, not biological age.

Note: the partial ("persecuted" phase) fires only for prophets who are also conquest-exiled — most prophets under local persecution stay in-region and never trigger the partial. The complete match is field-based and does not require the partial to have fired. Most Martyrs will go directly from `arc_phase=None` to `arc_type="Martyr"` on their death turn. The +1.5 arc involvement bonus is missed for in-progress martyrs, but the +2.5 completion bonus still fires. Accept as low-impact.

### Priority Resolution

When multiple archetypes match completely, the one with the most conditions satisfied wins. Tie-break: later-occurring completion event (more recent arc is more narratively relevant).

When multiple archetypes match partially but none completely, the partial with the most conditions satisfied sets `arc_phase`.

### Call Site (run_turn() in simulation.py)

**Placement:** AFTER `world.events_timeline.extend(turn_events)` — the classifier needs current-turn events (especially `character_death`, `conquest_exile`) to be on the timeline. This places the classifier after all Phase 10 processing and event collection, before the turn-end snapshot.

**Dynasty registry source:** `bridge.dynasty_registry if bridge else None`. The `bridge` parameter (`AgentBridge | None`) is already available in `run_turn()`. In `--agents=off` mode, `bridge` is `None` and Dynasty Founder detection is skipped.

```python
# After events_timeline.extend(turn_events), before snapshot
dynasty_reg = bridge.dynasty_registry if bridge else None

# Active characters across all civs
for civ in world.civilizations:
    for gp in civ.great_persons:
        prev_type = gp.arc_type
        gp.arc_phase, new_type = classify_arc(
            gp, world.events_timeline, dynasty_reg, world.turn
        )
        if new_type is not None and new_type != prev_type:
            gp.arc_type = new_type
            gp.arc_type_turn = world.turn

# Recently dead — death is often the completing event
for gp in world.retired_persons:
    if gp.death_turn == world.turn:
        prev_type = gp.arc_type
        gp.arc_phase, new_type = classify_arc(
            gp, world.events_timeline, dynasty_reg, world.turn
        )
        if new_type is not None and new_type != prev_type:
            gp.arc_type = new_type
            gp.arc_type_turn = world.turn
```

Already-classified retired characters from prior turns are skipped — no new events will involve them, so re-derivation would produce the same result.

### Performance

At turn 500 with ~50K events and ~50 named characters: O(events × characters) per turn. On a 9950X this is <1ms. Not worth optimizing with a per-character event cache. If future phases push to 2000+ turns or 200+ characters, a per-character event index (populated once per turn, O(events) amortized) would bring per-character cost from O(all_events) to O(character_events). Flag for Phase 7+ if needed.

---

## Curator Scoring Enhancement

### Changes to curator.py

**Signature change** — `curate()` and `compute_base_scores()` gain a new parameter:

```python
def curate(
    events: ...,
    ...,
    named_characters: set[str] | None = None,
    gp_by_name: dict[str, GreatPerson] | None = None,  # M45
) -> tuple[list[NarrativeMoment], list[GapSummary]]:
```

Backward compatible — `None` default, existing callers unaffected.

**`gp_by_name` construction** at `curate()` entry, from the same iteration that builds `named_characters` in `_run_narrate()`:

```python
gp_by_name = {}
for civ in world.civilizations:
    for gp in civ.great_persons:
        if gp.active and gp.agent_id is not None:
            gp_by_name[gp.name] = gp
# Include all retired characters (death and natural retirement) for arc scoring.
# Arc completion bonus is self-limiting via arc_type_turn check.
for gp in world.retired_persons:
    if gp.death_turn is not None:
        gp_by_name[gp.name] = gp
```

Note: `gp_by_name` is keyed by character name. Name collisions are theoretically possible (different civs, overlapping name pools) but unlikely. If a collision occurs, the later entry overwrites. Low risk — same theoretical issue exists in the `named_characters` set in `_run_narrate()`.

### Scoring Logic in compute_base_scores()

```python
# Existing (M30) — already active in _run_narrate() and live.py:
if named_characters and any(actor in named_characters for actor in ev.actors):
    score += 2.0  # Named character involvement

# New (M45) — arc involvement bonus:
if gp_by_name:
    for actor in ev.actors:
        gp = gp_by_name.get(actor)
        if gp is None:
            continue
        if gp.arc_phase is not None or gp.arc_type is not None:
            score += 1.5  # Character has a recognizable story
            break  # Once per event, not per character

    # Arc completion bonus — the defining moment:
    for actor in ev.actors:
        gp = gp_by_name.get(actor)
        if gp and gp.arc_type_turn == ev.turn:
            score += 2.5  # This event's turn completed an arc
            break
```

### Bonus Stacking

| Bonus | Source | Value |
|-------|--------|-------|
| Named character | M30 (existing, active) | +2.0 |
| Arc involvement | M45 (phase or type set) | +1.5 |
| Arc completion | M45 (event on arc_type_turn) | +2.5 |
| **Max character bonus** | | **+6.0** |

Stacks with existing bonuses (named event +3.0, rarity +2.0, causal links +2.0–4.0). An arc-completing named event could score +9.0+ before diversity penalties. Intentional — these are the chronicle's highest-impact moments. The diversity penalty already handles over-selection of character-heavy moments.

The +2.5 is turn-level, not event-level. All events on `arc_type_turn` involving the character get the bonus. In practice 1-2 events per character per turn. `[CALIBRATE]` for M47: `+1.5` and `+2.5` values.

---

## Narration-Side Arc Summaries

### Gate

Summary generation runs only when `--narrator api` is active. In `--narrator local`, the extra inference cost (30-100 seconds per follow-up call at 2-3 tk/s) is prohibitive for ~15 calls. `arc_summary` stays `None` in local mode. The narrator still receives structured arc data (`arc_phase`, `arc_type`) in the prompt — just not the narrative threading.

### Flow Within narrate_batch()

Steps 1-2 are existing. Steps 3-5 are M45 additions.

1. **Build moment prompt** with character context (existing `build_agent_context_for_moment()`)
2. **Narrate moment** → prose (existing main LLM call)
3. **Name-match** characters in the returned prose:
   ```python
   # Broader set: AgentContext names + event actors who are named characters
   known_names = {c["name"] for c in agent_ctx.named_characters}
   for ev in moment.events:
       for actor in ev.actors:
           if actor in gp_by_name:
               known_names.add(actor)
   matched = [name for name in known_names if name in prose]
   ```
4. **Batched follow-up LLM call** for all matched characters (one call, not one per character):
   ```
   Based on the following passage, write exactly one sentence summarizing each
   named character's role. Only reference events described in the passage.

   Characters: [name1], [name2]
   Passage: [prose]

   Respond as:
   [name1]: [sentence]
   [name2]: [sentence]
   ```
   ~100-200 output tokens total. Uses same `narrative_client`.
5. **Update `gp.arc_summary`** for each matched character:
   - Parse response into per-character sentences
   - Append new sentence to `gp.arc_summary`
   - If > 3 sentences, drop oldest
   - Store on GreatPerson (looked up via `gp_by_name`)

### Graceful Degradation

- `--simulate-only`: no narration runs, `arc_summary` stays `None`.
- `--narrator local`: summary generation skipped (cost gate). `arc_phase`/`arc_type` still in prompt.
- Moments with no character matches: no follow-up call.
- Follow-up call failure (timeout, parse error): log warning, skip summary update, next moment proceeds.

### Character Context Enhancement

**build_agent_context_for_moment()** — relaxed active filter to include dead characters involved in the moment:

```python
# Characters involved in this moment's events (includes dead)
moment_actors = {actor for ev in moment.events for actor in ev.actors}

for gp in great_persons:
    if gp.source != "agent":
        continue
    if not gp.active and gp.name not in moment_actors:
        continue  # Skip dead characters not in this moment
    # ... build character dict (existing logic)
```

This ensures:
- The death moment gets the character's accumulated `arc_summary` in its prompt (issue: dead characters were previously excluded).
- Name-matching catches the character for summary generation on their final moment.

**Character dict additions:**

```python
if gp.arc_type:
    char["arc_type"] = gp.arc_type
if gp.arc_phase:
    char["arc_phase"] = gp.arc_phase
if gp.arc_summary:
    char["arc_summary"] = gp.arc_summary
```

### Prompt Rendering Enhancement

**build_agent_context_block()** — new arc context in character rendering:

```
Named characters present:
- General Kiran [bold] (Aram, originally Bora) [active]:
  Arc: Rise-and-Fall (rising)
  Summary: Led the Bora rebellion and carved a new frontier. Rose to command
    Aram's northern armies.
  Recent: Promoted as general in Kesh; Migrated from Kesh to the Northern March
  House of Kiran (3/5 living)
```

New elements:
- `[bold]` — trait rendering (1-line addition, currently in char dict but not rendered)
- `Arc:` line — arc_type with arc_phase in parens (omitted if both None)
- `Summary:` line — arc_summary (omitted if None)

---

## Deeds Population

Fixes the long-standing gap where `gp.deeds` was defined but never populated. The narrator reads `gp.deeds[-3:]` for recent history — currently always empty.

### Mutation Points

| Actual Function | File | Event | Deed Text |
|----------------|------|-------|-----------|
| `_process_promotions()` | agent_bridge.py:500 | Promotion | `"Promoted as {role} in {region}"` |
| `kill_great_person()` | great_persons.py:251 | Death | `"Died in {region}"` |
| `_retire_person()` | great_persons.py:92 | Retirement | `"Retired in {region}"` |
| `apply_conquest_transitions()` | agent_bridge.py:688 | Conquest exile | `"Exiled after conquest of {region}"` |
| `_detect_character_events()` | agent_bridge.py:637 | Exile return | `"Returned to {region} after {n} turns"` |
| `_detect_character_events()` | agent_bridge.py:637 | Notable migration | `"Migrated from {source} to {target}"` |
| `apply_secession_transitions()` | agent_bridge.py:743 | Secession defection | `"Defected to {new_civ} during secession"` |
| `check_pilgrimages()` | great_persons.py | Pilgrimage departure | `"Departed on pilgrimage to {dest}"` |
| `check_pilgrimages()` | great_persons.py | Pilgrimage return | `"Returned from pilgrimage as Prophet"` |

9 mutation points. All have known character references — no invented attribution.

**Line numbers are valid at time of writing (2026-03-18).** If M44 lands first, line numbers will shift — use function names for lookup at implementation time.

**`--agents=off` asymmetry:** In aggregate mode, only 3 of 9 mutation points are active: `kill_great_person()`, `_retire_person()`, and `check_pilgrimages()` (if religion active). The 6 `agent_bridge.py` points require the agent bridge, which is `None` in `--agents=off`. Aggregate-mode characters get sparser deeds. No risk to bit-identical output — deeds are narration context, not simulation state.

### Cap

`deeds` list capped at 10 entries. When appending past 10, drop the oldest (`gp.deeds = gp.deeds[-10:]`). The narrator reads `gp.deeds[-3:]` for recent history. The cap prevents unbounded growth while keeping enough history for the classifier and narrator context.

### Deed Text Format

Terse, structured, no LLM involvement. These are structured data for the classifier and narrator context, not prose. Example: `"Exiled after conquest of Kesh"`.

### Relationship Deeds

Relationship formation deeds (from M40 `form_and_sync_relationships()` coordinator) are possible but require `agent_id → name` lookup for the other party. Deferred — the 9 mutation points provide sufficient classifier signal for all 8 archetypes. Can be added as a follow-up if narration quality testing shows gaps.

---

## Testing Strategy

### Arc Classifier Tests (arcs.py)

| Test | Verifies |
|------|----------|
| `test_classify_rise_and_fall` | Promotion event + death event → phase="fallen", type="Rise-and-Fall" |
| `test_classify_exile_and_return` | Exile event + return event → type="Exile-and-Return" |
| `test_classify_dynasty_founder` | Dynasty with gp as founder + 2nd gen promoted → type="Dynasty-Founder" |
| `test_classify_tragic_hero` | Bold trait + dead + short lifespan → type="Tragic-Hero" |
| `test_classify_wanderer` | 3+ migration events → type="Wanderer" |
| `test_classify_defector` | civ != origin_civ + secession/exile event → type="Defector" |
| `test_classify_prophet` | Pilgrimage return events → type="Prophet" |
| `test_classify_martyr` | Persecution events + death → type="Martyr" |
| `test_classify_partial_only` | Exile event only (no return) → phase="exiled", type=None |
| `test_classify_reclassification` | Wanderer → Exile-and-Return when return event added |
| `test_classify_priority` | Multiple archetypes match → most complete wins |
| `test_classify_dead_character` | Death on current turn still classifies |
| `test_arc_type_turn_set` | arc_type_turn updates on (re)classification |
| `test_classify_no_events` | Character with no matching events → (None, None) |

### Curator Scoring Tests (curator.py)

| Test | Verifies |
|------|----------|
| `test_curator_arc_phase_bonus` | arc_phase set → +1.5 on character events |
| `test_curator_arc_completion_bonus` | Event on arc_type_turn → +2.5 |
| `test_curator_bonus_stacking` | Named (+2.0) + arc (+1.5) + completion (+2.5) = +6.0 |
| `test_curator_no_arc_no_bonus` | Character with no arc → only +2.0 named bonus |
| `test_curator_gp_by_name_none` | gp_by_name=None → no arc bonuses, no crash |

### Deeds Tests

| Test | Verifies |
|------|----------|
| `test_deeds_populated` | Each of 9 mutation points appends a deed |
| `test_deeds_cap` | 11th deed drops the oldest, list stays at 10 |
| `test_deeds_format` | Deed strings are terse and structured |

### Narration Integration Tests

| Test | Verifies |
|------|----------|
| `test_arc_context_in_prompt` | arc_type and arc_phase appear in narrator prompt |
| `test_arc_summary_name_match` | Characters mentioned in prose get summary updates |
| `test_arc_summary_truncation` | 4th sentence drops the oldest |
| `test_arc_summary_dead_character` | Dead character in moment events gets summary |
| `test_arc_summary_api_only` | `--narrator local` skips summary generation |
| `test_dead_character_in_moment_context` | Dead character's arc data appears in death moment prompt |
| `test_trait_rendered` | Character trait appears in prompt block |

---

## M44 Interaction

M44 (API Narration) adds `AnthropicClient` as a `narrative_client` option and wires `curate()` into the `execute_run()` API narration path. M45's changes are orthogonal:

- **Classifier** runs in Phase 10 (simulation-side) — no M44 dependency.
- **Curator scoring** changes are in `compute_base_scores()` — works with any caller of `curate()`.
- **Summary generation** uses `narrative_client` abstractly — works with both `LocalClient` and `AnthropicClient`.
- **Only coordination point:** both M44 and M45 modify `narrate_batch()`. The changes don't conflict — M44 adds the API client, M45 adds the summary follow-up call. Either ordering works.

**Recommended ordering:** M44 first (simpler, 3-4 days, and the API client enables testing arc summaries with fast inference). Not a hard dependency.

---

## Calibration Constants (M47)

| Constant | Initial | Check |
|----------|---------|-------|
| `TRAGIC_HERO_LIFESPAN_THRESHOLD` | 30-40 turns | Bold characters who survive 100+ turns shouldn't classify. Measures career length (promotion to death), not biological age. |
| `MARTYR_LIFESPAN_THRESHOLD` | 30-40 turns | Prophet characters who survive 100+ turns shouldn't classify as martyrs. Same note as Tragic Hero. |
| `RISING_CAREER_THRESHOLD` | 20 turns | Only established characters (not just-promoted) should be in "rising" phase. |
| Arc involvement bonus | +1.5 | Character-arc moments in top 50% of curated events |
| Arc completion bonus | +2.5 | Arc-completing moments consistently selected |
| Archetype distribution | — | At least 4 archetype types appear per 500-turn run |

---

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Simulation-side classification, narration-side summaries | Arc types available in `--simulate-only` for regression metrics. Summaries need LLM, degrade gracefully. |
| 2 | Two-field system: `arc_phase` + `arc_type` | Maps to curator's two bonus tiers (+1.5 / +2.5). Phase is volatile, type persists. |
| 3 | Classifier uses `events_timeline`, not new data structure | Structured event log already exists. Filter by `gp.name in e.actors`. |
| 4 | LLM-generated summaries (not deterministic) | Deterministic summaries are redundant with deeds. Narrative framing is the value. |
| 5 | Summaries API-only | Local mode cost (8-25 min) prohibitive. Structured arc data still in prompt. |
| 6 | Stateless re-derivation (no ArcRegistry) | Pure function of character history. No drift, no state corruption. <1ms per turn. |
| 7 | `arc_type_turn` for +2.5 scoring | Avoids duplicating pattern logic in curator. Turn-level granularity sufficient. |
| 8 | Classifier is single authority for `arc_type` | Removes M38b explicit Prophet set. One writer, no conflicts. |
| 9 | Tragic Hero is lifespan-based | No rebellion character-attribution exists. Bold + dead + short career uses only GP fields. `[CALIBRATE]` threshold. Diverges from roadmap — update roadmap when M45 lands. |
| 10 | Defector uses field check + character events | `civilization != origin_civilization` as primary signal. `secession_defection`/`conquest_exile` confirm mechanism. |
| 11 | Classifier operates on character-specific events only | Civ-level events don't include character names in actors. All 8 archetypes defined with character-level data. |
| 12 | Deeds populated at 9 verified mutation points | No invented attribution (rebellion/conquest dropped). Relationship deeds deferred. |
| 13 | Dead characters included in moment context | Relaxed active filter for characters in moment event actors. Death moment gets accumulated arc_summary. |
| 14 | Martyr uses field-based detection | Persecution events use `actors=[civ.name]` — no character names. Redefined as prophet role + short career. Same lifespan approach as Tragic Hero, different narrative dimension. |
| 15 | Classifier call site after `events_timeline.extend()` | Current-turn events (death, exile) must be on timeline for classifier to match them. |
| 16 | Dynasty registry from AgentBridge | `bridge.dynasty_registry if bridge else None`. Dynasty Founder skipped in `--agents=off`. |

---

## Scope Boundary

**In scope:**
- `arcs.py` classifier module (8 archetypes, pure function)
- `arc_phase`, `arc_summary`, `arc_type_turn` fields on GreatPerson
- Curator scoring enhancement (+1.5 / +2.5)
- Narration context enhancement (arc data in prompt)
- Arc summary follow-up LLM calls (API mode only)
- Deeds population (9 mutation points)
- M38b Prophet migration (remove explicit set)
- Trait rendering in prompt block

**Out of scope:**
- Civ-level event filtering for classifier (future archetype need)
- Relationship deeds (follow-up if needed)
- Dynasty-spanning arcs (Phase 7+)
- Arc-aware moment sequencing in curator (Approach C — rejected)
- `arc_completion_event_type` fine-grained scoring (defer unless M47 shows need)
- `CivThematicContext` population (dead infrastructure, not M45)
