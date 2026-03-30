# Chronicler Phase 8 — Governance: Emergent Institutions & Secular Cycles

> **Status:** Draft. Phase 7 depth track validated through M53. Scale track (M54-M61b) in progress.
>
> **Phase 7 prerequisite:** M61b (Scale Validation & Calibration) validates depth + scale systems at 500K-1M agents. However, M63a/M63b and M66a/M66b have ZERO dependency on the scale track and can early-start after M53.
>
> **Structural principle:** Governance emerges from existing systems — factions propose institutions, treasury constrains enforcement, ecology creates commons dilemmas, demographics drive elite dynamics. Phase 8 adds the *rules layer* between individual agents and civilizational outcomes. Validate the secular cycle and institutional dynamics standalone before Phase 9 layers culture and revolution on top.
>
> **Academic grounding:** Turchin (structural-demographic theory, PSI), Ostrom (commons governance, graduated sanctions), Bueno de Mesquita (selectorate theory), HANDY model (elite-commons coupling), Maudet et al. (institutional life-cycles). See `references/phase8-9-academic-foundations.md`.
>
> **Game design precedents:** Old World (political capital, ambitions, cognomen inheritance), Victoria 3 (interest group opposition, directional sensitivity), CK3 (faction thresholds, schemes). See `references/phase8-9-game-design-references.md`.

---

## Why Governance

Phase 7 agents remember, want, bond, and inhabit space. But they live in a world without laws. There are no courts, no property rights, no succession norms, no tax codes. Factions compete for influence but have nothing concrete to fight over — no bill to pass, no institution to capture. Rulers exist as GreatPersons but have no political capital to spend, no legitimacy to earn or squander, no ambitions beyond the civ-level action distribution. The economy produces goods and the ecology constrains growth, but there's no *tragedy of the commons* — no mechanism where individual rational exploitation leads to collective ruin, and no institutional response that could prevent it.

Phase 8 introduces the structures that sit between individual agents and civilizational outcomes. Four capabilities that Phase 7 structurally cannot deliver:

1. **Institutions as emergent rule-sets.** Laws, norms, and governance structures that factions create, fight over, and that then constrain the simulation itself. Institutions have legitimacy that erodes when unenforced, and enforcement costs that drain the treasury — creating the fiscal-institutional crisis link that drives real civilizational collapse.

2. **Commons management and exploitation.** The tragedy of the commons as a mechanized feedback loop. Without institutional guardrails, rational individual exploitation leads to collective ecological ruin. The HANDY model's critical missing piece — wealthy agents extracting disproportionately from commons — creates the historically realistic dual collapse (inequality + overdepletion).

3. **Elite dynamics and secular cycles.** Turchin's structural-demographic theory as an emergent macro-rhythm. The PSI (Political Stress Indicator) product of mass mobilization, elite overproduction, and state fiscal distress drives a 200-300 turn secular cycle: expansion, stagflation, crisis, depression, recovery.

