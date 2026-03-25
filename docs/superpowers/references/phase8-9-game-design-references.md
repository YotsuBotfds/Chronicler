# Phase 8-9 Game Design References

> **Purpose:** Mechanical analysis of Old World, Victoria 3, Crusader Kings 3, and Dwarf Fortress — extracting parameter values and adaptation notes for Phase 8-9. Referenced from the Phase 8-9 Horizon roadmap.
>
> **Generated:** 2026-03-25 from deep research by brainstorm team.

---

## Chronicler-Ready Parameter Values

| Parameter | Source | Value | Chronicler Application |
|-----------|--------|-------|----------------------|
| Legitimacy → political capital | Old World | +0.1 per point | `political_capital = base + legitimacy × 0.1` |
| Ambition completion bonus | Old World | +10 legitimacy | Ruler ambition reward |
| Ambition failure penalty | Old World | -5 legitimacy | Ruler ambition failure |
| Cognomen inheritance decay | Old World | 1/n for predecessor n | Dynasty legitimacy decay curve |
| Max cognomen bonus | Old World | +100 legitimacy ("The Great") | Ruler title cap |
| Angry faction stall multiplier | Victoria 3 | 1.5× opposition | Institution blocking |
| Neutral faction stall multiplier | Victoria 3 | 0.5× opposition | Institution ease |
| Faction discontent threshold | CK3 | 80% military power ratio | Faction activation |
| Faction acceleration threshold | CK3 | 110% military power | Faction urgency |
| Ultimatum trigger | CK3 | 100 discontent | Faction demand |
| Scheme breach auto-failure | CK3 | 5 breaches | Espionage timeout (M71) |
| Scheme discovery penalty | CK3 | -75% success chance | Espionage risk (M71) |
| Memory slots | Dwarf Fortress | 8 short + 8 long | Agent memory budget (M48 has 8) |
| Memory review period | Dwarf Fortress | 1 year (annual reliving) | Satisfaction memory tick |
| Cultural era gate | CK3 | 8 innovations per era | Tech prerequisite count |

---

## What Creates Emergent Stories (Cross-Game Synthesis)

Seven properties shared by the best emergent narrative mechanics:

1. **Single shared resource budgets** — Old World orders, CK3 prestige/piety. Everything competes for the same pool → tradeoffs create drama. Chronicler should resist adding separate currencies for each system. Political capital should be ONE shared budget.

2. **Directional sensitivity** — Victoria 3's Standard of Living changes generating radicals. It's the *change*, not the level, that drives interesting behavior. Declining wealthy pops are more dangerous than stable poor ones. → J-curve integration for M70.

3. **Threshold-based phase transitions** — CK3's 80%/110% faction power thresholds, Victoria 3's revolution clock phases. Gradual accumulation with sudden phase changes creates "slowly, then all at once." → PSI threshold crossings.

4. **Endogenous antagonist emergence** — DF's villains from simulation state, not spawn triggers. The most compelling conflicts arise from the system producing the adversary. → Frustrated elites with grudge memories becoming conspirators.

5. **Imperfect information creating realistic failure** — DF's villain technique selection, CK3's scheme breaches. Wrong choices from incomplete knowledge produce better narratives than random dice. → M71 information asymmetry.

6. **Multi-generational decay curves** — Old World's 1/n cognomen inheritance, DF's memory slot displacement. Prestige and grudges fade but don't disappear — the half-life creates natural dynasty arcs. → Dynasty legitimacy decay.

7. **Loosely coupled event prerequisites** — Old World's memory→requirement chains. Events that check for *tags* rather than *specific prior events* scale better and produce more surprising combinations. → M48 memory_tags for event chains.

---

## Old World — Orders & Legitimacy

**Core loop:** Legitimacy → Orders → Actions → Legitimacy

Orders are a **shared pool** for ALL actions. +0.1 orders per legitimacy point. Typical mid-game: 30-50 orders/turn.

**Ambitions:** Dynamically generated at accession from weighted pool filtered by game state. "Virtual deck of cards." Cognomens earned from achievements with diminishing inheritance (1/2 from previous ruler, 1/3 from two back, etc.).

**Event chains:** Events give characters Memories and Traits. Those become requirements for future events. "Loosely coupled" — different writers create compatible events without coordination.

**Adaptation notes:** Political capital as single shared budget (not separate currencies). Cognomen 1/n decay is directly implementable. Event memory tags for loosely coupled chains.

---

## Victoria 3 — Interest Groups & Revolution

**Core loop:** Pops → Interest Groups → Laws → Effects → Pop Satisfaction → Pops

**Clout** from wealth and population of member pops. Laws enacted if IG endorsement clout > opposition stall. Angry IGs provide 150% stall; neutral provide 50%.

**Revolution pipeline:** Radicals (from SoL decline) → Political Movements → Revolution Clock → Ultimatum → Civil War. Direction of change matters more than absolute level.

**Adaptation notes:** Angry/neutral faction multiplier on institution blocking is clean and tunable. Directional sensitivity (SoL delta → radicals) maps to satisfaction memory gap → revolt threshold.

---

## Crusader Kings 3 — Schemes & Factions

**Schemes:** Power vs Resistance, monthly tick. Grace period before detection. 5 breaches = auto-failure. Discovery penalty -75%.

**Factions:** Form around specific demands. Military power ratio thresholds: 80% → discontent begins, 110% → acceleration, 100 discontent → ultimatum. Peasant factions don't need military superiority.

**Cultural innovations:** Era-gated (8 prerequisites per era). Exposure-based spread (neighbors with innovation boost adoption). Cultural Acceptance from shared traditions, intermarriage, proximity.

**Adaptation notes:** 80%/110% thresholds and acceleration curve for faction activation. Breach-accumulation for espionage (M71). Exposure-based innovation spread maps to conformist bias.

---

## Dwarf Fortress — Emergent Antagonists

**Villain emergence:** Any historical figure with "nefarious intent" — endogenous, not scripted. 7 corruption techniques (intimidation, rank assertion, blackmail, flattery, religious sympathy, promising revenge, bribery), each with relationship-dependent effectiveness.

**Artifacts:** Created during "Strange Moods." Family claims, external claims via rumor system, escalation from diplomacy to theft to military. Knowledge propagation through tavern conversations.

**Memory:** 8 short-term + 8 long-term slots with strength-based displacement. Annual "reliving" of 8 strongest events. Long-term memories retained forever until overwritten by stronger ones. Grudges persist via cultural memory.

**Adaptation notes:** Villain emergence from frustrated elite + grudge memory + wealth + faction alignment (already have substrate via M48+M41+M50). Corruption technique taxonomy as utility function. Artifact provenance chains for prestige goods.

---

## What Doesn't Apply

- **Old World's player-centric victory conditions** — Chronicler's AI rulers need state-derived ambitions, not difficulty-curated goals
- **Victoria 3's UI-driven law phases** — Chronicler processes per-turn, simpler probability model fits
- **CK3's Fame/Devotion lifetime tracks** — never-spent currencies don't create cycles; Chronicler's currencies must be spendable
- **DF's Strange Mood triggers** — gameplay event, not simulation-appropriate; use GreatPerson achievements instead
- **Victoria 3's convoy logistics** — too granular; principle (infrastructure gates trade) applies but not the mechanic
