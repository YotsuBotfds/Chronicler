# Phase 8-9 Brainstorm Synthesis — Emergent Order

> **Generated:** 2026-03-25 by 9-agent research team (15 tasks, ~25 minutes)
>
> **Purpose:** Consolidates deep codebase research, academic foundations, game design references, performance analysis, and cross-system feedback loop tracing into a spec-ready reference for M63-M73.
>
> **How to use:** Each milestone section contains mechanical proposals grounded in the existing codebase (with file:line references), academic calibration targets, game design precedents, and narrative integration hooks. Use alongside the Phase 8-9 Horizon doc when drafting specs.

---

## Table of Contents

1. [Cross-Cutting Findings](#cross-cutting-findings)
2. [Milestone Proposals (M63-M73)](#milestone-proposals)
3. [Cross-System Feedback Loops](#cross-system-feedback-loops)
4. [Dependency Graph & Implementation Order](#dependency-graph)
5. [Performance Budget](#performance-budget)
6. [Academic Calibration Targets](#academic-calibration)
7. [Game Design Reference Values](#game-design-values)
8. [Degenerate Condition Guards](#degenerate-guards)
9. [Narrative Integration Summary](#narrative-summary)
10. [Open Questions for Spec Resolution](#open-questions)

---

## 1. Cross-Cutting Findings {#cross-cutting-findings}

### The κ Coupling (Critical Missing Piece)

HANDY model analysis reveals that Chronicler currently has no mechanism for wealthy agents to extract disproportionately from commons. In HANDY, elites consume κ× more per capita — this drives the dual-collapse (inequality + overdepletion) that produces the most historically realistic civilizational failures. **M64+M65 must create this coupling:** `elite_extraction_rate = base_rate × f(wealth_percentile)`. Without it, Type-C (combined) collapse cannot emerge.

### The 2.5x Weight Cap Problem (REVIEW B-5)

The action weight cap was designed for 3 multiplicative contributors (traditions, tech focus, factions). Phase 7 added Mule (4th). Institutions would be 5th. The current proportional rescale silently nerfs all existing systems when new contributors are added.

**Proposed resolution:** Per-system contribution ceilings applied before multiplication:
- Trait weights: max 2.0x (already constrained by TRAIT_WEIGHTS table)
- Situational: max 2.5x (high military WAR*2.5 is the biggest)
- Faction: max ~1.5x (power function of influence)
- Tech focus: max ~1.5x
- Institutions: max 1.5x (new)
- Mule: existing utility_overrides with 0.1x floor
- **Revised global cap: 3.5x** or priority ordering where earlier-in-pipeline modifiers have reserved bandwidth

### The 0.40 Satisfaction Penalty Budget

Current budget: cultural + religious + persecution + class tension + memory = 5 terms competing for 0.40. Phase 8-9 adds inflation (M71 enrichment) and potentially institutional effects. The budget is crowded.

**Options:** (a) Raise cap to 0.50, (b) move inflation OUTSIDE cap (like food_sufficiency — material condition, not social), (c) redesign penalty as percentage-of-remaining-satisfaction rather than flat deduction.

### One-Turn Lag Discipline

All cross-system signals must use the N→N+1 lag pattern (matching Gini, economy signals). This prevents within-turn circular dependencies. Phase 8-9 signals that must follow this: PSI, institutional legitimacy, elite status, revolt risk, cultural trait frequencies.

### Signal Timing Table

| Signal | Produced (Phase) | Consumed (Phase) | Lag |
|--------|------------------|-------------------|-----|
| PSI | Phase 10 (turn N) | Phase 2-3 (turn N+1) | 1 turn |
| Gini coefficient | Agent tick (turn N) | Agent tick (turn N+1) | 1 turn |
| Cultural distance | Satisfaction (turn N) | Behavior (turn N) | 0 turns |
| Ecology (soil/water) | Phase 9 (turn N) | Satisfaction (turn N+1) | 1 turn |
| Faction influence | Phase 10 (turn N) | Phase 8 weights (turn N+1) | 1 turn |
| Institutional legitimacy | Phase 10 (turn N) | Phase 2 enforcement (turn N+1) | 1 turn |
| Prestige goods | Phase 2 economy (turn N) | Phase 10 patronage (turn N) | 0 turns |

---

## 2. Milestone Proposals {#milestone-proposals}

### M63: Institutional Emergence

**Split recommendation:** M63a (data model + lifecycle, ~3-4 days) → M63b (effects + cap revision, ~3-5 days)

**EARLY START — no Phase 7 scale dependency.** Only needs faction/treasury substrate from Phase 6.

#### Data Model

```python
class InstitutionType(str, Enum):
    # Military
    MILITARY_ACCLAMATION = "military_acclamation"
    CONSCRIPTION = "conscription"
    FRONTIER_GARRISONS = "frontier_garrisons"
    MARTIAL_LAW = "martial_law"
    # Merchant
    PROPERTY_RIGHTS = "property_rights"
    FREE_TRADE = "free_trade"
    MERCHANT_COURTS = "merchant_courts"
    TAX_CODE = "tax_code"
    # Cultural
    WRITTEN_LAW = "written_law"
    PATRONAGE_SYSTEM = "patronage_system"
    EDUCATION = "education"
    REPUBLICAN_VIRTUE = "republican_virtue"
    # Clergy
    TEMPLE_TITHE = "temple_tithe"
    DIVINE_RIGHT = "divine_right"
    HOLY_INQUISITION = "holy_inquisition"
    COMMONS_MANAGEMENT = "commons_management"
```

Max 3 active institutions per civ (forces tradeoffs). Each has:
- `enforcement_cost`: treasury drain (per-region, per-trade-route, or flat)
- `legitimacy`: 0.0-1.0, erodes when unenforced, collapses below 0.05
- `faction_alignment`: proposing and opposing factions
- `action_weight_modifiers`: dict of ActionType → multiplier (subject to per-system 1.5x ceiling)

#### Integration Points

- **Enforcement costs:** Map onto `apply_governing_costs()` (`politics.py:58-86`). Each institution adds to the per-region cost baseline.
- **Action weight modifiers:** Insert after faction modifiers (`action_engine.py:864`) but before holy war bonus.
- **Proposal/repeal:** In Phase 10 after `tick_factions()`. Dominant faction (influence > 0.35) proposes aligned institution. Blocked if opposing faction has influence > 0.30.
- **Victoria 3 adaptation:** Angry faction opposition uses 1.5× stall weight; neutral uses 0.5×.
- **Graduated sanctions (Ostrom):** Per-agent `institution_violation_count: u8` in Rust pool (+1 byte/agent). Sanction severity = f(violation_count). Per-institution, not global.

#### Selectorate Theory Integration (Enrichment)

W/S ratio (winning coalition / selectorate) determines public vs private goods allocation: `private_goods_share = 1 - (W/S)`. Small-coalition regimes boost WAR/BUILD; large-coalition boost DEVELOP/TRADE. Leader survival condition: coalition members stay loyal if payoff > challenger's offer.

---

### M64: Commons & Exploitation

**Compact scope (4-6 days). Depends on M63 (COMMONS_MANAGEMENT institution) and M54a (Rust ecology).**

#### Existing Substrate

Ecology already tracks: `soil_pressure_streak` (30-turn → 2× degradation), `overextraction_streaks` (35-turn → 10% permanent yield penalty), `resource_reserves` (mineral depletion). The lag-then-crash is already half-built.

#### What M64 Adds

1. **Exploitation rate = f(farmer_count, miner_count, infrastructure, κ_coupling)** — the κ coupling from HANDY is the critical new piece. Elite agents extract more.
2. **COMMONS_MANAGEMENT modifier:** Extends `overextraction_streak_limit` (slower degradation) and raises `soil_pressure_threshold` (higher pop before pressure kicks in). Implemented as per-region config modifier via `EcologyConfig`.
3. **Integration point:** `ecology.rs:396-452` (`tick_depletion_feedback`) — add institutional modifier fields to `RegionState`.

#### Calibration Targets

- **GovSim:** Without institutions, ~90%+ of civs should over-extract at some point during 500-turn runs (96% collapse rate in GovSim).
- **HANDY:** Sustainable equilibrium at ~60-80% of carrying capacity with moderate inequality.
- **Resource volatility (Ostrom insight not in horizon doc):** Variable-yield resources stress institutions differently than low-but-stable yields. Climate cycles should interact with institutional stability independently of yield decline.

---

### M65: Elite Dynamics & PSI

**Split recommendation:** M65a (elite positions + EMP, ~2-3 days) → M65b (PSI formula + secular cycle, ~3-4 days)

#### Elite Classification

- **Definition (must be locked in spec):** Agents with `wealth_percentile > 0.90` within their civ OR occupation in {Merchant, Scholar, Priest} with skill ≥ 0.8 OR GreatPerson status.
- **Elite positions:** `max(2, civ_population / 100)` — fixed per-civ, scaling with size.
- **Frustrated aspirant:** Qualifies as elite but no position available AND satisfaction < 0.3.
- **Rust implementation:** Piggyback on existing `wealth_tick()` per-civ sort — zero additional iteration cost.
- **New pool field:** `elite_status: u8` (0=commoner, 1=elite, 2=frustrated_aspirant) — 1 byte/agent.

#### PSI Formula

Implement exponent-ready from day one:
```
PSI = MMP^a × EMP^b × SFD^c    (defaults a=b=c=1.0)
```

Where:
- **MMP** = `(1/relative_wage) × urbanization_rate × youth_bulge_fraction`
- **EMP** = `(elite_count / elite_positions) × conspicuous_consumption_index`
- **SFD** = `(governing_cost / max(treasury, 1)) × (1 - institutional_legitimacy)`

Computed in Phase 10 after `tick_factions()`. Stored on `civ._psi` (transient, one-turn-lagged). `state_debt` doesn't exist yet — use governing_cost/treasury ratio as proxy until M66 introduces proper debt tracking.

#### Calibration (Turchin)

- PSI crisis crossing → crisis outcomes within 10-40 turns in ≥65% of seeds.
- All three sub-indices must co-occur in crisis — if they don't, soften exponents below 1.0.
- Conspicuous consumption ratchet timescale must balance with demographic reset timescale (M67 validates).
- Nested 40-60 turn violence sub-cycle during disintegrative phases (Turchin "fathers and sons").

---

### M66: Legitimacy & Ambitions

**Split recommendation:** M66a (legitimacy + political capital, ~2-3 days) → M66b (ambitions + event chains, ~2-3 days)

**EARLY START — only needs M39 (dynasty) and existing succession mechanics.**

#### Political Capital (Old World Adaptation)

Political capital as single shared budget (Old World's key insight — everything competes for the same pool):
```
political_capital_per_turn = base + legitimacy × 0.1
```

Spending: enact institution (-0.1), suppress secession (-0.2), diplomatic overture (-0.05), move army (-0.02 per region). Low-capital rulers can barely govern.

#### Legitimacy Sources

- **Dynasty prestige:** Cognomen decay 1/n for n-th predecessor (Old World).
- **Institutional support:** Sum of aligned institution legitimacy values.
- **Victories:** +10 per ambition completed, -5 per failure (Old World values).
- **Faction alignment:** +0.3 if leader's trait matches dominant faction.

#### Ambitions

2-3 generated at accession from pool filtered by civ state:
- Conquer region X (military state high → eligible)
- Build wonder (treasury > threshold → eligible)
- Establish trade (trade routes exist → eligible)
- Religious conversion (clergy influence high → eligible)

Duration: 20-40 turns. Completion/failure triggers named event + legitimacy change.

#### Event Memory Chains (Old World Adaptation)

Add `memory_tags: set[str]` to GreatPerson memories. Event templates specify `requires_memory_tags` and `grants_memory_tags`. Loosely coupled — one event grants "Offended_by_X", a later event requires "Offended_by_X" + "X_is_now_ruler".

---

### M67: Governance Tuning Pass

**GATE MILESTONE. Depends on M61b (scale validation) + M63-M66 (all governance systems).**

#### Acceptance Gates

| Gate | Threshold |
|------|-----------|
| Crisis predictiveness | PSI crisis → outcomes within 10-40 turns in ≥65% of crisis seeds |
| Co-occurrence integrity | All three PSI sub-indices exceed threshold in same 20-turn window for ≥50% |
| Secular-cycle recovery | ≥60% of crisis seeds show recovery within 120 turns (not one-way collapse) |
| Institutional regime reachability | All 3 regimes (frozen/fluctuating/cycling) in ≥10% of runs |
| Runtime budget | Combined M63-M66 within planned envelope |

---

### M68: Discrete Cultural Traits

**Split recommendation:** M68a (memome storage + transmission, ~3-4 days) → M68b (cultural distance + behavioral effects, ~2-3 days)

#### Memome Storage

Per-agent `memome: [u8; 8]` — 8 trait slots, each indexing ~20-30 trait types. 8 bytes/agent. Stored as `Vec<[u8; 8]>` in AgentPool (same pattern as relationship slots).

#### Conformist Bias

**Critical: use algebraic form for D=2:**
```rust
fn conformist_adoption_prob(freq: f32) -> f32 {
    let f2 = freq * freq;
    let inv2 = (1.0 - freq) * (1.0 - freq);
    f2 / (f2 + inv2)
}
```
This saves ~90% computation cost vs `powf()` (perf analysis finding). Branchless, auto-vectorization friendly.

#### Prestige Bias

Weight agents in frequency distribution by `1 + (wealth / PRESTIGE_WEALTH_SCALE)`. Named characters keep additive NAMED_CULTURE_WEIGHT (currently 5). GreatPersons and wealthy agents are cultural "stars."

#### Trait Compatibility Matrix

Global constant `[i8; N*N]` (~900 bytes at 30 traits). Query: `compatibility[trait_a * N + trait_b]`. -1 = incompatible (adoption blocked), 0 = orthogonal, +1 = synergistic (adoption boosted).

#### Anti-Conformist Personality (Academic Insight)

Some agents could have D < 1 (prefer rare traits). These are natural cultural innovators and bridge agents — they carry foreign ideas into homogeneous zones. Map to agents with high boldness personality trait.

#### Environmental Crisis → Weakened Conformism

During ecological crises (drought, famine), conformist bias should weaken temporarily — people in crisis are more open to radical ideas. Creates ecology→culture coupling: stable environments → homogenization, crisis → innovation bursts.

---

### M69: Prestige Goods & Patronage

**Compact scope (4-6 days). Depends on M67 + M65.**

#### Prestige Good Classification

Existing PRECIOUS resource (ResourceType=6) is the natural prestige good. Zero transit decay, zero storage decay (already in M43a). Add prestige subtypes via region assignment at world_gen.

#### Patronage Network

Gift-debt tracking at GreatPerson/elite level (not all agents). `PatronageEdge` with giver, receiver, good_type, bond_strength, gift_turn. Bond strength decays without resupply.

#### Cultural Influence

`cultural_influence = INFLUENCE_WEIGHT × prestige_exports / max(importer_demand, 0.1)`. Flows through existing trade route infrastructure. Importers' agents slowly adopt exporter's cultural traits.

#### Endogenous Brake

Elite overproduction → more elites competing for same prestige → diluted per-elite allocation → erosion even without supply shock. This must fire even when supply is stable.

---

### M70: Revolution Cascading

**Depends on M68 + M69. Compact scope (4-6 days).**

#### Threshold Computation (Epstein + Granovetter)

```rust
let grievance = (1.0 - satisfaction) * (1.0 - legitimacy);
let j_curve = (memory_score - satisfaction).max(0.0);  // Davies J-curve
let effective_hardship = grievance + J_CURVE_WEIGHT * j_curve;
let arrest_prob = 1.0 - (-2.3 * soldiers_ratio / rebels_ratio.max(0.01)).exp();
let net_risk = risk_aversion * arrest_prob;
if effective_hardship - net_risk > REBEL_THRESHOLD { rebel(); }
```

#### Critical Design Choice: Threshold Distribution

**Do NOT use Gaussian distribution** (Granovetter/Watts finding). Normal CDF produces either no cascade or total cascade — no partial outcomes. Derive thresholds from agent state (satisfaction × personality × cultural traits) for naturally heterogeneous distribution. Add small stochastic noise for stability (Granovetter "predictability paradox").

#### Urban vs Rural Cascade Speed

Dense networks (cities, trade hubs) → bimodal cascade sizes (fizzle or explode). Sparse networks (rural) → power-law sizes (gradual spread). This emerges naturally from M55a spatial + M56 settlement density.

#### Bridge Agents

Agents with cross-region/cross-civ relationships. Merchants naturally form these via trade. Assassination of bridge agent prevents cascade spread — narratively powerful.

#### Decision Lock

Must resolve before spec: does revolt awareness use M59's information propagation channel (architecturally cleaner) or its own? Planning default: reuse M59 with tagged message types.

---

### M71: Information Asymmetry

**Most independent Phase 9 milestone (4-6 days). Can develop concurrently with M68/M69/M70.**

Per-civ beliefs about others, intelligence sources, decay toward uncertainty, strategic deception. Extends M59 information propagation. Dramatic irony narration: narrator receives both actual and believed state.

---

### M72: Culture Tuning Pass

**GATE MILESTONE. Validates full Phase 9 stack.**

#### Acceptance Gates

| Gate | Threshold |
|------|-----------|
| Trait diversity | No single trait >85% global in >80% of seeds |
| Cascade plausibility | 0.2-2.0 major cascades per 100 turns (median band) |
| Prestige stability | Patronage concentration exceeds guardrail in <25% of seeds |
| Cross-system coupling | ≥2 interaction patterns from roadmap occur in ≥40% of seeds |
| Runtime budget | Combined M68-M71 within planned envelope |

---

### M73: Phase 8-9 Viewer

**Terminal milestone. 17 viewer deliverables (5 new components, 12 extensions).**

Top new components: PSIDashboard (3-panel, highest complexity), RevoltCascadeMap (animated spatial, second highest), InstitutionTimeline, PatronageNetwork, CulturalTraitMap.

All fit within Bundle v2's existing 7 layer kinds — no new kinds needed. Uses M62a's reserved namespaces for institutions, cultural_traits, prestige_goods, patronage_edges, revolt_clusters.

---

## 3. Cross-System Feedback Loops {#cross-system-feedback-loops}

### Named Interactions (from Horizon Doc)

**1. Secular Cycle → Institutional Collapse**
PSI spike → fiscal crisis → enforcement failure → PROPERTY_RIGHTS lapse → raider incentive rises → immiseration → PSI rises. Positive loop (~5-15 turn cycle). Braked by population decline (~30-80 turns) and stability recovery (+20/turn).

**2. Elite Overproduction → Institutional Capture**
Elite surplus → faction alignment → dominant faction pushes aligned institution → institution reinforces faction → self-sustaining lock. Braked by economic consequences of military dominance suppressing trade (~15-30 turns) and power struggle mechanic.

**3. Cultural Distance → Revolution Barrier/Catalyst**
Conquered regions with high cultural distance → low satisfaction → revolt susceptible BUT cascade can't cross cultural boundary to core. Dual nature: cultural distance makes local revolt more likely, cross-regional cascade less likely.

**4. Prestige Goods → Legitimacy → Institutional Stability**
Prestige control → patronage → legitimacy → political capital → institution enforcement. Disruption cascades through entire governance stack in 2-3 turns.

**5. Commons Overshoot → Elite Conflict**
Capacity drop → fewer material positions → EMP rises → elite competition → secular cycle compresses. COMMONS_MANAGEMENT institution is the Ostrom solution.

### Emergent Interactions (NOT in Horizon Doc)

**6. PSI + Commons Simultaneous Collapse:** All three PSI sub-indices spike at once. Compound crash may have no recovery path. Guard: subsistence floor mechanism.

**7. Revolution + Spatial Topology:** Trade route hubs become revolution transmission vectors. Revolution geography follows trade network topology, not just political boundaries.

**8. Mule + Patronage Disruption:** Mule redirects resources away from patronage → network atrophies during Mule's 30-turn window → post-fade legitimacy crisis the civ didn't see coming.

**9. Unbreakable Military Capture:** Military institution capture + war victories + treasury drain from war costs + cultural homogenization from expansion = self-reinforcing loop. Only exits: military defeat, treasury bankruptcy, or internal faction split. Guard: reform pressure at >70% influence for >30 turns.

**10. Ecology → Faith Transitions:** Famine refugees carry beliefs to new regions → conversion pressure → faction realignment → institutional change → different commons management → different ecological outcome.

---

## 4. Dependency Graph & Implementation Order {#dependency-graph}

### Critical Path (11 milestones, ~48-72 days)

```
M53 → M63a → M63b → M64 → M65b → M67 → M68a → M68b → M70 → M72 → M73
```

True critical path (blocked on Phase 7): `M61b → M67 → M68a → M68b → M70 → M72 → M73`

### Early Starts (Before Phase 7 Scale Track)

These have ZERO dependency on M54-M61:
1. **M63a** — Institution Data Model (needs only factions + treasury from Phase 6)
2. **M63b** — Effects + Cap Revision (resolves REVIEW B-5)
3. **M66a** — Legitimacy (hooks existing succession in politics.py)
4. **M66b** — Ruler Ambitions (hooks M48 memory)

### Maximum Parallelism Schedule

| Sprint | Milestones | Parallel? |
|--------|-----------|-----------|
| 1 (early, pre-M61b) | M63a → M63b, M66a → M66b | Yes (2 tracks) |
| 2 (post-M63b, pre-M61b) | M64 ∥ M65a, then M65b | Partial |
| 3 (post-M61b) | M67 | Gate (sequential) |
| 4 (post-M67) | M68a/b ∥ M69 ∥ M71 | Yes (3 tracks) |
| 5 (post-M68/M69) | M70 | Sequential |
| 6 | M72 | Gate (sequential) |
| 7 | M73 | Sequential |

### Sub-Milestone Splits (19 total from original 11)

| Original | Split Into | Rationale |
|----------|-----------|-----------|
| M63 | M63a + M63b | Cap revision is high-risk, isolate from data model |
| M65 | M65a + M65b | EMP tracking can start before commons; PSI needs both |
| M66 | M66a + M66b | Legitimacy is data model; ambitions are behavioral |
| M68 | M68a + M68b | Storage/transmission is Rust; distance effects are Python |

---

## 5. Performance Budget {#performance-budget}

**Current headroom: 27-47× at 10K agents.** All Phase 8-9 overhead fits comfortably.

| Milestone | Complexity | Projection | Key Risk |
|-----------|-----------|------------|----------|
| M63 Institutions | O(civs × institutions) | +1-3% | Negligible |
| M64 Commons | O(regions) | +0.5-1% | Negligible |
| M65 Elite/PSI | O(agents) + O(civs) | +2-4% | Piggyback on wealth_tick |
| M66 Legitimacy | O(civs) | +0.5-1% | Negligible |
| M68 Cultural Traits | O(agents × 8 traits) | +4-8% | **Primary risk.** Use algebraic sigmoid. |
| M69 Prestige | O(routes × goods) | +2-5% | Depends on patronage density |
| M70 Revolution | O(agents × 8 rels × iterations) | +2-4% avg, +8-15% spikes | Amortize checks (every 4 turns) |
| M71 Info Asymmetry | O(civs²) | +0.5-1% | Negligible |
| **Cumulative** | | **+15-30%** | **20-30× headroom remains** |

### Memory Budget

Current: 224 bytes/agent. Phase 8-9 adds ~24 bytes. New total: ~248 bytes/agent. At 1M agents: 248 MB (fits in 192GB DDR5 with 700× headroom). Cache pressure from memome (8 bytes in hot path) is the concern at 1M scale — place adjacent to cultural_value fields in SoA layout.

### Key Optimization

**Algebraic sigmoid for D=2:** `f²/(f²+(1-f)²)` saves ~90% of M68 per-agent cost. This single optimization keeps M68 within budget.

---

## 6. Academic Calibration Targets {#academic-calibration}

### Turchin (PSI / Secular Cycles)

- 200-300 turn secular cycles at standard turn length
- Conspicuous consumption ratchet faster than demographic reset (creates asymmetric cycle: slow rise, fast crash, slow recovery)
- All three sub-indices (MMP/EMP/SFD) must co-occur for crisis — if they don't naturally, soften exponents
- Nested 40-60 turn violence sub-cycle during disintegrative phases

### Ostrom (Commons)

- Commons collapse should be the DEFAULT without institutional guardrails (~90%+ of unmanaged civs)
- Graduated sanctions: warning → fine → temporary exclusion → permanent exclusion
- Resource VOLATILITY (not just depletion) stresses institutions independently
- Group size matters: large civs need polycentric governance or institutions strain

### Granovetter (Revolution)

- Threshold distribution must be BROAD (not Gaussian) for realistic partial cascades
- Add stochastic noise to thresholds for stability ("predictability paradox")
- Urban (dense) networks → bimodal cascades (fizzle or explode). Rural (sparse) → power-law (gradual spread).
- Bridge agents are disproportionately important — assassination literally prevents spread

### Boyd & Richerson (Cultural Traits)

- D = 2-3 for conformist bias (intermediate conformity outperforms extremes)
- Conformist + prestige bias can conflict when prestigious agents have rare traits
- Environmental crisis should temporarily weaken conformist bias (innovation during turmoil)
- Anti-conformist agents (D < 1) as cultural innovators and bridge agents

### Bueno de Mesquita (Selectorate)

- W/S ratio drives public vs private goods — small coalitions boost military, large boost infrastructure
- Medium W/S (0.15-0.40) is the most unstable regime (transition zone)
- Transitions between regime types create temporary vulnerability ("institutional trap")

---

## 7. Game Design Reference Values {#game-design-values}

| Parameter | Source | Value | Chronicler Application |
|-----------|--------|-------|----------------------|
| Legitimacy → political capital | Old World | +0.1 per point | `political_capital = base + legitimacy × 0.1` |
| Ambition completion bonus | Old World | +10 legitimacy | Ruler ambition reward |
| Ambition failure penalty | Old World | -5 legitimacy | Ruler ambition failure |
| Cognomen inheritance decay | Old World | 1/n for predecessor n | Dynasty legitimacy |
| Angry faction opposition multiplier | Victoria 3 | 1.5× stall weight | Institution blocking |
| Neutral faction opposition | Victoria 3 | 0.5× stall weight | Institution ease |
| Faction discontent threshold | CK3 | 80% military power ratio | Faction activation |
| Faction acceleration threshold | CK3 | 110% military power | Faction urgency |
| Scheme breach auto-failure | CK3 | 5 breaches | Espionage timeout |
| Memory slots | Dwarf Fortress | 8 short + 8 long | Agent memory budget (already 8) |
| Cultural era prerequisite gate | CK3 | 8 per era | Tech prerequisite count |
| Conformist bias D parameter | Academic | D = 2-3 optimal | Cultural trait transmission |

---

## 8. Degenerate Condition Guards {#degenerate-guards}

| Condition | Severity | Guard |
|-----------|----------|-------|
| Unbreakable military capture | High | Internal reform pressure at >70% faction influence for >30 turns |
| Simultaneous PSI + commons collapse | Critical | Subsistence floor; validate recovery in M67 oracle |
| Permanent revolt province | Medium | Forced assimilation as institutional option |
| Prestige monopoly stability trap | Medium | Ensure elite dilution fires even at stable supply |
| Soil floor permanent famine cycling | Medium | Region abandonment mechanic |
| Clergy theocratic capture | High | Same reform pressure as military |
| Mule-induced patronage collapse | Medium | Patronage resilience buffer (2-3 turns stored legitimacy) |
| Gaussian threshold distribution | High | Use agent-state-derived thresholds, not imposed distribution |
| One-way secular cycle (no recovery) | Critical | Validate recovery in ≥60% of crisis seeds (M67 gate) |

---

## 9. Narrative Integration Summary {#narrative-summary}

### Aggregate Counts

| Category | Current | Phase 8-9 Additions | New Total |
|----------|---------|---------------------|-----------|
| Event types | 44+ | ~37 new | ~81 |
| Causal patterns | 24 | ~57 new | ~81 |
| Narrator context blocks | 10 | 4 new + 3 extensions | 14 |
| Viewer components | 14 | 5 new + 12 extensions | ~26 |

### New Context Blocks

1. **`institutional_context`** — active institutions, enforcement status, faction alignment
2. **`secular_cycle_context`** — PSI sub-indices, cycle phase, elite ratio, wage trend
3. **`ruler_context`** — legitimacy, political capital, active ambitions, recent events
4. **`revolt_context`** — cascade origin, spread, bridge agents, suppression status (conditional — only during active cascades)

Plus extensions to existing cultural, ecology, and diplomacy blocks.

### Infrastructure Required

- Conditional narrator context injection (M70 — context blocks that fire only during active events)
- Multi-turn arc clustering in curator (M65/M66 — secular cycles and ambition arcs span 50-100+ turns)
- ERA_REGISTER trait vocabulary mapping (M68 — trait names in era-appropriate language)
- Dramatic irony narration pattern (M71 — narrator receives both actual and believed state)

### Bundle v2 Compatibility

All Phase 8-9 data fits within existing 7 layer kinds (summary, entities, timeline, metrics, overlays, networks, detail). No new layer kinds needed. Validates M62a's generic design.

---

## 10. Open Questions for Spec Resolution {#open-questions}

### Must Lock Before M63

1. **Weight cap mechanism.** Keep 2.5x with per-system ceilings? Raise to 3.5x? Priority ordering? → Resolve in M63 spec.
2. **Institution scope: per-civ or per-region?** Recommendation: per-civ first (ties to faction power), per-region for COMMONS_MANAGEMENT only.
3. **Max active institutions per civ.** Proposed: 3 (forces tradeoffs). Could be 4-5 for large empires.

### Must Lock Before M65

4. **Elite definition.** Proposed: wealth percentile > 0.90 OR high-skill occupation OR GreatPerson. Must be formal and locked.
5. **State debt proxy.** `state_debt` doesn't exist. Use governing_cost/treasury ratio until explicit debt lands.
6. **PSI exponent defaults.** Start at a=b=c=1.0 but implement the exponent form from day one.

### Must Lock Before M70

7. **Revolt awareness diffusion path.** Reuse M59 info propagation (planning default) or separate engine?
8. **Threshold distribution.** Must NOT be Gaussian. Derive from agent state (satisfaction × personality × traits).
9. **Cascade propagation.** Per-tick iterative (up to 3-5 rounds per turn) or single-pass per turn?

### Research Questions for M67/M72

10. **Do the three PSI sub-indices naturally co-occur?** If not, the multiplicative form needs softened exponents.
11. **Does the conspicuous consumption ratchet timescale match demographic reset?** If not, secular cycle becomes one-way.
12. **Does institutional capture create stable attractors?** If so, need reform pressure guard.
13. **What conformist bias D value produces cultural regions without lock-in?** Literature says 2-3; M72 validates.

---

## Appendix: RNG Stream Offset Registry (Phase 8-9)

| Proposed Offset | System | Milestone |
|-----------------|--------|-----------|
| 300 | `REVOLT_CASCADE_OFFSET` | M70 |
| 400 | `MEMOME_DRIFT_OFFSET` | M68 |
| 1000 | `ELITE_DYNAMICS_OFFSET` | M65 |
| 1200 | `INSTITUTION_VIOLATION_OFFSET` | M63 |
| 1500 | `PRESTIGE_GOODS_OFFSET` | M69 |
| 1600 | `LEGITIMACY_AMBITION_OFFSET` | M66 |

Standard formula: `stream = region_id * 1000 + turn + OFFSET`. Per-civ systems (elite dynamics, legitimacy) use `civ_id * 1000 + turn + OFFSET`.

---

## Appendix: FFI Signal Flow (Phase 8-9 Additions)

### Python → Rust (CivSignals extensions)

```rust
// M63
pub active_institutions: u32,           // bitmask
pub institutional_legitimacy: f32,      // 0.0-1.0
pub enforcement_cost_ratio: f32,        // cost / treasury

// M65
pub elite_positions: u16,
pub conspicuous_consumption_index: f32,
pub psi: f32,                           // lagged 1 turn

// M66
pub ruler_legitimacy: f32,
pub political_capital: f32,

// M68
pub trait_drift_multiplier: f32,
```

### Python → Rust (RegionState extensions)

```rust
// M64
pub exploitation_rate: f32,
pub commons_health: f32,

// M70
pub revolt_active: bool,
pub revolt_intensity: f32,
```

### Rust → Python (new output columns)

Elite classification in snapshot: `elite_status: u8`. EMP aggregate per-civ. Revolt events in events batch. Cultural trait frequencies in new batch or snapshot extension.

All follow existing optional-column pattern with `map_or` defaults — backward compatible.