4. **Legitimacy and political capital.** Rulers earn legitimacy from victories, institutional support, dynastic prestige, and fulfilling personal ambitions. Everything costs political capital — a single shared budget (Old World's key insight). Low-legitimacy rulers can barely govern. Each reign becomes a narrative arc without scripting.

---

## Milestone Overview

| # | Milestone | Depends On | Est. Days |
|---|-----------|------------|-----------|
| M63a | Institution Data Model & Lifecycle | M53 (factions, treasury) | 3-4 |
| M63b | Institutional Effects & Weight Cap Revision | M63a | 3-5 |
| M64 | Commons & Exploitation | M63b, M54a (Rust ecology) | 4-6 |
| M65a | Elite Position Tracking & EMP | M53 (wealth_tick) | 2-3 |
| M65b | PSI Formula & Secular Cycle | M65a, M64 | 3-4 |
| M66a | Legitimacy & Political Capital | M39 (dynasty), M53 | 2-3 |
| M66b | Ruler Ambitions & Event Chains | M66a, M48 (memory) | 2-3 |
| M67 | Governance Tuning Pass | M63-M66, M61b | 4-6 |

**Core Phase 8 estimate:** 24-34 days across 8 milestones/sub-milestones. No contingency buffer.

**Early starts (before M61b):** M63a, M63b, M66a, M66b have zero dependency on Phase 7 scale track (M54-M61). Front-loads ~12-16 days of governance work without blocking on anything.

**Critical path:** `M63a -> M63b -> M64 -> M65b -> M67` (5 milestones, ~18-25 days). True gate: `M61b -> M67` (governance tuning gates on scale validation).

**Maximum parallelism:**

| Sprint | Milestones | Parallel? |
|--------|-----------|-----------|
| 1 (early, pre-M61b) | M63a -> M63b, M66a -> M66b | Yes (2 tracks) |
| 2 (post-M63b, pre-M61b) | M64, M65a (parallel start) | Partial |
| 3 (post-M64 + M65a) | M65b | Sequential |
| 4 (post-M61b + M65b + M66b) | M67 | Gate (sequential) |

---

## M63a: Institution Data Model & Lifecycle

### Goal

Define the `InstitutionType` enumerated set (16 types, 4 per faction alignment), the `InstitutionState` data model on `Civilization`, and the propose/repeal lifecycle driven by faction dominance. Institutions are a finite parameterized set (like ActionTypes and FactionTypes), not a generative grammar. ADICO informs the *design* of the enumerated set but is not the runtime representation.

### Depends On

- M53 (Depth Tuning Pass) — validated faction system, treasury mechanics
- Existing faction infrastructure in `factions.py`
- Existing governing cost framework in `politics.py`

### Storage / Data Model

```python
class InstitutionType(str, Enum):
    # Military faction
    MILITARY_ACCLAMATION = "military_acclamation"  # succession favors generals
    CONSCRIPTION = "conscription"                    # boosts military, tanks farmer satisfaction
    FRONTIER_GARRISONS = "frontier_garrisons"        # defensive bonus, treasury drain
    MARTIAL_LAW = "martial_law"                      # suppresses revolt, kills trade

    # Merchant faction
    PROPERTY_RIGHTS = "property_rights"              # reduces raid incentive, boosts investment
    FREE_TRADE = "free_trade"                        # increases trade volume, hurts local artisans
    MERCHANT_COURTS = "merchant_courts"              # trade dispute resolution, merchant satisfaction
    TAX_CODE = "tax_code"                            # treasury efficiency, compliance cost

    # Cultural faction
    WRITTEN_LAW = "written_law"                      # reduces governing cost, requires literacy
    PATRONAGE_SYSTEM = "patronage_system"            # boosts prestige, cultural output
    EDUCATION = "education"                          # tech advancement bonus, treasury drain
    REPUBLICAN_VIRTUE = "republican_virtue"          # broad legitimacy, conflicts with DIVINE_RIGHT

    # Clergy faction
    TEMPLE_TITHE = "temple_tithe"                    # faith income, tithe compliance
    DIVINE_RIGHT = "divine_right"                    # ruler legitimacy, conflicts with REPUBLICAN_VIRTUE
    HOLY_INQUISITION = "holy_inquisition"            # conversion boost, persecution penalty
    COMMONS_MANAGEMENT = "commons_management"        # extends overextraction limits (Ostrom)


class InstitutionState(BaseModel):
    institution_type: InstitutionType
    enacted_turn: int
    legitimacy: float = 1.0          # 0.0-1.0, erodes when unenforced
    enforcement_cost: float          # treasury drain per turn
    faction_alignment: str           # proposing faction type
    opposing_faction: str            # blocking faction type

    class Config:
        validate_assignment = False
```

Add to `Civilization`:
```python
institutions: list[InstitutionState] = []  # max 3 active
```

**Max 3 active institutions per civ.** Forces tradeoffs — a civ cannot have both MILITARY_ACCLAMATION and REPUBLICAN_VIRTUE, both FREE_TRADE and HOLY_INQUISITION. The constraint creates faction conflict over the scarce institutional slots.

### Mechanism

**Proposal (Phase 10, after `tick_factions()`):**
1. Identify dominant faction (influence > 0.35).
2. Check if an aligned institution is not already active.
3. Roll proposal against `INSTITUTION_PROPOSAL_PROBABILITY` `[CALIBRATE]`.
4. Block if opposing faction has influence > 0.30 (Victoria 3 adaptation: angry faction 1.5x stall weight, neutral 0.5x).
5. If not blocked, enact institution. Set `legitimacy = 1.0`, compute `enforcement_cost` from institution type and civ state.

**Enforcement cost computation:**
- Per-region cost: `FRONTIER_GARRISONS`, `CONSCRIPTION`, `COMMONS_MANAGEMENT`
- Per-trade-route cost: `FREE_TRADE`, `MERCHANT_COURTS`, `TAX_CODE`
- Flat cost: `EDUCATION`, `WRITTEN_LAW`, `PATRONAGE_SYSTEM`, others

**Legitimacy erosion:**
- Each turn: if treasury cannot fully pay enforcement cost, `legitimacy -= LEGITIMACY_EROSION_RATE` `[CALIBRATE]`.
- If treasury pays in full: `legitimacy` recovers slowly toward 1.0 (`+LEGITIMACY_RECOVERY_RATE` per turn `[CALIBRATE]`).
- If `legitimacy < 0.05`: institution auto-repealed (collapse from neglect).

**Repeal:**
- Opposing faction reaching influence > 0.40 can force repeal of an aligned-enemy institution.
- Repeal costs political capital (M66a) when available; before M66a, repeal is free but gated on faction threshold.

**Graduated sanctions (Ostrom):**
- Per-agent `institution_violation_count: u8` in Rust pool (+1 byte/agent).
- Violation count is per-institution type, not global.
- Sanction severity = `f(violation_count)`: warning -> fine -> temporary exclusion -> permanent exclusion.
- First warning is often sufficient (Ostrom finding); communities that jump to harsh punishment destabilize faster.

### Integration Points

- **`politics.py`**: `apply_governing_costs()` (lines 58-86) — each active institution adds to per-region cost baseline.
- **`factions.py`**: `tick_factions()` — proposal/repeal checks added after faction influence updates in Phase 10.
- **`models.py`**: New `InstitutionType` enum, `InstitutionState` model, `institutions` field on `Civilization`.
- **`accumulator.py`**: Institution enactment/repeal routed as `keep` category (applies in all modes).

### Gate

- 16 institution types defined with enforcement cost formulas.
- Propose/repeal lifecycle functional across 200-seed, 500-turn runs.
- Institutions form, persist, and collapse at reasonable rates (~1-3 active per civ at steady state).
- Enforcement cost correctly drains treasury via governing cost framework.
- Legitimacy erodes when unenforced and recovers when funded.
- Graduated sanctions track per-agent violation counts.
- No regression in Phase 6/7 calibrated behaviors with `--agents=off`.

### Constants

| Constant | Role | Target Range |
|----------|------|-------------|
| `MAX_ACTIVE_INSTITUTIONS` | Per-civ institution cap | 3 |
| `INSTITUTION_PROPOSAL_PROBABILITY` | Per-turn chance dominant faction proposes | `[CALIBRATE]` |
| `FACTION_DOMINANCE_THRESHOLD` | Influence needed to propose | 0.35 |
| `FACTION_BLOCK_THRESHOLD` | Opposing influence to block proposal | 0.30 |
| `ANGRY_FACTION_STALL_WEIGHT` | Opposition multiplier for angry faction (Vic3) | 1.5 |
| `NEUTRAL_FACTION_STALL_WEIGHT` | Opposition multiplier for neutral faction (Vic3) | 0.5 |
| `LEGITIMACY_EROSION_RATE` | Per-turn erosion when unenforced | `[CALIBRATE]` |
| `LEGITIMACY_RECOVERY_RATE` | Per-turn recovery when fully enforced | `[CALIBRATE]` |
| `LEGITIMACY_COLLAPSE_THRESHOLD` | Below this, institution auto-repeals | 0.05 |
| `FACTION_REPEAL_THRESHOLD` | Opposing influence to force repeal | 0.40 |

### Enrichments

> **Selectorate Theory (Bueno de Mesquita):** W/S ratio (winning coalition / selectorate) determines public vs private goods allocation: `private_goods_share = 1 - (W/S)`. Small-coalition regimes boost WAR/BUILD; large-coalition boost DEVELOP/TRADE. Leader survival condition: coalition members stay loyal if payoff > challenger's offer. Each government type gets mechanically different action weight modifiers. O(n) per turn. Deferred to M63b or later.

> **Institutional Evolution (Acemoglu/Robinson):** Institutions change when enforcement costs exceed state capacity. Transition triggers: Chiefdom -> Monarchy (external military threat + population growth), Monarchy -> Republic (faction conflict + elite competition + economic complexity), Any -> Autocracy (crisis + strong leader). Content for enriching the M63a institution set, not a separate milestone.

> **Legal system emergence:** 6 legal system types (customary, religious courts, trial by ordeal, merchant law, common law, codified law) as content within the enumerated institution set. Transition triggers: merchant law when trade_income > threshold, religious courts when clergy_power > threshold, codified law when literacy > 0.6.

---

## M63b: Institutional Effects & Weight Cap Revision

### Goal

Wire institution modifiers into action weights, satisfaction, and governing costs. Resolve the 2.5x action weight cap problem (REVIEW B-5) — the cap was designed for 3 multiplicative contributors (traditions, tech focus, factions); Phase 7 added Mule (4th), institutions would be 5th. Adding contributors without revising the cap silently nerfs existing systems.

### Depends On

- M63a (institution data model and lifecycle)

### Storage / Data Model

Add to `InstitutionState`:
```python
action_weight_modifiers: dict[str, float] = {}  # ActionType name -> multiplier
satisfaction_modifiers: dict[str, float] = {}    # modifier key -> value
```

Per-institution modifier tables are static constants defined in a lookup table keyed by `InstitutionType`.

### Mechanism

**Action weight modifiers:**
Each institution contributes multiplicative modifiers to specific ActionTypes. Examples:
- `PROPERTY_RIGHTS`: DEVELOP +1.2x, TRADE +1.1x, FUND_INSTABILITY 0.8x
- `CONSCRIPTION`: WAR +1.3x, DEVELOP 0.9x
- `FREE_TRADE`: TRADE +1.3x, EMBARGO 0.7x
- `MARTIAL_LAW`: WAR +1.2x, TRADE 0.7x, revolt suppression

**Weight cap revision (resolves REVIEW B-5):**

Per-system contribution ceilings applied *before* multiplication into the combined weight:

| System | Max Contribution | Source |
|--------|-----------------|--------|
| Trait weights | 2.0x | TRAIT_WEIGHTS table (existing) |
| Situational | 2.5x | Highest: military WAR at 2.5x (existing) |
| Faction influence | 1.5x | Power function of influence (existing) |
| Tech focus | 1.5x | Focus effects (existing) |
| Institutions | 1.5x | **New** — sum of institutional modifiers clamped |
| Mule | Existing utility_overrides with 0.1x floor | (existing) |

**Revised global cap: 3.5x** (up from 2.5x). The per-system ceilings prevent any single system from dominating. The global cap provides a hard safety net. The proportional rescale fires only when the product of per-system-clamped contributions exceeds 3.5x.

**Satisfaction effects:**
- `CONSCRIPTION`: farmer satisfaction penalty (guards context, not ecological)
- `MARTIAL_LAW`: trade income penalty -> merchant satisfaction
- `FREE_TRADE`: local artisan satisfaction penalty
- `HOLY_INQUISITION`: persecution satisfaction penalty (within 0.40 non-ecological cap)

**Governing cost interaction:**
Institution enforcement costs are additive to existing governing costs in `apply_governing_costs()`. Total governing cost = base governing cost + sum of active institution enforcement costs. This is the fiscal-institutional crisis link: when treasury is under stress, institutions become the first thing that suffers.

### Integration Points

- **`action_engine.py`**: Insert institutional modifiers after faction modifiers (line ~864) but before holy war bonus. Apply per-system 1.5x ceiling before combining.
- **`action_engine.py`**: Update combined weight cap from 2.5x to 3.5x. Add per-system ceilings for all 6 contributor categories.
- **`politics.py`**: `apply_governing_costs()` — add institutional enforcement cost sum.
- **`simulation.py`**: Wire institution satisfaction effects into appropriate accumulator categories.

### Gate

- All 16 institution types have defined action weight modifier tables.
- Per-system contribution ceilings prevent any single system from dominating action weights.
- Revised 3.5x global cap passes 200-seed regression (action distributions remain reasonable).
- Institutional satisfaction effects correctly route through the 0.40 non-ecological penalty cap.
- Institutional enforcement costs drain treasury via governing cost framework.
- `--agents=off` produces no regression in Phase 4 output.
- No single institution creates a degenerate attractor (e.g., permanent war state).

### Constants

| Constant | Role | Target Range |
|----------|------|-------------|
| `INSTITUTION_WEIGHT_CEILING` | Max combined institutional modifier per ActionType | 1.5x |
| `REVISED_GLOBAL_WEIGHT_CAP` | New combined weight cap (all systems) | 3.5x |
| `TRAIT_WEIGHT_CEILING` | Max trait contribution | 2.0x |
| `FACTION_WEIGHT_CEILING` | Max faction contribution | 1.5x |
| `TECH_FOCUS_WEIGHT_CEILING` | Max tech focus contribution | 1.5x |
| Per-institution modifier tables | ActionType -> multiplier per InstitutionType | `[CALIBRATE]` |

### Enrichments

> **Selectorate W/S ratio mechanics:** Wire W/S into public/private goods split, creating government-type-specific action weight profiles. Medium W/S (0.15-0.40) is the most unstable regime — the "institutional transition trap." Deferred — validate base institution effects first.

---

## M64: Commons & Exploitation

### Goal

Add per-region exploitation rate vs sustainable yield with lag-then-crash dynamics, the HANDY model's critical kappa coupling (wealthy agents extract disproportionately from commons), and institutional mitigation via `COMMONS_MANAGEMENT`. Without the kappa coupling, the historically realistic dual collapse (inequality + overdepletion) cannot emerge. Without institutional guardrails, ~90%+ of civs should over-extract during 500-turn runs (GovSim calibration target).

### Depends On

- M63b (COMMONS_MANAGEMENT institution type and effects)
- M54a (Rust ecology migration — `ecology.rs` is the integration target)
- Existing ecology substrate: `soil_pressure_streak`, `overextraction_streaks`, `resource_reserves`

### Storage / Data Model

Extend `RegionState` in Rust:
```rust
pub exploitation_rate: f32,     // current extraction rate
pub commons_health: f32,        // 0.0-1.0, derived from soil/water/forest
pub kappa_extraction: f32,      // elite extraction multiplier for this region
pub commons_managed: bool,      // COMMONS_MANAGEMENT institution active
```

Extend `EcologyConfig` (or equivalent per-region config):
```rust
pub overextraction_streak_limit: u16,   // default 35, raised by COMMONS_MANAGEMENT
pub soil_pressure_threshold: f32,       // default from EcologyConfig, raised by COMMONS_MANAGEMENT
```

### Mechanism

**Exploitation rate computation:**
```
exploitation_rate = base_extraction × farmer_count × (1 + miner_count × MINE_EXTRACT_MULTIPLIER)
                  × (1 + kappa_extraction)
```

Where `kappa_extraction` is the critical HANDY coupling:
```
kappa_extraction = KAPPA_BASE × mean_elite_wealth_in_region / KAPPA_WEALTH_SCALE
```

Elite agents extract more from the commons proportional to their wealth. This drives the Type-C dual collapse: inequality amplifies ecological crisis.

**COMMONS_MANAGEMENT institutional modifier:**
When active, modifies per-region ecology config:
- `overextraction_streak_limit` raised by `COMMONS_STREAK_EXTENSION` (slower degradation)
- `soil_pressure_threshold` raised by `COMMONS_PRESSURE_EXTENSION` (higher pop before pressure kicks in)
- Graduated sanctions reduce individual agent exploitation rate (via `institution_violation_count` from M63a)

**Lag-then-crash dynamics:**
The existing ecology substrate already has the lag-then-crash half-built:
- `soil_pressure_streak` (30-turn -> 2x degradation)
- `overextraction_streaks` (35-turn -> 10% permanent yield penalty)
- `resource_reserves` (mineral depletion)

M64 adds the kappa coupling that makes the crash *wealth-driven* and the COMMONS_MANAGEMENT institution that can delay it.

**Resource volatility interaction (Ostrom insight):**
Variable-yield resources (climate-affected agriculture) stress institutions differently than low-but-stable yields. Climate cycles interact with institutional stability via the *uncertainty* that makes rules harder to calibrate, not just via yield decline. The existing climate cycle system in `climate.py` provides the volatility — M64 wires it into institutional stress.

### Integration Points

- **`ecology.rs`**: `tick_depletion_feedback()` (lines 396-452) — add kappa_extraction field to RegionState, modify depletion computation.
- **`economy.py`**: Exploitation rate feeds into farmer income and food sufficiency calculations.
- **`simulation.py`**: Wire COMMONS_MANAGEMENT institutional modifier into ecology config before Phase 9 tick.
- **`accumulator.py`**: Commons events (overshoot, collapse, recovery) routed as `keep` category.

### Gate

- Exploitation rate correctly scales with farmer count, miner count, and elite wealth (kappa coupling).
- Without COMMONS_MANAGEMENT, ~90%+ of civs over-extract at some point during 500-turn runs (GovSim calibration target).
- With COMMONS_MANAGEMENT, sustainable equilibrium at ~60-80% of carrying capacity with moderate inequality (HANDY target).
- COMMONS_MANAGEMENT institutional modifier correctly extends streak limits and pressure thresholds.
- Kappa coupling creates visible divergence between high-inequality and low-inequality civs in resource depletion rates.
- Climate cycle volatility interacts with institutional stability independently of yield decline.
- No regression in existing ecology behavior when no institutions are active.

### Constants

| Constant | Role | Target Range |
|----------|------|-------------|
| `KAPPA_BASE` | Base elite extraction multiplier | `[CALIBRATE]` |
| `KAPPA_WEALTH_SCALE` | Wealth normalization for kappa | `[CALIBRATE]` |
| `MINE_EXTRACT_MULTIPLIER` | Mining extraction amplification | `[CALIBRATE]` |
| `COMMONS_STREAK_EXTENSION` | Additional turns before overextraction penalty (with institution) | `[CALIBRATE]` |
| `COMMONS_PRESSURE_EXTENSION` | Additional pop capacity before pressure (with institution) | `[CALIBRATE]` |
| `COMMONS_OVERSHOOT_THRESHOLD` | exploitation_rate / sustainable_yield ratio triggering events | `[CALIBRATE]` |
| `COMMONS_COLLAPSE_THRESHOLD` | commons_health below which irreversible degradation starts | `[CALIBRATE]` |

### Enrichments

> **HANDY model full ODE system:** Four coupled differential equations (commoner population, elite population, nature, wealth) as a parallel shadow model for validation. Run the ODE system with Chronicler's parameters and compare trajectories. Useful for calibration but not runtime.

> **Region abandonment mechanic:** When degradation exceeds recovery capacity for extended periods, regions become uninhabitable. Agents migrate out, region enters dormant state, slow rewilding begins. Natural brake on the permanent famine cycling degenerate condition.

---

## M65a: Elite Position Tracking & EMP

### Goal

Define elite positions based on civ size and institutional count, classify agents as commoners/elites/frustrated aspirants, track the conspicuous consumption ratchet within EMP (Elite Mobilization Potential). Piggybacks on the existing `wealth_tick()` per-civ sort — zero additional iteration cost for elite classification.

### Depends On

- M53 (validated wealth_tick, Gini computation)
- Existing `wealth_tick()` sort in `tick.rs`

### Storage / Data Model

New per-agent field in Rust pool:
```rust
pub elite_status: u8,  // 0=commoner, 1=elite, 2=frustrated_aspirant
```
+1 byte/agent. At 1M agents: 1MB.

New per-civ fields (Python-side, on `Civilization` or transient):
```python
elite_positions: int          # max(2, population // 100)
elite_count: int              # agents meeting elite criteria
frustrated_aspirant_count: int
conspicuous_consumption_index: float  # ratchets upward during elite overproduction
emp: float                    # Elite Mobilization Potential
```

### Mechanism

**Elite definition (must be locked in spec):**
An agent qualifies as elite if ANY of:
- `wealth_percentile > 0.90` within their civ
- Occupation in {Merchant, Scholar, Priest} AND skill >= 0.8
- GreatPerson status

**Elite positions:**
```
elite_positions = max(2, civ_population / 100)
```
Scales with civ size. Institutions that expand bureaucracy could increase positions (enrichment).

**Classification (in `wealth_tick()`):**
1. During the existing per-civ wealth sort, compute wealth percentile cutoffs.
2. For each agent: evaluate elite criteria. Count total qualifying agents.
3. Rank qualifying agents by wealth. Top `elite_positions` agents get `elite_status = 1`.
4. Remaining qualifying agents with `satisfaction < 0.3` get `elite_status = 2` (frustrated aspirant).
5. All others: `elite_status = 0`.

**Frustrated aspirant:** An agent who *qualifies* for elite status but cannot attain it AND is dissatisfied. These are the firebrands of Turchin's secular cycle — educated, capable, with no outlet for their ambition.

**Conspicuous consumption ratchet:**
```
consumption_pressure = elite_count / max(elite_positions, 1)
conspicuous_consumption_index += RATCHET_UP_RATE * max(0, consumption_pressure - 1.0)
conspicuous_consumption_index -= RATCHET_DOWN_RATE  # slow decay
conspicuous_consumption_index = clamp(conspicuous_consumption_index, 0.0, RATCHET_CAP)
```

The ratchet only goes up fast during elite overproduction (consumption_pressure > 1.0) and decays slowly. This asymmetry (fast rise, slow fall) is the key positive feedback: intra-elite competition drives up the cost of maintaining elite status, creating more frustrated aspirants, which amplifies competition further.

**EMP computation:**
```
EMP = (elite_count / max(elite_positions, 1)) * conspicuous_consumption_index
```

Stored on civ as transient one-turn-lagged signal (same pattern as Gini).

### Integration Points

- **`tick.rs`**: `wealth_tick()` — piggyback elite classification on existing per-civ sort. Zero extra iteration.
- **`ffi.rs`**: Export `elite_status` in agent snapshot Arrow batch. Export `emp`, `elite_count`, `frustrated_aspirant_count` in per-civ signals.
- **`models.py`**: New fields on `Civilization` for elite tracking.
- **`simulation.py`**: Compute and store EMP after agent tick in Phase 10.

### Gate

- Elite classification produces reasonable distributions (5-15% of agents qualify as elite in most civs).
- Frustrated aspirant count rises when elite_count exceeds elite_positions AND those surplus agents have low satisfaction.
- Conspicuous consumption ratchet rises during overproduction and decays slowly during equilibrium.
- EMP correctly reflects the product of elite surplus and consumption pressure.
- Zero additional iteration cost — classification piggybacks on existing wealth_tick sort.
- No regression in wealth_tick behavior or Gini computation.

### Constants

| Constant | Role | Target Range |
|----------|------|-------------|
| `ELITE_WEALTH_PERCENTILE` | Wealth threshold for elite qualification | 0.90 |
| `ELITE_SKILL_THRESHOLD` | Skill threshold for occupation-based qualification | 0.8 |
| `ELITE_POSITIONS_DIVISOR` | Population divisor for position count | 100 |
| `ELITE_POSITIONS_MIN` | Minimum positions per civ | 2 |
| `FRUSTRATED_ASPIRANT_SATISFACTION_THRESHOLD` | Max satisfaction for frustrated classification | 0.3 |
| `RATCHET_UP_RATE` | Consumption index increase rate during overproduction | `[CALIBRATE]` |
| `RATCHET_DOWN_RATE` | Consumption index decay rate | `[CALIBRATE]` |
| `RATCHET_CAP` | Maximum conspicuous consumption index | `[CALIBRATE]` |

### Enrichments

> **Institutional position expansion:** Certain institutions (EDUCATION, TAX_CODE) could increase elite_positions, absorbing aspirants into bureaucratic roles. Delays secular cycle but creates fiscal drag.

---

## M65b: PSI Formula & Secular Cycle

### Goal

Implement the Political Stress Indicator (PSI) as the product of three sub-indices — MMP (Mass Mobilization Potential), EMP (Elite Mobilization Potential, from M65a), and SFD (State Fiscal Distress) — computed in Phase 10 with one-turn lag. PSI drives the 200-300 turn secular cycle: expansion, stagflation, crisis, depression, recovery. Implement the exponent-ready form from day one: `PSI = MMP^a * EMP^b * SFD^c` with defaults `a=b=c=1.0`.

### Depends On

- M65a (EMP computation, elite classification)
- M64 (commons present for ecological amplifier calibration)
- Phase 7 extractors: `median_agent_wealth`, `urbanization_rate`, `youth_bulge_fraction`

### Storage / Data Model

Per-civ transient fields (one-turn-lagged, same pattern as Gini):
```python
_psi: float = 0.0            # composite PSI
_mmp: float = 0.0            # Mass Mobilization Potential
_emp: float = 0.0            # Elite Mobilization Potential (from M65a)
_sfd: float = 0.0            # State Fiscal Distress
_psi_crisis: bool = False    # True when PSI exceeds crisis threshold
```

### Mechanism

**MMP (Mass Mobilization Potential):**
```
relative_wage = median_agent_wealth / max(gdp_per_capita_proxy, 1)
MMP = (1 / max(relative_wage, 0.01)) * urbanization_rate * youth_bulge_fraction
```
- `relative_wage`: median wealth / GDP per capita. Inverted — low wages = high mobilization.
- `urbanization_rate`: fraction of agents in settlements (M56, or population density proxy pre-M56).
- `youth_bulge_fraction`: fraction of agents aged 15-30 (from demographics age distribution).

**EMP (Elite Mobilization Potential):** From M65a.

**SFD (State Fiscal Distress):**
```
fiscal_ratio = governing_cost / max(treasury, 1)
SFD = fiscal_ratio * (1 - institutional_legitimacy)
```
`state_debt` doesn't exist yet — `governing_cost / treasury` is the proxy. `institutional_legitimacy` is the mean legitimacy of active institutions (from M63a). If no institutions, `institutional_legitimacy = 0.0` (maximum distress contribution from legitimacy term).

**PSI composite:**
```
PSI = MMP^a * EMP^b * SFD^c    (defaults a=b=c=1.0)
```

The exponent-ready form allows M67 to soften or amplify individual sub-indices without restructuring the formula. If the three sub-indices don't naturally co-occur (the multiplicative form's calibration cliff), exponents < 1.0 prevent any single near-zero factor from collapsing the whole indicator.

