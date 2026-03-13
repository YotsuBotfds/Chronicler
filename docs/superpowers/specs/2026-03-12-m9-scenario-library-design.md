# M9: Scenario Library — Design Spec

**Date:** 2026-03-12
**Status:** Draft
**Depends on:** M8 (Custom Scenarios) — COMPLETE
**Roadmap:** `chronicler-phase2-roadmap.md` lines 87-107

## Overview

M9 delivers three themed scenario YAML files plus three small schema extensions that enable richer scenario authoring. The M8 infrastructure (scenario.py, YAML loading, validation, apply pipeline) handles all heavy lifting — M9 adds minimal new code and substantial new content.

**Deliverables:**
1. Three new ScenarioConfig fields: `event_flavor`, `leader_name_pool` (on CivOverride), `narrative_style`
2. Three integration points: leader succession, narrative prompt, event display
3. Three scenario YAMLs: Post-Collapse Minnesota, Sentient Vehicle World, Dead Miles / Port Junction

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vehicle World ↔ Dead Miles coupling | Shared naming, separate YAMLs (no mechanical coupling) | Thematic continuity without infrastructure overhead. Chained pipelines (state inheritance) would require designing lore artifact formats before seeing 500-turn output. |
| Custom events | Flavor mapping to existing event types | Zero simulation changes. "Harsh Winter" is mechanically a drought with a custom name swapped at the narrative prompt layer. Arbitrary custom stat effects would require a modding framework — not M9 scope. |
| Leader succession names | Custom name pools per civ in YAML | Keeps naming control in scenario author's hands. Domain-based cultural pools in `leaders.py` are fantasy-themed and would produce immersion-breaking names in post-apocalyptic/vehicle scenarios. |
| Narrative tone | Single freeform string injected into LLM system prompt | Maximum creative control, trivial implementation. Structured tone controls (vocabulary allow/deny lists) are brittle and overengineered for this purpose. |
| Presentation-layer data location | On ScenarioConfig / NarrativeEngine, NOT WorldState | `event_flavor` and `narrative_style` are presentation concerns. WorldState is simulation state that serializes to `state.json`. Narrative engine is the natural boundary. |

## Schema Extensions

### New Model: EventFlavor

```python
class EventFlavor(BaseModel):
    name: str          # Display name, e.g. "Harsh Winter"
    description: str   # Context for LLM, e.g. "Supply lines freeze across the river valleys"
```

### ScenarioConfig Additions

```python
# Maps existing event type keys to themed display names/descriptions
event_flavor: dict[str, EventFlavor] | None = None

# Freeform narrative directive injected into LLM system prompt
narrative_style: str | None = None
```

### CivOverride Addition

```python
# Custom leader succession names for this civ
leader_name_pool: list[str] | None = None
```

### Civilization Model Addition

```python
# Populated by apply_scenario from CivOverride; used by _pick_name in leaders.py
leader_name_pool: list[str] | None = None
```

### Validation Rules

- `event_flavor` keys must exist in `DEFAULT_EVENT_PROBABILITIES` (same validation as `event_probability_overrides`). Invalid keys raise `ValueError` with the bad key name.
- `leader_name_pool` must contain at least 5 names if provided. Empty list rejected.
- `narrative_style`: no validation beyond non-empty if present.

## Integration Points

Three leaf-level modifications. No architectural changes. The simulation engine, action engine, tech system, world_gen, events processing, and memory/reflection system are untouched.

### 1. Leader Succession (`leaders.py` — `_pick_name`)

If `civ.leader_name_pool` is non-empty, draw from it before falling back to cultural pools.

```python
def _pick_name(civ, world, rng):
    if civ.leader_name_pool:
        available = [n for n in civ.leader_name_pool if n not in world.used_leader_names]
        if available:
            name = rng.choice(available)
            # name gets added to world.used_leader_names by existing caller flow
            return name
    # existing cultural pool logic unchanged
```

