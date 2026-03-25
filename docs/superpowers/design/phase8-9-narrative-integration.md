# Phase 8-9 Narrative Integration — Per-Milestone Spec Sketch

> **Purpose:** For each milestone M63-M73, specifies: new event types, causal patterns, narrator context blocks, bundle sections, and viewer components. Use as reference when drafting individual milestone specs.
>
> **Generated:** 2026-03-25 from deep research by brainstorm team. Based on thorough reading of curator.py, narrative.py, bundle.py, analytics.py, viewer components, and Phase 7.5 roadmap.

---

## Quick Reference: What's Free vs Infrastructure

**Free (append to existing lists):** All new event types, all new causal patterns, M64/M66/M68/M71 context extensions, M64 bundle additions.

**New infrastructure required:**
- Conditional narrator context injection (M70) — blocks that fire only during active events
- Multi-turn arc clustering in curator (M65/M66) — secular cycles and ambition arcs span 50-100+ turns
- ERA_REGISTER trait vocabulary (M68) — trait names in era-appropriate language
- Dramatic irony narration (M71) — narrator receives actual AND believed state
- PSIDashboard viewer component (M65/M73) — three-panel, highest complexity
- RevoltCascadeMap viewer component (M70/M73) — animated spatial, second highest complexity

---

## M63: Institutional Emergence

**Event types:** `institution_enacted` (4-6), `institution_repealed` (4-6), `institution_enforcement_lapse` (3-5), `institution_capture` (5-7), `institutional_regime_shift` (6-8), `legal_system_emergence` (5-7)

**Causal patterns (7):**
- `institution_enacted → institution_enforcement_lapse` (gap 30, bonus 1.5)
- `institution_enforcement_lapse → institution_repealed` (gap 15, bonus 2.0)
- `institution_capture → institutional_regime_shift` (gap 20, bonus 1.5)
- `fiscal_crisis → institution_enforcement_lapse` (gap 10, bonus 2.5)
- `faction_dominance → institution_enacted` (gap 10, bonus 1.5)
- `faction_dominance → institution_capture` (gap 15, bonus 2.0)

**Context block:** New `institutional_context` — active institutions, enforcement status, faction alignment, regime label. ~40-60 lines, follows `build_agent_context_block()` pattern.

**Bundle:** v1 reuse event format; v2 new `institutions` entity layer. **Viewer:** InstitutionTimeline (horizontal bars), CivPanel extension.

---

## M64: Commons & Exploitation

**Event types:** `commons_overshoot` (4-6), `commons_collapse` (6-8), `commons_management_enacted` (4-5), `commons_recovery` (3-5)

**Causal patterns (6):**
- `commons_overshoot → commons_collapse` (gap 20, bonus 2.5)
- `commons_collapse → famine` (gap 10, bonus 2.0)
- `commons_collapse → migration` (gap 15, bonus 1.5)
- `commons_management_enacted → commons_recovery` (gap 40, bonus 1.5)
- `institution_enforcement_lapse → commons_overshoot` (gap 10, bonus 2.0)

**Context block:** Extend existing ecology block with exploitation-rate/yield ratio. ~10-15 lines.

**Bundle:** Add exploitation fields to region metrics. **Viewer:** RegionMap exploitation heatmap overlay.

---

## M65: Elite Dynamics & PSI

**Event types:** `elite_overproduction` (4-6), `psi_crisis` (7-9), `psi_recovery` (5-7), `secular_cycle_peak` (6-8), `secular_cycle_trough` (5-7), `conspicuous_consumption_ratchet` (3-5), `fiscal_crisis` (5-7)

**Causal patterns (10 — largest single addition):**
- `elite_overproduction → psi_crisis` (gap 30, bonus 2.5)
- `conspicuous_consumption_ratchet → elite_overproduction` (gap 20, bonus 1.5)
- `psi_crisis → institution_enforcement_lapse` (gap 10, bonus 2.5)
- `psi_crisis → succession_crisis` (gap 15, bonus 2.0)
- `fiscal_crisis → psi_crisis` (gap 10, bonus 2.0)
- `commons_collapse → elite_overproduction` (gap 20, bonus 1.5)
- `psi_recovery → institution_enacted` (gap 20, bonus 1.5)
- `secular_cycle_peak → psi_crisis` (gap 40, bonus 2.0)

**Context block:** New `secular_cycle_context` — PSI sub-indices, cycle phase, elite ratio, wage trend. ~60-80 lines. **Infrastructure:** ERA_REGISTER modifications for era-sensitive PSI narration.

**Bundle:** New `psi` metrics family (per-civ time series). **Viewer:** PSIDashboard (3-panel — most complex new component). TimelineScrubber secular cycle color bands.

---

## M66: Legitimacy & Ambitions

**Event types:** `ambition_fulfilled` (5-7), `ambition_failed` (4-6), `legitimacy_crisis` (6-8), `political_capital_spent` (2-3), `succession_contested` (5-7)

**Causal patterns (8):**
- `ambition_failed → legitimacy_crisis` (gap 10, bonus 2.5)
- `legitimacy_crisis → succession_contested` (gap 10, bonus 2.5)
- `legitimacy_crisis → psi_crisis` (gap 15, bonus 2.0)
- `ambition_fulfilled → institution_enacted` (gap 15, bonus 1.5)
- `military_victory → ambition_fulfilled` (gap 5, bonus 2.0)