**Turn loop placement:** Phase 10 (Consequences), after `tick_factions()`. PSI from turn N affects Phases 2-3 of turn N+1 as a one-turn-lagged signal — same pattern as `AgentBridge._gini_by_civ`.

**Crisis threshold crossing:**
When `PSI > PSI_CRISIS_THRESHOLD` `[CALIBRATE]`, set `_psi_crisis = True`. Crisis state triggers:
- Increased secession probability in `politics.py`
- Increased revolt susceptibility (consumed by M70 in Phase 9)
- Named event generation (`psi_crisis` event type)
- Fiscal crisis cascades through enforcement failure (M63 link)

**Secular cycle emergence:**
The cycle is NOT an exogenous clock. It emerges from timescale mismatch:
- **Positive loop (fast, ~30-60 turns):** Labor oversupply -> wage decline -> elite income rises -> elite overproduction -> conspicuous consumption ratchet -> PSI rises -> crisis
- **Negative loop (slow, ~100-200 turns):** Instability -> population decline -> labor scarcity -> wage recovery -> new integrative phase

The conspicuous consumption ratchet (M65a) creates asymmetry: slow rise, fast crash, slow recovery. This matches the historical secular cycle shape.

**Nested sub-cycle:** 40-60 turn violence sub-cycle ("fathers and sons" generational dynamics) manifests only during disintegrative phases (when `_psi_crisis = True`). Periodic violence spikes within the crisis period. Implementation: modulated secession/revolt probability with a secondary oscillator active only during crisis.