**Critical:** Must use the `rng` parameter (seeded deterministic RNG), not `random.choice`. The picked name must be added to `world.used_leader_names` to prevent cross-civ duplication. Both behaviors are already handled by the existing caller flow — the custom pool path must not bypass them.

When the custom pool is exhausted, fallback to the existing cultural pool logic. The generic fallback may produce names like "Axle III" (dynasty-style numbering), which is acceptable.

### 2. Event Flavor Swap (`narrative.py`)

Before event data reaches the LLM prompt, check the narrative engine's `event_flavor` dict. If the event type has a flavor entry, substitute the display name and description in the prompt context. The simulation output is unchanged.

```python
# In narrative prompt construction
event_type = event.event_type
display_name = event_type
display_desc = event.description
if self.event_flavor and event_type in self.event_flavor:
    display_name = self.event_flavor[event_type].name
    display_desc = self.event_flavor[event_type].description
```

The `NarrativeEngine` receives `event_flavor: dict[str, EventFlavor] | None` and `narrative_style: str | None` at initialization when a scenario is loaded. These are instance attributes on the engine, not WorldState fields.

### 3. Narrative Style Injection (`narrative.py` — system prompt)

If `self.narrative_style` is set, inject it into the system prompt after the historian role line:

```
You are a mythic historian chronicling the world of {world_name}.

NARRATIVE STYLE: {self.narrative_style}
```

When no scenario is loaded (or scenario has no `narrative_style`), the prompt is unchanged.

### apply_scenario Changes

One addition to the existing `apply_scenario` flow:
- During civ injection, copy `civ_override.leader_name_pool` to the matched `Civilization.leader_name_pool`.

`event_flavor` and `narrative_style` stay on `ScenarioConfig` and are passed to the narrative engine at initialization — they do not flow through `apply_scenario`.

## Scenario 1: Post-Collapse Minnesota

**File:** `scenarios/post_collapse_minnesota.yaml`
**Theme:** Grid-down survival in real Minnesota geography.
**Turns:** 80
**Starting era:** Tribal

### Regions (10)

| Region | Terrain | Capacity | Notes |
|--------|---------|----------|-------|
| Northern Prairies | plains | 6 | Open farmland, exposed |
| Red River Valley | river | 8 | Fertile floodplain |
| Iron Range | forest | 4 | Mining country, low agriculture |
| Boundary Waters | forest | 3 | Wilderness, hard to sustain |
| Twin Cities Ruins | plains | 5 | Scavengeable but dangerous |
| Mississippi Corridor | river | 7 | Trade artery |
| Bluff Country | hills | 5 | Defensible terrain |
| Lake Country | forest | 6 | Fishing, timber |
| Willmar | plains | 9 | Prime agricultural zone |
| Benson | plains | 8 | Farming community, river access |

### Civilizations (6)

**Farmer Co-ops**
- Stats: population 6, military 3, economy 7, culture 4, stability 7
- Tech era: tribal | Domains: agriculture, community | Values: pragmatism, self-reliance
- Goal: cautious | Leader: Elder Johansson (trait: pragmatic)
- Leader name pool: Johansson, Larsen, Olson, Henning, Bakke, Dahl, Lundquist, Pedersen, Thorson, Halverson, Erikson, Lindgren, Nyquist, Bergstrom, Engstrom

**River Towns Alliance**
- Stats: population 5, military 4, economy 6, culture 5, stability 5
- Tech era: tribal | Domains: commerce, navigation | Values: trade, cooperation
- Goal: calculating | Leader: Captain Mercer (trait: shrewd)
- Leader name pool: Mercer, Lockwood, Braddock, Stillwater, Redwing, Hastings, Winona, Dubuque, Prescott, LaCrosse, Wabasha, Frontenac, Tremaine, Pepin, Albion

**National Guard Remnant**
- Stats: population 4, military 8, economy 3, culture 2, stability 6
- Tech era: tribal | Domains: warfare, discipline | Values: order, duty
- Goal: aggressive | Leader: Colonel Voss (trait: disciplined)
- Leader name pool: Voss, Reeves, Harding, Kessler, Brandt, Marsh, Caldwell, Eriksen, Tanner, Novak, Schaefer, Albrecht, Kowalski, Dietrich, Meier

