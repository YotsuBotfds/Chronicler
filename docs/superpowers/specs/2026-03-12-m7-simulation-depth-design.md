# M7: Simulation Depth — Design Spec

> Make the simulation produce histories worth reading. Fix the all-DEVELOP problem, add tech progression, named events, and persistent landmarks.

## 1. Expanded Turn Loop

The 6-phase loop becomes 9 phases:

```
Phase 1: Environment          (unchanged — natural disasters, conditions)
Phase 2: Production            (unchanged — income, maintenance, pop growth)
Phase 3: Technology            (NEW — tech advancement checks, era transitions)
Phase 4: Action Selection      (REWORKED — deterministic engine replaces LLM)
Phase 5: Action Resolution     (REWORKED — named events generated here, tech disparity in war)
Phase 6: Random Events         (extended — new event types for cascading)
Phase 7: Leader Dynamics       (NEW — succession depth, legacy, rivalry updates, trait evolution)
Phase 8: Consequences          (extended — asabiya, collapse, condition tick)
Phase 9: Chronicle             (extended — historical callbacks from named events)
```

`run_turn()` signature unchanged. New phases are internal. Old state files load with defaults on new fields.

---

## 2. Action Engine

New module `action_engine.py`. Deterministic action selection as the primary path; LLM opt-in via `--llm-actions` flag.

### Weight Calculation

Base weights start equal (20% each). Three layers of bias stack multiplicatively:

#### Layer 1: Personality Weights

Each leader trait applies a full weight profile:

| Trait | WAR | EXPAND | DEVELOP | TRADE | DIPLOMACY |
|-------|-----|--------|---------|-------|-----------|
| aggressive | 2.0 | 1.3 | 0.5 | 0.8 | 0.3 |
| cautious | 0.2 | 0.5 | 2.0 | 1.3 | 1.5 |
| opportunistic | 1.0 | 1.5 | 0.8 | 2.0 | 0.7 |
| zealous | 1.5 | 2.0 | 1.3 | 0.5 | 0.4 |
| ambitious | 1.2 | 1.8 | 1.5 | 1.0 | 0.6 |
| calculating | 0.7 | 0.8 | 1.8 | 1.5 | 1.3 |
| visionary | 0.4 | 1.0 | 1.8 | 1.3 | 1.5 |
| bold | 1.8 | 1.8 | 0.6 | 1.0 | 0.5 |
| shrewd | 0.5 | 0.7 | 1.2 | 2.0 | 1.8 |
| stubborn | (repeat last action x2.0, all others x0.8) |

#### Layer 2: Situational Overrides

Game state conditions that modify weights. Multiple rules can stack:

| Condition | Effect |
|-----------|--------|
| stability <= 2 | DIPLOMACY x3.0, WAR x0.1 |
| military >= 7 AND hostile neighbor | WAR x2.5 |
| treasury >= 20 | EXPAND x2.0, TRADE x1.5 |
| treasury <= 3 | DEVELOP x0.3, EXPAND x0.2 |
| population >= 8 AND regions <= 2 | EXPAND x3.0 |
| economy <= 3 | DEVELOP x2.0, TRADE x1.5 |
| no hostile/suspicious neighbors | WAR x0.1 |
| all neighbors ALLIED | DIPLOMACY x0.1 |

#### Layer 3: Streak Breaker

Track last 3 actions per civ in `action_history`. If same action 3x in a row, set that action's weight to 0 and redistribute. Stubborn trait: streak breaks at 5 instead of 3.

### Eligibility Filter

Before weighting, remove actions the civ cannot take:
- EXPAND: requires military >= 3, unclaimed regions exist
- WAR: requires hostile/suspicious neighbor (disposition HOSTILE or SUSPICIOUS)
- TRADE: requires NEUTRAL+ partner, requires BRONZE+ tech era
- DIPLOMACY treaties: require CLASSICAL+ tech era
- EXPAND into harsh terrain (tundra, desert): requires IRON+

**Eligibility gates selection AND resolution.** If WAR is selected (whether by engine or LLM opt-in) but no eligible target exists, the action falls back to DEVELOP. The existing `_resolve_war_action` must be updated to enforce the same HOSTILE/SUSPICIOUS disposition threshold. This prevents the LLM opt-in path from bypassing eligibility.

### Selection

Weighted random from final distribution, seeded from `world.seed + turn + civ_index` for determinism.

### LLM Opt-in

`--llm-actions` flag: sends computed weights as context to LLM, LLM picks action, deterministic engine is fallback if LLM returns ineligible action.

