# Chronicler Phase 3 — World Simulation Depth

> Phase 1 (M1-M6) delivered the core pipeline. Phase 2 (M7-M12) added simulation depth, custom scenarios, workflow automation, and visualization. Phase 3 gives the simulation material foundations — economics, politics, geography, culture, and characters — so that emergent behavior replaces scripted narrative.
>
> All mechanics in Phase 3 are **pure Python simulation** — no LLM calls required. The narrative engine describes what happened; it doesn't decide what happens. Every system produces emergent behavior from simple rules interacting with each other.

---

## Architectural Prerequisites

These changes are required before any M13 work begins. They unblock the entire phase.

### P1: Stat Scale Migration

The current 1-10 integer scale for population, military, economy, culture, stability cannot support the treasury sinks/sources, trade income formulas, and military maintenance curves in this phase.

**Decision: expand to 0-100 integer scale for all civ stats.** Treasury uncapped (currently capped at `10 + economy*3`).

- Multiply all existing stat values by 10 during migration.
- Update all thresholds, formulas, action weights, tech requirements proportionally.
- Existing scenario YAML files get a `stat_scale: 10` compatibility field — loader multiplies values by 10 on load, so old scenarios work unchanged.
- Asabiya stays 0.0-1.0 float (already fine).
- Write a migration test: load every existing scenario, run 20 turns, assert no crashes and stats stay in expected ranges.

### P2: Region Adjacency Graph

Currently regions are names with optional x/y. No adjacency data exists. Trade routes, governing distance, chokepoint inference, migration chains, and movement spread all require a graph.

**Add an explicit adjacency list to the world model.**

- `Region` gains `adjacencies: list[str]` (region names).
- World generation auto-computes adjacency from x/y: **k-nearest (k=2-3) for maps under 10 regions** to ensure sparse graphs with chokepoints and strategic geography; **Delaunay triangulation for 10+ regions** where natural sparsity emerges from point distribution. Small maps with Delaunay produce near-complete graphs — every region adjacent to every other — which kills strategic topology.
- Scenario YAML gains optional `adjacencies` block for manual override.
- Coastal regions additionally connect to all other coastal regions (sea routes) — tagged as `sea_route: true` on the edge.
- Graph utilities: `shortest_path(a, b)`, `graph_distance(a, b)`, `is_chokepoint(r)`, `connected_components()`.
- Existing scenarios without x/y: generate positions from region count using force-directed layout, then compute adjacency.

### P3: Action Engine v2

The current engine selects ONE action per civ per turn from 5 options. Phase 3 needs ~10 new action types (embargo, build infrastructure, fund instability, explore, move capital, vassalize, cultural projection, scorched earth, hire mercenaries, form federation).

**Split actions into automatic phase effects and deliberate actions.**