### Integration Points

- **`simulation.py`**: Phase 10 — compute MMP, SFD, PSI after `tick_factions()` and agent tick. Store on civ as one-turn-lagged transient.
- **`politics.py`**: PSI crisis state feeds into secession probability, governing cost spiral.
- **`accumulator.py`**: PSI crisis crossing generates `guard-shock` signal.
- **`curator.py`**: New event types: `psi_crisis`, `psi_recovery`, `secular_cycle_peak`, `secular_cycle_trough`, `elite_overproduction`, `conspicuous_consumption_ratchet`, `fiscal_crisis`.
- **`narrative.py`**: New `secular_cycle_context` narrator context block (~60-80 lines) — PSI sub-indices, cycle phase, elite ratio, wage trend.

### Gate

- PSI correctly computes as the product of three sub-indices with configurable exponents.
- One-turn lag correctly implemented (turn N PSI affects turn N+1).
- PSI crisis crossing triggers named events and increased instability.
- In 200-seed, 500-turn runs: PSI crisis seeds show crisis outcomes within 10-40 turns in >= 65% of those seeds (M67 draft gate, validated here directionally).
- Secular cycle emergence visible in long runs (200+ turns): expansion/crisis phases detectable in PSI time series.
- Conspicuous consumption ratchet timescale is asymmetric (rises faster than it falls).
- No regression in existing politics/secession behavior when PSI is below crisis threshold.

### Constants

| Constant | Role | Target Range |
|----------|------|-------------|
| `PSI_EXPONENT_MMP` | MMP exponent (a) | 1.0 (default) |
| `PSI_EXPONENT_EMP` | EMP exponent (b) | 1.0 (default) |
| `PSI_EXPONENT_SFD` | SFD exponent (c) | 1.0 (default) |
| `PSI_CRISIS_THRESHOLD` | PSI value triggering crisis state | `[CALIBRATE]` |
| `PSI_RECOVERY_THRESHOLD` | PSI value below which crisis ends | `[CALIBRATE]` |
| `CRISIS_SECESSION_MULTIPLIER` | Secession probability multiplier during PSI crisis | `[CALIBRATE]` |
| `SUBCYCLE_PERIOD` | Nested violence sub-cycle period (turns) | 40-60 |
| `SUBCYCLE_AMPLITUDE` | Violence spike magnitude during sub-cycle | `[CALIBRATE]` |
| `GDP_PER_CAPITA_PROXY` | Wealth proxy for relative wage computation | `[CALIBRATE]` |

### Enrichments

> **Analytical pre-validation:** Before M65b implementation, run an analytical model of the three sub-indices using Phase 7 M61 output data to determine whether the multiplicative form is viable. If sub-indices don't naturally co-occur, pre-configure exponents < 1.0.

> **PSI dashboard viewer component:** Three-panel display (MMP/EMP/SFD time series, composite PSI with crisis bands, secular cycle phase indicator). Highest-complexity new viewer component. Deferred to M73.

---

## M66a: Legitimacy & Political Capital

### Goal

Add ruler legitimacy and political capital as a single shared budget (Old World's key insight — everything competes for the same pool). Rulers earn legitimacy from victories, dynasty prestige, institutional support, and faction alignment. Political capital funds all governance actions. Low-legitimacy rulers can barely govern.

### Depends On

- M39 (dynasty tracking, succession)
- M53 (validated existing succession and governing cost mechanics)
- Existing succession logic in `politics.py`

**EARLY START — no Phase 7 scale dependency.** Only needs dynasty system from Phase 6.

### Storage / Data Model

Add to `Civilization` (or Leader model if one exists):
```python
ruler_legitimacy: float = 0.5      # 0.0-1.0
political_capital: float = 0.0     # accumulated, spent on governance
legitimacy_sources: dict[str, float] = {}  # breakdown for narration
```

### Mechanism

**Political capital generation:**
```
political_capital_per_turn = POLITICAL_CAPITAL_BASE + ruler_legitimacy * LEGITIMACY_TO_CAPITAL_RATE
```
Old World reference: +0.1 per legitimacy point. Typical mid-simulation: 0.5-1.5 political capital per turn.

**Political capital spending:**
Everything costs political capital from the single shared budget:

| Action | Cost |
|--------|------|
| Enact institution | 0.10 |
| Suppress secession | 0.20 |
| Diplomatic overture | 0.05 |
| Move army (per region) | 0.02 |
| Force repeal of institution | 0.15 |

Low-capital rulers cannot afford expensive governance actions. This creates the "weak ruler" dynamic where a ruler with low legitimacy enters a spiral: can't enact institutions -> institutions lapse -> legitimacy falls further -> less capital.

**Legitimacy sources:**

1. **Dynasty prestige:** Cognomen inheritance with 1/n decay for n-th predecessor (Old World adaptation). First ruler's cognomen at full value, second at 1/2, third at 1/3, etc.
2. **Institutional support:** Sum of aligned institution legitimacy values. A ruler whose trait matches an active institution's faction gets a legitimacy bonus.
3. **Victories:** +`VICTORY_LEGITIMACY_BONUS` per successful war, conquest, ambition completion (M66b). `DEFEAT_LEGITIMACY_PENALTY` per failed war or lost territory.
4. **Faction alignment:** `+FACTION_ALIGNMENT_BONUS` if ruler's trait matches dominant faction.

**Legitimacy formula:**
```
ruler_legitimacy = clamp(
    LEGITIMACY_BASE
    + dynasty_prestige_contribution
    + institutional_support_contribution
    + victory_contribution
    + faction_alignment_contribution,
    0.0, 1.0
)
```

**Succession legitimacy reset:**
On ruler succession (existing mechanics in `politics.py`), new ruler starts with legitimacy derived from:
- Inherited dynasty prestige (1/n decay)
- Current institutional state (stable institutions provide baseline)
- Succession type: peaceful succession gets `PEACEFUL_SUCCESSION_BONUS`, contested succession gets penalty

### Integration Points

- **`politics.py`**: Succession events trigger legitimacy reset. Political capital check gates governance actions.
- **`simulation.py`**: Legitimacy/capital computation in Phase 3 (Politics) or Phase 10.
- **`models.py`**: New fields on `Civilization`.
- **`accumulator.py`**: Legitimacy changes routed as `keep` category.
- **`ffi.rs`**: Export `ruler_legitimacy` and `political_capital` in CivSignals for Rust consumption.

### Gate

- Political capital correctly gates governance actions.
- Legitimacy sources compute correctly (dynasty, institutions, victories, factions).
- Succession correctly resets legitimacy with dynasty inheritance decay.
- Low-legitimacy rulers have visibly constrained governance capability.
- Political capital accumulation rate scales with legitimacy.
- No regression in existing succession mechanics.

### Constants

| Constant | Role | Target Range |
|----------|------|-------------|
| `POLITICAL_CAPITAL_BASE` | Base per-turn capital generation | `[CALIBRATE]` |
| `LEGITIMACY_TO_CAPITAL_RATE` | Capital per legitimacy point per turn | 0.1 (Old World) |
| `LEGITIMACY_BASE` | Starting legitimacy for new rulers | 0.5 |
| `VICTORY_LEGITIMACY_BONUS` | Per successful war/conquest | `[CALIBRATE]` |
| `DEFEAT_LEGITIMACY_PENALTY` | Per failed war/lost territory | `[CALIBRATE]` |
| `FACTION_ALIGNMENT_BONUS` | Bonus when ruler matches dominant faction | 0.3 |
| `PEACEFUL_SUCCESSION_BONUS` | Legitimacy bonus for orderly succession | `[CALIBRATE]` |
| `COGNOMEN_DECAY_FACTOR` | 1/n decay for n-th predecessor | 1/n |
| `ENACT_INSTITUTION_COST` | Political capital cost to enact | 0.10 |
| `SUPPRESS_SECESSION_COST` | Political capital cost to suppress | 0.20 |
| `DIPLOMATIC_OVERTURE_COST` | Political capital cost per overture | 0.05 |
| `MOVE_ARMY_COST` | Political capital per region moved | 0.02 |

### Enrichments

> **Old World-style cognomen system:** Ruler achievements earn cognomens ("the Great", "the Conqueror", "the Pious") with specific legitimacy values. Cognomens decay through inheritance. Max cognomen bonus: +100 legitimacy ("The Great" — Old World value). Creates dynasty narrative arcs.

---

## M66b: Ruler Ambitions & Event Chains

### Goal

Generate 2-3 randomized ambitions at ruler accession, filtered by civ state. Ambition completion raises legitimacy; failure erodes it. Wire into M48's memory system for loosely-coupled event chain prerequisites (Old World's "memory -> requirement -> event" pattern). Every reign becomes a narrative arc without scripting.