### Integration with run_turn() Callback

`run_turn()` keeps its existing `action_selector: Callable[[Civilization, WorldState], ActionType]` callback signature. Wiring in `main.py`:
- **Default:** pass `ActionEngine(world).select_action` as the callback
- **`--llm-actions`:** pass a wrapper that tries `NarrativeEngine.action_selector` first, falls back to `ActionEngine.select_action` if the LLM returns an ineligible action

This preserves the callback pattern with no signature change.

---

## 3. Technology Progression

New module `tech.py`. Tech phase runs after Production, before Action Selection.

### Advancement Requirements

| Transition | Culture | Economy | Treasury Cost |
|-----------|---------|---------|---------------|
| TRIBAL -> BRONZE | >= 4 | >= 4 | 10 |
| BRONZE -> IRON | >= 5 | >= 5 | 12 |
| IRON -> CLASSICAL | >= 6 | >= 6 | 15 |
| CLASSICAL -> MEDIEVAL | >= 7 | >= 7 | 18 |
| MEDIEVAL -> RENAISSANCE | >= 8 | >= 8 | 22 |
| RENAISSANCE -> INDUSTRIAL | >= 9 | >= 9 | 28 |

At most one advancement per turn per civ. Deducts treasury on advancement. Generates `Event(event_type="tech_advancement", importance=7)`.

### Era Bonuses

Applied once on advancement, stack across history:

| Era | Bonuses |
|-----|---------|
| BRONZE | military +1 |
| IRON | economy +1 |
| CLASSICAL | culture +1, unlock formal treaties |
| MEDIEVAL | military +1, +0.2 defender asabiya bonus in war |
| RENAISSANCE | economy +2, culture +1 |
| INDUSTRIAL | economy +2, military +2 |

### Tech Disparity in War

- Era gap >= 2: attacker power x1.5
- Era gap >= 4: attacker power x2.0
- Works symmetrically (defender gets bonus if more advanced)

### Tech-Gated Actions

- TRADE requires BRONZE+
- Formal DIPLOMACY treaties require CLASSICAL+
- EXPAND into harsh terrain (tundra, desert) requires IRON+

### Starting Era

