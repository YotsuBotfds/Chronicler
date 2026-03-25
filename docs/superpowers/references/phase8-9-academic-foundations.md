# Phase 8-9 Academic Foundations

> **Purpose:** Exact mathematical formulations, parameter values, and implementation insights for the five academic theories underpinning Phase 8-9. Referenced from the Phase 8-9 Horizon roadmap.
>
> **Generated:** 2026-03-25 from deep research by brainstorm team.

---

## 1. Turchin — Structural-Demographic Theory & PSI

### Exact PSI Formula (Turchin 2012)

```
PSI = MMP × EMP × SFD
```

- **MMP** = w⁻¹ × (N_urb / N) × A_(20-29)
  - w = relative wage (median wage / GDP per capita), inverted
  - N_urb / N = urbanization rate
  - A_(20-29) = youth bulge fraction (agents aged 20-29 equivalent)
- **EMP** = ε⁻¹ × e
  - ε⁻¹ = inverse relative elite income
  - e = elite count or proportion
- **SFD** = (D / GDP) × (1 - T)
  - D / GDP = debt-to-income ratio
  - T = institutional trust/legitimacy (0-1)

### Secular Cycle Periodicity (200-300 turns)

NOT an exogenous clock. Emerges from timescale mismatch:
- **Positive loop (decades):** Labor oversupply → wage decline → elite income rises → elite overproduction → conspicuous consumption ratchet → PSI rises → crisis
- **Negative loop (centuries):** Instability → population decline → labor scarcity → wage recovery → new integrative phase

The ratchet only goes up during expansion — social expectations are sticky. This asymmetry makes the cycle asymmetric: slow rise, fast crash, slow recovery.

### Nested Sub-Cycle

40-60 turn violence cycle ("fathers and sons" generational dynamics) only manifests during disintegrative phases. Periodic violence spikes within the crisis period — richer narrative texture.

### Critiques & Implications

1. **Flexible elite definition:** Turchin shifts between top 1%, top 10%, and "any educated professional." M65 spec MUST lock a formal definition.
2. **Wage polarization alternative:** Recent studies attribute US instability to automation/globalization, not Malthusian labor oversupply. Treat PSI as correlative indicator, not validated causal model.
3. **Post-hoc rationalization risk:** M67 acceptance gates force the model to be predictive within the simulation.
4. **2010/2020 prediction:** Directional accuracy (instability increased by order of magnitude), not precise timing.

---

## 2. Ostrom — Governing the Commons

### The 8 Design Principles for Long-Enduring CPR Institutions

1. **Clearly defined boundaries** — who can appropriate, resource boundaries unambiguous
2. **Congruence** — rules match local conditions; rules that work in one ecology fail in another
3. **Collective-choice arrangements** — affected parties can modify rules
4. **Monitoring** — active auditing of both resource conditions AND appropriator behavior
5. **Graduated sanctions** — warning → fine → temporary exclusion → permanent exclusion (NOT all-or-nothing)
6. **Conflict resolution** — rapid, low-cost, local mechanisms
7. **Minimal recognition of rights to organize** — external authorities don't undermine self-governance
8. **Nested enterprises** — multiple governance layers for larger systems

### ADICO Grammar (Crawford & Ostrom 1995)

- **A**ttribute — who (e.g., "farmers")
- **D**eontic — obligated/permitted/forbidden
- **a**Im — prescribed action
- **C**ondition — circumstances
- **O**r-else — sanction

Three levels: Strategy (AIC), Norm (ADIC), Rule (ADICO). Norms are cheaper to maintain but weaker than rules.

### Key Variables for Collapse vs Persistence

1. **Monitoring frequency** — single strongest predictor
2. **Group size** — smaller groups cooperate better; large groups need nested governance
3. **Resource predictability** — predictable resources sustain institutions better than volatile ones
4. **Communication channels** — face-to-face cooperation far better
5. **Heterogeneity of interests** — moderate helps, extreme undermines

### Graduated Sanctions Detail

First warning tells the violator "we're watching and we care" — often sufficient. Communities that jump straight to harsh punishment destabilize faster (resentment and defection cascades). Implementation: per-agent `violation_count` (u8) should be **per-institution, not global**.

### Missed Insight: Resource Volatility

Resource *volatility* matters independently of depletion. High but variable yield stresses institutions differently than low but stable yield. Climate cycles should interact with institutional stability via the *uncertainty* that makes rules harder to calibrate, not just yield decline.