### Depends On

- M66a (legitimacy and political capital)
- M48 (agent memory system for event chain prerequisites)

### Storage / Data Model

```python
class AmbitionType(str, Enum):
    CONQUER_REGION = "conquer_region"          # military state high -> eligible
    BUILD_WONDER = "build_wonder"              # treasury > threshold -> eligible
    ESTABLISH_TRADE = "establish_trade"        # trade routes exist -> eligible
    RELIGIOUS_CONVERSION = "religious_conversion"  # clergy influence high -> eligible
    EXPAND_TERRITORY = "expand_territory"      # frontier regions -> eligible
    PATRON_OF_ARTS = "patron_of_arts"          # cultural faction influence -> eligible
    DIPLOMATIC_TRIUMPH = "diplomatic_triumph"  # multiple diplomatic contacts -> eligible


class Ambition(BaseModel):
    ambition_type: AmbitionType
    target: Optional[str] = None       # region name, civ name, etc.
    generated_turn: int
    deadline_turn: int                 # 20-40 turns after generation
    completed: bool = False
    failed: bool = False

    class Config:
        validate_assignment = False
```

Add to `Civilization`:
```python
ruler_ambitions: list[Ambition] = []  # 2-3 active per ruler
```

### Mechanism

**Ambition generation (at ruler accession):**
1. Filter ambition pool by civ state eligibility conditions.
2. Weight eligible ambitions by ruler trait alignment (military ruler -> CONQUER_REGION weighted higher).
3. Select 2-3 ambitions without replacement.
4. Set deadline: `current_turn + randint(AMBITION_MIN_DURATION, AMBITION_MAX_DURATION)`.
5. Set target where applicable (e.g., specific region to conquer, specific civ to establish trade with).

**Completion check (Phase 10):**
Each turn, check active ambitions against civ state:
- `CONQUER_REGION`: target region in civ.regions?
- `BUILD_WONDER`: temple/infrastructure built since generation?
- `ESTABLISH_TRADE`: active trade route with target?
- etc.

On completion: `+AMBITION_COMPLETION_LEGITIMACY` to ruler legitimacy (Old World: +10), generate `ambition_fulfilled` named event. Write completion memory to ruler's M48 memory buffer.

**Failure (deadline reached without completion):**
`-AMBITION_FAILURE_LEGITIMACY` (Old World: -5), generate `ambition_failed` named event. Write failure memory to ruler's buffer.

**Event memory chains (Old World adaptation):**
Add `memory_tags: set[str]` to GreatPerson memories (M48). Event templates specify `requires_memory_tags` and `grants_memory_tags`.

Example chain:
1. Ruler offends a foreign leader at a diplomatic event -> grants tag `"offended_by_{civ_name}"`
2. Years later, offended leader's heir accedes -> event checks for `"offended_by_{civ_name}"` + `"{civ_name}_new_ruler"` -> triggers diplomatic crisis event

The coupling is loose — events grant and require *tags*, not specific prior events. This scales: different event writers can create compatible prerequisites without coordination.

### Integration Points

- **`simulation.py`**: Phase 10 — ambition completion checks after action resolution.
- **`politics.py`**: Ruler succession triggers ambition generation.
- **`curator.py`**: `ambition_fulfilled` and `ambition_failed` as high-priority named events. Memory tag prerequisites for event chain generation.
- **`narrative.py`**: New `ruler_context` narrator context block (~40-50 lines) — legitimacy, political capital, active ambitions, recent events.
- **`models.py`**: New `AmbitionType` enum, `Ambition` model, `ruler_ambitions` field on `Civilization`.

### Gate

- 2-3 ambitions generated at each ruler accession, filtered by civ state.
- Ambitions complete when conditions met, fail at deadline.
- Legitimacy correctly updated on completion (+10) and failure (-5).
- Memory tags written on ambition events.
- At least one event chain fires from memory tag prerequisites in 200-seed, 500-turn runs.
- Ambition generation does not produce nonsensical targets (landlocked civ getting naval ambitions, etc.).
- No regression in existing succession mechanics.

### Constants

| Constant | Role | Target Range |
|----------|------|-------------|
| `AMBITIONS_PER_RULER` | Number of ambitions at accession | 2-3 |
| `AMBITION_MIN_DURATION` | Minimum turns before deadline | 20 |
| `AMBITION_MAX_DURATION` | Maximum turns before deadline | 40 |
| `AMBITION_COMPLETION_LEGITIMACY` | Legitimacy bonus on completion | +10 (Old World) |
| `AMBITION_FAILURE_LEGITIMACY` | Legitimacy penalty on failure | -5 (Old World) |
| `AMBITION_MILITARY_WEIGHT` | Weight for military ambitions if ruler is military | `[CALIBRATE]` |
| `AMBITION_CULTURAL_WEIGHT` | Weight for cultural ambitions if ruler is cultural | `[CALIBRATE]` |

### Enrichments

> **DF-inspired villain emergence:** A frustrated elite (M65a) with a grudge memory (M48), high wealth, and faction alignment could become an active conspirator — recruiting bridge agents into a plot to capture an institution or destabilize a rival. Not a scripted arc: the system state produces the plot. Likely a curator enhancement rather than a new simulation system.

> **Extended event chain vocabulary:** More memory tags and event templates covering dynastic grudges, trade disputes, religious conflicts, cultural clashes. Each new tag pair is a potential multi-turn narrative arc.

---

## M67: Governance Tuning Pass

### Goal

Calibrate M63-M66 systems and validate emergent governance behavior across 200-seed runs. This is the GATE MILESTONE: secular cycle must emerge, PSI must predict crisis, institutions must exhibit all three Maudet regimes (frozen, fluctuating, complex cycling), and the ratchet/reset timescale must balance so secular cycles recover rather than one-way collapse.

### Depends On

- M63a, M63b (institutional emergence and effects)
- M64 (commons and exploitation)
- M65a, M65b (elite dynamics and PSI)
- M66a, M66b (legitimacy and ambitions)
- M61b (scale validation — governance tuning gates on scale validation to ensure behavior holds at 500K-1M agents)

### Mechanism

**Method:** Same as M47/M53 — 200-seed x 500-turn runs, metric extraction, constant adjustment.

**Validation targets:**

*PSI predictiveness:*
- In seeds with PSI crisis crossing, crisis outcomes (succession crisis, institutional collapse, secession spike, revolt) occur within 10-40 turns in >= 65% of those seeds.
- All three PSI sub-indices (MMP/EMP/SFD) exceed calibration thresholds in the same 20-turn window for >= 50% of crisis seeds (co-occurrence integrity).
- If sub-indices don't naturally co-occur, soften exponents (a, b, c) below 1.0.

*Secular cycle recovery:*
- In crisis seeds, >= 60% show recovery trajectory (not one-way collapse) within 120 turns after peak PSI.
- If the conspicuous consumption ratchet accelerates faster than the demographic reset, adjust `RATCHET_DOWN_RATE` until timescales balance.
- Asymmetric cycle shape visible: slow rise, fast crash, slow recovery.

*Institutional regime reachability:*
- Across calibration sweeps, all 3 institutional regimes appear in >= 10% of tested runs:
  - **Frozen/stable:** Institutions form fast, lock society into stable but rigid patterns.
  - **Highly fluctuating:** Institutions exist briefly, high trust but no stability.
  - **Complex cycling:** Institutions structure and destructure in irregular waves (narratively richest).