**Prepper Networks**
- Stats: population 3, military 5, economy 4, culture 2, stability 8
- Tech era: tribal | Domains: survival, fortification | Values: independence, preparedness
- Goal: cautious | Leader: Elder Crandall (trait: cautious)
- Leader name pool: Crandall, Whitmore, Duggan, Falk, Bremer, Stoltz, Gruber, Harlan, Ecklund, Renner, Bauer, Selvig, Kramer, Ohlsen, Engel

**Church Communities**
- Stats: population 5, military 2, economy 4, culture 7, stability 7
- Tech era: tribal | Domains: faith, diplomacy | Values: compassion, unity
- Goal: cautious | Leader: Pastor Lindahl (trait: visionary)
- Leader name pool: Lindahl, Engstrom, Sorensen, Arneson, Fjelstad, Haugen, Solberg, Nordstrom, Lund, Bjornson, Nygaard, Dalen, Strand, Hagen, Vik

**Carleton Enclave**
- Stats: population 3, military 2, economy 5, culture 8, stability 5
- Tech era: classical | Domains: knowledge, preservation | Values: learning, reason
- Goal: calculating | Leader: Dean Alderman (trait: visionary)
- Leader name pool: Alderman, Thorne, Whitfield, Lowell, Pemberton, Ashworth, Marlowe, Kingsley, Sinclair, Harwood, Prescott, Elsworth, Fairbanks, Winslow, Cartwright

**Note:** Carleton Enclave starts at classical era while all others are tribal. This creates immediate tech asymmetry — the Enclave hits tech war multipliers from turn 1, but their low military and population make them vulnerable. The knowledge-preservation angle generates "protect vs. hoard" narrative tension.

### Relationships

| Pair | Disposition |
|------|-------------|
| Farmer Co-ops ↔ Church Communities | friendly |
| National Guard Remnant ↔ Prepper Networks | suspicious |
| Carleton Enclave ↔ Church Communities | friendly |
| Carleton Enclave ↔ National Guard Remnant | suspicious |
| All other pairs | neutral |

### Event Flavor

| Event Type | Flavor Name | Description |
|------------|-------------|-------------|
| drought | Harsh Winter | Supply lines freeze across the river valleys |
| discovery | Supply Cache Discovery | A pre-collapse warehouse is found intact |
| migration | Refugee Column | Displaced survivors arrive seeking shelter |
| rebellion | Food Riot | Hungry citizens turn on their own leadership |
| cultural_renaissance | Harvest Festival | A successful growing season brings rare celebration |
| border_incident | Territorial Standoff | Armed patrols meet at a disputed boundary |
| plague | Sickness Outbreak | Disease spreads through crowded shelters |
| religious_movement | Revival Movement | A charismatic preacher draws followers across faction lines |
| earthquake | Bridge Collapse | Critical infrastructure fails without warning |
| leader_death | Winter Took Them | A leader succumbs to the harsh conditions |

### Starting Conditions

- `grid-down`: affects all 6 civs, duration 999 (effectively permanent), severity 4
  - Severity 4 is below the `phase_consequences` stability drain threshold (>=5). Represents persistent hardship that shapes strategic decisions without causing a mechanical death spiral over 80 turns.
  - **Test note:** Tune severity during 20-turn smoke tests. If factions stabilize too easily, bump to 5. If they collapse, drop to 3.

### Narrative Style

```
Terse, pragmatic tone. Midwestern understatement. Focus on weather, crops, community
survival, and the hard math of calories and firewood. No high fantasy language.
Think Cormac McCarthy on the prairie.
```

## Scenario 2: Sentient Vehicle World

**File:** `scenarios/sentient_vehicle_world.yaml`
**Theme:** Deep mythic pre-history of a world where vehicles are sentient beings.
**Turns:** 500
**Starting era:** Tribal
**Purpose:** Generates canonical ancient lore referenced by the Dead Miles scenario. A reader of both chronicles should recognize faction names and cultural DNA that evolved over centuries.

