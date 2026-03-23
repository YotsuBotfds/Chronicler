# External Repository Catalog

> **Purpose:** Reference catalog of open-source projects with techniques relevant to Chronicler's simulation systems. Organized by subsystem. Each entry notes what's transferable and where it maps in Chronicler's architecture.
>
> **Last updated:** 2026-03-19

---

## Agent Memory & LLM Narration

| Repo | Lang | Key Technique | Chronicler Mapping |
|------|------|---------------|-------------------|
| [joonspk-research/generative_agents](https://github.com/joonspk-research/generative_agents) | Python | Three-factor memory retrieval (recency × importance × relevance), importance-budget reflection trigger, unbounded memory stream with SPO triples | M48 memory retrieval/eviction, M44 narration context selection |
| [StanfordHCI/genagents](https://github.com/StanfordHCI/genagents) | Python | 3,505 demographic-profile agents queried via LLM; validates that traits alone produce valid behavior without per-agent narrative memory | Validates Chronicler's deterministic trait system |
| [4thfever/cultivation-world-simulator](https://github.com/4thfever/cultivation-world-simulator) | Python/Vue | Two-tier AI (rules + LLM), 16 narrator styles, model tier routing (max/flash), perception-limited agent context, two-pass interaction processing | M44 narration, M59 information propagation, M50 relationships |

## Procedural World Generation

| Repo | Lang | Key Technique | Chronicler Mapping |
|------|------|---------------|-------------------|
| [Mindwerks/worldengine](https://github.com/Mindwerks/worldengine) | Python | Plate tectonics → rain shadow precipitation → erosion → Holdridge life zone biomes, A* trade pathfinding | ecology.py terrain, climate.py, deferred continuous terrain |
| [ftomassetti/civs](https://github.com/ftomassetti/civs) | Clojure | Bands → tribes → chiefdoms → nations (Service typology), settlement emergence, language generation | M63 institutional emergence, M68 cultural traits |
| [Azgaar/Fantasy-Map-Generator](https://github.com/Azgaar/Fantasy-Map-Generator) | JS | **Dijkstra flood fill with domain-specific cost functions** for culture/state/religion expansion (same algorithm, different cost weights — nomads 10x in forests, naval 2x on land, religion cheap along roads). **Urquhart graph** (pruned Delaunay) for natural trade route topology. Culture fitness functions score cells by temperature/biome preference. Markov chain naming with 43 language bases. Static generation — no temporal simulation | world_gen.py expansion, trade route topology, M68 cultural naming |
| [bdharris/ProcgenMansion](https://github.com/bdharris/ProcgenMansion) | — | Procedural rooms with emergent entity interactions | Spatial agent interaction patterns (M55) |

## Large-Scale Emergent Simulation

| Repo | Lang | Key Technique | Chronicler Mapping |
|------|------|---------------|-------------------|
| [CleverRaven/Cataclysm-DDA](https://github.com/CleverRaven/Cataclysm-DDA) | C++ | ~500K lines. **Effect on Condition (EOC)** — data-driven condition-effect rules for cross-system coupling (JSON-defined, no C++ changes needed). **Variable-frequency processing** (monsters every turn, overmap NPCs every 5min, groups daily). **Deterministic weather** as pure `f(pos, time, seed)` with no mutable state. **Event bus** with 108 typed events + compile-time schema validation. Personality as threshold modifiers (cheaper than utility evaluation). Horde abstraction (lightweight entities promoted to full sim when relevant) | emergence.py rules engine, climate.py, architecture patterns |
| [yairm210/Unciv](https://github.com/yairm210/Unciv) | Kotlin | **Asymmetric modifier decay** — betrayal persists 4-8x longer than warmongering (160 vs 40 turns). **Pressure-based religion** — cumulative competitive pressure per city, holy city 5x amplifier, proportional follower allocation. **War motivation** — 15-factor score with pathing hard gate (-30 to -50 if unreachable). **Scarcity-tiered trade** — 1st copy 500, 5th copy 100. **Tech catch-up** — cost decreases as more civs discover. **Bankruptcy loop** — auto-disband units until solvent. **Personality** — 16 dimensions as multiplier functions | diplomacy, religion, economy, tech, politics |
| [nethope/world-sim](https://github.com/nethope/world-sim) | — | Multi-civ world history simulation | General architecture comparison |

## ABM Frameworks

| Repo | Lang | Key Technique | Chronicler Mapping |
|------|------|---------------|-------------------|
| [projectmesa/mesa](https://github.com/projectmesa/mesa) | Python | Tops out at ~10K agents (per-agent Python dispatch bottleneck). **SeedSequence replication spawning** for independent reproducible child seeds. **Parquet streaming data recorder** with sliding window retention. **Scenario class** — frozen parameter containers. Validates that Chronicler's Rust SoA approach is the correct scaling solution | Seed management, analytics streaming, scenario formalization |
| [projectmesa/mesa-examples](https://github.com/projectmesa/mesa-examples) | Python | Reference ABM models including forest fire, predator-prey, wealth distribution | ecology.py, economy.py pattern reference |
| [PeWeX47/Axelrod-Model](https://github.com/PeWeX47/Axelrod-Model) | Python | **Axelrod cultural dissemination**: interaction probability proportional to cultural similarity. Creates natural cultural islands — similar cultures merge, different cultures resist convergence. Conformist bias: `p' = p + D*p*(1-p)*(2p-1)` | M36 culture_tick assimilation rate, M68 trait transmission |

## Climate & Weather

| Repo | Lang | Key Technique | Chronicler Mapping |
|------|------|---------------|-------------------|
| [sandeepdhakal/abm-ccid](https://github.com/sandeepdhakal/abm-ccid) | Python/Mesa | **Fermi function** for probabilistic migration: `1/(1+exp(-beta*delta))` replaces hard thresholds with smooth curves. **Two-gate decision** — threshold gate then probabilistic destination comparison. **Cooperation thresholds** creating coordination traps. **Sigmoid dampening** on runaway processes. **Tag-based trust** with EMA decay | behavior.rs migration, ecology.py dampening, culture_tick |
| [HeQinWill/awesome-WeatherAI](https://github.com/HeQinWill/awesome-WeatherAI) | — | Curated collection: FourCastNet, GraphCast, ClimaX foundation models | climate.py reference for weather pattern generation |
| [baafiadomako/CDSim](https://github.com/baafiadomako/CDSim) | R | Synthetic climate data generation (temp, rainfall). Climatologically realistic time series | Reproducible climate input for deterministic sims |

## Disease & Epidemic Models

| Repo | Lang | Key Technique | Chronicler Mapping |
|------|------|---------------|-------------------|
| [Judikardo14/Covid19_Simulation](https://github.com/Judikardo14/Covid19_Simulation) | Python | 3D spatial SEIR ABM with R₀ calculations, multi-scenario lockdown | emergence.py pandemics, M35b endemic baseline |
| COVID19-CBABM (arxiv:2409.05235) | Python/Mesa | City-based SEIR with geographic awareness, facility-type transmission | Geographic plague spread, settlement-based transmission (M56) |
| [epispot/epispot](https://github.com/epispot/epispot) | Python | SIR/SEIR compartment models, extensible | emergence.py epidemic mechanics |
| [SABS-R3-Epidemiology/openabm](https://github.com/SABS-R3-Epidemiology/openabm) | — | Highly configurable agent-based epidemic simulation | Complex pandemic scenarios |

## Ecology, Land Use & Vegetation

| Repo | Lang | Key Technique | Chronicler Mapping |
|------|------|---------------|-------------------|
| [PIK-LPJmL/LPJmL](https://github.com/PIK-LPJmL/LPJmL) | C/Fortran | **Two-pool soil decomposition** (fast leaf litter + slow humus, different k rates — realistic lag). **Multiplicative stress stacking** — `productivity = base * temp * water * nitrogen * light` (each 0-1, two stresses combining = severe crash). **20-year climate buffers** for biome decisions (short droughts reduce yield, only sustained shifts change biomes). **SPITFIRE fire model** — fire danger = accumulated heat stress (Nesterov index) × fuel load × ignition. **Conservation law enforcement** — model fails on imbalance | ecology.py soil/water/forest, terrain transitions, fire mechanics |
| [bsleeter/lucas](https://github.com/bsleeter/lucas) | R | State-and-transition land use model with carbon stocks/flows. USGS-backed | ecology.py terrain succession (forest → grassland → desert) |
| [GeoSOS/FLUS](https://github.com/GeoSOS/FLUS) | C++ | Cellular automata land dynamics with climate/socioeconomic coupling | Terrain transitions, deforestation from civ expansion |
| [ghislainv/forestatrisk](https://github.com/ghislainv/forestatrisk) | Python/R | Deforestation risk from spatial + climate factors | ecology.py forest tick, M64 commons exploitation |
| [ESCOMP/CTSM](https://github.com/ESCOMP/CTSM) | Fortran | Community Land Model: biogeophysics, carbon/nitrogen cycling | Reference for coupled earth system dynamics |
| [NetLogo/models](https://github.com/NetLogo/models) | NetLogo | Forest fire model, predator-prey, ecosystem dynamics | ecology.py fire/disaster mechanics |

## Infrastructure & Urban Systems

| Repo | Lang | Key Technique | Chronicler Mapping |
|------|------|---------------|-------------------|
| [UDST/urbansim](https://github.com/UDST/urbansim) | Python | **Vacancy-driven construction** — build to maintain target service gap, not on schedule. **Iterative clipped price adjustment** — demand/supply ratio clipped [0.75, 1.25], iterated to convergence (validates M42 approach). **Profit-as-probability** site selection. **Account class** — running balance + transaction log + subaccount breakdown for treasury auditing | infrastructure.py, economy.py pricing validation, M56 |
| [matsim-org/matsim](https://github.com/matsim-org/matsim) | Java | Multi-agent transport simulation, infrastructure + traffic dynamics | Trade route logistics, M58 merchant travel |
| [cityflow-project/CityFlow](https://github.com/cityflow-project/CityFlow) | Python/C++ | Large-scale city traffic, infrastructure lifecycle logic | Settlement infrastructure (M56) |

## Economy & Trade

| Repo | Lang | Key Technique | Chronicler Mapping |
|------|------|---------------|-------------------|
| [aminya/EconomicalModels](https://github.com/aminya/EconomicalModels) | Rust/Python | Economic models with Rust backend, Python-Rust FFI | economy.py, M54b Rust economy migration |
| [agentic-system/economic-simulation](https://github.com/agentic-system/economic-simulation) | Python | Supply-demand pricing, trader agents | economy.py goods pricing, M58 agent trade |
| [larsiusprime/bazaarBot](https://github.com/larsiusprime/bazaarBot) | Haxe | **Price belief ranges** `[min, max]` per good per market — tighten on success, widen on failure. Favorability-scaled quantities. Surplus/shortage against ideal inventory. Emergent price discovery from decentralized bilateral negotiation | M58 per-agent merchant pricing |
| [AB-CE/abce](https://github.com/AB-CE/abce) | Python | **Reservation system** for committed goods (prevents double-counting). **Deque-based perishability** (FIFO, oldest consumed first). **Three-phase trade protocol** (reserve → transport → settle/unwind). Cobb-Douglas/Leontief/CES production functions | M58 goods reservation, M43a perishability |
| [amzn/supply-chain-simulation-environment](https://github.com/amzn/supply-chain-simulation-environment) | Python | **Edge-resident transit goods** with `time_until_arrival` counter. **Virtual inventory** shadow copy prevents double-allocation. NetworkX directed graph supply chain | M58 goods in transit |
| [fiquant/marketsimulator](https://github.com/fiquant/marketsimulator) | Python/Haxe | **Stale prices via latency links** — merchants see delayed prices at distant markets. FIFO ordering on links. **Arbitrage strategy** across linked order books. Trade disruption = link degradation (embargo = infinite latency, war = edge removal) | M58 + M59 information propagation, trade disruption |
| [google/or-tools](https://github.com/google/or-tools) | C++/Python | **VRP validation oracle** — solve optimal routing offline, compare to emergent merchant behavior. Capacity dimensions, time windows, multi-vehicle. ~2 sec for 50 regions. Clarke-Wright savings heuristic extractable for per-agent use | M58 validation, trade route optimization |
| [graphhopper/jsprit](https://github.com/graphhopper/jsprit) | Java | **Max-time-in-vehicle IS perishability.** Skills for route compatibility (ship-only, escort-needed). **Prize-collecting framing** (optional profitable stops). **Regret-based insertion** for constrained merchants. Ruin-and-recreate metaheuristic. Convoy emergence from time-window synchronization | M58 constraint modeling, route planning |

## Character Generation & Dynasties

| Repo | Lang | Key Technique | Chronicler Mapping |
|------|------|---------------|-------------------|
| [ShiJbey/minerva](https://github.com/ShiJbey/minerva) | Python | **Trait-as-modifier-stack** with apply/remove + conflicting trait constraints. **Acquired traits from simulation events** (rule-based queries). **Trait inheritance** probabilities. **Proclivity system** — traits influence AI decisions via tagged utility scores. **Depth-chart succession.** CK3-inspired 20 personality traits | M48 generalized acquired traits, M45 character arcs, M50 bond formation |
| [atanvardo/DYNASTY](https://github.com/atanvardo/DYNASTY) | Python | **Succession scoring** — genealogical distance + sibling rank + sex preference. **2-parent-1-random trait mixing** for family resemblance. **Royal numbering** post-processing ("Philip II"). Actuarial mortality/fertility tables | M51 dynasties, M39 lineage |
| [Cellule/npc-generator](https://github.com/Cellule/npc-generator) | TypeScript | **Weighted tables with side-effect mutations** — selecting a trait automatically adjusts stats. 272 JSON data tables. Accumulator-based alignment from all generation steps. Social strata influencing stats | M48 trait generation, GreatPerson creation |

## Religion & Belief

| Repo | Lang | Key Technique | Chronicler Mapping |
|------|------|---------------|-------------------|
| religiongenius (not found — repo deleted/private) | — | N/A | — |
| "Future of Faith" NetLogo model (Djoudi) | NetLogo | **Conviction-gradient conversion** — `P = (neighbor_conv - agent_conv) * scale`. Converts get 80% of converter's conviction (zeal decay dampens cascades). **Demographic-driven spread** via religion-specific birth rates | religion.py conversion mechanics, M37-M38b |
| [amesoudi/cultural_evolution_ABM_tutorial](https://github.com/amesoudi/cultural_evolution_ABM_tutorial) | R | **Conformist bias** — `p' = p + D*p*(1-p)*(2p-1)`. D=2-3 optimal (fast regional homogenization, slow enough for innovation). **Prestige bias** — copy high-status agents. **Directly biased** — `p' = p + p(1-p)*s` for intrinsically attractive traits | M68 cultural traits, religion.py belief aggregation |

## Rust Architecture & FFI

| Repo | Lang | Key Technique | Chronicler Mapping |
|------|------|---------------|-------------------|
| [bevyengine/bevy](https://github.com/bevyengine/bevy) | Rust | Archetype-table SoA with type erasure (prevents SIMD auto-vectorization — manual SoA is strictly better for homogeneous agents). **Per-civ signal change detection** — skip satisfaction recomputation for civs with unchanged signals. **Explicit rayon batch sizing** via `par_chunks(N)` tuned to L2 cache. **Access-pattern assertions** — debug-mode checks that phases don't read/write wrong arrays. Bevy's determinism has known gaps (non-stable topological sort); Chronicler's explicit phase ordering is more correct | chronicler-agents SoA validation, engineering optimizations |
| [PyO3/pyo3](https://github.com/PyO3/pyo3) | Rust | Reference Python-Rust bindings, working FFI patterns | agent_bridge.py, ffi.rs reference |
| [PyO3/maturin](https://github.com/PyO3/maturin) | Rust | Build tool for Python-Rust packages | Build system reference |

## Text Games & Narrative Engines

| Repo | Lang | Key Technique | Chronicler Mapping |
|------|------|---------------|-------------------|
| [evennia/evennia](https://github.com/evennia/evennia) | Python | Framework for text-based multiplayer worlds, world gen + narrative scripting | Viewer/narrative architecture reference |
| [Latitude-IO/AIDungeon](https://github.com/Latitude-IO/AIDungeon) | Python/JS | GPT-powered real-time narrative generation | M44 API narration patterns |

## Diplomacy & Strategy

| Repo | Lang | Key Technique | Chronicler Mapping |
|------|------|---------------|-------------------|
| [jordanorelli/diplomacy](https://github.com/jordanorelli/diplomacy) | Python | Classic Diplomacy board game simulation: alliance-building, negotiation | Phase 5 diplomacy, M71 alliance formation |

---

## To Be Considered (Batch 3 — 2026-03-19 research session)

Findings from 12 research agents. Not yet filed to roadmap enrichment notes. Review and integrate during relevant milestone spec work.

### War & Conflict

| Repo/Source | Key Pattern | Target |
|-------------|------------|--------|
| [doolanshire/Combat-Models](https://github.com/doolanshire/Combat-Models) | **Lanchester linear (N=1) vs square (N=2) law.** `effective_power = force^N × lethality × terrain`. Tech level determines exponent. | M60 military units |
| [dmasad/Agents-In-Conflict](https://github.com/dmasad/Agents-In-Conflict) | **Bueno de Mesquita expected utility**: `EU(war) = P(win)×U(win) + P(lose)×U(lose) - cost`. Validated against Correlates of War 1816-2016 | M60 war decisions |
| Civ VI war weariness | **Accumulator with asymmetric decay** — +events at war, -50/turn at war, -200/turn at peace, -2000 on treaty. Nonlinear conversion to penalties | M47d war weariness |
| Victoria 3 diplomatic plays | **Maneuver points** — same pool for swaying allies AND adding war goals. Ambition vs coalition size tradeoff | Phase 5 diplomacy |
| EU4 coalitions | **Aggressive Expansion tracker** per civ-pair. Conquest near neighbors increases AE, decays over time, triggers balancing coalition above threshold | Phase 5 diplomacy |
| CINC (Correlates of War) | **6-component power index**: mil_personnel, mil_expenditure, iron_steel, energy, total_pop, urban_pop as fractions of world total | War motivation scoring |
| [agiresearch/WarAgent](https://github.com/agiresearch/WarAgent) | Alliance accuracy 77.78% vs historical. Escalation lock-in: once war starts, peace mechanisms rarely activate | M60, M71 alliances |

### Demographics & Population

| Repo/Source | Key Pattern | Target |
|-------------|------------|--------|
| Siler 5-parameter model | **`h(x) = a1*exp(-a2*x) + a3 + a4*exp(a5*x)`** — infant decline + background + senescent rise. Bathtub curve. One `exp` per agent per turn. Gage & Dyke Level 15 params for pre-industrial baseline | demographics.rs mortality |
| Gompertz-Makeham | **3-param simpler alternative** for adults: `h(x) = alpha*exp(beta*x) + lambda`. Modal death age: `M = (1/beta)*ln(beta/alpha)` | demographics.rs |
| Galor-Weil unified growth | **Demographic transition**: death rate drops before birth rate (tech-driven), producing Stage 2 population boom naturally. Sigmoid functions of development index | demographics.rs fertility |
| Malthusian equilibrium | **Dynamic carrying capacity**: `K = K_base × tech × soil_quality × (1 + trade_food_import)`. Overshoot degrades K itself | ecology.py, demographics |
| Age-specific fertility | **Peaked curve**: `fertility = max(0, 1 - ((age - 27) / 15)^2)` instead of flat rate | demographics.rs |
| Harris-Todaro migration | **Expected urban income vs rural income** — migration equilibrium with persistent urban unemployment | M56 settlements |

### Social Networks

| Repo/Source | Key Pattern | Target |
|-------------|------------|--------|
| Dunbar layers (JASSS ABM) | **Log-growth + linear-decay** on trust naturally produces 5/15/150 layers without coding them. Strong ties decay slower | M50 relationships |
| Triadic closure research | **Friend-of-friend > preferential attachment** for real social networks. Dominant edge formation mechanism | M50 bond formation |
| Label Propagation Algorithm | **~50 lines Rust** on flat edge vec, identifies communities. Run every 5-10 turns for cohort detection | M53 cohort validation |
| Bounded confidence (Hegselmann-Krause) | Agents only influence others within confidence bound → natural schisms and cultural islands | M68 culture, religion.py |
| [GiulioRossetti/ndlib](https://github.com/GiulioRossetti/ndlib) | **18 epidemic + 10 opinion dynamics models** on networks. Threshold, Independent Cascades, Kertesz (community-aware) | M59, M68, M70 revolution |
| Friedkin-Johnsen model | **Stubbornness parameter** (0-1) — some agents anchored to initial beliefs, others susceptible. Produces stable disagreement | M68 cultural traits |

### Procedural History & Narrative

| Repo/Source | Key Pattern | Target |
|-------------|------------|--------|
| Six emotional arcs (Reagan 2016) | **Classify civ stat trajectories** into recognized story shapes (rags-to-riches, tragedy, man-in-a-hole) from population/prestige/territory curves | curator.py, arcs.py |
| [mkremins/felt](https://github.com/mkremins/felt) + [winnow](https://github.com/mkremins/winnow) | **Story sifting** via Datalog queries over event DB. **Partial sifting** detects incomplete arcs in progress | curator.py |
| Caves of Qud sultan histories | **Retroactive causality** — generate events first, rationalize causal connections afterward. Dual narrative voice (gospel vs inscription) | narrative.py |
| [dmasad/WorldBuilding](https://github.com/dmasad/WorldBuilding) | **Era detection from wealth inflection points** — find local extrema in time series, divide history into growth/decline periods | era register validation |
| [sajidurdev/SyntheticCiv](https://github.com/sajidurdev/SyntheticCiv) | **Closest architectural analog** — deterministic, three-scale (agent/settlement/civ), seeded RNG, settlement-level pricing, pressure-differential migration | Architecture reference |

### Political Factions & Governance

| Repo/Source | Key Pattern | Target |
|-------------|------------|--------|
| Victoria 3 interest groups | **Clout = share of total political strength** (zero-sum). Three tiers: powerful >20%, influential 5-19%, marginalized <5%. Wealth → political strength mediated by institutions | M63 institutions |
| [tpike3/bilateralshapley](https://github.com/tpike3/bilateralshapley) | **Coalition formation** with Shapley values. Compromise parameter controls preference alignment on merge | M63 faction dynamics |
| Epstein civil violence (Mesa) | **`grievance = hardship × (1 - legitimacy)`**. Cascade: more rebels → lower arrest risk → more rebels. Sharp phase transitions | M70 revolution |
| J-curve theory (Davies) | Revolution when **rising expectations suddenly frustrated** — track satisfaction moving average, risk spikes when current drops below trailing average | M70 revolution triggers |
| Turchin PSI implementation | Full **MMP × EMP × SFD** with elite dynamics `de/dt = μ₀(w₀-w)/w`. Demographic-Wealth Model produces Hopf bifurcations | M65 elite dynamics |
| [alexrutherford/corruption](https://github.com/alexrutherford/corruption) | **Weaker centralized authority enables stronger society** through peer enforcement. Corruption as hysteresis | M63 institutional decay |
| Acemoglu-Robinson narrow corridor | **Three regimes**: despotic, weak-state, balanced. State capacity and societal power co-evolve via contest functions | M63 governance |

### Deterministic Replay

| Repo/Source | Key Pattern | Target |
|-------------|------------|--------|
| Python `set` iteration | **NOT deterministic** — grep simulation code for order-dependent `set` iteration. `dict` is safe (insertion-ordered since 3.7) | Immediate audit |
| ChaCha8Rng streams | Pin exact `rand` crate versions. Never sample `usize`/`isize`. Named algorithms reproducible within version | agent.rs RNG |
| Per-turn state hash | Hash `WorldState` at end of each turn, store sequence, compare across runs. Cheapest divergence detection | Regression testing |
| Riot Games hierarchical logging | Per-civ per-variable logging on divergence. Diff to find first diverging field | Debug tooling |
| [NautilusTrader](https://deepwiki.com/nautechsystems/nautilus_trader) | Production **Rust+Python hybrid via PyO3+Arrow** with deterministic event ordering | Architecture reference |

### Monetary Systems

| Repo/Source | Key Pattern | Target |
|-------------|------------|--------|
| Historical debasement | **`debasement_level` (0-1)** per civ. Seigniorage = `debasement × mint_throughput`. Diminishing returns on repeated debasement | M71 money supply |
| Quantity theory (MV=PQ) | **Price index** from weighted `RegionGoods` prices. `inflation = delta_M / delta_Q`. Already have the data | M71 inflation |
| Currency trust with hysteresis | Below threshold → trade disruption, satisfaction spike, foreign civs refuse currency. Slow to rebuild | M71 monetary crisis |
| Gresham's Law | Bad money drives out good — emerges naturally from debasement | M71 |
| Kiyotaki-Wright | Most-traded good becomes **commodity money** naturally. Pre-monetary → coined → debased as tech/culture progression | M71 currency emergence |
| Faucet/sink accounting | Track per-civ inflows vs outflows. When monetary pressure exceeds goods production growth, prices rise | M71 |
| Inflation as wealth erosion | Feed inflation rate into Rust agent pool wealth decay. Shifts Gini, changes class tension | M71 + M41 wealth |

### Exploration & Discovery

| Repo/Source | Key Pattern | Target |
|-------------|------------|--------|
| Freeciv vision.c | **Per-civ knowledge cache** with `last_observed_turn`. Stale snapshots drift from reality | M59 information, EXPLORE |
| CDDA graduated vision | **`familiarity: float` (0-1)** per civ-region. Reveal thresholds: terrain at 0.1, resources at 0.3, population at 0.8 | M59, EXPLORE action |
| Multi-channel propagation | Trade routes (partial), migration (full origin), diplomacy (curated), rumors (degraded with hops) | M59 channels |
| Explore/exploit tradeoff | `explore_weight *= (1 + adjacent_unknown_count × terrain_promise)` | EXPLORE ActionType |
| Deferred detail generation | Generate sub-region features from `RNG(seed, region, category)` on first discovery. Deterministic | world_gen.py extension |
| Maps as diplomatic asset | Knowledge exchange valued by `sum(familiarity_delta)`. Non-rival, perishable, network effects | Phase 5 diplomacy |

### Innovation & Tech Diffusion

| Repo/Source | Key Pattern | Target |
|-------------|------------|--------|
| Bass diffusion model | **`P(adopt) = p + q × (adopting_neighbors / total)`**. p = innovation, q = imitation. S-curve naturally | Phase 7 tech |
| Comin-Hobijn empirics | **73% decay per 1000km**. East-west faster than north-south. Distance effect diminishes as tech spreads widely | Phase 7 tech |
| Complex contagion | Tech needs **sustained multi-turn contact**, not single exposure. Threshold varies by complexity | Phase 7 tech |
| Absorptive capacity | Prior related knowledge determines ability to even recognize foreign tech. Path-dependent specialization | Phase 7 tech focus |
| Branching vs recombinant | **Incremental** within domain (cheap) vs **combining** two domains (rare, big impact). Combinatorial possibility space growth | Phase 7 tech |
| Catch-up discount | `difficulty -= 0.3 × (neighbors_with_tech / civs_alive)`. Simplest viable spillover | Phase 7 tech |
| Learning-by-doing | Economic activity in domain boosts tech advancement. Trade-heavy civs develop trade tech naturally | Phase 7 tech focus |
| [KadinTucker/THTSim](https://github.com/KadinTucker/THTSim) | **Terrain-driven advancement** — mountains boost metalwork, forests boost woodwork. Migration carries tech | Phase 7 tech |

### Piracy & Raiding Economics

| Repo/Source | Key Pattern | Target |
|-------------|------------|--------|
| Becker crime calculus | `E[raid] = p_success × loot - p_caught × punishment - opportunity_cost`. When > E[trade], raiding is rational | M43b raider incentive |
| Olson stationary bandit | Repeated raiding → "encompassing interest" → transition to tribute/vassalage. Raider → overlord → state | M43b + politics.py |
| Lotka-Volterra predator-prey | Too much raiding kills trade, collapses raiding revenue. Self-limiting oscillation | M43b dynamics |
| Leeson pirate reputation | Known raiders face less resistance (signal). Reputation reduces cost until targets invest in defense | M43b + prestige |
| Hawk-Dove equilibrium | Frequency-dependent: too many raiders → returns drop below trading → civs switch back. Self-correcting | M43b calibration |
| Routine Activity Theory | Crime needs: motivated offender + suitable target + absent guardian. Maps to raider incentive inputs | M43b |

### Marriage & Kinship Diplomacy

| Repo/Source | Key Pattern | Target |
|-------------|------------|--------|
| CK3 marriage mechanics | Alliance auto-created on marriage, **breaks on death**, must be renewed each generation | M57 marriage |
| [KenjiItao/clan](https://github.com/KenjiItao/clan) (PNAS 2020) | Clans emerge from marriage exchange + incest taboo. **Generalized** (A→B→C→A) vs **restricted** (A↔B) exchange | M57 + M50 |
| Exogamy/endogamy | **Cultural value** — exogamy = wider alliances + assimilation risk. Endogamy = identity preservation + isolation + fertility penalty | M57 + M36 culture |
| Bride price/dowry | **Treasury transfer at marriage**. Direction from cultural system. Economic crises drive marriage spikes | M57 + economy |
| Patrilineal/matrilineal | **Descent system as dynasty param** — determines which civ benefits from cross-civ marriage. Affects succession | M39 dynasties |
| Stable matching (Gale-Shapley) | Marriage market when multiple civs seek alliances simultaneously. Prevents monopolization | M57 |

### Novel Finds (Wild Card)

| Repo/Source | Key Pattern | Target |
|-------------|------------|--------|
| [martndj/handy](https://github.com/martndj/handy) (HANDY model) | **4 coupled ODEs**: Commoners, Elites, Nature, Wealth. Dual collapse: ecological OR inequality. Inequality alone can cause collapse with abundant resources | M64 commons, M65 elites |
| [cvanwynsberghe/pyworld3](https://github.com/cvanwynsberghe/pyworld3) | **Delay functions** — consequences lag cause by generations. 5 coupled subsystems with nonlinear lookup tables | Architecture pattern |
| [TheApexWu/psychohistoryML](https://github.com/TheApexWu/psychohistoryML) | **Complexity-duration reverses across eras**. Religion shortens polity lifespan (HR 1.58). Violent transitions converge to 36%. Single tuning params won't work across all eras | M53/M67 calibration |
| [giorgiopiatti/GovSim](https://github.com/giorgiopiatti/GovSim) | LLM agents collapse commons **96% of the time**. Useful calibration target: most civs should struggle with commons | M64 commons |
| [mbyim/turchin_metaethnic_frontier_theory](https://github.com/mbyim/turchin_metaethnic_frontier_theory) | **NetLogo implementation** of asabiya frontier model with `exp(-distance/h)` power decay. Ethnogenesis at frontier intersections | M55 spatial asabiya |
| [kdelwat/Onset](https://github.com/kdelwat/Onset) | **Language evolution** via systematic phonetic sound changes. Cognate drift, mutual intelligibility | M68 language |
| Bass diffusion | **S-curve tech adoption**: `P = p + q × (adopters/total)`. Innovation coefficient + imitation coefficient | Phase 7 tech |
| [marmiskarian/bassmodeldiffusion](https://github.com/marmiskarian/bassmodeldiffusion) | Python Bass model package with fitting, prediction, shock models | Phase 7 tech |
| Artificial Anasazi (NetLogo) | **Gold standard validation** against archaeology. Environment alone insufficient — social mechanics must be added | Validation methodology |
| [Socrats/EGTTools](https://github.com/Socrats/EGTTools) | **Evolutionary game theory** C++ toolkit. Fixation probabilities for strategy invasion in finite populations | Faction dynamics |
| [langerv/sugarscape](https://github.com/langerv/sugarscape) | Canonical ABM. Diagonal migration waves, wealth inequality emergence, cultural tag-flipping, combat front lines | Architecture reference |

---

## Subsystem Integration Map

```
Climate (abm-ccid, CDSim)
  ↓ affects
Ecology (LPJmL carbon/water, NetLogo fire)
  ↓ drives
Land Use (LUCAS state transitions, FLUS cellular automata)
  ↓ impacts
Infrastructure (UrbanSim decay, matsim transport)
  ↓ stresses
Agent Health (SEIR compartment models)
  ↓ feeds
Civilization Dynamics (emergence.py, politics.py)
  ↓ narrated by
LLM Narration (generative_agents retrieval, cultivation-sim style variation)
```