---

## 3. Granovetter — Threshold Models of Collective Behavior

### Core Framework

Each agent i has threshold θ_i ∈ [0,1]. Equilibrium: r* = F(r*) where F is CDF of threshold distribution.

### Distribution Shape Is Critical

- **Uniform [0,1]:** Extreme sensitivity to initial conditions — tiny perturbations → full cascade or nothing
- **Normal (Gaussian):** Either no cascade or everyone cascades — **unrealistic, do NOT use for Chronicler**
- **Broad/heterogeneous (from agent state):** Produces realistic partial cascades and multiple stable states — **use this**

### Watts (2002) — Network Extensions

Two cascade regimes:
- **Sparse networks (rural):** Cascade size follows power law. Most connected nodes disproportionately trigger cascades.
- **Dense networks (urban/trade hubs):** Bimodal cascade sizes — either fizzle or explode globally within the connected component. Most connected nodes are NOT special.

**Implication:** Rural revolts spread like wildfire (trackable turn by turn). Urban revolts are explosions (nearly instantaneous within city social network).

### Predictability Paradox (Granovetter & Soong 2020)

Small amount of randomness in individual behavior makes collective behavior LESS sensitive to threshold perturbations and MORE predictable. Adding stochastic noise to thresholds produces more robust cascade dynamics.

---

## 4. Richerson & Boyd — Dual-Inheritance Theory

### Two Mathematical Formulations

**Population-level (Boyd & Richerson 1985):**
```
p' = p + D × p × (1 - p)
```

**Individual-level (used in Chronicler):**
```
P(adopt) = f^D / (f^D + (1-f)^D)
```

### Key Parameter Values

| D | Effect | 60% frequency → adoption prob |
|---|--------|-------------------------------|
| 1 | No bias (linear) | 60% |
| 2 | Moderate conformism | ~69% |
| 3 | Strong conformism | ~80% |
| 5+ | Threshold voting | ~97% |

**D = 2-3 is the empirically supported sweet spot.** Pure conformism blocks innovation; pure payoff-bias is noisy.

### Anti-Conformist Bias (D < 1)

Some agents prefer rare traits — natural cultural innovators and boundary-crossers. Map to high-boldness personality. These agents carry foreign ideas into homogeneous cultural zones.

### Environmental Crisis Interaction

Conformist bias is maladaptive in rapidly changing environments. During ecological crises, conformist bias should weaken temporarily — people in crisis try new things. Creates ecology→culture coupling.

### Implementation Pitfalls

1. **Sampling bias:** `f` must be frequency among sampled models (spatial neighbors + relationship connections), not global population
2. **Lock-in from compatibility:** If incompatible traits block adoption, first traits constrain all future adoption. Need paradigm shift mechanism (PSI spikes temporarily reduce conformist bias)
3. **Biased transformation erosion:** If guided variation is too strong, conformist transmission can't maintain cultural regions

---

## 5. Bueno de Mesquita — Selectorate Theory

### Core Model

- **N** = total population, **S** = selectorate, **W** = winning coalition
- **Loyalty norm** = W/S = probability of being in next coalition
- **Resource allocation:** Leader maximizes kleptocracy = R - g - Wx (revenue - public goods - private goods)

### Leader Survival Condition

```
x + ln(g) ≥ (W/S) × x_challenger + ln(g_challenger)
```

When W/S is small (autocracy), coalition accepts less. When W/S is large (democracy), coalition can credibly defect.

### Regime Types

| W/S | Type | Spending | Stability |
|-----|------|----------|-----------|
| ~0.01-0.05 | Military dictatorship | Nearly all private | Very stable once established |
| ~0.05-0.15 | Autocracy | Heavy private | Stable |
| ~0.15-0.40 | Hybrid/oligarchy | Mixed | **Most unstable (transition zone)** |
| ~0.40-0.80 | Limited democracy | Public dominant | Moderately stable |
| ~0.80-1.0 | Full democracy | Nearly all public | Stable, high leader turnover |

### Institutional Transition Trap

Transitions between regime types are the most dangerous periods. Increasing W (expanding franchise) requires providing more goods to more members while new members haven't developed loyalty and old members feel diluted. Creates temporary vulnerability window.

### Interaction with PSI

When PSI is high, challengers make more credible offers → leader turnover increases non-linearly with PSI → succession crises during secular cycle crises.

---

## 6. HANDY Model (Motesharrei et al. 2014)

### Four Coupled ODEs

