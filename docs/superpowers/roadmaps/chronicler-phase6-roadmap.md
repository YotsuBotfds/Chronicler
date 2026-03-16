# Chronicler Phase 6 Roadmap — Living Society

> **Status:** Draft. Pending Phoebe architectural review.
>
> **Phase 5 prerequisite:** All M25–M31 milestones landed. Oracle gate passed (M28). Agent narrative calibrated (M31). Performance targets met (M29).
>
> **Toolchain:** Same as Phase 5 — Python 3.12, Rust stable, pyo3-arrow, jemalloc (cfg-gated). Phase 6 adds `anthropic` SDK as optional dependency for API narration.

---

## Why Living Society

Phase 5 introduced agents as individual actors making isolated decisions. They rebel, migrate, switch occupations, and drift loyalty — but they don't know each other. A farmer in the river valley has no relationship to the soldier on the frontier. A merchant's wealth is invisible. A child inherits nothing from their parent. The land itself is abstract — soil and water, but no wheat fields, no iron mines, no river trade.

Phase 6 transforms agents from population units into members of a society living in a material world. Five capabilities that isolated agents on abstract terrain structurally cannot deliver:

1. **Material geography.** Regions produce specific goods — wheat, iron, spices, timber. Rivers connect distant regions as trade corridors. Minerals deplete, creating boom-bust cycles. Seasonal weather shapes harvests. Endemic disease creates ongoing demographic pressure. The land is no longer a set of numbers — it's a place with character.

2. **Social structure.** Families, mentors, rivals. A dynasty of bold generals spanning three generations. An exile community that resists cultural assimilation. A merchant's apprentice who surpasses her mentor. These relationships turn named characters from data points into narrative arcs.

3. **Cultural and religious heterogeneity.** Phase 5 agents have `civ_affinity` but no cultural identity or faith. Culture and religion are still aggregate numbers on the Civilization model. Phase 6 gives agents individual cultural values and religious beliefs that drift based on neighbors, trade contact, and satisfaction. Assimilation becomes bottom-up. Schisms split civilizations. Holy wars erupt from doctrinal opposition.

4. **Emergent economic class.** Phase 5 agents have occupations but no wealth. Economy is a number, not a distribution. Phase 6 adds personal wealth accumulation driven by specific goods production and trade. Merchants in undersupplied regions get rich. Class stratification emerges from individual economic outcomes. Supply chains connect regions into economic networks where a drought in the wheat heartland cascades into famine in trade-dependent cities.

5. **Supply chain economics.** Goods flow along trade routes with transport costs, perishability, and stockpiles. Food trade stays local; luxury trade crosses continents. Trade dependency creates strategic vulnerability. Embargo cuts supply lines. The economy becomes a simulation within the simulation.

If Phase 5 made Chronicler a simulation with people in it, Phase 6 makes it a simulation of a *society in a material world*.

**Hardware:** Same 9950X + 4090 setup. Agent count target increases to 10K–50K as systems mature (M29 headroom supports this). Phase 6 adds ~24 bytes/agent for personality, cultural identity, belief, wealth, and family — pool size from ~44 to ~68 bytes/agent. Per-region at 500 agents = 34KB, comfortably within L1 cache (64KB per core).

---

## Design Decisions (Open — Pending Review)

### Decision 1: Utility-Based Decisions Replace Short-Circuit

Phase 5 uses priority-ordered short-circuit (rebel → migrate → switch → drift). Phase 6 replaces this with weighted utility selection: each action computes a continuous utility score, agent picks `argmax(utility + noise)`.

**Rationale:** Short-circuit creates artificial priority. A farmer at both the rebellion and migration thresholds always rebels, never migrates — even if migration would be the rational choice. Utility selection lets relative urgency determine behavior.

**Backward compatibility:** The short-circuit model is the degenerate case of utility selection (infinite weight gaps between priority levels). With appropriate weights, Phase 6 agents should approximate Phase 5 behavior. A regression test verifies this.

**Validation impact:** Utility selection increases behavioral variance. The Phase 5 oracle gate compared agent distributions to aggregate. Phase 6 shifts to internal consistency validation — bold agents rebel more, cautious agents migrate more, neutral agents approximate Phase 5 behavior.

### Decision 2: Personality Is Three Floats, Not Categorical

Three continuous dimensions [-1, +1] rather than discrete categories (bold/cautious/greedy). Continuous values enable inheritance with noise, smooth gradients in utility modification, and avoid artificial clustering. Named characters get narrative labels derived from their strongest dimension.

### Decision 3: Family Only, No Marriage Model

Parent-child lineage via single-parent recording. No spousal relationships, no marriage market, no household economics. Family is the cheapest relationship type with the highest narrative ROI (dynasty arcs). Marriage adds complexity with diminishing narrative returns — defer to Phase 7 if needed.

### Decision 4: Social Networks Are Named-Character Only

Regular agents don't form mentor/rival/exile bonds. Only named characters (max 50 per run) participate in the social graph. This bounds the edge count to ~500 max and keeps per-tick cost negligible. The narrative pipeline only references named characters anyway.

### Decision 5: API Narration Is Optional, Not Default

`--narrator api` flag switches to Claude Sonnet 4.6. Local LLM remains the default (`--narrator local`). No API dependency for core simulation. Cost is low (~20-30K tokens per 500-turn run) but non-zero — users control when they pay.

### Decision 6: Viewer Integration Is One Milestone, Last

All deferred viewer work from Phases 3-6 ships in a single consolidated milestone. This prevents rework from subsequent milestones changing what's worth displaying. The viewer milestone captures everything at once.

### Decision 7: Environment Before Culture Before Religion

Regional resources and seasons define the material world first (M34-M35). Cultural identity develops on that terrain (M36). Religion layers on cultural identity as a belief system with institutional power (M37-M38). Family inherits all three layers simultaneously (M39). This ordering ensures each system has the substrate it needs.

### Decision 8: Supply Chains Extend Existing Trade Routes

The existing trade route system (adjacency-based, disposition-gated, embargo-capable) becomes the transport layer for goods. Supply chains don't replace trade routes — they add cargo to them. Goods production (M42) feeds into trade routes; transport costs and perishability (M43) make geography matter.

### Decision 9: Religion Is a Fourth Faction, Not a Value Dimension

Religion gets institutional power (temples, clergy influence, tithes) and its own faction weight competing with military/merchant/cultural. This is stronger than treating religion as another cultural value — it creates political tension between secular and religious authority, which is a primary driver of civilizational history.

---

## M32: Utility-Based Decision Model

**Goal:** Replace the short-circuit decision priority with weighted utility selection. Each action computes a utility score; agents choose the highest-utility action with noise.

### Utility Functions

One function per action type. Inputs are agent state (satisfaction, loyalty, occupation, skill, region context) + personality modifiers (Phase 6 adds personality in M33, but M32 uses neutral personality [0,0,0] for all agents).

| Action | Utility Inputs | Short-Circuit Equivalent |
|--------|---------------|-------------------------|
| Rebel | Low loyalty, low satisfaction, cohort size, contested region | loyalty < 0.2 AND satisfaction < 0.2 AND cohort ≥ 5 |
| Migrate | Low satisfaction, adjacent region quality delta, hysteresis | satisfaction < 0.3 AND adjacent better by 0.05 |
| Switch Occupation | Oversupply ratio, undersupply opportunity, skill level | supply > demand × 2.0 AND undersupply exists |
| Loyalty Drift | Satisfaction delta from civ mean, loyalty distance from threshold | Continuous drift / hard flip at 0.3 |
| Stay | Base utility (inertia) | Default when nothing triggers |

Each function returns a float. Agent picks `argmax(utility + noise)` where noise is scaled by `DECISION_NOISE` constant `[CALIBRATE]`.

### Noise Model

Gumbel noise for `argmax` selection (equivalent to softmax with temperature). Temperature parameter `DECISION_TEMPERATURE` controls exploration vs exploitation. High temperature = more random; low temperature ≈ deterministic (approaches short-circuit behavior).

### Validation

- **Regression test:** With `DECISION_TEMPERATURE → 0` and utility weights matching Phase 5 thresholds, behavior should approximate Phase 5 short-circuit within statistical tolerance.
- **Shadow comparison:** Run 200 seeds in utility mode vs Phase 5 mode. Document divergences. Correlation structure (military/economy, culture/stability) should hold even if distributions shift.

### Deliverables

- Modified `behavior.rs`: utility functions replace `decide_for_agent()`
- Constants in `agent.rs`: utility weights, noise parameters
- Regression test: utility-with-extreme-weights ≈ short-circuit
- Shadow comparison report (200 seeds)