### Regions (10)

| Region | Terrain | Capacity | Notes |
|--------|---------|----------|-------|
| The Proving Grounds | plains | 6 | Open testing terrain |
| Rust Flats | plains | 3 | Harsh, corrosive environment |
| The Interchange | river | 7 | Crossroads, high traffic |
| Fuel Springs | forest | 9 | Abundant fuel deposits |
| The Long Straight | plains | 5 | Open highway territory |
| Axle Mountains | hills | 4 | Defensible, resource-poor |
| The Scrapyard Wastes | forest | 3 | Parts salvage, dangerous |
| Chrome Valley | river | 7 | Prosperous, scenic |
| The Terminal Plains | plains | 6 | Gateway region |
| Oil Delta | river | 8 | Rich fuel estuary |

### Civilizations (5)

**Geargrinders**
- Stats: population 5, military 7, economy 5, culture 3, stability 4
- Tech era: tribal | Domains: warfare, engineering | Values: strength, conquest
- Goal: aggressive | Leader: Warchief Axle (trait: aggressive)
- Leader name pool: Axle, Torque, Piston, Crankshaw, Diesel, Camber, Ratchet, Wrench, Sprocket, Burnout, Clutch, Gasket, Flywheel, Crank, Bore, Rotor, Manifold, Throttle, Turbo, Intake

**Haulers Union**
- Stats: population 6, military 4, economy 7, culture 4, stability 7
- Tech era: tribal | Domains: commerce, logistics | Values: trade, solidarity
- Goal: calculating | Leader: Guildmaster Convoy (trait: shrewd)
- Leader name pool: Convoy, Haul, Rig, Freight, Payload, Overpass, Junction, Tarmac, Blacktop, Roadway, Flatbed, Tanker, Chassis, Hitch, Kingpin, Axleguard, Trailhead, Loadstar, Driveshaft, Bumper

**Chrome Council**
- Stats: population 4, military 3, economy 6, culture 8, stability 5
- Tech era: tribal | Domains: art, governance | Values: beauty, refinement
- Goal: cautious | Leader: High Polisher Sterling (trait: visionary)
- Leader name pool: Sterling, Gleam, Polish, Lustre, Brilliance, Mirror, Sheen, Radiance, Lacquer, Platinum, Gloss, Luster, Veneer, Enamel, Gilt, Finesse, Glaze, Prism, Aurora, Shimmer

**Rustborn**
- Stats: population 7, military 3, economy 4, culture 3, stability 8
- Tech era: tribal | Domains: survival, community | Values: endurance, solidarity
- Goal: cautious | Leader: Elder Patina (trait: pragmatic)
- Leader name pool: Patina, Corrode, Flake, Oxide, Weather, Dent, Scratch, Bondo, Primer, Salvage, Rivet, Weld, Slag, Scrap, Galvanize, Tarnish, Grit, Alloy, Solder, Temper

**Electrics**
- Stats: population 3, military 2, economy 6, culture 7, stability 5
- Tech era: tribal | Domains: innovation, philosophy | Values: progress, enlightenment
- Goal: calculating | Leader: Archon Volt (trait: visionary)
- Leader name pool: Volt, Ampere, Watt, Ohm, Tesla, Farad, Joule, Coulomb, Hertz, Lumen, Charge, Spark, Dynamo, Capacitor, Relay, Cathode, Anode, Circuit, Flux, Inductor

### Relationships

| Pair | Disposition |
|------|-------------|
| Geargrinders ↔ Rustborn | hostile |
| Chrome Council ↔ Electrics | friendly |
| All other pairs | neutral |

The Geargrinders-Rustborn hostility creates the defining early-history arc: military predator vs. resilient underdog. Rustborn's high stability and population enable asabiya-driven survival through Turchin dynamics. The Chrome Council-Electrics cultural bloc forms the other power axis, with the Haulers Union as the pragmatic swing faction.

### Event Flavor