*Legitimacy and ambitions:*
- Political capital constraints visibly affect governance capability in low-legitimacy periods.
- Ambition completion/failure generates named events at reasonable rates.
- Dynasty legitimacy decay (1/n) produces visible multi-generational arcs.

*Degenerate condition checks:*
- Unbreakable military capture: verify reform pressure guard fires at >70% influence for >30 turns.
- Simultaneous PSI + commons collapse: verify recovery path exists (subsistence floor).
- One-way secular cycle: verify >= 60% recovery rate (the critical gate).
- Clergy theocratic capture: verify same reform pressure as military.

*Regression:*
- No regression in Phase 6/7 calibrated behaviors.
- `--agents=off` produces bit-identical Phase 4 output.

### Gate

| Gate | Threshold |
|------|-----------|
| Crisis predictiveness | PSI crisis -> outcomes within 10-40 turns in >= 65% of crisis seeds |
| Co-occurrence integrity | All three PSI sub-indices exceed threshold in same 20-turn window for >= 50% |
| Secular-cycle recovery | >= 60% of crisis seeds show recovery within 120 turns |
| Institutional regime reachability | All 3 regimes (frozen/fluctuating/cycling) in >= 10% of runs |
| Legitimacy constraint | Low-legitimacy periods produce measurably different governance rates |
| Degenerate condition guards | All 4 guards verified functional |
| Runtime budget | Combined M63-M66 additions within planned envelope (+5-9% total) |
| Regression | No regression in Phase 6/7 calibrated behaviors |

### Constants Tuned

All `[CALIBRATE]` constants from M63-M66, plus:

| Constant | Role | Target Range |
|----------|------|-------------|
| `PSI_EXPONENT_MMP` | May be softened from 1.0 if sub-indices don't co-occur | 0.5-1.0 |
| `PSI_EXPONENT_EMP` | May be softened | 0.5-1.0 |
| `PSI_EXPONENT_SFD` | May be softened | 0.5-1.0 |
| `PSI_CRISIS_THRESHOLD` | Threshold for crisis state | `[CALIBRATE]` |
| Per-institution modifier tables | Fine-tune all 16 institution types' action weight effects | `[CALIBRATE]` |
| `KAPPA_BASE` | Elite extraction coupling strength | `[CALIBRATE]` |
| `RATCHET_UP_RATE` / `RATCHET_DOWN_RATE` | Consumption ratchet timescale balance | `[CALIBRATE]` |

### Enrichments

> **Governance diagnostics in analytics:** PSI distribution histograms, regime frequency counts, cycle timing measurements, crisis-to-outcome lag distributions. Add to `analytics.py` BatchAnalytics for automated validation.

> **Oracle shadow model:** Run Turchin's analytical secular cycle model in parallel with Chronicler's PSI, compare trajectories. Useful for identifying when Chronicler's emergent behavior diverges from the analytical prediction and why.

---

## Phase 7 → Phase 8 Dependency Table

| Phase 8 System | Consumes from Phase 7 | Specific Milestone |
|----------------|----------------------|-------------------|
| Institutions (M63) | Factions (M22/M38), treasury (Phase 2), agent occupations, governing costs (`politics.py`) | M47 (tuning validates factions) |
| Commons (M64) | Ecology (Phase 9 turn loop), Rust ecology migration, spatial positioning | M54a (Rust ecology), M55a (spatial substrate) |
| Elite dynamics (M65) | Wealth distribution (M41 Gini), GreatPerson count, dynasty tracking, `wealth_tick()` sort | M39 (dynasties), M41 (wealth), M53 (depth tuning) |
| PSI computation (M65b) | `median_agent_wealth`, `urbanization_rate`, `youth_bulge_fraction` from Phase 7 extractors | M61b (scale validation exposes PSI input quantities) |
| Legitimacy (M66) | Dynasty system, Mule system, artifacts, succession/governing cost mechanics | M39 (dynasties), M48 (Mule), M52 (artifacts) |
| Ruler ambitions (M66b) | Agent memory ring buffer for event chain prerequisites | M48 (agent memory) |

**Phase 7 extractor requirement:** M61b's extractor suite must compute and expose `median_agent_wealth` (for relative wage), `urbanization_rate` (from M56 settlements), and `youth_bulge_fraction` (from demographics age distribution). These are cheap to extract and prevent a data gap at Phase 8 start. `state_debt` does not exist yet — Phase 8 M65/M66 introduces a proxy.

---

## Early-Start Analysis

Four milestones have **zero dependency on the Phase 7 scale track** (M54-M61) and can start with only the Depth track (M47-M53) complete:

| Milestone | Prerequisites (all Phase 6) | Why It Can Start Early |
|-----------|----------------------------|----------------------|
| M63a — Institution Data Model | Factions + treasury from Phase 6 | Data model and lifecycle mechanics operate at civ level, no agent-scale dependency |
| M63b — Effects & Cap Revision | M63a | Resolves REVIEW B-5 (2.5x cap) before more modifiers are added — front-loading prevents silent nerfs |
| M66a — Legitimacy & Political Capital | M39 (dynasty), existing succession in `politics.py` | Hooks existing succession mechanics, no spatial or scale dependency |
| M66b — Ruler Ambitions & Event Chains | M66a, M48 (agent memory) | Hooks M48 memory for event chain prerequisites, no scale dependency |

**Recommended early start:** M63a → M63b → M66a → M66b in parallel with Phase 7 scale track. Front-loads ~12-16 days of governance work without blocking on anything. M64 and M65 must wait for M54a (Rust ecology) and M61b (scale validation) respectively.

---

## Dependency Graph

```text
M47 (Phase 6 tuning)
  |
  +-> M63a (Institution Data Model) -----> M63b (Effects & Cap Revision)
  |                                              |
  |                                              +-> M64 (Commons) <- M54a (Rust Ecology)
  |                                                    |
  |                                                    +-> M65a (Elite Tracking & EMP)
  |                                                          |
  |                                                          +-> M65b (PSI & Secular Cycle)
  |                                                                |
  +-> M66a (Legitimacy) <- M39 (Dynasty)                          |
       |                                                          |
       +-> M66b (Ambitions) <- M48 (Memory)                      |
                                                                  |
M61b (Scale Validation) -----------------------------------------+
  |
  +-> M67 (Governance Tuning Pass) <- M63a-b, M64, M65a-b, M66a-b

Early-start tracks (parallel with Phase 7 scale):
  Track A: M63a -> M63b  (institutions)
  Track B: M66a -> M66b  (legitimacy/ambitions)

Post-scale track:
  M64 -> M65a -> M65b -> M67  (commons -> elites -> PSI -> tuning)
```

Critical path: `M63a -> M63b -> M64 -> M65a -> M65b` then blocked on `M61b -> M67`. True critical path length: M61b → M67 (governance tuning gates on scale validation).

---

## Design Decisions

| # | Decision | Planning Default | Lock By | Rationale |
|---|----------|------------------|---------|-----------|
| D1 | Action-weight cap mechanics with institutions | Per-system contribution ceilings (trait 2.0x, situational 2.5x, faction 1.5x, tech 1.5x, institutions 1.5x, Mule per existing). Revised global cap: 3.5x | M63b spec | 2.5x cap designed for 3 contributors. Phase 7 adds Mule (4th), institutions (5th). Without revision, new contributors silently nerf existing systems (REVIEW B-5) |
| D2 | Institution scope | Per-civ first (ties to faction power); per-region for COMMONS_MANAGEMENT only | M63a spec | Per-region institutions add O(regions x institutions) complexity; per-civ is sufficient for faction dynamics |
| D3 | Max active institutions per civ | 3 (forces tradeoffs) | M63a spec | Higher counts reduce tension between faction-aligned institutions |
| D4 | Elite definition | Wealth percentile > 0.90 within civ OR high-skill occupation (merchant/scholar/priest skill >= 0.8) OR GreatPerson. Positions = `max(2, pop/100)`. Frustrated aspirant = qualifies but no position AND satisfaction < 0.3 | M65a spec | Formal definition required for EMP. Must be locked before any elite-consuming system |
| D5 | State debt proxy | `governing_cost / max(treasury, 1)` ratio for SFD until M66 introduces explicit debt tracking | M65b spec | `state_debt` doesn't exist. Proxy is cheap, directionally correct, upgradeable |
| D6 | PSI formula interface | Implement exponent-ready form: `PSI = MMP^a * EMP^b * SFD^c` with defaults `a=b=c=1.0` | M65b spec | Avoids post-M67 rework if pure multiplicative doesn't work. Configurable exponents provide escape hatch |
| D7 | The κ coupling (HANDY model) | `elite_extraction_rate = base_rate * f(wealth_percentile)` | M64 spec | Without this, Type-C dual collapse (inequality + overdepletion) cannot emerge |
| D8 | PSI input extractors | `median_agent_wealth`, `urbanization_rate`, `youth_bulge_fraction` as required Phase 7 extractor outputs | M63 kickoff | Prevents data gap at Phase 8 start. Cheap to extract in M61b |
| D9 | Institutional enforcement costs | Map onto existing `apply_governing_costs()` in `politics.py`. Each institution adds to per-region cost baseline | M63a spec | Reuses existing fiscal framework. Enforcement failure from treasury collapse creates natural institutional decay |
| D10 | Political capital as single shared budget | `political_capital_per_turn = base + legitimacy * 0.1`. Spend on: enact (-0.1), suppress (-0.2), diplomatic (-0.05), move army (-0.02/region) | M66a spec | Old World's key insight: everything competes for the same pool. Low-capital rulers can barely govern |

---

## Per-Agent Memory Budget