- **Automatic effects** (happen every turn, no choice): trade income, military maintenance, fertility recovery/degradation, infrastructure upkeep, cultural assimilation ticks, vassal tribute. These run in production/upkeep phases.
- **Deliberate actions** (civ chooses one per turn): DEVELOP, DIPLOMACY, EXPAND, WAR, TRADE (existing) plus BUILD, EXPLORE, EMBARGO, INVEST_CULTURE, MOVE_CAPITAL (new). Not all available from M13 — added as milestones introduce them.
- **Reactions** (triggered by other civs' actions, not chosen): DEFEND (auto in war), COUNTER_ESPIONAGE, REBEL. Resolved in the action phase when triggered.
- Action weights system stays — just expanded with new entries in `TRAIT_WEIGHTS`.

---

## Dependency Graph

```
Prerequisites (P1, P2, P3) — before any milestone
  │
  M13a (Resource Foundations)
  │ │
  │ M13b (Economic Dynamics) — needs trade routes, resources
  │   │
  │   ├── M14 (Political Topology) — needs treasury, trade, governing costs
  │   │     └── M17 (Great Person Engine) — needs succession, vassals, exile
  │   │
  │   ├── M15 (Living World) — needs resources, fertility, infrastructure investment
  │   │     └── M16 (Memetic Warfare) — needs terrain effects, trade routes
  │   │           └── M17 (Great Person Engine) — needs movements, culture
  │   │
  │   └── M14½ (Systemic Dynamics) — needs economy + politics basics
  │
  └── M18 (Emergence and Chaos) — needs all systems interacting

Parallelism:
  - M14 and M15 can run in parallel after M13b
  - M16 can start once M15 terrain effects land
  - M14½ can start after M13b + M14 basics
  - M17 needs M14 + M16
  - M18 needs everything
```

---

## M13a: Resource Foundations

*Give the economy material foundations. Regions produce specific things; civs need diverse things.*

### Specialized Resources
- Regions produce specific resource types: **grain, timber, iron, fuel, stone, rare_minerals**.
- Resource type derived from terrain + per-region seed (deterministic, not random at runtime):
  - Plains → grain (80%) or stone (20%)
  - Forest → timber (80%) or grain (20%)
  - Mountains → iron (50%), stone (30%), rare_minerals (20%)
  - Coast → grain (40%), maritime/salt (40%), rare_minerals (20%)
  - Desert → rare_minerals (60%), stone (40%)
  - Tundra → iron (50%), fuel (50%)
- Each region produces one primary resource and has a 20% chance of a secondary.
- Scenario YAML can override resource assignments explicitly.

### Resource Diversity Requirements
- Civs need **resource diversity** to advance tech eras. Requirements added to `TECH_REQUIREMENTS`:
  - BRONZE: iron + timber (or 1 unique resource)
  - IRON: iron + timber + grain (or 2 unique)
  - CLASSICAL: 3 unique resources
  - MEDIEVAL: 4 unique resources
  - RENAISSANCE: 5 unique resources
  - INDUSTRIAL: fuel + iron + 4 unique
  - INFORMATION: 5 unique + economy ≥ 70
- Resources obtained via: controlling a region that produces it, or active trade route with a civ that has it.
- This single change makes conquest strategic — you grab the region with what you need.

### Trade Routes
- Region pairs form trade links based on adjacency graph edges.
- Coastal regions trade with other coastal regions via sea routes regardless of adjacency.
- A trade route is **active** when both endpoint regions are controlled by civs with disposition ≥ NEUTRAL.
- Controlling both ends = economy bonus for the controller (+3/turn per route).
- One end each = interdependence: +2 economy each, but creates leverage.
- Trade routes are the primary vector for economic growth. A landlocked civ with no trade partners stagnates.
- **Embargo action**: either side can embargo — cuts bonuses for both, disposition penalty (-1 level), stability -5 for the embargoing civ's trade-dependent regions.

### Resource Depletion / Fertility System
- `carrying_capacity` (existing, 1-10) becomes the **base** capacity (renamed `base_capacity`, scaled to 10-100 by P1).
- New `fertility: float` (0.0-1.0) represents current land health. **Effective capacity = base_capacity × fertility**.
- Fertility degrades by 0.02/turn when population exceeds effective capacity.
- Fertility recovers by 0.01/turn when population < 50% of effective capacity.
- Pure math — creates migration pressure as mechanical inevitability.

### Simulation-Only Mode
- `--simulate-only` CLI flag: runs full simulation, skips chronicle generation.
- Writes `chronicle_bundle.json` with full history/events but empty `chronicle_entries`.
- Viewer displays mechanical data without prose.
- Enables rapid iteration: 500 turns in seconds on local hardware.
- First-class deliverable, not an afterthought.

### Tech Era: INFORMATION
- Add INFORMATION era after INDUSTRIAL in `tech.py`.
- Requirements: culture ≥ 90, economy ≥ 80, treasury cost 35, 5 unique resources.
- Era bonuses: +10 culture, +5 economy.
- Mechanical effects deferred to M16 (cultural influence projects globally).

---

## M13b: Economic Dynamics

*Money becomes interesting. Armies cost money, wars drain it, trade generates it, and running out has consequences.*

### Treasury Mechanics Overhaul
- Treasury uncapped (P1). New sinks and sources:
  - **Military maintenance**: each military point above 30 costs 1 treasury/turn. Large armies are expensive.
  - **Trade income**: active trade routes generate treasury (+2/route/turn to each partner).
  - **War costs**: declaring war drains 10 treasury. Each turn at war costs 3. Prolonged wars bleed you dry.
  - **Development cost**: DEVELOP action costs scale with economy (base 5 + economy/10).
  - **Infrastructure investment**: BUILD action costs treasury (M15).
- A civ that wins a war but empties its treasury is vulnerable. Pyrrhic victory as emergent property.

### Famine Events
- When a region's fertility drops below 0.3, trigger famine (deterministic threshold, not random).
- Effects: population -15, stability -10 in affected region.
- Neighboring regions (adjacency graph): population +5, stability -5 (refugee pressure).
- Chain reaction potential — famine cascades across connected regions.
- Famine ends when population drops below effective capacity (self-correcting but devastating).

### Black Markets
- When an embargo exists between two civs, smuggling emerges automatically if their regions are ≤ 2 hops apart on the adjacency graph.
- 30% of normal trade benefit, stability -3 for both sides.
- Neither can fully cut the other off without controlling the physical route between them.
- Sanctions are leaky. Narrative gold.

### Economic Specialization
- Tracked as resource concentration ratio: `dominant_resource_count / total_resource_count`.
- Ratio > 0.6 = "specialized": +15% economy bonus on that resource's trade income.
- But vulnerability: if trade routes for that resource are cut, economy drops by 20%.
- Monoculture economies boom in peace, collapse when supply chains break. Emergent boom/bust.

### Mercenary Companies
- When military maintenance cost > treasury income for 3 consecutive turns, excess military "goes mercenary."
- Mercenary band spawns as a lightweight entity: attached to a region, has military strength, no civ allegiance.
- Other civs can hire them (treasury cost = military strength × 3) for wars — adds to military for that war only.
- Unhired mercenaries in a region become bandits: fertility -0.05/turn, trade income -1 for routes through that region.
- **Decay**: mercenary bands lose 2 military strength per turn (desertion, local integration). Dissolve entirely when strength < 5. A collapsing empire seeds the map with destabilizing armed groups, but they're a 10-15 turn crisis, not a permanent map poison.
- **Cap**: max 3 active mercenary bands on the map at once. If a 4th would spawn, the weakest existing band dissolves first.

---

## M14: Political Topology

*Power is expensive to hold and interesting to lose. This milestone makes empires structurally unstable.*

### Governing Cost
- Each region beyond the 2nd costs stability (-3) and treasury (-2) per turn.
- Cost scales with **graph distance** from capital (adjacency hops): distance × 2 treasury, distance × 1 stability.
- A 6-region empire bleeds unless rich and stable. "Too big to hold" from pure arithmetic.

### Capital Designation
- Each civ has a capital region (default: starting region, or most populated).
- Losing capital: stability -20, immediate leader succession check, governing distances recalculated from new most-populated region.
- **MOVE_CAPITAL action**: costs 15 treasury, -10 stability for 5 turns, resets all governing distances. Strategic retreat as a mechanic.

### Civil War / Secession
- When stability < 20 AND region count ≥ 3, secession probability = `(20 - stability) / 100` per turn.
- Breakaway civ spawns from most distant regions (by graph distance from capital).
- Inherits local military and population proportional to regions taken.
- Generated name from cultural name pool, new leader. Starts HOSTILE to parent.
- **The single biggest narrative generator.** Empires splitting is where history gets interesting.

### Vassal States
- After winning a war, victor can vassalize instead of absorbing (if winner's stability > 40).
- **New data model**: `VassalRelation(overlord, vassal, tribute_rate, turns_active)` stored on WorldState.
- Vassal pays tribute (treasury transfer = vassal economy × tribute_rate per turn).
- Vassal can't declare wars independently. Retains identity and internal governance.
- Vassals rebel if overlord stability < 25 OR overlord treasury < 10 (no tribute = no loyalty).
- Empires are federations of resentment held together by strength.

### Federations
- Civs with disposition ALLIED for 10+ turns can form a federation.
- **New data model**: `Federation(name, members: list[str], founded_turn)` stored on WorldState.
- Shared defense pact: attack one member, all members join the war.
- Shared trade network: all member pairs get trade routes regardless of adjacency.
- Members can't attack each other without dissolving the federation first (stability -15 to all members).
- Natural lifespan — hold during external threat, fracture during peace when internal rivalries resurface.

### Proxy Wars
- Civs can fund instability in rival's vassals or border regions. New action or sub-action of DIPLOMACY.
- Cost: 8 treasury/turn. Effect: target region secession probability +0.05.
- Detection probability: `target_civ_culture / 100`. If detected: disposition → HOSTILE, potential casus belli.
- Cold War dynamics from pure mechanics.

### Diplomatic Congresses
- When 3+ civs at war simultaneously, 5% probability per turn of a congress event.
- Negotiating power per participant: `(military + economy + allies_count × 10) / war_turns`.
- Outcomes: full peace (all wars end, borders frozen), partial ceasefire (highest-power pairs settle), or collapse (nothing changes, stability -5 for all).
- Congress of Vienna as an emergent system.

### Governments in Exile
- When a civ loses all regions, it persists as a diaspora modifier on the absorbing civ.
- Conquered regions get stability -5 per turn (restless population) for 20 turns.
- Restoration event possible if absorber's stability < 20: original civ respawns in one region.
- Other civs can "recognize" the exile (diplomatic action): increases restoration probability by 0.03/turn.
- A conquered people are a ticking clock inside your empire.

---

## M14½: Systemic Dynamics

*Mechanics that only need economy + basic politics. Pulled from M18 because they're independent of living world / culture systems.*

### Balance of Power
- When a single civ's power score (military + economy + region_count × 5) exceeds 40% of total, all other civs get +10 disposition toward each other per turn (coalition pressure).
- Not scripted — just mechanical pressure making dominance progressively harder.
- The simulation produces antibodies against runaway winners. Unipolarity is unstable.

### Fallen Empire Modifier
- A civ that once held 5+ regions and is now reduced to 1:
  - Asabiya +0.3 (they remember who they were).
  - Action selection biased 2.0× toward WAR and EXPAND.
  - Other civs' coalition pressure against them reduced by 50% (underestimation).
- Ibn Khaldun in reverse — the conquered remember, the conquerors grow complacent.
- Creates "return of the king" arcs from pure mechanics.

### Civilizational Twilight
- A civ holding 1 region with declining stats (economy + military + culture all decreased last 10 turns) for 20+ consecutive turns enters twilight.
- Twilight: population -3/turn, culture -2/turn (slow bleed).
- Revivable by: new leader with asabiya > 0.6, resource discovery, alliance with rising power.
- If not revived within 20 turns, peacefully absorbed by most culturally similar neighbor.
- "Whimper, not a bang" endings — historically more common than dramatic last stands.

### The Long Peace Problem
- If no wars occur for 30+ consecutive turns:
  - Military-heavy civs (military > 60): stability -2/turn (armies with nothing to do become political threats).
  - Economic inequality between civs grows: richest civ's economy +2/turn, poorest -1/turn (trade benefits compound).
  - Movement spread rate doubles (bored populations adopt radical ideas — feeds into M16).
- Sustained peace is as dynamically interesting as war — different kind of instability.

---

## M15: Living World

*The map is a living system that changes over centuries, rewards investment, punishes neglect.*

### Terrain Mechanical Effects
- Terrain types get mechanical weight (currently flavor text):
  - **Mountains**: +20 military defense bonus, fertility cap 0.6, iron/stone resources.
  - **Coast**: enables sea trade routes, vulnerable to flooding events, grain/maritime.
  - **Plains**: high fertility (base 0.9), no defensive bonus, vulnerable to drought.
  - **Forest**: timber resource, fertility 0.7, +10 defensive bonus.
  - **Desert**: fertility cap 0.3, rare minerals, immune to flooding.
  - **Tundra**: fertility cap 0.2, iron/fuel, +10 defensive bonus (harsh terrain).
- Terrain now load-bearing for every military, economic, and environmental calculation.

### Chokepoint Inference
- Derived from adjacency graph, not manually tagged:
  - **Crossroads**: connected to 3+ regions → trade +3, defense -5 (exposed).
  - **Frontier**: connected to only 1 region → defense +10, trade -2.
  - **Chokepoint**: only path between two graph clusters → trade toll +5, strategic value flag.
- Creates natural Thermopylae moments from pure graph structure.
- Computed once at world generation, recomputed if regions are destroyed/created.

### Infrastructure
- Civs build improvements via **BUILD action**. Each costs treasury and takes multiple turns:
  - **Roads** (cost 10, 2 turns): trade +2 between connected regions, adjacent military movement bonus.
  - **Fortifications** (cost 15, 3 turns): defense +15. Persists through conquest.
  - **Irrigation** (cost 12, 2 turns): fertility +0.15, reduces drought vulnerability.
  - **Ports** (cost 15, 3 turns): coastal only. Enables sea trade, +3 trade income.
  - **Mines** (cost 10, 2 turns): resource extraction +50% (double resource trade value), but fertility -0.03/turn (tradeoff).
- Infrastructure persists through conquest — built environment accumulates over centuries.
- **Scorched earth**: destroying infrastructure is a valid war action (defender's choice on losing a region). Costly but denies value.
- New data model: `Infrastructure(type, region, builder_civ, built_turn, active: bool)` stored on Region.

### Climate Cycles
- Configurable period (default 75 turns). Deterministic cycle — period and severity in scenario config.
- Climate states rotate: **temperate** (default, 40% of cycle) → **warming** (20%) → **drought** (20%) → **cooling** (20%).
- Effects on terrain productivity:
  - **Drought**: plains fertility ×0.5, forest ×0.7, desert unchanged.
  - **Warming**: coastal flooding risk (5%/turn, destroys ports), mountain defense bonus removed, tundra fertility ×2.
  - **Cooling**: all fertility ×0.8, tundra fertility ×0.3, southern regions (low y) less affected.
- Civs can see it coming (deterministic). Drama is whether they adapted in time.
- Scenario config: `climate: { period: 75, severity: 1.0, start_phase: "temperate" }`.

### Migration
- When a region's effective capacity < population × 0.5 (famine, war destruction, climate), population moves to adjacent regions.
- Receiving regions: population +5 per wave, stability -3 (refugee pressure).
- Drought in the steppe → domino chain of displacement. Mongol invasion pattern emerges from climate + adjacency mechanics.

### Natural Disasters
- Low probability per turn, terrain-dependent:
  - **Earthquake** (mountains, 2%/turn): fertility -0.2, destroys 1 random infrastructure.
  - **Flood** (coast, 3%/turn, doubled during warming): fertility -0.1, destroys ports.
  - **Wildfire** (forest, 2%/turn, doubled during drought): timber resource suspended 10 turns, fertility -0.15.
  - **Sandstorm** (desert, 3%/turn): trade routes through region suspended 5 turns.
- Adds variance to long runs. Disaster hitting the dominant empire's capital at the worst moment makes chronicles worth reading.

### Exploration / Terra Incognita
- Not all regions visible at simulation start.
- Each civ knows only home region + adjacencies. New regions discovered via:
  - **EXPLORE action**: reveals 1 unknown adjacent region. Costs 5 treasury.
  - Expansion into a region reveals its adjacencies.
  - Trade contact: trading with a civ shares their known-region set.
- First contact between isolated civs is a major event (importance 8+).
- Viewer territory map shows fog-of-war lifting over time.
- Scenario config: `fog_of_war: true/false` (default true for ≥15 regions, false for smaller maps).

### Ruins and Archaeology
- When a civ is absorbed or a region depopulated for 20+ turns, it becomes "ruins."
- Ruins discoverable via EXPLORE. One-time tech boost: `ruin_quality = peak_infrastructure_count × 5` added to culture.
- Highly developed regions leave better ruins. Discovering ruins of a great empire → tech leap narrative moment.
- Gives mechanical reason to explore depopulated regions.

---

## M16: Memetic Warfare

*Culture is a weapon, a glue, and a fault line. Ideas spread, mutate, and tear alliances apart.*

### Ideological Compatibility
- Civ values (already exist as string lists) create pairwise disposition modifiers.
- Shared values: +2 disposition/turn drift toward friendly.
- Opposing values: -2 disposition/turn drift toward hostile.
- Replaces some random disposition changes with principled ones.
- Value opposition table defined in config (e.g., "freedom" opposes "order", "tradition" opposes "progress").

### Cultural Assimilation
- Regions controlled by a foreign civ for 15+ turns gain that civ's cultural identity.
- `cultural_identity: str` added to Region (default: original controller's name).
- If reconquered by original controller: stability -5 for 10 turns ("restless population" — they've changed).
- If region's cultural identity ≠ controller: stability -2/turn ongoing.
- Irredentism as a simulation mechanic.

### Movements
- Periodic emergence (1 per 30 turns, configurable) of cross-border ideological movements.
- Types: reformation, revolution, enlightenment, industrialism, nationalism, environmentalism.
- Each movement has a value affinity (e.g., reformation → "freedom", industrialism → "progress").
- Spread via trade routes to civs with compatible values. Adoption probability: `trade_volume × value_compatibility / 100`.
- Adopters: +5 disposition with co-adopters, -5 with non-adopters.
- Creates alliance-breaking dynamics.

### Splinter Ideologies
- After a movement reaches 3+ civs AND 10+ turns pass, each adopter's version drifts.
- `movement_variant: int` increments independently per civ per 10 turns.
- Variants diverging by 3+ become incompatible: co-adopter disposition bonus flips to penalty.
- Protestant/Catholic dynamics from mechanical drift. The simulation doesn't know about religion.

### Technological Paradigm Shifts
- Advancing tech eras changes rules, not just numbers:
  - **BRONZE → IRON**: military effectiveness +30%. Bronze-age civs dramatically outmatched.
  - **IRON → CLASSICAL**: culture projection range +1 hop. Assimilation spreads faster.
  - **CLASSICAL → MEDIEVAL**: fortification effectiveness ×2. Defensive advantage.
  - **MEDIEVAL → RENAISSANCE**: trade income ×1.5. Merchant civs thrive.
  - **RENAISSANCE → INDUSTRIAL**: resource extraction ×2, fertility -0.05/turn in industrial regions. Coal regions critical.
  - **INDUSTRIAL → INFORMATION**: cultural influence projects across entire map regardless of adjacency. Soft power replaces hard power.
- Each era shift changes what's optimal. Iron age strategy becomes self-destructive in industrial age.

### Cultural Works Get Teeth
- Existing cultural works events now provide: asabiya +0.05, culture +5, and `prestige` modifier (+2 trade income, +1 diplomatic weight in congresses).
- Makes `develop_culture` / INVEST_CULTURE action a genuine strategic choice.

### Cultural Victory Tracking
- No win conditions (chronicle, not a game), but tracks cultural influence metrics.
- When one civ's culture exceeds all others combined → "cultural hegemony" event (importance 9).
- When a movement is adopted by every living civ → "universal enlightenment" event (importance 10).
- Milestone events the narrative engine treats as climactic.

### Propaganda and Information Warfare
- Civs with culture > 60 can spend treasury (5/turn) to project influence into rival regions.
- Target region: stability -3/turn, cultural assimilation timer accelerated (counts double).
- Defending civ can counter-spend (cultural defense, 3/turn per region) to neutralize.
- Information-era civs project at double effectiveness.
- Soft power as a simulation system.

---

## M17: The Great Person Engine

*History is made by individuals under structural pressures. Leaders and notable figures become characters with arcs.*

### Succession Crises
- On leader death, if civ has 3+ regions, 40% chance of contested succession (3-5 turns).
- During crisis: stability -10, action effectiveness halved, other civs can back candidates (costs 10 treasury).
- Backing the winner: +1 disposition level. Backing the loser: -1 disposition level.
- Winner's trait influenced by backing faction — military-backed → aggressive, trade-backed → cautious.

### Personal Grudges
- Leaders who lose wars gain `grudge: str` (rival civ name).
- Grudge: +0.5× WAR weight against that civ, decays by 0.1 per 5 turns.
- Persists weakly through succession: new leader inherits grudge at 50% intensity.
- Multi-generational feuds that fade unless refreshed by new conflicts.

### Exiled Leaders
- Deposed leaders (from civil war or succession) flee to random non-hostile civ.
- Host gains: culture +3 (exile brings expertise).
- Origin civ can demand extradition. Refusal: disposition -1 level. Compliance: exile removed but host looks weak (other civs' disposition toward host -5).
- "Pretender" narratives from pure mechanics.

### Legacy System Expansion
- Long-reigning leaders (15+ turns) already create legacy conditions. Expanded:
  - **Golden age memory**: next 2 leaders get asabiya +0.1. The civ remembers greatness.
  - **Shame memory** (lost capital): successor gets stability -10 but military +10 (revenge motivation).
  - **Fracture memory** (oversaw secession): next leader biased 1.5× toward DEVELOP and stability-building actions.
- Leaders become characters whose impact persists after death.

### Named Characters Beyond Leaders
- **Generals**: attached to civ, military +10 in wars. Can be captured (captor gets boost). Defect if stability < 15.
- **Merchants**: trade route income +3 per route. Can establish long-distance routes (non-adjacent civs via 3+ hop paths).
- **Prophets**: trigger and accelerate movement adoption in neighboring civs. If exiled, spreads movement to destination.
- **Scientists**: tech advancement treasury cost reduced by 30%. Capturable in war (tech theft).
- Generation: 1 per civ per era, drawn from cultural name pool with domain specialty. Lifespan: 20-30 turns, then retire/die.
- **Retirement**: characters past lifespan are archived — removed from active simulation state, preserved in history for narrative.

### Character Relationships
- Lightweight relationship system: rivalry, mentorship, marriage_alliance.
- Rivalry between two generals on opposite sides of a war → "duel" event (importance +2).
- Marriage alliance between civs → disposition +1 level for one leader generation.
- No complex relationship graph — just pairwise modifiers on relevant events.

### Institutional Memory (Traditions)
- Civs accumulate traditions based on history:
  - Survived 3+ famines → **food stockpiling**: fertility floor 0.2 (never below).
  - Won 5+ wars → **martial tradition**: military +5, but neighbors' disposition -5 (fear).
  - Maintained federation 30+ turns → **diplomatic tradition**: federation stability bonus +5.
  - Lost capital and recovered → **resilience tradition**: stability recovery rate ×2.
- Traditions stored as `traditions: list[str]` on Civilization.
- Old civs feel mechanically different from young ones.

### Hostage Exchanges
- After peace treaty (attacker lost), losing civ sends a named character to winner as hostage.
- Hostage gains host's cultural identity after 10 turns.
- If hostage later becomes leader (through succession): mixed cultural traits, disposition +1 toward former captor.
- Cultural cross-pollination through the mechanism designed to prevent it.

### Patron Saints and Folk Heroes
- Named character who dies in dramatic event (battle, last stand, movement persecution) → 20% chance of becoming folk hero.
- Folk hero: permanent asabiya +0.03 for the civ.
- Biases cultural name pool: future characters 30% more likely to share hero's domain.
- A civ with three military folk heroes has deep structural bias toward warfare. Cultural path dependence from emergent history.

---

## M18: Emergence and Chaos

*Every system above is predictable in isolation. M18 adds rare events and cross-system interactions that make long simulations genuinely surprising.*

> Depends on M13-M17. Cannot start until all prior milestones are complete.

### Black Swan Events
Very low probability per turn (< 1%), very high impact. Most 100-turn runs see zero. A 500-turn epic sees 2-3.

- **Supervolcano**: 3+ adjacent regions devastated. Fertility → 0.1, infrastructure destroyed, population halved. Climate cycle advanced to next phase early.
- **Pandemic**: spreads along trade routes. High-population, high-trade civs hit hardest (population -20, economy -15 per affected region). Isolation advantageous. Can kill named characters including leaders.
- **Resource discovery**: previously worthless region gains a critical resource (fuel or rare_minerals). Instantly strategic — every civ with a trade route benefits, every civ without wants one.
- **Technological accident**: industrial+ era civ's region causes ecological disaster. Fertility -0.3 in 2-region radius. Massive diplomatic fallout (everyone's trade routes affected).

### Cascade Failures
- Systemic stress index: `active_wars + famines + secession_events + natural_disasters` across all civs.
- When stress > `living_civ_count × 2`: all negative event probabilities ×1.5.
- Crisis breeds crisis. Famine → secession → war → refugees → another famine.
- Bronze Age Collapse dynamics from pure mechanical feedback.
- Viewer shows stress index as background color on timeline (green → yellow → red).

### Technological Regression
- Civs can lose tech eras. Triggers:
  - Lost capital + lost 50%+ regions in same turn: 30% regression chance.
  - Entered twilight: 50% regression chance.
  - Black swan event (pandemic, supervolcano) while stability < 20: 20% regression chance.
- Regression: lose one tech era, lose era bonuses. Recovery requires re-meeting requirements.
- Knowledge is fragile — maintained by institutions that need stability.
- Viewer shows era boundary going backwards on timeline.

### Ecological Succession
- Optional mechanic (scenario config: `ecological_succession: true/false`, default false).
- Regions slowly change terrain over 100+ turns based on conditions:
  - Forest with fertility < 0.3 for 50+ turns → plains (deforestation).
  - Desert with irrigation infrastructure for 80+ turns → plains (terraforming).
  - Plains depopulated for 100+ turns → forest (rewilding).
  - Mountains with mines for 100+ turns → barren hills (degradation, lose defensive bonus).
- The map at turn 500 looks different from turn 1. Environmental consequences as simulation mechanics.
- Off by default because it only matters in very long runs.

---

## Cross-Cutting Notes

### Narrative Engine Upgrades
Each milestone adds new event types. The narrative engine's prompt templates expand to cover them. No new LLM capabilities needed — just richer structured data in prompts.

### Scenario Compatibility
All new mechanics have sensible defaults. Existing scenarios work without modification:
- Missing `adjacencies` → auto-computed from x/y or force-directed layout.
- Missing `resources` → terrain-based defaults.
- Missing `climate` → default period 75, severity 1.0.
- Missing `fog_of_war` → false for maps < 15 regions, true otherwise.
- Old stat values (1-10 scale) → multiplied by 10 on load via `stat_scale` detection.

### Viewer Extensions
M11 viewer's panel architecture extends naturally. Each milestone adds snapshot fields; viewer adds overlays/tabs. No rewrites — incremental additions:
- M13: resource overlay, trade route lines, treasury graph.
- M14: political structure overlay (vassals, federations), secession probability heatmap.
- M15: infrastructure icons, climate state indicator, fog-of-war.
- M16: culture/movement spread animation, ideology map.
- M17: character panel, relationship graph, tradition badges.
- M18: stress index on timeline, regression markers.

### Testing Philosophy
Each milestone's mechanics testable in isolation with deterministic seeds:
- Condition-based assertions: "given this config, assert famine occurs within turns 10-15" (not exact turn — cascading nature means small upstream changes shift timing).
- Invariant tests: "treasury never negative while trade routes active", "fertility never > 1.0", "secession only fires when stability < 20 AND regions ≥ 3."
- Regression tests: existing scenario test suite must pass at each milestone.
- Scale test: 500 turns × 10 civs × 20 regions completes in < 30 seconds with `--simulate-only`.

### Performance Budget
- `--simulate-only` target: 500 turns < 5 seconds for a 5-civ, 15-region map.
- Bundle size: < 20MB for 500 turns (larger maps will need snapshot compression or delta encoding).
- Named character cap: 50 active characters max across all civs. Excess retired automatically (oldest first).