| Event Type | Flavor Name | Description |
|------------|-------------|-------------|
| drought | Fuel Shortage | Fuel reserves run dangerously low across the land |
| plague | Rust Plague | A corrosive epidemic spreads through the population |
| discovery | Ancient Blueprint Discovery | Plans for a forgotten technology are unearthed |
| rebellion | Rogue Fleet | A faction splinters as dissidents break formation |
| migration | The Great Convoy | A mass movement of vehicles seeking new territory |
| cultural_renaissance | The Reforging | A burst of creative energy transforms society |
| religious_movement | Cult of the Engine | A spiritual movement centered on mechanical transcendence |
| earthquake | Road Collapse | The ground gives way, severing vital routes |
| border_incident | Highway Blockade | Armed vehicles bar passage at a contested crossing |
| leader_death | Final Breakdown | A leader's systems fail beyond repair |

### Narrative Style

```
Mythic and reverent, as if written by a sentient vehicle historian recording sacred
history. Vehicles are people — they speak, think, feel, age, and die. Use automotive
metaphors as natural language, not as wordplay. 'She rusted with grief' is literal.
Chronicle the rise of civilizations with weight and grandeur.
```

### Known Concerns

- **500 turns = 50 era reflections.** The reflection prompt summarizes recent events against all prior reflections. By turn 400, the context fed to the LLM includes 40 era summaries. Monitor for coherence degradation during manual test runs. A sliding window (last 5 summaries + key highlights from earlier eras) may be needed as a future enhancement, but is out of M9 scope.
- **Leader name pool exhaustion.** 20 names per faction across 500 turns with `leader_death` probability + 15-turn legacy system will likely exhaust pools. The fallback to cultural pool logic (which may produce dynasty-style "Axle III" names) is acceptable and thematically appropriate.

## Scenario 3: Dead Miles / Port Junction

**File:** `scenarios/dead_miles.yaml`
**Theme:** Urban post-collapse faction politics in a decaying port city.
**Turns:** 300
**Starting era:** Iron
**Purpose:** Generates 300 turns of backstory as canonical lore for the Dead Miles setting. Thematically linked to Sentient Vehicle World — same faction names, centuries later, evolved into territorial urban power blocs.

### Relationship to Sentient Vehicle World

The Dead Miles YAML shares the five faction names from the Vehicle World (Geargrinders, Haulers Union, Chrome Council, Rustborn, Electrics). The continuity is purely thematic — shared naming convention and cultural DNA, not mechanical state inheritance. A reader of both chronicles recognizes factions that evolved from mythic tribal origins into modern political entities. No chained pipeline or lore artifact format is needed.

### Regions (10)

| Region | Terrain | Capacity | Notes |
|--------|---------|----------|-------|
| Gasoline Alley | plains | 5 | Geargrinder territory, fuel storage |
| The Terminal | river | 9 | Major port infrastructure |
| The Gulch | hills | 3 | Decayed lowland zone |
| Dockside | river | 8 | Port operations, Chrome Council |
| The Interchange | river | 7 | Traffic nexus, contested |
| Scrap Row | forest | 4 | Salvage district, Rustborn turf |
| Chrome Heights | hills | 6 | Elevated, affluent district |
| Voltage Park | plains | 5 | Electrics' innovation quarter |
| The Long Haul | plains | 6 | Freight corridor |
| Rust Narrows | forest | 3 | Cramped, corroded passages |

### Civilizations (5)

**Geargrinders**
- Stats: population 5, military 8, economy 5, culture 2, stability 4
- Tech era: iron | Domains: warfare, engineering | Values: strength, dominance
- Goal: aggressive | Leader: Warboss Torque (trait: aggressive)
- Regions: Gasoline Alley (1 region — territorially squeezed, high expand pressure)
- Leader name pool: Axle, Torque, Piston, Crankshaw, Diesel, Camber, Ratchet, Wrench, Sprocket, Burnout, Clutch, Gasket, Flywheel, Crank, Bore