```
dxC/dt = βC·xC - αC·xC         (Commoner population)
dxE/dt = βE·xE - αE·xE         (Elite population)
dy/dt  = γ·y·(λ-y)/λ - δ·xC·y  (Nature: logistic growth - depletion)
dw/dt  = δ·xC·y - CC - CE       (Wealth: production - consumption)
```

Death rate is wealth-dependent: normal `α_m` when w ≥ w_th, famine `α_M` (7× normal) when w < w_th. Elites buffered: they don't experience famine until w < w_th/κ.

### Three Collapse Scenarios

1. **Type-L (Labor):** High inequality (κ) → commoners starve → labor disappears → elites collapse after lag
2. **Type-N (Nature):** High depletion (δ) → nature exhausted → both classes collapse
3. **Type-C (Combined):** Both interact — appears sustainable long, then sudden collapse

### The κ Coupling (Critical for Chronicler)

Elites consume κ× more per capita. **Chronicler currently lacks this.** Wealthy agents don't extract more from commons. M64+M65 must create: `elite_extraction_rate = base_rate × f(wealth_percentile)`.

### HANDY Parameter → Chronicler Mapping

| HANDY | Default | Chronicler Analog |
|-------|---------|-------------------|
| βC = βE = 0.03 | Birth rate | demographics.rs fertility |
| α_m = 0.01 | Normal death rate | demographics.rs mortality baseline |
| α_M = 0.07 | Famine death rate | 7× normal — calibrate vs ecology.py famine severity |
| γ = 0.01 | Nature regen | EcologyConfig.soil_recovery_rate |
| δ | Depletion per worker | EcologyConfig.depletion_rate — **key tuning knob** |
| κ | Inequality coefficient | Gini → elite extraction multiplier — **must be created** |

---

## 7. Epstein Civil Violence Model (PNAS 2002)

### Decision Rule

```
IF (Grievance - Net_Risk) > Threshold THEN rebel
```

- `Grievance = Hardship × (1 - Legitimacy)`
- `Net_Risk = Risk_Aversion × P(Arrest)`
- `P(Arrest) = 1 - exp(-k × Cops_visible / max(Rebels_visible, 1))`
- k ≈ 2.3 (so P ≈ 0.9 when cops = rebels = 1)

### Chronicler Mapping

```rust
let grievance = (1.0 - satisfaction) * (1.0 - legitimacy);
let j_curve = (memory_score - satisfaction).max(0.0); // Davies J-curve
let effective_hardship = grievance + J_CURVE_WEIGHT * j_curve;
let arrest_prob = 1.0 - (-2.3 * soldiers_ratio / rebels_ratio.max(0.01)).exp();
let net_risk = risk_aversion * arrest_prob;
if effective_hardship - net_risk > REBEL_THRESHOLD { rebel(); }
```

### Calibration Targets

- L=0.7, H=0.5: ~5% active rebels (background unrest)
- L=0.3, H=0.7: cascade to ~40-60% active (revolution)
- J-curve frustration triggers only when gap > 0.15 and sustained improvement > 10-20 turns

---

## 8. GovSim — LLM Commons Baseline (Piatti et al. 2024)

43 out of 45 scenarios collapsed (96%). Only GPT-4 class models occasionally cooperated. Failure cause: agents cannot reason about long-term equilibrium effects.

**Calibration target for M64:** Without Ostrom-style institutions, ~90%+ of civs should over-extract during 500-turn runs. Cooperation is the EXCEPTION requiring specific institutional conditions.

---

## Cross-Theory Synthesis

The five theories form a coherent stack:
1. **Ostrom** → institutional foundation (how rules emerge, persist, fail)
2. **Bueno de Mesquita** → political structure (leader-coalition → institutional incentives)
3. **Turchin** → secular rhythm (demographic + elite + fiscal pressures)
4. **Boyd & Richerson** → cultural substrate (idea transmission dynamics)
5. **Granovetter/Watts** → cascade mechanics (individual dissatisfaction → collective action)

**Key cross-theory interaction:** PSI should modulate Granovetter's threshold distribution. High PSI → lower thresholds (frustrated elites become firebrands, immiserated workers become desperate). The *shape* of the threshold distribution shifts during secular cycle crises.

**Second interaction:** Ostrom's institutional failure should weaken Boyd & Richerson's conformist transmission. When institutions collapse, social signals maintaining conformism weaken → cultural fragmentation → further institutional stress (positive feedback).