| System | Bytes/agent | At 50K | At 500K | At 1M |
|--------|-------------|--------|---------|-------|
| Phase 7 baseline | 242 | 12.1MB | 121MB | 242MB |
| Institution violation count (M63) | 1 | 0.05MB | 0.5MB | 1MB |
| Elite status (M65) | 1 | 0.05MB | 0.5MB | 1MB |
| **Phase 8 total** | **244** | **12.2MB** | **122MB** | **244MB** |

244MB at 1M agents. 192GB DDR5 provides ~787x headroom. Phase 8 per-agent additions are negligible — governance operates primarily at civ/region level. PSI, institutional legitimacy, political capital, and ruler ambitions are per-civ fields (Python-side), not per-agent.

---

## Performance Budget

**Current headroom: 27-47x at 10K agents** (~0.25ms/tick vs 6s target). All Phase 8 overhead fits comfortably.

| Milestone | Complexity | Turn-Time Overhead | Key Risk |
|-----------|-----------|-------------------|----------|
| M63 Institutions | O(civs x institutions) | +1% to +3% | Negligible — not O(agents) |
| M64 Commons | O(regions) | +0.5% to +1% | Per-region exploitation extends existing ecology tick |
| M65a Elite/EMP | O(agents) + O(civs) | +1% to +2% | Piggybacks on existing `wealth_tick()` sort — zero extra iteration |
| M65b PSI | O(civs) | +0.5% to +1% | Three multiplications per civ |
| M66 Legitimacy/Ambitions | O(civs + ruler events) | +0.5% to +1% | Per-civ computation, low frequency events |
| M67 Tuning Pass | Validation/oracles | No new steady-state | Oracle overhead is profiling-only |
| **Cumulative Phase 8** | | **+3.5% to +8%** | **25-45x headroom remains** |

Phase 8's scaling risks begin in Phase 9 (M68 cultural traits at O(agents x 8 traits)), not here.

---

## New Constants Summary

| Constant | Source | Calibrate In | Default |
|----------|--------|-------------|---------|
| `MAX_ACTIVE_INSTITUTIONS` | M63a | M63 spec (locked) | 3 |
| `INSTITUTION_PROPOSAL_PROBABILITY` | M63a | M67 | `[CALIBRATE]` |
| `FACTION_DOMINANCE_THRESHOLD` | M63a | M67 | 0.35 |
| `LEGITIMACY_EROSION_RATE` | M63a | M67 | `[CALIBRATE]` |
| `LEGITIMACY_RECOVERY_RATE` | M63a | M67 | `[CALIBRATE]` |
| `INSTITUTION_WEIGHT_CEILING` | M63b | M67 | 1.5x |
| `REVISED_GLOBAL_WEIGHT_CAP` | M63b | M67 | 3.5x |
| `REFORM_PRESSURE_INFLUENCE_THRESHOLD` | M63b | M67 | 0.70 |
| `REFORM_PRESSURE_DURATION_THRESHOLD` | M63b | M67 | 30 turns |
| `KAPPA_BASE` | M64 | M67 | `[CALIBRATE]` |
| `COMMONS_STREAK_EXTENSION` | M64 | M67 | `[CALIBRATE]` |
| `ELITE_WEALTH_PERCENTILE` | M65a | M67 | 0.90 |
| `ELITE_POSITIONS_DIVISOR` | M65a | M67 | 100 |
| `RATCHET_UP_RATE` | M65a | M67 | `[CALIBRATE]` |
| `RATCHET_DOWN_RATE` | M65a | M67 | `[CALIBRATE]` |
| `PSI_EXPONENT_MMP` / `EMP` / `SFD` | M65b | M67 | 1.0 |
| `PSI_CRISIS_THRESHOLD` | M65b | M67 | `[CALIBRATE]` |
| `POLITICAL_CAPITAL_BASE` | M66a | M67 | `[CALIBRATE]` |
| `LEGITIMACY_TO_CAPITAL_RATE` | M66a | M67 | 0.1 (Old World) |
| `AMBITION_COMPLETION_LEGITIMACY` | M66b | M67 | +10 (Old World) |
| `AMBITION_FAILURE_LEGITIMACY` | M66b | M67 | -5 (Old World) |
| `COGNOMEN_DECAY_FACTOR` | M66a | M67 | 1/n |

~24 new constants. All deferred to M67 governance tuning pass. Constants with game design reference values have starting defaults; others are `[CALIBRATE]`.

---

## Determinism Guardrails

Phase 8 inherits all Phase 7 determinism rules. Phase 8 additions:

- **Institutional proposal ordering.** When multiple factions qualify to propose in the same turn, sort by `(faction_index, institution_type_index)` — never by faction influence (floating-point ties) or Python dict iteration order.
- **Elite classification stability.** Elite status derived from `wealth_tick()` sort must produce identical classification regardless of thread count. Tie-breaking on wealth percentile boundaries uses `agent_id` as secondary key.
- **PSI one-turn lag.** PSI from turn N feeds Phases 2-3 of turn N+1. Store explicitly (like `_gini_by_civ`), not recomputed from stale state. Clear transient PSI buffers before the return in Phase 10.
- **Political capital spending order.** When multiple actions compete for the same budget in a turn, resolution follows fixed priority (enact > suppress > diplomatic > military movement), not arrival order or floating-point comparison.
- **Ambition generation determinism.** Use reserved RNG stream (`LEGITIMACY_AMBITION_OFFSET`), not the civ-level action RNG. Sort candidates by enum index before selection.

---

## Risk Register

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| R1 | Unbreakable military faction capture — self-reinforcing loop with no exit | High | Reform pressure at >70% influence for >30 turns. Same guard for clergy theocratic capture |
| R2 | Simultaneous PSI + commons collapse with no recovery path | Critical | Subsistence floor mechanism; M67 oracle validates recovery exists |
| R3 | One-way secular cycle — ratchet faster than demographic reset | Critical | M67 gate: >=60% of crisis seeds show recovery within 120 turns. PSI exponents (D6) provide calibration escape |
| R4 | 2.5x weight cap silent nerf from adding 5th contributor | High | D1 resolves cap before M63b implementation. Per-system ceilings prevent cross-system interference |
| R5 | PSI sub-indices don't naturally co-occur — multiplicative form collapses | Medium | Exponent-ready form (D6). If M67 shows poor co-occurrence, soften exponents below 1.0 |
| R6 | 0.40 satisfaction penalty budget crowding from Phase 9 additions | Medium | Phase 8 operates through political capital/legitimacy, not satisfaction. Flag for Phase 9 spec |
| R7 | Permanent revolt province — conquered, culturally distant regions loop | Medium | Forced assimilation as institutional option. Depopulation as natural brake |
| R8 | Calibration cascade across tuning passes (M47→M53→M67) | Medium | Constant-locking: M47/M53 constants cannot be re-tuned in M67 without explicit approval |
| R9 | Soil floor permanent famine cycling | Medium | Region abandonment mechanic (M64 enrichment). COMMONS_MANAGEMENT extends recovery |
| R10 | Phase 7→8 elite concept bridge gap | Low | Elite classification piggybacks on `wealth_tick()` sort (D4). M61b extractors provide PSI inputs (D8) |

---

## Scope Containment Triggers

1. **Effort overrun:** If a milestone exceeds its draft effort window by >25%, cut enrichments before changing core acceptance gates.
2. **Runtime budget miss:** If runtime budget misses by >15% across two profiling passes, freeze new feature surface and tune current mechanics first.
3. **Unresolved decision locks:** If a milestone starts with unresolved decision locks, do not begin implementation until the lock section is resolved in spec.
4. **Tuning pass failure:** If M67 draft gates fail two consecutive calibration cycles, reduce model surface (fewer mechanics) before adding enrichments.
5. **Downstream pressure:** If Phase 9 milestones (M68-M72) are blocked by Phase 8 instability, prioritize M67 tuning over new Phase 8 enrichments.

---

## Cross-System Interactions (Phase 9 Payoffs)

These interactions require both Phase 8 Governance and Phase 9 Culture to be present. They are Phase 9 validation targets, listed here for forward reference:

1. **Secular cycle -> institutional collapse:** PSI spike -> fiscal crisis -> enforcement failure -> PROPERTY_RIGHTS lapse -> immiseration -> PSI rises further.

2. **Elite overproduction -> institutional capture:** Frustrated elites push for faction-aligned institutions, creating self-reinforcing institutional lock-in.

3. **Prestige goods -> legitimacy -> institutional stability:** Prestige disruption cascades through patronage -> legitimacy -> institutions -> fiscal crisis.

4. **Commons overshoot -> elite conflict:** Ecological crisis amplifies elite overproduction, compressing the secular cycle's expansion phase.

5. **PSI + commons simultaneous collapse:** The "perfect storm" — compound recovery may be structurally impossible without subsistence floor guard.

---

## Narrative Examples

These are the kinds of chronicles Phase 8 should produce:

> *"The merchant courts of Velanya resolved disputes without bloodshed for three generations. But when the treasury collapsed under Kiral the Profligate, the courts went unpaid. By the time his daughter restored order, the merchants had already turned to hired swords — and the institution of mercantile law was a memory."*

> *"The court of Ashara grew fat with would-be governors — forty nobles vying for twelve seats. When the treasury could no longer pay the frontier garrisons, three of the passed-over lords raised their own armies."*

> *"The valley of Tessara fed three cities for a century. No one noticed the soil thinning beneath the wheat until the year the rains came late. The granaries held barely a season's reserve, and the surplus nobles — forty families with ancestral claims to land that could no longer feed them — turned on each other."*

---

## RNG Stream Offsets (Phase 8)