**Haulers Union**
- Stats: population 6, military 4, economy 8, culture 4, stability 7
- Tech era: iron | Domains: commerce, logistics | Values: trade, solidarity
- Goal: calculating | Leader: Guildmaster Freight (trait: shrewd)
- Regions: The Terminal, The Long Haul (2 regions — controls freight infrastructure)
- Leader name pool: Convoy, Haul, Rig, Freight, Payload, Overpass, Junction, Tarmac, Blacktop, Roadway, Flatbed, Tanker, Chassis, Hitch, Kingpin

**Chrome Council**
- Stats: population 4, military 4, economy 7, culture 8, stability 5
- Tech era: iron | Domains: governance, art | Values: beauty, authority
- Goal: cautious | Leader: High Polisher Gleam (trait: visionary)
- Regions: Chrome Heights, Dockside (2 regions — cultural and economic power)
- Leader name pool: Sterling, Gleam, Polish, Lustre, Brilliance, Mirror, Sheen, Radiance, Lacquer, Platinum, Gloss, Luster, Veneer, Enamel, Gilt

**Rustborn**
- Stats: population 6, military 3, economy 4, culture 3, stability 8
- Tech era: iron | Domains: survival, community | Values: endurance, solidarity
- Regions: Rust Narrows, Scrap Row (2 regions — marginal but defensible)
- Goal: cautious | Leader: Elder Salvage (trait: pragmatic)
- Leader name pool: Patina, Corrode, Flake, Oxide, Weather, Dent, Scratch, Bondo, Primer, Salvage, Rivet, Weld, Slag, Scrap, Galvanize

**Electrics**
- Stats: population 3, military 2, economy 6, culture 7, stability 5
- Tech era: iron | Domains: innovation, philosophy | Values: progress, enlightenment
- Regions: Voltage Park (1 region — small but culturally influential)
- Goal: calculating | Leader: Archon Spark (trait: visionary)
- Leader name pool: Volt, Ampere, Watt, Ohm, Tesla, Farad, Joule, Coulomb, Hertz, Lumen, Charge, Spark, Dynamo, Capacitor, Relay

### Starting Region Assignments

| Region | Controller |
|--------|-----------|
| Gasoline Alley | Geargrinders |
| The Terminal | Haulers Union |
| The Long Haul | Haulers Union |
| Chrome Heights | Chrome Council |
| Dockside | Chrome Council |
| Rust Narrows | Rustborn |
| Scrap Row | Rustborn |
| Voltage Park | Electrics |
| The Gulch | (uncontrolled) |
| The Interchange | (uncontrolled) |

The Gulch and The Interchange are contested neutral zones. The Geargrinders (1 region, high military, aggressive goal) will face heavy `expand` weight pressure from the action engine's situational modifiers, creating an early crisis point.

### Relationships

| Pair | Disposition | Rationale |
|------|-------------|-----------|
| Geargrinders ↔ Rustborn | hostile | Ancient enmity carried forward from deep history |
| Chrome Council ↔ Electrics | friendly | Centuries-old cultural alliance persists |
| Haulers Union ↔ Chrome Council | friendly | Trade dependency — Haulers move Chrome's goods |
| Haulers Union ↔ Geargrinders | suspicious | Geargrinders want to control freight by force |
| Rustborn ↔ Electrics | friendly | Underdog solidarity, tech sharing |
| Geargrinders ↔ Chrome Council | suspicious | Military vs. cultural power tension |

Six explicit directional relationships create genuine political tension. The Haulers Union as swing faction — two friendly relationships, one suspicious — makes them politically valuable to all sides.

### Event Flavor

| Event Type | Flavor Name | Description |
|------------|-------------|-------------|
| drought | Parts Shortage | Critical components become impossible to source |
| plague | Rust Plague | Corrosion spreads through the crowded districts |
| discovery | Salvage Find | A valuable cache of pre-collapse technology surfaces |
| rebellion | Dock Strike | Haulers refuse to move freight until demands are met |
| migration | The Recall | A mass summons draws vehicles from across the city |
| cultural_renaissance | Showroom Revival | A burst of aesthetic innovation transforms the culture |
| religious_movement | Cult of the Open Road | A spiritual movement yearning for life beyond the city |
| earthquake | Infrastructure Collapse | Overloaded roads and bridges give way |
| border_incident | Checkpoint Standoff | Armed vehicles block a disputed crossing |
| leader_death | Final Breakdown | A leader's systems fail beyond repair |