---

## M33: Agent Personality

**Goal:** Add a personality trait vector that modifies utility weights, creating behaviorally diverse agents.

### Personality Dimensions

Three continuous floats, each in [-1.0, +1.0]:

| Dimension | -1.0 | +1.0 | Utility Effect |
|-----------|------|------|---------------|
| Boldness | Cautious — avoids risk | Bold — seeks conflict | Multiplier on rebel and migrate utility |
| Ambition | Content — stays put | Ambitious — seeks advancement | Multiplier on occupation switch utility |
| Loyalty | Mercenary — drifts easily | Steadfast — resists change | Divisor on loyalty drift utility |

### Storage

3 × f32 = 12 bytes per agent. Pool size: ~44 → ~56 bytes.

### Assignment

- **At spawn (no family):** Random from civ-level personality distribution. Each civ gets a mean personality vector (derived from civ values/domains at world gen) with per-agent noise.
- **At birth (with family, M39):** Inherited from parent with N(0, 0.15) noise per dimension. Clamped to [-1.0, +1.0].

### Named Character Integration

Named characters include personality in their narration context. The narrator receives descriptive labels derived from the dominant dimension:

| Strongest Dimension | Label |
|-------------------|-------|
| Bold > 0.5 | "the Bold" / "reckless" |
| Bold < -0.5 | "the Cautious" / "wary" |
| Ambitious > 0.5 | "the Ambitious" / "driven" |
| Ambitious < -0.5 | "the Humble" / "content" |
| Loyal > 0.5 | "the Steadfast" / "loyal" |
| Loyal < -0.5 | "the Fickle" / "mercenary" |

Neutral personalities (all dimensions near 0) get no label.

### Validation

- **Distribution check:** Personality dimensions remain normally distributed across population after 500 turns (no collapse to extremes).
- **Behavioral correlation:** Bold agents rebel at higher rates than cautious agents (measurable from event counts partitioned by personality).
- **Regression:** Agents with personality [0,0,0] approximate Phase 5 / M32-neutral behavior.

### Deliverables

- New SoA fields in `pool.rs`: `boldness`, `ambition`, `loyalty_trait` (3 × `Vec<f32>`)
- Modified utility functions in `behavior.rs`: personality multipliers
- Personality assignment in `demographics.rs` (spawn) and `tick.rs` (birth, post-M39)
- Named character personality in promotion RecordBatch
- Tests: distribution stability, behavioral correlation, neutral regression

---

## M34: Regional Resources & Seasons

**Goal:** Replace abstract soil/water ecology with specific crop and mineral resources per region, and add a seasonal cycle that shapes yields, demographics, and agent behavior.

### Regional Resource Model

Each region gets 1–3 resources at world gen, determined by terrain + ecology:

| Terrain | Crops | Minerals | Special |
|---------|-------|----------|---------|
| Plains | Wheat, barley | — | Breadbasket regions |
| Forest | Timber, herbs | — | Lumber trade |
| Mountains | — | Iron, copper, silver | Mining economy |
| Coast | Fish, salt | — | Port access |
| Desert | Dates, spices | Gold | Caravan trade |
| Tundra | — | Furs | Subsistence only |

Each resource is a struct: `(type_id: u8, base_yield: f32, current_yield: f32, reserves: f32)`. Crops are renewable (yield fluctuates with ecology); minerals deplete (`reserves` drops with extraction, exhausted below 0.1 — output falls to 10% of base).

Mineral depletion creates boom-bust cycles: a silver strike draws population, the region booms for 50-100 turns, the mine depletes, the economy collapses, population migrates to the next opportunity.

### Resource Type Registry

Global enum in Rust, max 16 resource types (fits in u8 with room):

```
Wheat=0, Barley=1, Timber=2, Herbs=3, Fish=4, Salt=5,
Iron=6, Copper=7, Silver=8, Gold=9, Dates=10, Spices=11, Furs=12
```

Good categories derived from resource type:
- **Food:** Wheat, barley, fish, dates (perishable, local demand)
- **Raw materials:** Timber, iron, copper, furs (durable, construction/military demand)
- **Luxury:** Silver, gold, spices, herbs (durable, high value, long-distance)
- **Preservative:** Salt (extends food shelf life in stockpiles)

### Seasonal Cycle

12-step cycle layered on existing climate phases:

| Season | Turns (mod 12) | Effects |
|--------|---------------|---------|
| Spring | 0–2 | Planting: +soil recovery, +birth rate modifier |
| Summer | 3–5 | Peak yield, peak water demand, drought risk |
| Autumn | 6–8 | Harvest: trade peak, stockpile accumulation |
| Winter | 9–11 | Reduced yields, +mortality modifier, migration pressure |

Climate phase modifies the seasonal baseline: a drought-phase summer is devastating (water demand peaks while supply drops), a temperate-phase winter is mild. This creates ~48-turn macro cycles (4 climate phases × 12 seasonal steps) that shape long-term civilizational rhythms.

### Crop Yield Formula

```
current_yield = base_yield × soil_factor × water_factor × season_modifier × climate_modifier
```

Failed harvests (yield < `FAMINE_YIELD_THRESHOLD` `[CALIBRATE]`) create famine pressure on agent satisfaction. Surplus creates trade goods for M42.

### Mineral Extraction

```
extraction_rate = base_yield × miner_count / target_miner_count
reserves -= extraction_rate × DEPLETION_RATE [CALIBRATE]
if reserves < 0.1: current_yield = base_yield × 0.1  // exhausted
```

Miner count = agents in region with occupation matching resource type (farmer for crops, soldier proximity for mines needing protection). Extraction rate scales linearly with workforce up to a cap.

### Rust-Side Changes

`RegionState` gains new fields:

```rust
pub resource_types: [u8; 3],      // up to 3 resource IDs (0 = empty slot)
pub resource_yields: [f32; 3],    // current per-resource yield
pub resource_reserves: [f32; 3],  // mineral depletion (1.0 = full, 0.0 = gone)
pub season: u8,                   // 0-11 seasonal position
pub climate_phase: u8,            // 0-3 drought/temperate/cooling/warming
```

### Agent Integration

- Farmer satisfaction reads crop yields instead of abstract soil quality
- Merchant satisfaction reads trade good availability
- Occupation demand shifts based on regional production: mining region → more soldiers (protection), more merchants (trade); agricultural region → more farmers
- `satisfaction.rs` reads `resource_yields` from RegionState
- Utility weights (M32) factor in resource context: migrate utility increases when local yields collapse

### Validation

- **Resource distribution:** All terrain types produce resources consistent with their ecology. No empty regions.
- **Seasonal variation:** Crop yields fluctuate ±30% across seasons. Winter mortality > summer mortality.
- **Depletion:** Mineral regions that start rich reach exhaustion within 80-150 turns at full exploitation.
- **Regression:** `--agents=off` mode uses resource yields to modify existing economy calculations without changing aggregate behavior.

### Deliverables

- Resource type enum and per-region resource assignment at world gen (Python: `simulation.py`)
- Seasonal cycle integrated into ecology tick (Python: `ecology.py`)
- Crop yield and mineral extraction formulas (Python: `ecology.py`)
- Extended `RegionState` with resource/season fields (Rust: `region.rs`)
- Satisfaction formula updates reading resource yields (Rust: `satisfaction.rs`)
- Tests: resource distribution, seasonal variation, depletion curves, regression

---

## M35: Rivers, Disease & Environmental Events

**Goal:** Add river systems as trade/migration corridors, endemic disease as ongoing demographic pressure, resource depletion feedback loops, and environmental events that disrupt regional economies.

### River Systems

Rivers as a second adjacency layer connecting non-neighboring regions:

- **River adjacency:** Stored as `river_mask: u32` on RegionState (separate from terrain adjacency). Assigned at world gen — scenarios define river paths through 3-8 connected regions.
- **River region bonuses:** +0.15 water baseline, fish resource if not already present, +20% carrying capacity.
- **Trade corridors:** Trade routes along rivers get 0.5× transport cost (M43). This makes river regions natural trade hubs.
- **Migration corridors:** Migration along rivers has reduced utility threshold — agents prefer following waterways.
- **Upstream-downstream coupling:** Deforestation (forest_cover < 0.2) in an upstream river region → water loss (-0.05/turn) in downstream regions. Creates cascading ecology where mismanagement upstream devastates downstream.

### Endemic Disease

Persistent per-region disease state, replacing one-time black swans with ongoing demographic pressure:

