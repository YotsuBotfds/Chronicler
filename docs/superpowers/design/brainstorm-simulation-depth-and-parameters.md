# Brainstorm: Simulation Depth & CLI Parameters

> **Status:** Brainstorm document. Raw ideas for deepening the simulation and expanding user-configurable parameters. Not all ideas are feasible or desirable — this is the unfiltered list.
>
> **Context:** Chronicler can serve as (a) a standalone story generator, (b) a world-gen backend for games, or (c) a TTRPG campaign setting generator. Different use cases value different parameters.
>
> **Date:** 2026-03-18

---

## Current State: What Users Can Already Configure

### CLI Flags (main.py)

| Flag | Type | Default | What It Controls |
|------|------|---------|-----------------|
| `--seed` | int | 42 | RNG seed — fully deterministic |
| `--turns` | int | 50 | Simulation length |
| `--civs` | int | 4 | Number of civilizations |
| `--regions` | int | 8 | Number of regions (max 12 from template pool) |
| `--agents` | enum | off | Agent mode (off/demographics-only/shadow/hybrid) |
| `--scenario` | path | — | YAML scenario file |
| `--tuning` | path | — | Tuning YAML for constant overrides |
| `--simulate-only` | bool | false | Skip LLM narration |
| `--batch` | int | — | Run N chronicles with sequential seeds |
| `--parallel` | int | — | Worker count for batch |
| `--seed-range` | str | — | Seed range for batch (e.g., 1-200) |
| `--llm-actions` | bool | false | LLM-driven action selection |
| `--interactive` | bool | false | Pause at intervals for commands |
| `--live` | bool | false | WebSocket live mode for viewer |
| `--narrate` | path | — | Post-hoc narration of sim-only bundle |
| `--budget` | int | 50 | Narration moment count |
| `--local-url` | str | — | LM Studio endpoint |
| `--sim-model` / `--narrative-model` | str | — | Model names |

### Scenario YAML (scenario.py)

Already configurable per-scenario:
- World name, size, duration, seed
- Region definitions (name, terrain, capacity, resources, ecology, adjacencies, rivers)
- Civilization definitions (name, stats, tech era, domains, values, goals, leader pools)
- Starting relationships (disposition matrix, auto-symmetrized)
- Starting conditions (type, severity, duration, affected civs)
- Event probability overrides (14 event types)
- Event flavor reskinning (rename events thematically)
- Narrative style (free-form tone description for LLM)
- Climate config, fog of war, chaos multiplier, black swan cooldown
- Terrain transition rules
- Interestingness weights for curation scoring

### Tuning YAML

Constant overrides — any `[CALIBRATE]` constant can be overridden per-run.

---

## Gap Analysis: What's Missing

### A. World Generation Parameters

**Current limitation:** 12 hardcoded region templates. No procedural geography. No control over continent shape, climate zones, or resource distribution patterns.

Proposed new CLI flags and scenario YAML fields:

#### A1. Geography Generation

| Parameter | Type | Range | Effect |
|-----------|------|-------|--------|
| `--world-shape` | enum | `pangaea / continents / archipelago / ring` | Macro geography template |
| `--continent-count` | int | 1-6 | Number of landmasses (if `continents`) |
| `--region-count` | int | 4-200 | Total regions (remove 12-template cap, generate procedurally) |
| `--ocean-fraction` | float | 0.0-0.8 | Fraction of regions that are ocean/sea |
| `--mountain-density` | float | 0.0-1.0 | Probability of mountain terrain |
| `--river-density` | float | 0.0-1.0 | Number of river systems relative to region count |
| `--latitude-climate` | bool | true | Enable latitude-based climate (polar/temperate/tropical bands) |
| `--terrain-seed` | int | — | Separate seed for terrain gen (allows same geography, different history) |