### Starting Conditions

None. Dead Miles is a mature, functioning (if tense) urban setting. No grid-down equivalent.

### Narrative Style

```
Noir-inflected political chronicle. Hard-boiled, cynical, focused on power, territory,
and loyalty. Vehicles are people in a decaying city — they scheme, betray, negotiate,
and occasionally do the right thing at the wrong time. Think Raymond Chandler narrating
a trade war between sentient trucks.
```

## Testing Strategy

### Schema Extension Tests (unit)

- `EventFlavor` model validation: valid construction, required fields
- `event_flavor` key validation: keys must exist in `DEFAULT_EVENT_PROBABILITIES`. Invalid keys (e.g., `"tech_advancement"`, `"nonexistent_event"`) raise `ValueError`
- `leader_name_pool` validation: minimum 5 names enforced, empty list rejected, `None` accepted (optional field)
- `narrative_style` round-trips through `ScenarioConfig` (present when set, absent when `None`)
- `load_scenario` correctly parses all three new fields from YAML
- `apply_scenario` copies `leader_name_pool` from `CivOverride` to matched `Civilization`

### Integration Point Tests

- `_pick_name` draws from custom pool before cultural pool, using deterministic `rng` parameter
- `_pick_name` adds custom pool picks to `world.used_leader_names` (cross-civ dedup)
- `_pick_name` falls back to cultural pool when custom pool is exhausted
- **Deterministic succession test:** Run a scenario with custom name pool, set `leader_death` probability to 1.0 via test-specific override, verify successor name is identical across two runs with the same seed. Confirms custom pool draws go through deterministic RNG.
- Event flavor swap produces correct display name/description in narrative prompt context
- Event flavor swap is a no-op when `event_flavor` is `None`
- Narrative style string appears in system prompt when set, absent when not

### Scenario Smoke Tests

Per roadmap criteria, each of the 3 scenarios:
- Loads and validates without errors
- Runs 20 turns without crashes
- Determinism check: same seed produces identical `WorldState` after 5 turns (run twice, compare)

### Not Tested in M9 (Manual Validation)

- 500-turn and 300-turn full runs (too slow for CI; validated by manual run + reading output)
- Narrative output quality (subjective; validated by reading chronicle prose)
- Reflection context bloat at 500 turns (flagged as known concern; tune during manual runs)

## Milestone Structure

| Milestone | Scope | Parallelizable |
|-----------|-------|---------------|
| M9.1: Schema extensions | New fields, validation, wiring (leader succession, narrative prompt, event flavor swap) | No (foundation) |
| M9.2: Post-Collapse Minnesota | YAML file + 20-turn smoke test | Yes (after M9.1) |
| M9.3: Sentient Vehicle World | YAML file + 20-turn smoke test | Yes (after M9.1) |
| M9.4: Dead Miles | YAML file + 20-turn smoke test (written after M9.3 for naming consistency review) | After M9.3 |

M9.2 and M9.3 are independent and can be parallelized. M9.4 depends on M9.3 only for a naming consistency check — the YAML content is already designed above, so the dependency is lightweight.

## Key Constraints

- `REGION_TEMPLATES` pool (12 entries) is not a constraint — all three scenarios define all regions explicitly via overrides.
- `CIV_TEMPLATES` pool (6 entries) is not a constraint — all scenarios define all civs explicitly.
- `leader_name_pool` sizes: 15 names for Minnesota and Dead Miles factions, 20 for Vehicle World (longer run). Exhaustion falls back to cultural pools.
- `event_flavor` covers all 10 `DEFAULT_EVENT_PROBABILITIES` keys in each scenario — complete thematic coverage.
- No changes to simulation engine, action engine, tech system, or memory/reflection system.