| Climate Zone | Endemic Vector | Base Severity |
|-------------|---------------|---------------|
| Tropical (water > 0.6 AND soil > 0.5) | Fever | 0.03 mortality modifier |
| Temperate (population > 70% capacity) | Plague | 0.02 mortality modifier |
| Arid (water < 0.3) | Cholera | 0.025 mortality modifier |

Disease severity modified by:
- **Population density:** Higher density = higher severity (overcrowding)
- **Water quality:** Low water increases cholera risk; high stagnant water increases fever risk
- **Trade contact:** More trade routes = more disease exposure (pathogen import)
- **Season:** Summer peaks for fever, winter peaks for plague
- **Army movement:** Soldiers moving between regions carry disease (+0.01 severity per military migration event)

Agent mortality in `demographics.rs` reads regional disease severity as an additive term on the base mortality rate. Existing M18 pandemic black swans become acute spikes (severity 0.10-0.20) on top of the endemic baseline (0.02-0.03).

### Resource Depletion Feedback

- **Monoculture penalty:** Region producing only 1 crop type for 50+ consecutive turns → soil degradation rate doubles. Crop rotation (2+ crop types) → 0.5× degradation rate.
- **Deforestation cascade:** Forest loss in upstream river region → water loss downstream (described above).
- **Overgrazing/overfishing:** If extraction rate exceeds sustainable yield for 20+ turns, base_yield permanently decreases by 10%. Creates irreversible environmental damage.

### Environmental Events

New events integrated into emergence system:

| Event | Trigger | Effect | Duration |
|-------|---------|--------|----------|
| Locust swarm | Plains/desert, summer, crop yield > 0.5 | Crop yield → 0 in target region | 3-5 turns |
| Flood | River region, spring, water > 0.8 | Destroy infrastructure; +0.2 soil (silt deposit) | 1 turn |
| Mine collapse | Mountain region, reserves < 0.3 | Extraction halved; 5-10 agent deaths | 10 turns |
| Drought intensification | Existing drought phase + summer | Carry capacity halved temporarily | 6 turns |

### Rust-Side Changes

`RegionState` gains:

```rust
pub river_mask: u32,              // river adjacency bitmask
pub disease_severity: f32,        // 0.0-1.0 endemic disease level
```

(Resource reserves already added in M34.)

### Validation

- **River geography:** River regions have higher water, carrying capacity, and trade value than non-river neighbors.
- **Disease demographics:** Regions with high endemic severity show 2-5% higher mortality than clean regions over 500 turns.
- **Depletion:** Monoculture regions degrade faster than diversified regions (measurable soil difference after 100 turns).
- **Cascading effects:** Upstream deforestation produces measurable water loss in downstream river regions.

### Deliverables

- River system definition in scenario format + world gen assignment
- Endemic disease computation in ecology tick (Python: `ecology.py`)
- Disease severity on RegionState (Rust: `region.rs`)
- Mortality modifier integration (Rust: `demographics.rs`)
- Environmental events in emergence system (Python: `emergence.py`)
- Monoculture/deforestation feedback loops (Python: `ecology.py`)
- Tests: river bonuses, disease demographics, depletion feedback, cascading ecology

---

## M36: Cultural Identity

**Goal:** Give agents individual cultural values that drift based on neighbors and environment, replacing aggregate-only cultural mechanics.

### Cultural Values Per Agent

Each agent stores 3 cultural value indices as `u8`, matching the civ-level VALUES enum from M16 (Freedom, Order, Tradition, Knowledge, Honor, Cunning, etc.). At spawn, agents inherit their civ's cultural values.

Storage: 3 × u8 = 3 bytes per agent. Pool size: ~56 → ~59 bytes.

### Cultural Drift

Per-tick probability of adopting a neighboring agent's value (within same region):

- Base drift rate: `CULTURAL_DRIFT_RATE` `[CALIBRATE]`
- Modified by: satisfaction (dissatisfied agents drift faster), foreign_control_turns (occupied regions drift faster), trade contact (merchants drift faster)
- Drift target: randomly sampled from agents in same region with different values, weighted by proximity and influence (named characters have higher cultural influence)
- **Environmental shaping (M34):** Agents in resource-rich regions drift toward Prosperity/Trade values. Agents in harsh terrain drift toward Honor/Self-reliance values. The land shapes the culture.

### Integration with Existing Culture System

- **`tick_cultural_assimilation()` in culture.py:** Currently uses `foreign_control_turns` threshold (15 turns → flip). Phase 6 replaces this: a region's `cultural_identity` flips when >60% of agents hold the controller's cultural values. The timer becomes a guideline, not a trigger.
- **Memetic warfare (M16):** `INVEST_CULTURE` action shifts agent cultural values in the target region (propaganda). More effective than organic drift but agents can resist based on loyalty.
- **Value drift disposition effects:** The aggregate `apply_value_drift()` reads agent cultural distribution to compute shared/opposing value counts between civs. Bottom-up disposition influence.

### Narrative Integration

Named characters include their cultural values in narration context. Cultural mismatch between a character and their civ creates narrative tension: "Kiran, who had long adopted Kethani customs, found herself defending Aramean borders."

### Validation

- **Geographic clustering:** Cultural values cluster by region and adjacency, not randomly. Measure spatial autocorrelation.
- **Environmental correlation:** River trade regions show more cultural diversity than isolated mountain regions.
- **Drift rate sanity:** With no external pressure, cultural homogeneity within a civ is maintained. With conquest pressure, occupied regions drift toward conqueror culture at reasonable rates (not instant, not never).
- **Regression:** `tick_cultural_assimilation()` produces equivalent outcomes for the same scenarios as Phase 5 (within tolerance).

### Deliverables

- New SoA fields in `pool.rs`: `cultural_values` (3 × `Vec<u8>`)
- Cultural drift logic in new `culture_tick.rs` module
- Environmental shaping of drift targets
- Modified `culture.py`: agent-driven assimilation replaces timer-based
- Agent cultural values in signals (FFI extension for value distribution per region)
- Tests: geographic clustering, environmental correlation, drift rate, regression

---

## M37: Belief Systems & Conversion

**Goal:** Add a religion system where agents hold individual beliefs with doctrines that drive conversion, holy war, and cultural conflict.

### Agent Religious Identity

Each agent gets `belief: u8` — index into a global belief table (max 16 faiths). Faiths generated at world gen: each civ starts with 1 faith.

### Doctrine System

Each faith has 2-3 doctrine values from opposing pairs:

| Doctrine Axis | Pole A | Pole B |
|--------------|--------|--------|
| Theology | Monotheism | Polytheism |
| Ethics | Ascetic | Prosperity |
| Stance | Militant | Pacifist |
| Outreach | Proselytizing | Insular |
| Structure | Hierarchical | Egalitarian |

Each faith stores its doctrine positions as a `[i8; 5]` array (-1 / 0 / +1 per axis). Doctrine oppositions create natural conflict: a Militant/Monotheist faith has casus belli against Pacifist/Polytheist civilizations.

### Conversion Mechanics

Similar to cultural drift but priest-driven:

```
conversion_rate = BASE_RATE × priest_ratio × (1 + foreign_control) × satisfaction_gap
```

- **Proselytizing doctrine:** 2× outbound conversion rate
- **Insular doctrine:** 2× resistance to incoming conversion
- **Low satisfaction:** Higher susceptibility (seeking meaning in hardship)
- **Named character influence:** Named prophet/priest characters in region double conversion rate
- Conversion sets `life_events` bit for M30 promotion system

### Holy War

New casus belli for the action engine:

- Militant-doctrine civs gain +0.15 WAR action weight against opposing faiths
- Defending faith: +5 stability bonus (righteous defense)
- Victory in holy war: forced conversion of conquered region's agents (immediate belief flip for 30% of population, remainder drifts over 10-20 turns)
- Holy war generates named events (importance 7)

### Integration Points

- **Cultural identity (M36):** Religion and culture are separate dimensions. An agent can adopt a foreign culture while keeping their faith, or convert while retaining cultural values. The tension between cultural and religious identity creates rich narrative possibilities.
- **Utility (M32):** Holy war adds a utility modifier to WAR action. Persecution adds rebel utility modifier.
- **Satisfaction (Rust):** Same-faith-as-region-majority bonus (+0.05), different-faith penalty (-0.10). `[CALIBRATE]`

### Data Model

- **Pool:** `beliefs: Vec<u8>` — 1 byte per agent. Pool size: ~59 → ~60 bytes.
- **Python:** `Belief` dataclass with faith_id, name, civ_origin, doctrines. Global `belief_registry: list[Belief]` on WorldState.
- **Rust RegionState:** `majority_belief: u8` passed through FFI for satisfaction formula.