**Context block:** New `ruler_context` — legitimacy, political capital, ambitions, recent events. Extends existing character context. ~40-50 lines.

**Bundle:** Extend named_events and character entity with legitimacy/ambition fields. **Viewer:** CharacterPanel Reign tab, CivPanel ruler card.

---

## M67: Governance Tuning Pass

No new event types, patterns, or context blocks. Validates M63-M66 event rates. Adds `governance_diagnostics` to analytics (PSI distribution, regime frequency, cycle timing). BatchAnalytics extensions.

---

## M68: Discrete Cultural Traits

**Event types:** `cultural_trait_adopted` (2-4), `cultural_trait_displaced` (3-5), `cultural_convergence` (4-6), `cultural_schism` (5-7), `lingua_franca_emerged` (5-7), `cultural_isolation` (4-6)

**Causal patterns (7):**
- `cultural_schism → secession` (gap 20, bonus 2.0)
- `cultural_schism → civil_war` (gap 15, bonus 1.5)
- `cultural_trait_displaced → cultural_schism` (gap 25, bonus 1.5)
- `conquest → cultural_trait_displaced` (gap 30, bonus 1.5)
- `trade_route_established → lingua_franca_emerged` (gap 40, bonus 1.5)

**Context block:** Extend existing cultural block with memome traits, cultural distance, compatibility tensions. ~20-30 lines. ERA_REGISTER trait vocabulary mapping.

**Bundle:** New `cultural_traits` overlay layer (spatial trait concentration). **Viewer:** CulturalTraitMap (spatial overlay), CivPanel trait composition, Cultural Distance Matrix heatmap.

---

## M69: Prestige Goods & Patronage

**Event types:** `prestige_good_discovered` (4-6), `patronage_network_formed` (4-6), `patronage_collapse` (6-8), `cultural_influence_projection` (4-6), `prestige_embargo` (5-7), `elite_dilution` (3-5)

**Causal patterns (8):**
- `supply_shock → patronage_collapse` (gap 10, bonus 2.5)
- `patronage_collapse → legitimacy_crisis` (gap 10, bonus 2.5)
- `prestige_embargo → patronage_collapse` (gap 5, bonus 3.0)
- `cultural_influence_projection → cultural_trait_displaced` (gap 30, bonus 1.5)
- `elite_dilution → patronage_collapse` (gap 20, bonus 1.5)

**Context block:** New `patronage_context` — prestige goods, bond count/health, key relationships, cultural influence. ~30-40 lines.

**Bundle:** New `patronage` network layer (edge list). **Viewer:** PatronageNetwork (D3-force graph), trade panel prestige highlight.

---

## M70: Revolution Cascading

**Event types:** `revolt_cascade_started` (6-8), `revolt_cascade_spread` (5-7), `revolt_cascade_stalled` (4-6), `bridge_agent_assassinated` (5-7), `revolt_suppressed` (5-7), `revolution_succeeded` (7-9)

**Causal patterns (10 — second largest):**
- `psi_crisis → revolt_cascade_started` (gap 15, bonus 2.5)
- `legitimacy_crisis → revolt_cascade_started` (gap 10, bonus 2.5)
- `revolt_cascade_started → revolt_cascade_spread` (gap 10, bonus 2.0)
- `bridge_agent_assassinated → revolt_cascade_stalled` (gap 5, bonus 3.0)
- `patronage_collapse → revolt_cascade_started` (gap 15, bonus 2.0)
- `revolution_succeeded → institution_enacted` (gap 10, bonus 2.0)
- `revolution_succeeded → ruler_accession` (gap 5, bonus 2.5)

**Context block:** New `revolt_context` (conditional — only during active cascades) — origin, spread, bridge agents, suppression status. ~50-70 lines. **Infrastructure:** Conditional context injection pattern.

**Bundle:** `revolt_cascade` network layer + `revolt_heat` overlay. **Viewer:** RevoltCascadeMap (animated spatial — most complex Phase 9 visualization). TimelineScrubber cascade arcs.

---

## M71: Information Asymmetry

**Event types:** `intelligence_gained` (2-4), `deception_attempted` (4-6), `deception_discovered` (5-7), `espionage_scheme_launched` (4-6), `espionage_scheme_discovered` (5-7)

**Causal patterns (7):**
- `deception_discovered → war_declared` (gap 10, bonus 2.0)
- `deception_discovered → alliance_broken` (gap 10, bonus 2.0)
- `espionage_scheme_discovered → war_declared` (gap 10, bonus 2.5)
- `trade_route_established → intelligence_gained` (gap 5, bonus 1.0)

**Context block:** Extend diplomacy block with belief accuracy, intelligence sources, active deceptions. ~15-20 lines. **Infrastructure:** Dramatic irony narration (narrator receives actual AND believed state).

**Bundle:** Belief-state metrics per civ-pair. **Viewer:** Knowledge overlay accuracy shading, CivPanel Intelligence tab.

---

## M72: Culture Tuning Pass

No new infrastructure. Validates M68-M71. Analytics: trait diversity, cascade frequency, prestige stability, cross-system coupling. BatchAnalytics extensions.

---

## M73: Phase 8-9 Viewer

17 deliverables total: 5 new components (InstitutionTimeline, PSIDashboard, CulturalTraitMap, PatronageNetwork, RevoltCascadeMap) + 12 extensions to existing components. ~2000-3000 lines TypeScript. All fit within Bundle v2's reserved namespaces.