**Implementation sketch:** Replace the 12-template system with a procedural region generator. Use a Voronoi tessellation or hex grid for region shapes, assign terrain by elevation + moisture (Amit Patel's approach). Adjacency computed from the tessellation rather than the current random graph. Rivers flow downhill. Coasts are regions adjacent to ocean cells. This is a prerequisite for "continuous terrain" (currently deferred beyond Phase 9) but a simpler version using discrete regions is feasible sooner.

#### A2. Resource Distribution

| Parameter | Type | Range | Effect |
|-----------|------|-------|--------|
| `--resource-abundance` | enum | `scarce / normal / abundant` | Global resource multiplier |
| `--resource-clustering` | float | 0.0-1.0 | How clustered vs. evenly distributed resources are |
| `--mineral-depletion` | bool | true | Whether mineral resources deplete over time |
| `--fertile-fraction` | float | 0.0-1.0 | Fraction of land regions with agricultural potential |
| `--special-resource-count` | int | 0-10 | Number of unique/rare resources (spices, gems, etc.) |

#### A3. Climate & Environment

| Parameter | Type | Range | Effect |
|-----------|------|-------|--------|
| `--climate-volatility` | float | 0.0-2.0 | Amplitude of climate cycle oscillation |
| `--climate-period` | int | 20-200 | Length of climate cycle in turns |
| `--disaster-frequency` | float | 0.0-3.0 | Multiplier on natural disaster probability |
| `--ice-age-probability` | float | 0.0-0.1 | Chance per turn of major climate shift |
| `--disease-virulence` | float | 0.0-2.0 | Multiplier on endemic disease severity |
| `--seasonal-intensity` | float | 0.0-2.0 | How much seasons affect production |

### B. Civilization Starting Conditions

#### B1. Cultural Diversity Parameters

| Parameter | Type | Range | Effect |
|-----------|------|-------|--------|
| `--cultural-distance` | enum | `homogeneous / moderate / diverse / alien` | Starting cultural similarity between civs |
| `--tech-spread` | enum | `equal / varied / one-advanced` | Starting tech era distribution |
| `--starting-era` | enum | TechEra values | Global starting tech era |
| `--power-balance` | enum | `equal / moderate / one-dominant / varied` | Starting stat distribution |
| `--religious-diversity` | enum | `monotheistic / polytheistic / diverse / secular` | Starting faith landscape |

#### B2. Political Configuration

| Parameter | Type | Range | Effect |
|-----------|------|-------|--------|
| `--starting-diplomacy` | enum | `peaceful / neutral / hostile / mixed` | Starting relationship distribution |
| `--vassal-count` | int | 0-N | Number of starting vassal relationships |
| `--federation-probability` | float | 0.0-1.0 | Chance of starting federations |
| `--uncontrolled-regions` | int | 0-N | Regions without a controller at start |

### C. Simulation Dynamics Parameters

These control *how* the simulation behaves, not just starting conditions.

#### C1. Pace & Scale

| Parameter | Type | Range | Effect |
|-----------|------|-------|--------|
| `--turn-scale` | enum | `year / decade / generation` | What a turn represents (affects all rates) |
| `--population-growth-rate` | float | 0.5-2.0 | Multiplier on base population growth |
| `--tech-speed` | float | 0.5-3.0 | Multiplier on tech advancement probability |
| `--war-frequency` | float | 0.0-3.0 | Multiplier on war action weight |
| `--diplomacy-weight` | float | 0.0-3.0 | Multiplier on diplomatic action weight |
| `--expansion-pressure` | float | 0.0-3.0 | Multiplier on EXPAND action weight |

#### C2. Simulation Flavor Knobs

| Parameter | Type | Range | Effect |
|-----------|------|-------|--------|
| `--realism` | enum | `mythic / historical / gritty` | Adjusts severity multiplier, black swan frequency, recovery rates |
| `--volatility` | float | 0.0-3.0 | Master chaos multiplier (already exists as `chaos_multiplier` in scenarios) |
| `--golden-age-length` | int | 10-100 | How long stable periods tend to last before disruption |
| `--collapse-severity` | float | 0.0-2.0 | How destructive political collapses are |
| `--trade-importance` | float | 0.0-3.0 | How much trade affects treasury/satisfaction |
| `--culture-drift-speed` | float | 0.0-3.0 | How fast cultural values shift |
| `--religious-fervor` | float | 0.0-3.0 | How intense religious dynamics are |

#### C3. Agent Behavior (hybrid/agents mode)

| Parameter | Type | Range | Effect |
|-----------|------|-------|--------|
| `--agent-count` | int | 1000-1000000 | Target initial agent count (currently derived from population) |
| `--great-person-frequency` | float | 0.0-3.0 | Multiplier on GreatPerson promotion rate |
| `--rebellion-threshold` | float | 0.0-1.0 | Satisfaction level below which rebellion risk increases |
| `--migration-mobility` | float | 0.0-3.0 | How willing agents are to migrate |
| `--occupational-mobility` | float | 0.0-3.0 | How willing agents are to switch occupations |

### D. Output & Presentation Parameters

#### D1. Narration Control

| Parameter | Type | Range | Effect |
|-----------|------|-------|--------|
| `--narrator` | enum | `local / api / none` | Narration engine (M44 adds API) |
| `--narrative-style` | str | — | Already in scenarios, promote to CLI flag |
| `--narrative-voice` | enum | `chronicle / epic / academic / journalistic / mythic` | Preset narrative styles |
| `--narrative-focus` | enum | `wars / culture / characters / economy / religion / all` | What the narrator prioritizes |
| `--chronicle-format` | enum | `prose / annals / encyclopedia / timeline` | Output structure |
| `--character-depth` | enum | `minimal / moderate / deep` | How much character detail in narration |
| `--moment-budget` | int | 10-500 | Already `--budget`, rename for clarity |

#### D2. Output Formats

| Parameter | Type | Range | Effect |
|-----------|------|-------|--------|
| `--output-format` | enum | `markdown / json / html / pdf` | Primary output format |
| `--export-timeline` | path | — | Export events as a standalone timeline JSON |
| `--export-atlas` | path | — | Export region/territory maps per era |
| `--export-genealogy` | path | — | Export dynasty family trees |
| `--export-world-bible` | path | — | Generate a comprehensive world reference document |
| `--export-ttrpg` | path | — | Export as TTRPG campaign setting (faction sheets, maps, hooks) |
| `--export-game-state` | path | — | Export world state in a game-engine-friendly format |

#### D3. Bundle Enhancements

| Feature | Description |
|---------|-------------|
| Searchable encyclopedia | Per-civ, per-character, per-region encyclopedia entries auto-generated from simulation data |
| Character dossiers | Named characters with biography, relationships, key events, personality |
| Relationship web | D3-compatible social graph export |
| Economic report | Trade flows, Gini trends, resource maps per era |
| Military history | War timeline, campaign maps, casualty reports |
| Cultural atlas | Cultural identity maps per era, showing drift and assimilation |
| Religious map | Faith distribution over time, schism events, pilgrimage routes |

---

## E. New Simulation Systems (Beyond Phase 9)

### E1. Procedural Geography (replaces 12-template system)

**What:** Generate terrain from parameters rather than hardcoded templates. Voronoi regions, elevation-driven terrain assignment, watershed rivers, latitude climate.

**Key parameters exposed:** `--world-shape`, `--region-count`, `--ocean-fraction`, `--mountain-density`

**Why it matters:** The 12-template cap is the single biggest limitation for both story gen (repetitive geography) and game use (can't generate varied worlds). Every other system builds on geography.

**Prerequisite for:** All scale-up ambitions. You can't have 200 regions with 12 templates.

### E2. Naval & Maritime Systems

**What:** Sea zones as connective tissue between coastal regions (EU4-inspired). Naval force projection, maritime trade, piracy as emergent behavior, thalassocracy mechanics.

**Minimum viable system:**
- Tag coastal regions. Add `sea_zone` connections between coastal region clusters with properties: `(distance, storm_risk, piracy_level, chokepoint: bool)`
- `naval_strength` per civ = sum of coastal region development * shipbuilding_tech_modifier
- Maritime trade routes: higher throughput than land routes but require `naval_strength > piracy_threshold` to be safe
- Trade value through sea zone = `base_value * (1 - piracy_level * (1 - naval_protection_ratio))`

**Piracy as emergent behavior:** Regions with low state authority + coastal access + poverty generate piracy. `piracy_level = base * (1 - coastal_authority) * poverty_factor`. Pirates raid trade and coastal settlements.

**Thalassocracy emergence:** Civs with naval_strength > X * army_strength AND controlling chokepoint sea zones get thalassocracy bonuses: trade, exploration, colonial projection. Penalties to land warfare focus.

**Feedback loops:**
- Naval power protects trade → trade funds ships → more projection (positive)
- Piracy throttles unprotected trade → incentivizes naval buildup
- Island/coastal civs naturally specialize toward naval power
- Chokepoint control = geopolitical leverage (Strait of Hormuz pattern)
- Blockades as warfare tool: cut off maritime trade to siege without land armies

**Parameters:**
- `--naval-enabled` (bool) — toggle maritime systems
- `--ocean-traversal` (enum: `none / coastal / open-sea`) — how far ships can travel
- `--piracy-frequency` (float) — risk on sea trade routes
- `--exploration-enabled` (bool) — uncharted ocean regions discoverable by naval civs

### E3. Disease & Epidemic System (beyond M35b baseline)

**What:** SEIRS compartmental model (Susceptible-Exposed-Infectious-Recovered-Susceptible) with per-region disease pools, mutation, quarantine as social response, and immunity dynamics.

**Core variables:**
- `beta` (transmission rate) = contact_rate x infection_probability — driven by population density, sanitation, trade connectivity
- `gamma` (recovery rate) — modifiable by medical knowledge tech
- `mu` (disease mortality) — scales with virulence
- `R0 = beta / gamma` — if >1, epidemic; if <1, disease dies out
- Per-region: `disease_pool: list[Disease]` each with `(virulence, lethality, visibility, vectors, strain_id)`
- Per-civ: `sanitation_level` (reduces beta), `medical_knowledge` (increases gamma), `quarantine_policy` (reduces contact at cost of trade penalty)

**Key feedback loops:**
- Trade routes spread disease (beta scales with trade volume) — maritime routes spread faster than overland
- Dense urban settlements (M56) have higher beta — cities are disease amplifiers
- Post-plague labor scarcity drives wage increases (Black Death effect — connects to elite dynamics)
- Quarantine reduces trade income but slows epidemic — a genuine policy tradeoff
- Endemic diseases create immunological advantage for natives vs. newcomers (colonization/first contact dynamic)
- Plague kills population → reduced economic output → reduced trade → reduced further spread (natural brake)

**Narrative hooks:** Plague as dynasty-ender, plague triggering religious movements ("God's punishment"), plague breaking sieges, disease wiping out isolated populations upon first contact.

**Parameters:**
- `--epidemic-model` (enum: `simple / SIR / agent-level`) — complexity level
- `--plague-narrative-weight` (float) — how much curator prioritizes disease events
- `--disease-virulence` (float 0.0-2.0) — global multiplier on virulence
- `--immunity-inheritance` (bool) — children inherit partial immunity from survivors

### E4. Language & Naming System

**What:** Procedural language generation for civ/region/character names. Language families that drift over time, creoles at cultural boundaries, lingua francas along trade routes.

**Core model (Naming Game / Lipowska & Lipowski):** Agents carry language feature inventories. When speaker/hearer interact, the hearer either learns a new feature or achieves mutual comprehension. Key parameters:
- `gamma` — probability that bilingual agents create a creole blend
- `epsilon` — cross-group interaction frequency (inversely proportional to segregation)
- `delta` — mutual intelligibility within a language family

**Concrete variables:**
- Per-civ: `lingua_franca_id`, `literary_tradition_strength` (resistance to drift)
- Language distance = float 0.0-1.0 between feature vectors
- Drift rate: `base_drift * (1 - literacy_rate) * (1 - literary_tradition)` — literate societies with written canons drift slower
- Contact rule: shared trade routes decrease language distance by `convergence_rate * trade_volume`
- When two very different languages meet at a trade hub, a pidgin/creole forms as a distinct entity

**Feedback loops:**
- Lingua francas reduce diplomatic friction → more trade → reinforces lingua franca
- Conquest imposes conqueror's language but creates substrate effects
- Isolation increases drift → eventually splits languages
- Religious texts freeze liturgical language while spoken forms drift away
- Printing press tech is a phase transition for language standardization

**Parameters:**
- `--language-gen` (bool) — enable procedural naming
- `--language-families` (int) — number of distinct language roots
- `--naming-style` (enum: `generic / phonemic / culture-mapped`) — how names are generated

### E5. Education & Knowledge System

**What:** Human capital accumulation with guild-based transmission (Hanushek & Woessmann, de la Croix/Doepke/Mokyr). Literacy rates, schools/universities as infrastructure, knowledge as a compounding resource, apprenticeship for skill transmission, libraries that preserve knowledge through collapse.

**Core model:** Knowledge grows via `delta_knowledge = (research_output * literacy_rate * institutional_support) - knowledge_decay`. Threshold effect: below 40% literacy, growth benefits are minimal; above 40%, compounding returns kick in.

**Guild/apprenticeship tiers:**
- *Apprentice*: learns from master, 2-7 turns, produces low-skill labor during training
- *Journeyman*: mobile skilled worker, travels between civs (spreading techniques)
- *Master*: produces masterworks, trains apprentices, institutional memory

**Key variables:** `literacy_rate`, `knowledge_stock`, `institutional_support` (schools/libraries/monasteries), `knowledge_decay_rate`, `guild_density` per region

**Feedback loops:**
- Literacy enables written records which reduce knowledge_decay
- Knowledge stock enables better education infrastructure which increases literacy
- Journeyman travel spreads techniques between civs (but guilds try to restrict this)
- War destroys libraries/institutions → knowledge collapse → dark age
- Printing press tech = phase transition — dramatically reduces knowledge_decay and increases literacy growth
- Religious institutions are double-edged: preserve knowledge (monasteries) but may restrict what knowledge is permitted

**Why it matters:** Currently tech advancement is a probabilistic roll. A knowledge system creates the substrate for why some civs advance faster (they invest in education) and why dark ages happen (knowledge loss). Libraries as burnable infrastructure adds a powerful narrative dimension.

### E6. Espionage & Intelligence

**What:** CK3-inspired scheme system. Schemes have `power` (attacker intrigue + agent network + resources) vs. `resistance` (target spymaster + counterintelligence + institutional security). Progress accumulates per turn; schemes can be discovered.

**Scheme types:** Assassination, Sabotage (reduce military/economy), Steal Technology, Destabilize (increase faction unrest), Fabricate Claims

**Core mechanic:** `scheme_progress += (power - resistance) * random_factor` each turn. Discovery chance = `base_discovery * (1 - attacker_stealth) * target_counterintelligence`. Discovery cancels scheme, damages relations, may trigger war.

**Key variables:** `intelligence_capability` per civ, `counterintelligence`, `secret_pool: list[Secret]`

**Feedback loops:**
- Intelligence scales with urbanization (more agents to recruit)
- Trade networks double as intelligence networks (merchants as spies)
- Espionage success breeds paranoia → target increases counterintelligence spending (arms race)
- Stolen technology accelerates the thief but alerts the victim
- Assassination of leaders triggers succession crises (links to dynasty system)

**Why it matters:** Phase 8-9 introduces information asymmetry at the civ level. Espionage is the active version — civs investing in knowing more about their rivals.

### E7. Art, Literature & Monuments

**What:** Cultural production as a simulation system. Works of art, philosophical treatises, monuments, wonders. Each with a creator, patron civ, thematic content derived from the world state at creation time, and lasting cultural influence.

**Key variables:** `cultural_output`, `patron_wealth_threshold`, `monument_construction_time`, `artistic_movement_spread`

**Why it matters:** Phase 7's artifacts are narrative hooks, not a cultural production system. A full art/literature system creates the "cultural golden age" phenomenon where prosperity enables creative output that then defines a civilization's identity for centuries. Monuments as visible landmarks that appear on maps.

### E8. Legal System Emergence

**What:** Legal systems that emerge from dispute resolution needs and evolve based on civ characteristics (from lex mercatoria research). Distinct from Phase 8 institutions — legal systems are a specific *type* of institution with their own evolution logic.

**Legal system types (enum, driven by civ state):**
- *Customary/Tribal* — default. Low overhead, works for small populations. Breaks down at scale.
- *Religious Courts* — emerge when clergy faction dominant. Preserves order but resists commercial innovation.
- *Trial by Ordeal/Combat* — military-dominant. Low adjudication cost, high variance. Favors the powerful.
- *Merchant Law (Lex Mercatoria)* — emerges along trade routes when trade_income > X%. Voluntary, fast, cross-border. Enforced by reputation and trade exclusion.
- *Common Law* — emerges from precedent accumulation. Requires literacy + record-keeping.
- *Codified Law* — requires high literacy + strong central authority. Reduces uncertainty, enables large-scale economic planning.

**Transition triggers:** Merchant law when trade_income > threshold. Religious courts when clergy_power > threshold. Codified law when literacy > 0.6 AND centralization > threshold.

**Feedback loops:** Better legal systems reduce transaction costs → more trade → funds institutional development. Merchant law is portable across borders. Weak rule of law enables corruption, enriching elites but reducing overall efficiency. Legal pluralism (multiple systems coexisting) creates friction but also flexibility.

### E8b. Diplomatic Instruments

**What:** Beyond disposition and federation — treaties, trade agreements, non-aggression pacts, mutual defense obligations, marriages of state, hostage exchanges, tribute arrangements. Each with terms, duration, violation consequences.

**Key variables:** `treaty.type`, `treaty.terms`, `treaty.duration`, `treaty.violation_penalty`, `diplomatic_reputation`

**Parameters:**
- `--diplomacy-complexity` (enum: `simple / moderate / detailed`) — how many treaty types are active
- `--treaty-reliability` (float) — how likely civs are to honor agreements

### E9. Migration & Diaspora

**What:** Utility-based migration with network effects (Klabunde & Willekens). Agents evaluate `utility(current) vs. utility(destination) - migration_cost`. Chain migration: diaspora communities at destination reduce migration_cost via `effective_cost = base_cost * (1 - diaspora_discount * diaspora_size)`.

**Key variables:**
- Push factors: war, famine, persecution, ecological collapse, overcrowding
- Pull factors: economic opportunity, safety, religious freedom, existing diaspora
- `diaspora_registry: dict[civ_id, dict[region_id, population]]` — tracks displaced populations
- `migration_pressure` per region = push - pull; when > threshold, mass migration triggers

**Refugee mechanics:** War/famine generates refugees proportional to severity. Refugees flow toward nearest safe region with lowest effective cost. Assimilation vs. enclave: rate depends on host tolerance, diaspora size, cultural distance.

**Feedback loops:**
- Diaspora creates trade links to origin (remittances)
- Large refugee influx strains host economy → backlash
- Chain migration creates self-reinforcing flows
- Persecution triggers exodus → weakens persecuting civ's economy
- Brain drain: educated agents migrate first, hollowing origin's knowledge stock

**Why it matters:** Migration is already in the agent system but as individual decisions. Diaspora communities — groups maintaining cultural identity in foreign lands — are a major driver of narrative (Jewish diaspora, Armenian diaspora, Huguenot exile). They create cross-cultural bridges, trade networks, and political complexity.

### E10. Technological Innovation (beyond tech trees)

**What:** Combinatorial search in adjacent possible space (Youn et al., Royal Society). Technologies are combinations of existing components. With N known techs, N*(N-1)/2 pairwise combinations exist. Most useless; a small fraction (viability rate) produce innovations.

**Core mechanic:** Each turn, civ makes `research_capacity` attempts to combine two known components. Success probability = `viability_rate * (1 + genius_bonus) * (1 + knowledge_stock_bonus)`. New tech = new component added to set, expanding the combinatorial space super-linearly.

**Key variables:** `tech_components: set[TechID]` per civ, `research_capacity`, `viability_rate`

**Key dynamics:**
- Larger populations generate more innovation attempts (more minds) — but with coordination overhead
- Trade routes and journeyman travel leak components between civs (cross-pollination)
- Contact with culturally diverse civs accelerates innovation (more novel combinations)
- Some combinations require specific prerequisites (metallurgy + bellows → steel) — natural tree emergence without a fixed tree
- GreatPersons with Scholar trait multiply local research_capacity (Renaissance Florence, Abbasid Baghdad "scene" effect)

**Feedback loops:**
- More components = super-linearly more combinations = accelerating returns
- "Low-hanging fruit" effect: early combinations easier, later ones need more attempts
- Education system's knowledge_stock increases viability_rate
- War destroys tech infrastructure but incentivizes military innovation
- Trade spreads components → convergence, but also competitive pressure to innovate faster

**Parameters:**
- `--tech-model` (enum: `tree / combinatorial / hybrid`) — innovation model
- `--innovation-rate` (float) — base probability of new combinations
- `--knowledge-diffusion` (float) — how fast knowledge spreads between civs

### E-Cross. Cross-System Interactions (where the real depth lives)

The richest emergent behavior comes from system interactions, not individual systems:

| System A | System B | Interaction |
|----------|----------|-------------|
| Disease | Trade | Trade routes spread plagues. Quarantine kills trade income. Maritime routes spread faster than overland. |
| Disease | Migration | Refugees flee plague zones, potentially carrying disease to new regions. |
| Disease | Naval | Ships carry rats, rats carry plague. First contact with isolated populations = demographic catastrophe. |
| Language | Trade | Lingua francas reduce trade friction → more trade → reinforces lingua franca. |
| Language | Conquest | Conquerors impose language but substrate effects create dialects. Long occupation + literary tradition = replacement. Short occupation = loanwords only. |
| Education | Innovation | Literacy compounds innovation rate. Printing press is a phase transition for both. |
| Education | Religion | Monasteries preserve knowledge but may restrict what's permitted. Reformation partly driven by literacy enabling direct scripture access. |
| Legal | Trade | Merchant law emerges from trade, then facilitates more trade. Legal pluralism at borders creates arbitrage. |
| Legal | Religion | Religious courts compete with secular courts. Reformation partly driven by legal jurisdiction disputes. |
| Espionage | Innovation | Tech theft as alternative to research. Arms race consumes resources that could be productive. |
| Migration | Knowledge | Brain drain weakens origin. Diaspora networks transmit innovations bidirectionally. |
| Naval | Disease | Maritime trade amplifies pandemic spread. Port cities are disease entry points. |
| Naval | Trade | Maritime trade has higher throughput but requires protection. Chokepoint control = leverage. |
| Naval | Military | Blockades as siege tool. Amphibious invasion. Island civs unconquerable without navy. |
| Knowledge | Collapse | Library burning = knowledge loss = dark age. Monastery preservation = knowledge survival through collapse. |
| Disease | Elite dynamics | Post-plague labor scarcity → wage increases → reduces elite overproduction pressure → can reset secular cycle. |

---

## F. Game Integration Features

### F1. Export Formats for Game Engines

| Format | Use Case | Contents |
|--------|----------|----------|
| Tiled JSON | 2D tile-based games | Region layout as tile map, terrain layers, resource markers |
| Heightmap PNG | 3D terrain | Elevation data as grayscale image |
| GeoJSON | Web-based maps | Region boundaries, properties, adjacencies |
| GraphML | Network visualization | Civ relationships, trade routes, social graphs |
| SQLite | Structured queries | Full world state in queryable tables |
| Protobuf/FlatBuffers | Performance-critical | Compact binary world state for game runtime |

### F2. World State API

**What:** Expose Chronicler's world state as a queryable API rather than just a CLI.

```python
# Library usage
from chronicler import World

world = World(seed=42, regions=50, civs=8, turns=500)
world.simulate()

# Query
world.civilizations["Kethani"].treasury
world.regions["Iron Peaks"].controller
world.get_wars_between("Kethani", "Dorrathi")
world.get_trade_routes(involving="Kethani")
world.get_character("General Ashani").memories
world.export_timeline(format="json")
world.export_map(turn=250, format="svg")
```

### F3. Scenario Templates Library

**What:** A curated library of scenario presets that users can mix and match.

| Template Category | Examples |
|-------------------|---------|
| Geography | Pangaea, Archipelago, River Valley, Continental, Island Chain |
| Era | Bronze Age, Classical, Medieval, Renaissance, Industrial, Modern, Post-Apocalyptic |
| Theme | Trade-focused, War-torn, Cultural renaissance, Religious conflict, Ecological collapse |
| Scale | City-state (4 civs, 8 regions), Regional (8 civs, 20 regions), Continental (12 civs, 50 regions), Global (20 civs, 200 regions) |
| Tone | Epic fantasy, Historical realism, Grimdark, Mythological, Journalistic |

### F4. Hooks & Callbacks

**What:** Allow external code to hook into simulation events for game integration.

```python
world = World(seed=42)

@world.on("war_declared")
def handle_war(event):
    # Game engine can react to simulation events
    play_sound("war_drums")
    show_notification(f"{event.aggressor} declares war on {event.defender}")

@world.on("turn_complete")
def update_game(snapshot):
    # Update game state from simulation
    update_minimap(snapshot.region_control)
    update_ui(snapshot.civ_stats)
```

### F5. Partial Simulation (Game Mode)

**What:** Run specific phases on demand rather than the full turn loop, for games that want to control pacing.

```python
world = World(seed=42)
world.run_phase("economy")  # Just the economy tick
world.run_phase("politics")  # Just politics
# Player makes decisions here
world.run_phase("military")  # Resolve conflicts
```

### F6. Interactive World Building

**What:** A mode where the user can modify the world between simulation steps.

```
chronicler --interactive --pause-every 10
> Turn 10. Kethani Empire (5 regions, pop 450). Paused.
> inject drought Kethani           # Inject an event
> set Kethani.treasury 500         # Modify state
> add-region "New Territory" plains # Add a region mid-simulation
> continue 10                      # Run 10 more turns
```

Already partially implemented via `--interactive` mode, but could be expanded with more commands.

---

## G. Narrative & Story Generation Improvements

### G1. Narrative Persona System

**What:** Named narrator personas with distinct voices, biases, and blind spots.

| Persona | Voice | Bias |
|---------|-------|------|
| The Court Historian | Formal, flattering to the patron civ | Downplays patron's failures, inflates victories |
| The Traveling Merchant | Practical, focused on trade and wealth | Sees everything through economic lens |
| The Temple Scribe | Religious, sees divine will in events | Attributes causation to gods/faith |
| The Exile | Bitter, critical of the dominant power | Sympathetic to the oppressed, cynical about rulers |
| The Natural Philosopher | Analytical, interested in patterns | Focuses on ecological and demographic forces |

Each persona would modify the narrator prompt context, creating chronicles that feel written by a *person* with a perspective.

### G2. Multiple Chronicle Perspectives

**What:** Generate the same history from multiple viewpoints. The fall of an empire reads very differently from the conqueror's chronicle vs. the conquered's oral history.

Parameter: `--perspectives` (int) — number of parallel chronicles to generate

### G3. Primary Source Generation

**What:** Generate fictional "primary sources" — diplomatic letters, battle reports, religious texts, trade manifests — as inserts within the chronicle.

Parameter: `--primary-sources` (bool) — include generated documents

### G4. Chronicle Compilation Modes

| Mode | Description |
|------|-------------|
| `annals` | Year-by-year (turn-by-turn) entries, terse |
| `chronicle` | Selected moments, narrative prose (current default) |
| `epic` | Extended narrative with character focus, mythologized |
| `encyclopedia` | Per-topic entries (each civ, each war, each character) |
| `timeline` | Events only, no prose, structured data |
| `atlas` | Map-centric, territory changes per era |
| `biography` | Character-centric, follows named characters' lives |
| `oral-history` | Fragmented, unreliable, multiple voices |

### G5. Era-Aware Narration Style

**What:** Narration style that evolves with the simulated era. Tribal age gets oral epic tone. Classical gets formal historical prose. Medieval gets chronicle style. Industrial gets journalistic reporting.

Parameter: `--era-adaptive-voice` (bool)

---

## H. Quality of Life & Tooling

### H1. World Preview

**What:** Generate and display a quick summary of the world before running the full simulation.

```
chronicler --preview --seed 42 --regions 50 --civs 8
> World: Aetheris (seed 42)
> Geography: 50 regions, 3 continents, 12 coastal, 8 mountain, 5 desert
> Civilizations: 8 (4 tribal, 2 classical, 1 iron, 1 medieval)
> Resources: iron (3 regions), wheat (12 regions), spices (2 regions)
> Climate: temperate dominant, tropical band at equator
> Run this world? [Y/n]
```

### H2. Seed Discovery

**What:** Run many seeds in batch, score them by interestingness criteria, and surface the best ones.

```
chronicler --discover --seed-range 1-1000 --turns 200 --score-by "war_count + named_event_count"
> Top 10 seeds by interestingness:
>  1. Seed 847 (score 342): 12 wars, 3 collapses, 2 golden ages
>  2. Seed 213 (score 318): 8 wars, 5 collapses, 1 Mule character
>  ...
```

### H3. Diff Between Runs

**What:** Compare two chronicle runs and highlight divergences.

```
chronicler --diff output/seed_42/ output/seed_42_fork/
> Divergence at turn 23: Kethani chose WAR (original) vs TRADE (fork)
> By turn 50: original has 3 civs, fork has 5 civs
```

### H4. Replay Mode

**What:** Load a completed bundle and step through it turn by turn in the viewer, with full state available at each step.

### H5. Scenario Generator

**What:** Use an LLM to generate scenario YAML from a natural language description.

```
chronicler --generate-scenario "A world inspired by the Silk Road era, with three major empires
connected by trade routes through a central desert region, competing for control of spice trade"
> Generated scenario: output/silk_road.yaml
```

---

## I. Performance & Scale Parameters

| Parameter | Type | Range | Effect |
|-----------|------|-------|--------|
| `--max-agents` | int | 1K-1M | Cap on total agent count |
| `--tick-budget-ms` | int | 50-1000 | Target tick time (adjusts computation depth) |
| `--thread-count` | int | 1-32 | Rayon thread pool size |
| `--memory-budget-mb` | int | 100-10000 | Cap on agent pool memory |
| `--spatial-resolution` | enum | `region / settlement / agent` | Spatial detail level |
| `--snapshot-interval` | int | 1-50 | How often to capture full state snapshots |

---

## Priority Assessment

### Tier 1: Do Now (days, not weeks — pure multipliers and CLI wiring)
1. **Simulation dynamics multipliers** — `--aggression-bias`, `--tech-diffusion-rate`, `--resource-abundance`, `--severity-multiplier`, `--cultural-drift-speed`, `--religion-intensity`, `--secession-likelihood`, `--trade-friction`. Each is one scalar multiplied into an existing code path. Wire through `tuning_overrides`.
2. **Promote narrative-style to CLI flag** — already in scenarios, just needs `--narrative-style` in argparse
3. **Narrative voice presets** — `--narrative-voice chronicle/epic/academic/journalistic/mythic` — maps to prompt templates
4. **Preset bundles** — `--preset=pangaea/archipelago/golden-age/dark-age/ice-age` — compound parameter shortcuts
5. **Export timeline as standalone JSON** — data already in bundle, extract and write

### Tier 2: Near-term (1-2 weeks each)
6. **World preview mode** (`--preview`) — generate world, display summary, optionally proceed
7. **Seed discovery** (`--discover --seed-range 1-1000`) — batch + sort by interestingness score
8. **TTRPG export** (`--export-ttrpg`) — LLM pass to generate faction sheets, NPC dossiers, regional overviews from bundle data
9. **Encyclopedia export** (`--export-encyclopedia`) — per-entity entries with cross-references, LLM-polished
10. **Chronicle format options** (`--chronicle-format annals/chronicle/encyclopedia/timeline`) — mostly narration prompt + compilation changes

### Tier 3: Medium-term (weeks)
11. **Procedural geography** (replace 12 templates) — noise-based or Voronoi region gen, weighted by `--terrain-roughness`, `--temperature`, `--rainfall`. Unlocks `--region-count` beyond 12. The single biggest unlock for replayability and game use.
12. **Narrative persona system** — named narrators with biases, perspectives, blind spots. Prompt engineering with structured context injection.
13. **World State API** — expose as a Python library, not just CLI. `from chronicler import World; w = World(seed=42); w.simulate()`. Unlocks game integration and programmatic use.
14. **Paradox-style event hooks** — externalize event triggers and effects into declarative YAML. Expose on_action hooks at phase boundaries. Makes Chronicler moddable.
15. **DF-compatible Legends export** — transform bundle to DF XML schema for LegendsViewer compatibility.

### Tier 4: Future phases (months)
16. **Naval & maritime systems** — ocean traversal, maritime trade, piracy, naval warfare, island civs
17. **Language generation** — procedural naming with cultural consistency, language drift, creoles
18. **Education/knowledge system** — literacy, libraries, compounding knowledge, dark age mechanics
19. **Combinatorial tech innovation** — adjacent possible, prerequisite knowledge, cross-cultural recombination
20. **Game engine export formats** — Tiled JSON, heightmap PNG, GeoJSON, SQLite

### Lower Priority (nice to have, no rush)
21. **Espionage system** — overlaps with Phase 9 info asymmetry
22. **Art/literature production** — overlaps with Phase 7 artifacts
23. **Era-adaptive narration voice** — polish
24. **Scenario generator from natural language** — `--generate-scenario "Silk Road era..."` — LLM-dependent quality
25. **Multiple perspectives** (`--perspectives 3`) — same history from conqueror vs conquered viewpoint

---

## Research Findings

### World Generation — What Other Games Expose

**Dwarf Fortress** (`world_gen.txt`): The gold standard. Key parameters: `WORLD_SIZE` (1-5 scale), terrain roughness (inverted as "world age" — young=rough, old=flat), mineral scarcity, number of civilizations, megabeast/titan caps, history length (`END_YEAR`). DF generates worlds of 1000+ years with thousands of historical figures, then exports as XML with cross-referenced entity IDs.

**Stellaris**: Galaxy size, habitable worlds percentage, AI aggressiveness (0.25x-5x), tech/tradition cost (0.25x-5x), crisis strength, mid-game/end-game start year. Key insight: compound presets bundle related settings.

**Civilization VI**: Map type (pangaea/continents/archipelago/etc.), world age (affects mountain density), temperature, rainfall, sea level, resource abundance (sparse/standard/abundant). These are simple enum/float knobs that weight existing generation.

**Shadow Empire**: Full planet generation — distance from sun, axial tilt, planet size, atmosphere composition, tectonic activity. Probably the deepest procedural geography in a strategy game.

**Implementation tiers for Chronicler:**
- **Tier 1 (pure multipliers):** `--resource-abundance`, `--severity-multiplier`, `--aggression-bias`, `--tech-diffusion-rate` — wire directly into existing code paths
- **Tier 2 (weighted template selection):** `--terrain-roughness`, `--temperature`, `--rainfall`, `--mineral-density` — modify `generate_regions()` to use weighted sampling instead of sequential draw
- **Tier 3 (new generation systems):** `--geo-method=noise/tectonics`, procedural regions beyond 12 templates — requires replacing the template pool entirely

### Narrative Output — How Others Present Generated History

**DF Legends XML structure:**
- `<regions>`, `<sites>`, `<entities>`, `<historical_figures>`, `<artifacts>`, `<historical_events>`, `<historical_event_collections>`
- Events are typed with cross-references to entity IDs — the proven interchange schema for procedural history
- Community tool **LegendsViewer** reprocesses XML into an HTML wiki with hyperlinked pages per figure/site/entity/war

**Chronicler's bundle is already close to this.** Main additions needed: formalize a public schema with versioning, ensure every event cross-references stable entity IDs.

**Academic research (event log → narrative):** Two-stage pipeline: (1) content determination (filter non-relevant events), (2) discourse planning (organize parallel threads into linear narrative). This maps directly to Chronicler's curator → narrator pipeline.

**BookWorld (ACL 2025):** Multi-agent simulation where simulation histories are woven together and polished by LLMs into novel-style narratives. 75.36% win rate over prior methods. Key pattern: structured scene logs + LLM narrative polish as separate pass — exactly Chronicler's architecture.

**Presentation formats in practice:**
- Chronicle/annals: year-by-year, terse. Oldest form.
- Chapbook: short focused narratives around a single dramatic arc (2-5 pages each)
- Encyclopedia: per-entity entries with cross-references
- Epistolary: fake letters, decrees, diary entries written "by" historical figures

**TTRPG needs (from WorldAnvil, Kanka, LegendKeeper, donjon feedback):**
- Must-have: NPC dossiers, settlement profiles, faction briefs, regional overview, encounter tables, random tables
- Sweet spot: "summary first, detail on demand" — one-page faction brief is useful, ten-page history is not (unless drilled into)
- Relationship webs and filterable timelines are the most-requested features DMs don't currently get from generators

### Game Integration — Patterns That Work

**Pattern 1: Generate-then-play.** Dominant pattern. Simulation runs to completion, serializes output, game loads it. No live simulation-as-backend exists. DF world gen → fortress/adventure mode. Caves of Qud world gen → gameplay.

**Pattern 2: DF-style Legends Export.** Flat event lists with typed events and entity cross-references. Chronicler's bundle JSON is already structurally similar.

**Pattern 3: Paradox-style Event Hooks.** CK3 exposes three primitives: triggers (boolean conditions), effects (state mutations), scopes (entity selection). Events are the primary extension point. To make Chronicler moddable: externalize event trigger conditions and effects into declarative JSON/YAML, expose on_action hooks at phase boundaries.

**Pattern 4: Caves of Qud-style Discoverable History.** History embedded in game world as discoverable artifacts — inscriptions, rumors, chronicles tagged with location, era, reliability. Player reconstructs history through exploration.

**Pattern 5: PersistentDM-style Context Assembly.** For LLM-powered games: semantic search over events + entity lookup by ID. Game queries "what happened in Region X between turns 50-75?" and gets relevant events formatted for LLM consumption.

**The empty niche:** Physical world generation has libraries (WorldEngine). 3D environment generation has APIs (World Labs). Procedural *history* generation with civilizations, wars, cultures, economies, and political dynamics has no API/service offering. Chronicler occupies an empty market position.

### Specific Additions from Research

**Parameters to add immediately (Tier 1 — pure multipliers on existing systems):**

| Flag | Type | Default | Maps To |
|------|------|---------|---------|
| `--aggression-bias` | float 0.0-1.0 | 0.5 | WAR/EXPAND weight shift in action_engine.py |
| `--tech-diffusion-rate` | float 0.25-4.0 | 1.0 | Tech spread probability multiplier |
| `--resource-abundance` | float 0.25-4.0 | 1.0 | Global RegionGoods production multiplier |
| `--trade-friction` | float 0.0-1.0 | 0.3 | Base trade route cost in economy.py |
| `--severity-multiplier` | float 0.5-2.0 | 1.0 | Global M18 severity scaling |
| `--cultural-drift-speed` | float 0.25-4.0 | 1.0 | Value drift multiplier in culture tick |
| `--religion-intensity` | float 0.0-1.0 | 0.5 | Religious event frequency scaling |
| `--secession-likelihood` | float 0.0-1.0 | 0.5 | Secession check weight in politics.py |

These are trivially implementable — each is a scalar multiplier on an existing code path. Can be exposed as CLI flags AND as scenario YAML fields AND as tuning overrides, using the existing `tuning_overrides` mechanism.

**Presets to add (compound parameter bundles):**

| Preset | Key Overrides | Theme |
|--------|--------------|-------|
| `--preset=pangaea` | continent-count=1, trade-friction=0.1 | Single landmass, easy trade, constant conflict |
| `--preset=archipelago` | continent-count=4, trade-friction=0.7 | Isolated islands, slow tech diffusion |
| `--preset=ice-age` | temperature=cold, famine-frequency=0.8, severity=1.5 | Harsh survival, population pressure |
| `--preset=golden-age` | resource-abundance=2.0, aggression-bias=0.2, tech-diffusion=2.0 | Prosperity, fast advancement |
| `--preset=dark-age` | severity=1.5, plague=0.8, secession=0.8 | Collapse, fragmentation, recovery |
| `--preset=silk-road` | trade-friction=0.1, cultural-drift=2.0, resource-clustering=0.8 | Trade-focused, cultural exchange |

**Export formats to add:**

| Format | Implementation | Use Case |
|--------|---------------|----------|
| Timeline JSON | Extract from bundle, structured event list | Visualization tools, web apps |
| Encyclopedia Markdown | LLM pass over bundle per-entity | TTRPG, world bible, wiki |
| Genealogy JSON | Extract from dynasty/GreatPerson data | Family tree visualizers |
| Faction Sheets | LLM-generated one-pagers per civ | TTRPG campaign prep |
| DF-compatible XML | Transform bundle to DF Legends schema | LegendsViewer compatibility |
| GeoJSON | Region boundaries + properties | Web map visualization |