### Validation

- **Conversion rates:** Proselytizing faiths spread 1.5-2× faster than insular faiths.
- **Holy war frequency:** Militant-doctrine civs engage in 20-40% more wars than pacifist-doctrine civs.
- **Coexistence:** Multi-faith regions can persist stably when no strong conversion pressure exists.
- **Regression:** With all beliefs set to the same value and no doctrine effects, behavior approximates Phase 5.

### Deliverables

- Belief registry and faith generation at world gen (Python: `simulation.py`)
- New SoA field in `pool.rs`: `beliefs: Vec<u8>`
- Conversion mechanics in new `belief_tick.rs` module or Python bridge
- Holy war casus belli in action engine (Python: `action_engine.py`)
- Satisfaction modifier for religious alignment (Rust: `satisfaction.rs`)
- Tests: conversion rates, holy war frequency, coexistence stability, regression

---

## M38: Religious Institutions & Schisms

**Goal:** Add institutional religious power — temples, clergy political influence, schisms, pilgrimages, and persecution — making religion a political force, not just a cultural attribute.

### Temples

New infrastructure type in existing system:

- Built via BUILD action (10 treasury)
- **Effects:** Boost conversion rate in region (+50%), boost priest satisfaction (+0.10), generate +1 prestige/turn
- Destroyable in conquest (named event, importance 5)
- Max 1 temple per region, 3 per civ `[CALIBRATE]`

### Clergy as Fourth Faction

Priests gain political weight alongside military/merchant/cultural:

```
clergy_influence = sum(priest_loyalty × priest_count) / total_civ_population
```

High clergy influence modifies:
- **Succession:** Priest-favored candidates get clergy influence bonus
- **Action weights:** INVEST_CULTURE gains +20% weight at high clergy influence (religious propaganda)
- **Treasury:** Tithe mechanic — `TITHE_RATE × sum(merchant_wealth)` flows to treasury as religious tax. `[CALIBRATE]`
- **Faction competition:** Clergy competes with military/merchant/cultural for policy influence. Four-way faction tension creates richer political dynamics than three-way.

Faction influence normalization extends from 3 to 4 factions (0.08 floor per faction, sum to 1.0).

### Schisms

When agents within a civ hold divergent beliefs (>30% minority faith in any region):

1. **Schism event fires** (importance 7 named event)
2. Faith splits into two variants (new belief entry with modified doctrines)
3. Minority-doctrine regions face intensified conversion pressure from both sides
4. Schism increases secession risk in minority regions (+10 to secession check)
5. **Reformation:** If >60% of agents adopt the reformed variant, civ-level faith officially changes

Schisms create the conditions for civil war and secession — a region that holds a different faith from the capital has both religious and political motivation to break away.

### Pilgrimages

Named characters with high loyalty + priest occupation (or any occupation with Loyal > 0.5 personality) may pilgrimage:

- **Destination:** Highest-prestige temple region in their faith
- **Mechanism:** Migration event with special flag (not counted as displacement)
- **During pilgrimage:** Agent is in destination region, gains +0.15 satisfaction
- **Return (after 5-10 turns):** Skill boost (+0.1 to current occupation), potential Prophet bypass promotion trigger
- **Narrative:** Pilgrimage and return are named events (importance 4 and 5)

### Persecution

When a civ's dominant faith differs from a region's majority faith:

- **Persecution intensity:** `Militant_doctrine × (1 - minority_ratio)` — stronger doctrine + smaller minority = harsher persecution
- **Agent effects:** Persecuted agents get satisfaction penalty (-0.15), increased rebel utility (+0.3), increased migrate utility (+0.2)
- **Mass persecution:** If >20 agents persecuted in same region → mass migration event (refugee wave, importance 6)
- **Named event:** "Persecution of [faith] in [region]" (importance 6)
- **Death overrides:** Persecution deaths get special narrative treatment (martyrdom → increases convert rate for that faith post-mortem)

### Validation

- **Institutional power:** Civs with temples convert faster than those without. Clergy influence visible in succession outcomes.
- **Schism dynamics:** Schisms correlate with multi-region civs holding diverse populations. Small homogeneous civs rarely schism.
- **Persecution cascades:** Militant persecution of a minority produces observable migration waves and rebel spikes.
- **Pilgrimage frequency:** 1-3 pilgrimages per 500-turn run per faith. `[CALIBRATE]`

### Deliverables

- Temple infrastructure type (Python: `simulation.py`)
- Fourth faction (clergy) with influence normalization (Python: `factions.py`)
- Schism detection and faith splitting logic (Python: new `religion.py` or `culture.py` extension)
- Pilgrimage mechanics in agent bridge
- Persecution effects on satisfaction and utility
- Tests: institutional effects, schism triggers, persecution cascades, pilgrimage frequency

---

## M39: Family & Lineage

**Goal:** Track parent-child relationships and enable personality/culture/religion inheritance, dynasty detection, and family-aware narration.

### Data Model

One `u32` per agent: `parent_ids: Vec<u32>` in the SoA pool. Points to parent's `agent_id` (not slot index — stable across compaction). Value `0` = no parent (root agent, spawned at world gen).

Storage: 4 bytes per agent. Pool size: ~60 → ~64 bytes.

### Birth Integration

When a new agent is born in `demographics.rs`:
1. Record `parent_id = mother.agent_id`
2. Inherit personality from parent with noise: `child.personality[i] = clamp(parent.personality[i] + N(0, 0.15), -1.0, 1.0)` (requires M33)
3. Inherit cultural values from parent (not region — cultural identity follows family, not geography)
4. Inherit belief from parent (not region — religious identity follows family)

### Dynasty Detection

A **dynasty** forms when a named character's descendant (child or grandchild) is also promoted to named character. Dynasty tracking:

- `NamedCharacterRegistry` gains a `dynasty_id: Option<u32>` field
- On promotion: check if new character's `parent_id` chain (up to 2 generations) includes an existing named character. If yes, assign same `dynasty_id`.
- Dynasty events emitted to Python:
  - `dynasty_founding` — first parent-child named character pair (importance 6)
  - `dynasty_extinction` — last dynasty member dies (importance 5)
  - `dynasty_split` — dynasty members end up in different civs (importance 5)

### Narrative Integration

Dynasty context in `AgentContext`:

```python
{
    "name": "Sera",
    "dynasty": "House of Kiran",
    "dynasty_founder": "Kiran",
    "generation": 2,
    "parent": "Tala",
    "inherited_trait": "boldness",
    "inherited_faith": "Church of the One",
}
```

The narrator receives dynasty relationships explicitly: "Sera, granddaughter of Kiran the Bold, inherited her grandfather's recklessness — and his faith."

### Deliverables

- New SoA field in `pool.rs`: `parent_ids: Vec<u32>`
- Modified `demographics.rs`: parent recording + personality/culture/religion inheritance
- Dynasty detection in promotion logic (`tick.rs` or `named_characters.rs`)
- Dynasty events: founding, extinction, split
- `dynasty_id` on `NamedCharacterRegistry`
- Dynasty context in narration pipeline
- Tests: inheritance, dynasty detection, multi-generation tracking

---

## M40: Social Networks

**Goal:** Named characters form mentor, rival, exile-bond, and co-religionist relationships that influence behavior and narration.

### Relationship Types

| Type | Formation | Effect | Narrative |
|------|-----------|--------|-----------|
| Mentor/Apprentice | Same occupation, high/low skill, same region, 10+ turns | Apprentice skill growth +50% | "trained by [mentor]" |
| Rivalry | Opposite sides of rebellion, or competing occupation niche | Rivals in different civs boost war utility. Same civ: faction tension. | "[name], rival of [name]" |
| Exile Bond | Displaced agents sharing origin_region in same new region | Solidarity: cultural resistance to assimilation, slower drift | "the exile community from [region]" |
| Co-religionist | Named characters sharing minority faith in same region | Conversion resistance, mutual satisfaction bonus | "fellow believers" |

### Storage

Named-character-only graph. At most 50 named characters × ~10 edges each = ~500 edges max.

```rust
pub struct SocialGraph {
    edges: Vec<SocialEdge>,
}

pub struct SocialEdge {
    agent_a: u32,
    agent_b: u32,
    relationship: RelationshipType,  // u8: Mentor=0, Rival=1, ExileBond=2, CoReligionist=3
    formed_turn: u16,
}
```

~11 bytes per edge × 500 = ~5.5KB total. Negligible.