Civs start at TRIBAL (changed from Phase 1's IRON) for longer progression arc. This change is made in `world_gen.py`'s `assign_civilizations` function (where starting era is set), not in `main.py`.

---

## 4. Named Events & Historical Landmarks

New module `named_events.py`. New model `NamedEvent` on WorldState.

### NamedEvent Model

```python
class NamedEvent(BaseModel):
    name: str              # "The Siege of Thornwood"
    event_type: str        # battle, treaty, cultural_work, tech_breakthrough, coup, legacy, rival_fall
    turn: int
    actors: list[str]      # Civs involved
    region: str | None = None
    description: str       # One-line summary for callbacks
    importance: int = 5    # 1-10, used for historical callback ranking
```

`WorldState.named_events: list[NamedEvent]` — append-only.

### Generation Triggers

**Named battles** — every decisive WAR outcome (not stalemate). Era-appropriate naming:
- TRIBAL/BRONZE: "The Raid on {Region}", "The Skirmish at {Region}"
- IRON/CLASSICAL: "The Battle of {Region}", "The Siege of {Region}"
- MEDIEVAL+: "The Siege of {Region}", "The Sack of {Region}", "The Rout at {Region}"

**Named treaties** — DIPLOMACY upgrade to FRIENDLY or ALLIED. Format: "The {Adjective} {Noun}" themed to civ domains/values. Stored in both `named_events` and `Relationship.treaties`.

**Cultural works** — triggered at culture >= 8 (first time) and culture >= 10. Format: "The {Work} of {CivAdjective} {Theme}". Tracked via `Civilization.cultural_milestones`.

**Tech breakthroughs** — each era advancement. Era-themed names: "The Forging of Bronze", "The Codification of Law", "The First Engines", etc.

### Historical Callbacks

Chronicle prompt (Phase 9) includes:
- 5 most recent named events
- Single highest-importance named event from all history
- LLM instructed to reference them when relevant

### Naming Seed

All name generation is seeded from `world.seed + turn + hash(actor_names)` for determinism. Same seed + state = same names.

### Name Deduplication

All generated names checked against existing `named_events`. Collision: append numeral suffix ("The Second Battle of Thornwood").

---

## 5. Leader Depth

New module `leaders.py`. Leader Dynamics phase (Phase 7) handles succession, legacy, rivalries.

### Succession Types

Weighted random on `leader_death`:

| Type | Weight | Trait Bias | Effects |
|------|--------|-----------|---------|
| heir (40%) | 50% inherit predecessor trait, else random | — |
| general (25%) | aggressive/bold/ambitious | stability -1, military +1 |
| usurper (20%) | ambitious/calculating/shrewd | stability -3, asabiya +0.1, generates coup named event |
| elected (15%) | cautious/visionary/shrewd | stability +1. Requires culture >= 5 or CLASSICAL+ |

**Elected fallback:** If `elected` is rolled but requirements not met (culture < 5 AND pre-CLASSICAL), re-roll among the remaining types (heir/general/usurper) with their weights renormalized: heir 47%, general 29%, usurper 24%.

### Name Generation

Names tracked in `WorldState.used_leader_names` — no duplicates across entire run.

**Cultural archetypes** mapped from civ `domains`:

| Archetype | Triggered by domains | Name flavor |
|-----------|---------------------|-------------|
| maritime | maritime, commerce, coastal | Seafaring names: Thalor, Nerissa, Caelwen, Maren, Pelago... |
| steppe | nomadic, pastoral, plains | Steppe names: Toghrul, Arslan, Khulan, Borte, Temüge... |
| mountain | highland, mining, fortress | Stone names: Grimald, Valdris, Kareth, Stonvar, Brynhild... |
| forest | woodland, sylvan, nature | Woodland names: Elara, Sylvain, Thornwick, Fernhollow, Alder... |
| desert | arid, trade, oasis | Desert names: Rashidi, Zephyra, Khalun, Amaris, Deshaan... |
| scholarly | knowledge, arcane, culture | Scholar names: Vaelis, Isendra, Codrin, Lexara, Sapienth... |
| military | warfare, conquest, martial | Warrior names: Gorath, Ironvar, Bladwyn, Shieldra, Warmund... |
| default | (anything else) | Mixed pool of all archetypes |

Each pool contains 40+ names. Pool selection: scan civ's `domains` list, first match wins. If no domain matches an archetype, use the default mixed pool.

Titles drawn from a separate pool of 15+ titles (Emperor, Empress, Warchief, High Priestess, Chancellor, Archon, etc.), also matched to archetype where applicable.

### Leader Legacy

When a leader dies after 15+ turn reign, leaves a legacy modifier:

| Leader Trait | Legacy Type | Effect |
|-------------|------------|--------|
| aggressive/bold | military_legacy | military +1 for 10 turns |
| cautious/calculating | stability_legacy | stability +1 for 10 turns |
| visionary/shrewd | economy_legacy | economy +1 for 10 turns |
| zealous/ambitious | culture_legacy | culture +1 for 10 turns |

Implemented as `ActiveCondition(condition_type="legacy_X", duration=10, severity=1)`. At most one active legacy per civ. Generates named event: "The Legacy of {LeaderName} the {Epithet}".

### Rival Leaders

- WAR between two civs sets `rival_leader` and `rival_civ` on both leaders
- Rivalry persists until one leader dies
- Effects: WAR weight x1.5 against rival's civ in action engine
- Chronicle prompt mentions active rivalries
- On rival death: surviving rival gets culture +1, named event "The Fall of {RivalName}"
- Heir successors inherit rival status; other succession types do not

### Trait Evolution

After 10 turns of reign, leader gains secondary trait based on action majority:
- Majority WAR -> "warlike" secondary
- Majority DEVELOP -> "builder" secondary
- Majority TRADE -> "merchant" secondary
- Majority EXPAND -> "conqueror" secondary
- Majority DIPLOMACY -> "diplomat" secondary

Secondary trait adds x1.3 multiplier to its associated action in the engine. Note: only the primary `Leader.trait` is used for Layer 1 personality weights. The `secondary_trait` applies a flat x1.3 boost to one action type — it does not use the full trait weight table.

---

## 6. Data Model Changes

### WorldState Additions

```python
named_events: list[NamedEvent] = []
used_leader_names: list[str] = []          # list (not set) for stable JSON serialization; dedup enforced in leaders.py
action_history: dict[str, list[str]] = {}
```

All new fields have safe defaults (`[]`, `{}`, `None`). Old state files without these fields load correctly via Pydantic defaults.

### Civilization Additions

```python
cultural_milestones: list[str] = []
action_counts: dict[str, int] = {}       # {action_type: count} for current leader's reign
```

### Leader Additions

```python
succession_type: str = "founder"
predecessor_name: str | None = None
rival_leader: str | None = None          # Name of rival leader (from war)
rival_civ: str | None = None             # Name of rival's civ (for lookup)
secondary_trait: str | None = None       # Earned after 10 turns of reign
```

**Why on Leader, not Civilization:** `rival_leader`, `rival_civ`, and `secondary_trait` are leader-scoped attributes. When a leader dies and a new `Leader` object is created, these fields naturally reset to `None` without manual cleanup. Heir succession explicitly copies `rival_leader`/`rival_civ` from the predecessor during `generate_successor()`. `action_counts` stays on Civilization because it's cleared on succession in `leaders.py` and is read by the action engine which operates on civs.

### New Modules

| Module | Purpose |
|--------|---------|
| `action_engine.py` | Deterministic action selection with personality/situational/streak logic |
| `tech.py` | Tech advancement checks, era bonuses, disparity multipliers |
| `leaders.py` | Succession, legacy, rivalry, trait evolution, name generation |
| `named_events.py` | Named event generation, naming pools, deduplication |

### Changes to Existing Modules

- `simulation.py`: expand `run_turn` to 9 phases, call new modules
- `narrative.py`: remove action selection as default path, update chronicle prompt with named events + rivalries
- `events.py`: add cascade rules for `tech_advancement`, `coup`, `legacy`, `rival_fall`
- `main.py`: add `--llm-actions` flag, wire ActionEngine as default callback
- `world_gen.py`: change default starting era from IRON to TRIBAL
- `models.py`: add new fields and NamedEvent model

---

## 7. Testing Strategy

### New Test Files

**`test_action_engine.py`** (~25 tests):
- Trait weight profiles produce expected biases (each trait)
- Situational overrides fire at correct thresholds
- Personality + situational stacking
- Streak breaker at 3 repeats, stubborn at 5
- Eligibility filter removes impossible actions
- Tech-gated action filtering
- Deterministic: same seed + state = same action
- Edge case: graceful handling when most actions ineligible

**`test_tech.py`** (~15 tests):
- Advancement at correct thresholds per transition
- Treasury deducted on advancement
- Era bonuses applied and stacked
- No advancement when requirements unmet
- At most one advancement per turn
- Tech war multiplier at gaps 0, 1, 2, 3, 4
- Tech-gated actions blocked below required era
- Starting era is TRIBAL

**`test_leaders.py`** (~20 tests):
- Each succession type produces correct stat effects
- Elected blocked below culture 5 / CLASSICAL
- Name deduplication across 100 successions
- Cultural name pools match civ domains
- Legacy applied for 15+ turn reign, correct type
- Legacy as ActiveCondition with correct duration
- Rival assignment on WAR
- Rival inheritance only for heir
- Rival fall bonus + named event
- Secondary trait after 10 turns with majority action
- Predecessor name tracked

**`test_named_events.py`** (~15 tests):
- Battle names on decisive war (not stalemate)
- Battle name format matches era
- Treaty names on FRIENDLY/ALLIED upgrade
- Cultural works at culture 8 and 10, once each
- Tech breakthrough names on advancement
- Deduplication with numeral suffix
- All events appended to WorldState.named_events
- Deterministic naming from seed

### Extensions to Existing Tests

**`test_simulation.py`** (+10 tests):
- 9-phase loop runs without errors
- Phase ordering correct (tech before action, leader dynamics after random events)
- 10-turn, 4-civ validation: >= 3 action types per civ, >= 1 tech advancement, >= 2 named events, no leader name duplicates
- Old state.json backward compatibility

**`test_narrative.py`** (+5 tests):
- Chronicle prompt includes 5 most recent named events
- Chronicle prompt includes highest-importance event
- Chronicle prompt mentions rivalries
- Historical callback text in output

### Critical Gate

**20-turn, 4-civ** end-to-end integration test (not 10-turn — TRIBAL starts need more turns to reach tech advancement thresholds). Test civs start with boosted stats (economy=5, culture=5, treasury=12) to ensure at least one BRONZE advancement is reachable within the test window. Validates all acceptance criteria from the roadmap.

### Total: ~90 new tests (184 total)

---

## 8. CLI Changes

| Flag | Behavior |
|------|----------|
| `--llm-actions` | Opt-in: use LLM for action selection with deterministic fallback (default: deterministic only) |
| (existing flags unchanged) | |

Default starting era changed from IRON to TRIBAL.

---

## 9. Acceptance Criteria

Run 50 turns with 4 civs. Verify:
- At least 3 different action types chosen per civ
- At least 1 tech advancement across all civs
- At least 2 named events generated
- No leader name duplicates
- No crashes, all stats bounded
- State serializes and deserializes correctly