| Proposed Offset | System | Milestone |
|-----------------|--------|-----------|
| 1000 | `ELITE_DYNAMICS_OFFSET` | M65 |
| 1200 | `INSTITUTION_VIOLATION_OFFSET` | M63 |
| 1600 | `LEGITIMACY_AMBITION_OFFSET` | M66 |

Standard formula: per-civ systems use `civ_id * 1000 + turn + OFFSET`.

---

## FFI Signal Flow (Phase 8 Additions)

### Python -> Rust (CivSignals extensions)

```rust
// M63
pub active_institutions: u32,           // bitmask of InstitutionType
pub institutional_legitimacy: f32,      // 0.0-1.0, mean of active institutions
pub enforcement_cost_ratio: f32,        // total enforcement cost / treasury

// M65
pub elite_positions: u16,
pub conspicuous_consumption_index: f32,
pub psi: f32,                           // lagged 1 turn

// M66
pub ruler_legitimacy: f32,
pub political_capital: f32,
```

### Python -> Rust (RegionState extensions)

```rust
// M64
pub exploitation_rate: f32,
pub commons_health: f32,
pub kappa_extraction: f32,
pub commons_managed: bool,
```

### Rust -> Python (new output columns)

- `elite_status: u8` in agent snapshot
- `emp`, `elite_count`, `frustrated_aspirant_count` per-civ aggregates
- All follow existing optional-column pattern with `map_or` defaults — backward compatible.

---

## Narrative Integration Summary

### New Event Types

| Event Type | Severity Range | Milestone |
|-----------|----------------|-----------|
| `institution_enacted` | 4-6 | M63 |
| `institution_repealed` | 4-6 | M63 |
| `institution_enforcement_lapse` | 3-5 | M63 |
| `institution_capture` | 5-7 | M63 |
| `institutional_regime_shift` | 6-8 | M63 |
| `commons_overshoot` | 4-6 | M64 |
| `commons_collapse` | 6-8 | M64 |
| `commons_recovery` | 3-5 | M64 |
| `elite_overproduction` | 4-6 | M65 |
| `psi_crisis` | 7-9 | M65 |
| `psi_recovery` | 5-7 | M65 |
| `secular_cycle_peak` | 6-8 | M65 |
| `secular_cycle_trough` | 5-7 | M65 |
| `fiscal_crisis` | 5-7 | M65 |
| `conspicuous_consumption_ratchet` | 3-5 | M65 |
| `ambition_fulfilled` | 5-7 | M66 |
| `ambition_failed` | 4-6 | M66 |
| `legitimacy_crisis` | 6-8 | M66 |
| `succession_contested` | 5-7 | M66 |

### New Causal Patterns

31 new causal patterns across M63-M66 (see `design/phase8-9-narrative-integration.md` for full list with gap/bonus values).

### New Narrator Context Blocks

1. **`institutional_context`** — active institutions, enforcement status, faction alignment, regime label (~40-60 lines)
2. **`secular_cycle_context`** — PSI sub-indices, cycle phase, elite ratio, wage trend (~60-80 lines)
3. **`ruler_context`** — legitimacy, political capital, active ambitions, recent events (~40-50 lines)

### Bundle Additions

All fit within Bundle v2's existing 7 layer kinds. No new kinds needed.
- `institutions` entity layer
- `psi` metrics family (per-civ time series)
- Legitimacy/ambition fields on character entities

---

## Phase 9 — Culture (Forward Reference)

Phase 9 layers culture, prestige goods, and revolution cascading on top of validated Phase 8 governance. These are committed scope from the Phase 8-9 horizon doc, listed here for dependency tracking. Full specs will be drafted after M67 passes.

| # | Milestone | Key Idea | Dependencies | Est. Days |
|---|-----------|----------|--------------|-----------|
| M68a | Memome Storage & Transmission | Per-agent `[u8; 8]` trait slots, conformist bias (algebraic sigmoid D=2), prestige bias, compatibility matrix | M67 | 3-4 |
| M68b | Cultural Distance & Behavioral Effects | Civ-level cultural distance, diplomacy friction, trade resistance, innovation at boundaries | M68a | 2-3 |
| M69 | Prestige Goods & Patronage | Prestige good classification, gift-debt patronage networks, cultural influence projection, endogenous brake via elite dilution | M67, M65 | 4-6 |
| M70 | Revolution Cascading | Granovetter thresholds, Epstein grievance formula, J-curve, cascade through network clusters, bridge agent bottlenecks | M68, M69 | 4-6 |
| M71 | Information Asymmetry | Per-civ beliefs about others, intelligence sources, decay toward uncertainty, strategic deception | M67 | 4-6 |
| M72 | Culture Tuning Pass | Validate trait diversity, cascade plausibility, prestige stability, cross-system coupling, runtime budget | M68-M71 | 4-6 |
| M73 | Phase 8-9 Viewer | InstitutionTimeline, PSIDashboard, CulturalTraitMap, PatronageNetwork, RevoltCascadeMap + 12 extensions | M72 | 6-8 |

**Phase 9 estimate:** 28-39 days across 8 milestones. **Combined Phase 8+9:** 52-73 days.

### Phase 9 Pre-Lock Decisions

| Decision | Planning Default | Lock By |
|----------|------------------|---------|
| Revolt awareness diffusion | Reuse M59 information-propagation channel (no parallel diffusion engine) | M70 spec |
| Revolt threshold distribution | Derived from agent state, NOT Gaussian (produces only total-cascade or no-cascade) | M70 spec |
| Conformist bias computation | Algebraic form for D=2: `f²/(f²+(1-f)²)` — saves ~90% vs `powf()` | M68 spec |

---

## Enrichments Deferred from Phase 6-7

Items marked "not in estimate" or deferred during Phase 6-7 implementation. Kept for future milestone enrichment or standalone pull-in.

| Source | Description | Dependency |
|--------|-------------|------------|
| M48 — Generative Agents (eviction) | Eviction by lowest (recency x importance) instead of pure FIFO | M48 |
| M48 — Generative Agents (synthesis) | Importance-budget reflection trigger for relationship reassessment | M50+ |
| M48 — Generative Agents (retrieval) | Three-factor retrieval weighting for narrator context (recency:relevance:importance) | None |
| M48 — Minerva | Generalize Mule acquired-trait pattern to all GreatPersons via rule-based queries | M48 |
| M50 — Axelrod | Similarity-gated bond formation: `P(form) = shared_traits / total_traits` | M50, M36 |
| M50 — Diaspora | Diaspora registry tracking, chain migration, enclave dynamics | M50 |
| M51 — DYNASTY | Succession scoring via genealogical distance, 2-parent-1-random trait mixing | M51, M39 |
| M52 — Cultural Production | Works of art, philosophical treatises, monuments, golden ages | M52 |
| M53 — Fermi function | Replace hard decision thresholds with `P(switch) = 1/(1+exp(-β*(u_dest-u_curr)))` | M53 |
| M58 — Gravity model | Endogenous trade route formation from profit signals (3-5 days enrichment) | M58a/b |

### Enrichments Deferred from Phase 8

| Source | Description | Dependency |
|--------|-------------|------------|
| M63 — Selectorate Theory | W/S ratio drives public vs private goods allocation. Government-type action weight profiles | M63 |
| M63 — Institutional Evolution | Emergent transitions: Chiefdom→Monarchy→Republic→Autocracy from structural pressure | M63 |
| M63 — Legal System Emergence | 6 legal system types as content within institution set | M63 |
| M66 — DF Villain Mechanics | Frustrated elite + grudge → emergent conspirator via curator enhancement | M66, M48, M50 |
| M68 — Religious Market Theory | Rational choice religion with utility-based faith selection | M68, M37 |
| M68 — Language Vectors | Per-civ language features, mutual intelligibility, lingua franca emergence | M68 |
| M69 — Economic Complexity | Hidalgo-Hausmann capability accumulation for goods production | M69 |
| M71 — Alliance Formation | Balance of threat theory, shared rival diplomatic bonuses | M71, M60 |
| M71 — Money Supply & Inflation | Treasury ≈ money supply, EMA price index, inflation satisfaction penalty | M71 or earlier |
| M71 — Espionage | CK3-inspired scheme system (assassination, sabotage, tech theft) | M71 |

---

## Deferred Beyond Phase 9

Not committed scope. Ideas to evaluate once Phase 8-9 systems are stable.

1. **Multiplayer / shared world** — different product architecture entirely
2. **Procedural scenario generation** — benefits from M55 spatial + Phase 8 institutions
3. **Metamodel validation** — parameter space exploration at scale, potentially using Claude API
4. **Continuous terrain** — heightmaps, erosion, procedural river generation
5. **Seldon Crises / interactive mode** — high-stakes choice points via viewer. Phase 8 PSI provides structural crises worth surfacing
6. **Agent-level diplomacy** — individual agents as diplomatic actors, requires stable institutional diplomacy
7. **Naval & maritime systems** — sea zones, naval force projection, piracy, thalassocracy, blockades
8. **Full epidemic model** — SEIRS compartmental model with mutation, quarantine, immunity
9. **Procedural geography** — replace 12-template system with Voronoi/hex procedural generation
10. **Education & knowledge system** — human capital accumulation, literacy, libraries, printing press transitions
11. **Art, literature & monuments** — cultural production, wonders, golden age phenomenon
12. **Advanced diplomatic instruments** — treaties, non-aggression pacts, mutual defense, hostage exchange
13. **Migration & diaspora** — utility-based migration with network effects, refugee mechanics, brain drain
14. **Technological innovation** — combinatorial search in adjacent possible space, super-linear growth
15. **Game integration features** — export formats (Tiled JSON, GeoJSON, SQLite), World State API, scenario templates
16. **Narrative improvements** — narrator personas, multiple chronicle perspectives, primary source generation, era-aware style