### Formation Logic

Runs in Python bridge after promotion processing (not every tick — only when named character state changes):

- **Mentor:** Newly promoted character spent 10+ turns in same region as existing named character with same occupation and higher skill.
- **Rival:** Shared rebellion (opposite sides) or consecutive promotions in same region with same occupation.
- **Exile Bond:** 2+ named characters share origin_region and are both currently displaced.
- **Co-religionist:** 2+ named characters share minority faith in a region where that faith is <30% of population.

### Narrative Integration

Social relationships appear in named character context:

```python
{
    "name": "Vesh",
    "relationships": [
        {"type": "apprentice_of", "target": "Kiran", "since_turn": 210},
        {"type": "rival", "target": "Maren", "context": "opposing sides in Bora rebellion"},
        {"type": "co_religionist", "target": "Sera", "context": "shared faith in polytheist minority"},
    ]
}
```

### Deliverables

- `SocialGraph` struct in new `social.rs` module
- Formation logic in Python bridge (post-promotion)
- Social graph query methods via FFI
- Relationship context in `AgentContext`
- Tests: formation conditions, edge limits, narrative context

---

## M41: Wealth & Markets

**Goal:** Add personal wealth accumulation per agent driven by specific resource production, creating emergent class stratification and economic tension.

### Wealth Model

One `f32` per agent: `wealth: Vec<f32>` in the SoA pool. Initial value: `STARTING_WEALTH` `[CALIBRATE: 0.5]`.

Storage: 4 bytes per agent. Pool size: ~64 → ~68 bytes.

### Accumulation

Per-tick wealth change based on occupation, resource context (M34), and market conditions:

| Occupation | Wealth Source | Rate |
|------------|-------------|------|
| Farmer | Crop yield × soil quality | `FARMER_INCOME × resource_yield` `[CALIBRATE]` |
| Soldier | War spoils (if region contested or civ at war) | `SOLDIER_SPOILS` if at_war, else 0 |
| Merchant | Trade route count × undersupply bonus × goods value | `MERCHANT_INCOME × (1 + undersupply_ratio) × goods_factor` |
| Scholar | Flat rate (institutional support) | `SCHOLAR_INCOME` `[CALIBRATE]` |
| Priest | Flat rate + satisfaction bonus + tithe share (M38) | `PRIEST_INCOME + mean_satisfaction × 0.5` |

Wealth decays by `WEALTH_DECAY` per turn (upkeep/consumption). Clamped to [0.0, `MAX_WEALTH`].

### Market Dynamics

Extend the existing per-region supply/demand occupation ratio with resource-specific pricing:

- Oversupplied resource: wealth growth reduced for producers (competition)
- Undersupplied resource: wealth growth increased (scarcity premium)
- **Resource-specific:** Farmer wealth depends on what they grow (wheat farmer in a wheat-surplus region earns less than a spice farmer in a spice-deficit region)
- Economic migration pressure through utility (M32): low-wealth agents have higher migrate utility toward regions with better economic opportunity

### Class Stratification

Per-civ Gini coefficient computed from agent wealth distribution (O(n log n) sort, once per turn per civ):

- High Gini (>0.6): rebellion utility boost for low-wealth agents. "The poor rebel against the rich."
- Very high Gini (>0.8): `class_tension` shock signal to satisfaction formula
- Gini reported in analytics and available in `AgentContext` for narration

### Treasury Integration

Civ-level treasury gains a tax component: `TAX_RATE × sum(merchant_wealth_in_civ)`. This replaces part of the aggregate income calculation in agent mode, making treasury partially agent-derived. War destruction reduces soldier wealth; famine reduces farmer wealth — these cascade into treasury via reduced tax base.

### Deliverables

- New SoA field in `pool.rs`: `wealth: Vec<f32>`
- Wealth accumulation/decay in `tick.rs` (new phase or added to existing)
- Resource-specific market dynamics modifier on wealth growth
- Gini coefficient computation (Rust-side, per-civ)
- Class tension signal through FFI
- Treasury integration in Python (`accumulator.py` modifications)
- Tests: wealth distribution shape, Gini bounds, tax/treasury integration

---

## M42: Goods Production & Trade

**Goal:** Regions produce specific goods from their resources; merchants carry goods along trade routes; supply and demand create prices that drive agent economic behavior.

### Goods Model

Each region produces goods based on its resources (M34):

| Resource | Good | Category | Properties |
|----------|------|----------|------------|
| Wheat, barley | Grain | Food | Perishable (5-turn shelf life) |
| Fish | Catch | Food | Perishable (3-turn shelf life) |
| Dates | Preserved food | Food | Semi-perishable (10-turn shelf life) |
| Timber | Lumber | Raw material | Durable |
| Iron, copper | Metal | Raw material | Durable |
| Furs | Pelts | Raw material | Durable |
| Silver, gold | Bullion | Luxury | Durable, high base value |
| Spices, herbs | Exotic goods | Luxury | Semi-perishable (15 turns), high value |
| Salt | Preservative | Special | Durable, extends food shelf life 2× |

Output per turn: `resource_yield × relevant_worker_count`. Worker count = agents in region with farmer occupation (for crops) or appropriate occupation for resource type.

### Merchant Carry Model

Merchants move goods along existing trade routes (already adjacency + disposition gated):

- Each merchant agent handles one unit of goods per turn
- Goods flow from surplus regions to deficit regions along trade routes
- **Arbitrage:** Merchant wealth gain = `price_at_destination - price_at_origin - transport_cost`
- Multiple merchants compete: first-come allocation from surplus pool

### Price Model

Per-region, per-good-category:

```
price = BASE_PRICE × (demand / max(supply, 0.1))
```

- **Food demand:** Proportional to population (every agent eats)
- **Raw material demand:** Proportional to military (weapons/armor) + active infrastructure projects
- **Luxury demand:** Proportional to wealthy agents (M41 wealth > threshold) + prestige score
- **Surplus:** production + imports - local_demand
- **Deficit:** local_demand - production - imports

Prices update each turn. High prices attract merchants (occupation switch incentive). Low prices repel them.

### Agent Integration

- **Merchant:** Satisfaction factors in trade profitability. Merchants in high-arbitrage positions (buying cheap, selling expensive) have high satisfaction and wealth growth.
- **Farmer:** Satisfaction factors in crop price. Surplus region + no merchant carrying → low price → unhappy farmers (they produce but can't sell).
- **Occupation switching:** Agents observe local prices and shift toward profitable occupations. High food prices → more farming. High metal prices → more mining.
- **New demand signal via FFI:** `goods_surplus` and `goods_deficit` per region per category.

### Storage

Per-region goods state in Python (not per-agent — goods are regional stockpiles):

```python
@dataclass
class RegionGoods:
    production: dict[str, float]    # good_type -> output this turn
    stockpile: dict[str, float]     # good_type -> accumulated surplus
    prices: dict[str, float]        # good_type -> current price
    imports: dict[str, float]       # good_type -> inbound this turn
    exports: dict[str, float]       # good_type -> outbound this turn
```

### Validation

- **Price responsiveness:** Surplus regions have lower prices than deficit regions for the same good.
- **Merchant behavior:** Merchants concentrate on high-margin routes (measurable from wealth accumulation by region pair).
- **Occupation response:** Food price spikes correlate with increased farmer count in subsequent turns.
- **No goods from nothing:** Total goods in system = sum of production - decay. Conservation law holds.

### Deliverables

- Goods model with production tied to M34 resources (Python: new `goods.py` or `economy.py`)
- Merchant carry model integrated with existing trade routes (Python: `simulation.py` Phase 2)
- Price computation per region per category
- Goods surplus/deficit signals through FFI
- Tests: price responsiveness, merchant behavior, occupation response, conservation

---

## M43: Transport, Perishability & Shock Propagation

**Goal:** Make geography matter for trade — transport costs create economic zones, perishability limits food trade range, stockpiles buffer shocks, and supply disruptions cascade through trade networks.

### Transport Costs

Moving goods between regions incurs cost based on terrain and infrastructure:

| Factor | Cost Modifier |
|--------|--------------|
| Base (per hop) | -10% goods value |
| Mountain hop | 2× base cost |
| River route (M35) | 0.5× base cost |
| Roads infrastructure | 0.7× base cost |
| Winter season (M34) | 1.5× base cost |
| Port-to-port (coast) | 0.6× base cost |

This creates economic geography: coastal and river regions become natural trade hubs. Inland mountain regions are isolated unless roads are built. Infrastructure investment has direct economic payoff.

### Perishability

Goods decay in stockpiles and during transport:

| Category | Shelf Life | Transport Decay |
|----------|-----------|----------------|
| Food (grain, catch) | 3-5 turns | -5% per hop |
| Semi-perishable (dates, spices) | 10-15 turns | -2% per hop |
| Durable (lumber, metal, bullion) | No decay | 0% |
| Salt preservation | Extends food shelf life 2× | — |

Result: food trade stays local (1-2 hops profitable). Luxury trade crosses continents. Salt becomes strategically valuable — a salt-producing region can extend the food trade radius of its neighbors. Realistic pattern: grain feeds the region, spices travel the silk road.

### Stockpiles

Regions accumulate surplus goods:

```
stockpile[good] = previous_stockpile × (1 - decay_rate) + current_surplus
```

- Buffer 1-2 turns of shortage (prevents immediate crisis from single bad harvest)
- Large food stockpiles attract raiders: +WAR utility for adjacent hostile civs when `stockpile[food] > RAIDER_THRESHOLD` `[CALIBRATE]`
- Salt in stockpile reduces food decay rate (halved)
- Stockpile destruction in conquest: 50% of stockpile lost when region changes hands

### Supply Shock Propagation

When a producing region's yield drops (drought, war, locust swarm, mine depletion):

1. **Turn 0:** Local production drops. Local price spikes. Stockpile begins depleting.
2. **Turn 1-2:** Stockpile exhausted. Local deficit appears. Import demand rises. Downstream regions that were importing from this region experience reduced supply.
3. **Turn 3+:** Shock propagates along trade routes at 1 hop per turn. Each hop attenuates the shock by 50%.
4. **Agent impact:** Satisfaction drops proportional to shortage severity. Farmer satisfaction drops if they can't sell (demand vanished). Merchant satisfaction drops if they can't source goods.

Cascading crisis example: drought in wheat heartland → crop failure → food prices spike → trade-dependent coastal cities can't import grain → famine satisfaction → migration wave → political instability → war → further supply disruption.

Supply shocks generate named events: "The Great Wheat Famine" (importance 7-8) with actors including named merchant characters who controlled the affected trade routes.

### Trade Dependency

Regions importing >60% of their food are "trade dependent":

- **Embargo vulnerability:** Satisfaction crash if trade route cut (no local production to fall back on)
- **Strategic target:** Attacking a trade-dependent region's supply route is as effective as attacking the region itself
- **Defensive responses:** Stockpiling (costs merchant labor), diversifying routes (requires multiple trade partners), conquering production regions
- **Narration:** Trade dependency status available in `AgentContext` for narration ("the city, wholly dependent on Aramean grain, watched the southern roads with dread")

### Validation

- **Geographic trade patterns:** Food trade concentrates in 1-2 hop radius. Luxury trade spans 3+ hops.
- **Salt value:** Salt-producing regions have higher trade value and attract more merchant agents.
- **Shock propagation:** A simulated drought produces measurable price spikes 2-3 hops away within 3-5 turns.
- **Trade dependency:** Embargoing a trade-dependent region produces satisfaction drop > 0.2 within 3 turns.
- **Stockpile buffer:** Regions with stockpiles survive 1-2 turn disruptions without satisfaction impact.

### Deliverables

- Transport cost computation based on terrain/infrastructure/season (Python: `goods.py`)
- Perishability model per good category
- Stockpile accumulation and decay
- Supply shock propagation along trade routes
- Trade dependency detection and embargo vulnerability
- Raider attraction from stockpiles (utility modifier)
- Tests: geographic trade patterns, salt economics, shock propagation, dependency vulnerability, stockpile buffer

---

## M44: API Narration Pipeline

**Goal:** Wire Claude Sonnet 4.6 as the primary narrator for curated chronicle moments, with local LLM as fallback.

### Architecture

`AnthropicClient` already exists in `narrative.py` as an optional class. M44 wires it into the production pipeline:

- `--narrator api` flag activates API narration (new CLI argument in `main.py`)
- `--narrator local` remains the default (backward compatible)
- `--narrator api --batch` queues all moments and processes them sequentially with inter-request context (previous entry's prose)

### Cost Model

- Curated moments per run: 10-20 (controlled by curator)
- Tokens per moment: ~2000 output, ~3000 input (NarrationContext + AgentContext + system prompt — larger now with material/religious detail)
- Per-run cost: ~30-50K tokens input + ~20-40K output ≈ $0.15-0.30 per 500-turn chronicle at Sonnet 4.6 pricing
- Batch mode (200 seeds × 500 turns): ~$30-60 total

### Implementation

1. Add `--narrator` argument to `_build_parser()` with choices `["local", "api"]`
2. In `NarrativeEngine.__init__()`: if `narrator == "api"`, instantiate `AnthropicClient`. Model: `claude-sonnet-4-6`.
3. Adapt `NarrationContext` serialization for API format (system prompt + user message). The existing `_build_prompt()` method produces the right content — just needs to target the API message format.
4. Previous-prose threading: pass `previous_prose` from the last narrated entry to the next API call, maintaining style continuity.

### Era Register Evaluation

Test whether the elaborate ERA_REGISTER system prompt instructions improve or constrain Claude's output. Claude may produce better era-appropriate prose with a lighter touch ("Write as a medieval chronicler" vs the detailed register instructions). Run A/B comparison on 10 seeds and document findings.

### Quality Comparison

20 seeds narrated with both local and API. Manual side-by-side review scoring:
- Prose quality (grammar, vocabulary, flow)
- Character continuity (named characters referenced correctly)
- Era-appropriate voice
- Emotional resonance
- Factual accuracy (does the prose match the events?)
- **Material detail:** Does the prose reference specific goods, trade routes, seasonal conditions?
- **Religious depth:** Do faith-driven events get appropriate theological framing?

### Deliverables

- `--narrator` CLI flag
- `AnthropicClient` wired as production narrator
- API message format adapter
- Era register A/B comparison report
- Quality comparison report (20 seeds)
- Cost documentation

---

## M45: Character Arc Tracking

**Goal:** Make the narrator aware of character arcs across the entire chronicle, enabling callbacks, thematic threading, and arc classification.

### Arc Summary

Per named character, maintain a running 2-3 sentence summary of their story. Stored on `GreatPerson` as `arc_summary: str | None`.

Updated after each narrated moment that references the character:
1. Extract character mentions from the narrated prose (name matching)
2. Append a one-sentence summary of what happened to them in this moment
3. Truncate to 3 sentences max (keep most recent)

### Arc Classification

Automatically tag character arcs based on event history patterns:

| Archetype | Pattern | Example |
|-----------|---------|---------|
| Rise-and-Fall | Promotion → high prestige → death/exile | General who conquered then fell |
| Exile-and-Return | Displacement → long exile → return to origin | Leader who returned to reclaim homeland |
| Dynasty Founder | Promotion → child promoted → dynasty formed | Matriarch whose line shaped a nation |
| Tragic Hero | Bold personality → rebellion → death in same region | Revolutionary who died for the cause |
| Wanderer | 3+ region changes → no permanent home | Merchant who never settled |
| Defector | Loyalty flip → serves new civ → named events in both | Spy, turncoat, or convert |
| Prophet | Religious conversion → pilgrimage → institutional power | Founder of a reformed faith |
| Martyr | Persecution → death → posthumous conversion spike | Believer whose death spread the faith |

Classification runs after each moment's narration. Archetype stored on `GreatPerson` as `arc_type: str | None`. Updated as new events occur (an arc can reclassify mid-chronicle).

### Narrator Context Enhancement

When a named character appears in a moment, the narrator receives:

```
Character: General Kiran (the Bold)
Arc: Rise-and-Fall
Faith: Church of the One (Monotheist, Militant)
Summary: Led the Bora rebellion and carved a new frontier. Rose to command Aram's
  northern armies. Now faces the coalition he provoked.
Last mentioned: Turn 340 ("Kiran's frontier holdings grew restless...")
```

### Curator Scoring Enhancement

Moments that continue an active character arc score higher:
- `+1.5` for moments referencing a character with an established arc (arc_summary exists)
- `+2.5` for moments that would complete an arc pattern (exile returns, dynasty forms, martyr dies)
- These stack with the existing `+2.0` character-reference bonus from M30

### Deliverables

- `arc_summary` and `arc_type` fields on `GreatPerson`
- Arc summary update logic in narration pipeline
- Arc classification module (pattern matching on event history)
- Prophet and Martyr archetypes (new, dependent on M37-M38)
- Enhanced curator scoring for arc continuation
- Narrator context with arc data
- Tests: arc classification patterns, summary truncation, curator scoring

---

## M46: Full Viewer Integration

**Goal:** One consolidated viewer milestone covering all deferred visual work from Phases 3-6.

### Phase 3-4 Backlog (~300 lines TS)

| Component | Feature | Source |
|-----------|---------|--------|
| CivPanel | Tech focus badge (icon + tooltip) | M21 deferred |
| CivPanel | Faction influence bar (four-segment: MIL/MER/CUL/CLR) | M22 + M38 |
| RegionMap | Ecology variables on hover (soil/water/forest progress bars) | M23 deferred |
| RegionMap | Intelligence quality indicator (confidence ring or fog overlay) | M24 deferred |

### Phase 5 Agent Data (~400 lines TS)

| Component | Feature | Source |
|-----------|---------|--------|
| RegionMap | Population heatmap (agent count, color by mean satisfaction) | M30 |
| RegionMap | Occupation distribution donut on region hover | M30 |
| TerritoryMap | Named character markers (icon + name label) | M30 |
| TerritoryMap | Migration flow arrows (aggregate direction/volume, 10-turn window) | M30 |

### Phase 6: Material World (~500 lines TS)

| Component | Feature | Source |
|-----------|---------|--------|
| RegionMap | Resource icons per region (crop/mineral/special) | M34 |
| RegionMap | Seasonal indicator (spring/summer/autumn/winter badge) | M34 |
| RegionMap | River overlay (blue lines connecting river-adjacent regions) | M35 |
| RegionMap | Disease severity heatmap layer (toggle) | M35 |
| RegionMap | Trade flow arrows (goods type + volume along routes) | M42-M43 |

### Phase 6: Society (~600 lines TS)

| Component | Feature | Source |
|-----------|---------|--------|
| CharacterPanel (new) | Personality radar chart (3 axes: boldness, ambition, loyalty) | M33 |
| CharacterPanel | Character arc timeline (horizontal, key events marked) | M45 |
| CharacterPanel | Family tree (vertical, max 3 generations) | M39 |
| CharacterPanel | Social network (d3-force mini-graph, relationships to other named chars) | M40 |
| CharacterPanel | Religious identity + faith icon | M37-M38 |
| RegionMap | Cultural identity overlay (color by dominant cultural values) | M36 |
| RegionMap | Religious majority overlay (color by dominant faith) | M37 |
| CivPanel | Wealth distribution histogram + Gini coefficient | M41 |
| CivPanel | Class tension indicator | M41 |
| CivPanel | Goods production/consumption balance | M42 |
| CivPanel | Trade dependency indicator | M43 |

### Bundle Schema

`bundle_version: 3` (Phase 6 additions):
- `named_characters` extended with personality, dynasty, faith, arc_type, relationships
- `agent_wealth_distribution` per-civ summary (histogram bins + Gini)
- `cultural_map` per-region cultural value distribution
- `religious_map` per-region faith distribution
- `goods_economy` per-region production, stockpiles, prices, trade flows
- `resource_map` per-region resource types and yields

### Estimated Scope

~1800-2200 lines TypeScript across 12-15 components. Largest single viewer milestone, but captures 4 phases of deferred work in one pass.

### Deliverables

- All Phase 3-4 viewer backlog items
- Material world visualizations (resources, rivers, disease, seasons, trade flows)
- Agent visualization components (heatmap, occupation, characters, migration)
- New CharacterPanel with personality, arc, family, social network, faith views
- Cultural, religious, and economic overlays
- `bundle_version: 3` schema
- Manual visual review across 5 sample bundles

---

## M47: Phase 6 Tuning Pass

**Goal:** Calibrate all Phase 6 constants and validate that the interconnected systems produce coherent, narratively rich outcomes.

### Calibration Targets

| Constant | Module | Initial | What to Check |
|----------|--------|---------|---------------|
| `DECISION_TEMPERATURE` | M32 | TBD | Behavioral diversity — too high = random, too low = deterministic |
| Utility weights (per action) | M32 | TBD | Action frequency distribution across 200 seeds |
| Personality weight multipliers | M33 | TBD | Bold agents rebel 2-3x more than cautious (not 10x, not 1x) |
| `FAMINE_YIELD_THRESHOLD` | M34 | TBD | Failed harvests occur 5-15% of turns in drought phases |
| `DEPLETION_RATE` | M34 | TBD | Rich mines last 80-150 turns at full exploitation |
| `DISEASE_BASE_SEVERITY` | M35 | 0.02-0.03 | Endemic disease adds 2-5% excess mortality |
| `CULTURAL_DRIFT_RATE` | M36 | TBD | Assimilation timeline matches Phase 5 within 2x |
| `CONVERSION_BASE_RATE` | M37 | TBD | Proselytizing faiths spread at 1.5-2x insular rate |
| Holy war WAR weight bonus | M37 | +0.15 | Militant civs engage in 20-40% more wars |
| `TITHE_RATE` | M38 | TBD | Clergy treasury contribution 5-15% of merchant wealth |
| Schism threshold | M38 | 30% minority | Schisms occur 1-3 per 500-turn run in diverse civs |
| Persecution intensity | M38 | TBD | Mass persecution produces observable migration waves |
| Dynasty detection depth | M39 | 2 generations | Dynasty frequency: 2-5 per 500-turn run |
| Mentor formation threshold | M40 | 10 turns | Mentor frequency: ~10-20 per 500-turn run |
| `STARTING_WEALTH` | M41 | 0.5 | Wealth distribution shape at turn 500 (log-normal) |
| Wealth accumulation rates | M41 | TBD | Gini coefficient range: 0.3-0.7 across civs |
| `TAX_RATE` | M41 | TBD | Treasury in agent mode within 20% of aggregate |
| `TRANSPORT_COST_PER_HOP` | M43 | 10% | Food trade profitable at 1-2 hops, luxury at 4+ |
| Food shelf life | M43 | 3-5 turns | Food stockpiles deplete realistically |
| `RAIDER_THRESHOLD` | M43 | TBD | Large stockpiles attract raids 10-20% of the time |
| Supply shock attenuation | M43 | 50%/hop | Shocks propagate 2-3 hops before negligible |
| Arc classification thresholds | M45 | TBD | At least 4 archetype types appear per run |
| Curator arc bonuses | M45 | +1.5/+2.5 | Character-arc moments in top 50% of curated events |

### Method

1. Run 200 seeds × 500 turns with all Phase 6 features active (`--agents hybrid --agent-narrative`)
2. Extract metrics: action distributions, personality-behavior correlations, cultural clustering, wealth distributions, dynasty counts, arc classifications, conversion rates, schism frequency, trade patterns, shock propagation distance
3. Compare against target ranges. Adjust constants, re-run 20 seeds to verify, then full 200-seed confirmation.
4. Flag structural issues for Phase 7 backlog.

### Validation Strategy

Phase 6 shifts from "match aggregate" to "internal consistency":

- **Personality correlation:** Bold agents rebel more. Cautious agents migrate more. Ambitious agents switch occupations more.
- **Cultural clustering:** Cultural values cluster by region and adjacency (spatial autocorrelation > 0).
- **Religious dynamics:** Proselytizing faiths spread faster. Militant faiths fight more. Schisms correlate with diversity.
- **Environmental shaping:** River trade regions are wealthier. Desert regions have more religious fervor. Mountain regions resist cultural assimilation.
- **Wealth distribution:** Log-normal shape. Gini between 0.3-0.7. No collapse to extremes.
- **Supply chain realism:** Food trade local, luxury trade long-distance. Embargo hurts dependent regions. Drought propagates.
- **Dynasty coherence:** Dynasty members share personality tendencies. Dynasty events produce narrative arcs.
- **Regression:** Agents with neutral personality, no relationships, uniform cultural values, and same-faith approximate Phase 5 behavior.

### Narrative Quality Review

Manual review of 20 curated+narrated chronicles:
- Do personalities appear in prose ("the cautious Vesh...")?
- Do dynasty arcs thread across multiple entries?
- Do cultural tensions appear in narration?
- Do religious conflicts drive narrative drama?
- Does economic class feature in narrative tone?
- Do supply crises create compelling narrative moments?
- Do social relationships create narrative callbacks?
- Does the material world feel real (specific crops, trade goods, seasonal references)?

### Deliverables

- Calibrated constants (committed with rationale)
- 200-seed metrics report
- Internal consistency validation results
- Narrative quality notes and prompt adjustments
- Structural issues flagged for Phase 7

---

## Cross-Cutting Concerns

### Per-Agent Memory Budget

| Phase | Fields Added | Bytes | Cumulative |
|-------|-------------|-------|-----------|
| M25-M26 | id, region, origin, civ, occ, loyalty, sat, skills, age, disp, alive | 42 | 42 |
| M27 | (no new agent fields) | 0 | 42 |
| M30 | life_events, promotion_progress | 2 | 44 |
| M32-M33 | boldness, ambition, loyalty_trait (3 × f32) | 12 | 56 |
| M36 | cultural_values (3 × u8) | 3 | 59 |
| M37 | belief (u8) | 1 | 60 |
| M39 | parent_id (u32) | 4 | 64 |
| M41 | wealth (f32) | 4 | 68 |

68 bytes/agent × 10K agents = 680KB. Well within L2 cache (9950X has 16MB L2). Per-region (500 agents × 68 bytes = 34KB) fits comfortably in L1 (64KB per core).

At 50K agents (future scaling): 3.4MB. Still within L2. Per-region (1250 agents × 68 bytes = 85KB) exceeds L1 but fits L2.

### Per-Region State Budget

| Phase | Fields Added | Bytes | Cumulative |
|-------|-------------|-------|-----------|
| M26 | id, terrain, capacity, pop, soil, water, forest, adj, civ, trade | ~30 | 30 |
| M34 | resource_types[3], resource_yields[3], resource_reserves[3], season, climate | ~38 | 68 |
| M35 | river_mask, disease_severity | ~8 | 76 |

76 bytes/region × 40 regions = 3KB. Negligible.

Goods state (M42-M43) is Python-side per-region, not in Rust RegionState. ~200 bytes/region for stockpiles, prices, flows = 8KB at 40 regions. Negligible.

### Determinism

Same guarantees as Phase 5:
- Region processing order by index
- ChaCha8Rng with stream splitting per region per turn
- Migration ordering by agent_id
- Personality assignment seeded deterministically
- Cultural drift target selection seeded deterministically
- Conversion target selection seeded deterministically
- Goods allocation seeded deterministically

### Performance Impact

Phase 6 adds per-agent computation:
- **Utility evaluation (M32):** 5 utility functions × ~10 ops each = ~50 ops/agent (replaces ~20 ops from short-circuit). ~2.5× compute increase for decisions.
- **Cultural drift (M36):** 1 probability check + conditional value copy. Negligible.
- **Conversion (M37):** 1 probability check + conditional value copy. Negligible.
- **Wealth accumulation (M41):** 1 multiply + 1 add + 1 clamp. Negligible.
- **Personality (M33):** Modifies existing utility computation, not a separate phase.
- **Social graph (M40):** Named-character-only, runs in Python. Negligible for Rust tick.
- **Gini computation (M41):** O(n log n) per civ per turn. At 10K agents / ~10 civs = 1K agents per civ. Fast.
- **Goods/supply chain (M42-M43):** Per-region, not per-agent. O(regions × trade_routes). Negligible for Rust tick; runs in Python.
- **Disease (M35):** Per-region computation. Negligible.

Net tick time increase: estimated ~30-50% from utility expansion. With M29 optimizations already landed (27-47× headroom), 0.25ms × 1.5 = 0.375ms for 10K/24. Still massively under the 5ms target. At 50K agents: ~1.9ms. Still under target.

If scaling to 100K+ agents, M29 Phase B (SIMD verification, decision short-circuit tuning) becomes relevant.

### Backward Compatibility

- `--agents=off` produces Phase 4 bit-identical output (unchanged)
- `--agents=hybrid` without Phase 6 features: set personality to [0,0,0], disable cultural drift, disable conversion, disable wealth accumulation. Behavior approximates Phase 5.
- `bundle_version` distinguishes Phase 4 (v1), Phase 5 (v2), and Phase 6 (v3) bundles. Consumer code handles all versions.

---

## Estimated Effort

| Milestone | Est. Days | Risk | Notes |
|-----------|----------|------|-------|
| M32 Utility Decisions | 5–7 | Medium | Utility tuning is iterative; regression against Phase 5 |
| M33 Personality | 4–6 | Medium | Personality × utility interaction: large parameter space |
| M34 Resources & Seasons | 5–7 | Medium | Extends ecology.py; resource type registry and yield formulas |
| M35 Rivers, Disease & Events | 5–7 | Medium–High | River topology at world gen; disease integration with demographics |
| M36 Cultural Identity | 5–7 | Medium–High | Touches existing Phase 3 culture.py code |
| M37 Belief Systems | 5–7 | Medium | New system but clean integration points via satisfaction + utility |
| M38 Religious Institutions | 5–7 | Medium–High | Fourth faction modifies political dynamics; schism logic is complex |
| M39 Family & Lineage | 4–6 | Low–Medium | Structurally simple; dynasty detection has edge cases |
| M40 Social Networks | 4–6 | Medium | Formation rules need careful scoping |
| M41 Wealth & Markets | 5–7 | Medium–High | Economic integration affects treasury and action weights |
| M42 Goods & Trade | 5–7 | Medium | New goods model but builds on existing trade route infrastructure |
| M43 Transport & Shocks | 5–7 | Medium–High | Shock propagation is the most complex new algorithm |
| M44 API Narration | 3–4 | Low | AnthropicClient exists; mostly wiring and quality comparison |
| M45 Character Arcs | 4–5 | Medium | Arc classification is heuristic; new archetypes for religion |
| M46 Viewer | 7–9 | Medium | Largest viewer milestone; ~2000 lines TS |
| M47 Tuning | 4–6 | Low–Medium | More constants to tune but proven pattern (M19b/M31) |
| **Total** | **75–105** | | ~3× Phase 5 scope |

---

## Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Utility-based decisions produce degenerate behavior | High | Temperature tuning; regression test against Phase 5 short-circuit |
| Personality collapses to extremes after many generations | Medium | Inheritance noise prevents fixation; distribution stability test |
| Cultural drift too fast or too slow | Medium | Calibration pass (M47); regression against Phase 5 timelines |
| Religion dominates all political dynamics | Medium | Clergy faction influence capped; doctrine effects tunable independently |
| Schisms fire too frequently (every civ splits) | Medium | Threshold tuning; minimum civ size for schism eligibility |
| Supply chain creates infinite money (arbitrage loop) | Medium | Conservation law: total goods = production - decay. Price floor prevents negative cost. |
| Shock propagation creates permanent depression | Medium | Attenuation per hop; stockpile buffer; production recovery after disruption ends |
| Agent wealth creates runaway inequality | Medium | Wealth decay rate + max cap prevent extremes; Gini monitoring |
| Endemic disease makes all regions unlivable | Medium | Disease severity capped; interaction with water quality provides player agency via irrigation |
| Phase 6 tick time exceeds targets at 50K+ agents | Medium | M29 Phase B (SIMD) available; utility computation is embarrassingly parallel |
| Phase 3 code integration (culture.py, economics) introduces regressions | High | Bit-identical regression test for `--agents=off`; shadow comparison for hybrid mode |
| 16-milestone phase is too large to manage | Medium | Each milestone is independently shippable; natural review gates between system pairs |

---

## Phase 7 Considerations

Ideas evaluated during Phase 6 planning that were deferred as out-of-scope.

### Marriage & Household Economics
Spousal relationships, household income pooling, marriage alliances between named characters across civs. Deferred because: single-parent lineage (M39) captures the key narrative arc (dynasty) without the economic modeling complexity of households.

### Agent-Level Diplomacy
Named characters negotiating on behalf of civs — envoys, hostage exchanges, marriage alliances. Deferred because: the aggregate diplomacy system (Phase 3) handles inter-civ relations; agent diplomacy would need to integrate with disposition, treaties, and federation mechanics simultaneously.

### Procedural Scenario Generation
Algorithmically generated maps with terrain constraints, resource placement rules, and narrative seeds. Deferred because: the YAML scenario system works; procedural generation is an orthogonal feature.

### Multiplayer / Shared World
Multiple users controlling different civs in the same simulation. Deferred because: this is an entirely different product architecture (networking, conflict resolution, UI redesign).

### Metamodel Validation
Surrogate model of the ABM for response surface comparison. Deferred because: internal consistency tests (M47) are sufficient for the current model complexity.

### Agent-Scale Scaling (100K+)
Scaling beyond 50K agents to 100K+ for city-level simulation detail. Deferred because: 50K agents with Phase 6 systems already provides extraordinary detail per seed. 100K+ may require architectural changes (spatial partitioning, GPU compute) that are better evaluated after Phase 6 lands.
