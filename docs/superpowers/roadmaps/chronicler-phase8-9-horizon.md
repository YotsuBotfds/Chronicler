# Chronicler Phase 8-9 Horizon — Emergent Order

> **Status:** Brainstorm. Not a commitment. Ideas to evaluate once Phase 7 systems are stable.
>
> **Phoebe + Cici review (2026-03-19):** See `[REVIEW]` tags for structural concerns identified during Phase 7 roadmap review.
>
> **Phase 7 prerequisite:** M61 tuning pass validates depth + scale systems at 500K-1M agents.
>
> **Extracted from:** Phase 7 roadmap during finalization (2026-03-19). Separated to keep Phase 7 focused on committed scope (M48-M62).

> **Structural principle:** Phase 7 gives agents inner lives and puts them in space. Phase 8-9 asks: what happens when agents collectively create *rules*, and those rules take on a life of their own? The shift is from individual depth to collective structure — institutions, legitimacy, secular cycles, and the macro-rhythms that make civilizational histories feel like civilizational histories rather than random walks.
>
> **Phase split rationale:** Governance (Phase 8) and Culture (Phase 9) interact heavily, but Governance provides the structural stakes that Culture then contests. Validating the secular cycle, institutional dynamics, and legitimacy standalone — before layering on discrete cultural traits, prestige goods, and revolution cascading — matches the project's established pattern: validate each substrate before building the next.

## Why Emergent Order

Phase 7 agents remember, want, bond, and inhabit space. But they live in a world without laws. There are no courts, no property rights, no succession norms, no tax codes. Factions compete for influence but have nothing concrete to fight over — no bill to pass, no institution to capture. Rulers exist as GreatPersons but have no political capital to spend, no legitimacy to earn or squander, no ambitions beyond the civ-level action distribution. The economy produces goods and the ecology constrains growth, but there's no *tragedy of the commons* — no mechanism where individual rational exploitation leads to collective ruin, and no institutional response that could prevent it.

Phase 8 introduces the structures that sit between individual agents and civilizational outcomes. Six capabilities that Phase 7 structurally cannot deliver:

1. **Institutions as emergent rule-sets.** Laws, norms, and governance structures that factions create, fight over, and that then constrain the simulation itself. `PROPERTY_RIGHTS` reduces raid incentive and increases investment. `CORVEE_LABOR` boosts infrastructure build speed but tanks farmer satisfaction. `FREE_TRADE` increases trade volume but hurts local artisans. Institutions have legitimacy that erodes when unenforced, and enforcement costs that drain the treasury via the existing governing-cost framework in `politics.py` — creating the link between fiscal crisis and institutional collapse. **Scope guard:** institutions are a finite enumerated set with parameterized effects (like ActionTypes and FactionTypes), not a generative grammar. ADICO (Attributes, Deontic, aIm, Conditions, Or-else) is useful for *designing* the enumerated set but is not the runtime representation. **Weight cap:** institutional modifiers on action weights are subject to the existing 2.5x combined multiplier cap (traditions x tech focus x factions x institutions). `[REVIEW B-5]` **Cap mechanism revision required before M63.** The 2.5x cap was designed for 3 contributors (traditions, tech focus, factions). Phase 7 adds Mule modifiers (4th). Institutions would be 5th. Adding contributors without revising the cap, per-system contribution limits, or the cap mechanism creates an implicit nerf to existing Phase 6 systems. Options: (a) raise the cap, (b) add per-system contribution ceilings, (c) priority scheme where stronger modifiers take precedence. Resolve in M63 spec.

2. **Elite overproduction and secular cycles.** Turchin's structural-demographic theory as a mechanized feedback loop. PSI is the product of three sub-indices: MMP (Mass Mobilization Potential — inverse real wages, urbanization, youth bulge), EMP (Elite Mobilization Potential — ratio of elite aspirants to positions, conspicuous consumption ratchet), and SFD (State Fiscal Distress — debt-to-income ratio, institutional legitimacy). The conspicuous consumption ratchet is a key positive feedback within EMP: intra-elite competition drives up the cost of "maintaining elite status," creating more aspirants who fall below the threshold, which amplifies competition further. PSI drives the 200-300 turn secular cycle: expansion → stagflation → crisis → depression → recovery. The negative feedback that resets the cycle: instability → population decline → labor scarcity → wage recovery → new integrative phase.

3. **Legitimacy and political capital.** Inspired by Old World's orders system — rulers earn legitimacy from victories, institutional support, dynastic prestige, and fulfilling personal ambitions. Everything costs political capital: moving armies, enacting laws, suppressing factions, diplomatic overtures. Low-legitimacy rulers can barely govern. Each ruler gets randomized ambitions at accession ("conquer region X", "build a great temple", "establish trade with civ Y") — completing them raises legitimacy, ignoring them erodes it. Every reign becomes a narrative arc without scripting. Old World's deeper insight: events give characters *memories* that become prerequisites for future events, creating multi-step causal chains ("you offended Alexander at a banquet → years later, Alexander inherits the throne → diplomatic crisis"). Phase 7's agent memory (M48) provides the substrate; Phase 8 wires it into a curator-driven event chain system where past actions seed future narrative opportunities.

4. **Cultural traits as discrete transmissible memes.** Move beyond floating-point cultural values to a per-agent `memome` of discrete traits (`ANCESTOR_WORSHIP`, `MARTIAL_HONOR`, `WRITTEN_LAW`, `DIVINE_RIGHT`). Transmission follows dual-inheritance rules: conformist bias with sigmoid adoption `P(adopt) = f^D / (f^D + (1-f)^D)` where D > 1 exaggerates majority preference, prestige bias (copy traits of high-status agents — second-order, creates cultural "stars"), and guided variation (modify based on experience). The key finding from cultural evolution ABMs: intermediate conformity outperforms both extremes — pure conformism blocks beneficial innovation, pure payoff-bias is noisy. Traits have compatibility scores — some reinforce (`WRITTEN_LAW` + `PROPERTY_RIGHTS`), others conflict (`DIVINE_RIGHT` + `REPUBLICAN_VIRTUE`). Cultural distance between civs drives diplomacy friction, trade resistance, and innovation potential (diverse ideas recombine at boundaries). Cultural trait dynamics don't converge to static equilibria — expect ongoing turnover and replacement even at steady state.

5. **Prestige goods and soft power.** A second economy orthogonal to material goods. Rare goods (jade, incense, purple dye) have negligible material utility but enormous political value. Rulers distribute prestige goods to subordinates, creating gift-debt patronage networks. Losing access to prestige goods (mine depletion, trade disruption) destabilizes the entire patronage chain. Civs that export cultural prestige goods gain cultural influence over importers — peaceful cultural conquest that can be deliberately weaponized via flood-then-embargo. **Endogenous brake on prestige stability trap:** elite overproduction creates more elites competing for the same prestige goods, diluting per-elite allocation and eroding patronage bonds even when supply is stable. Commons overshoot degrades the production base. These two channels ensure that a well-functioning prestige economy generates the seeds of its own disruption from within, not only from exogenous shocks (embargo, mine depletion).

6. **Revolution cascading via Granovetter thresholds.** Each agent has a revolt threshold — the fraction of their neighbors who must be revolting before they join. Low-threshold agents are firebrands. When dissatisfaction (from immiseration, elite overproduction, institutional failure) reaches critical mass in a network cluster, it cascades through connected clusters. The cascade stalls at network boundaries (mountains, seas) unless "bridge agents" (merchants, diplomats, exiled nobles) carry it across. Assassinating a bridge agent can literally prevent a revolution from spreading.

## Sketch Milestone Map

Two phases: **Phase 8 — Governance** (institutions, commons, elites, legitimacy) ships and tunes standalone. **Phase 9 — Culture** (discrete traits, prestige goods, revolution dynamics) layers on top of validated governance mechanics. The cross-system interactions (section below) are Phase 9 payoffs.

| # | Milestone | Phase | Key Idea |
|---|-----------|-------|----------|
| | **Phase 8 — Governance** | | |
| M63 | Institutional Emergence | 8 | Factions propose/repeal from a finite enumerated institution set (ADICO informs design, not runtime); institutions modify sim parameters within 2.5x weight cap; enforcement costs map onto existing governing-cost framework; three institutional regimes to validate (frozen/stable, fluctuating/unstable, complex cycling) |
| M64 | Commons & Exploitation | 8 | Per-region exploitation rate vs. sustainable yield; lag-then-crash; institutional mitigation via `COMMONS_MANAGEMENT` |
| M65 | Elite Dynamics & PSI | 8 | Elite positions, frustrated aspirants, Political Stress Indicator, secular cycle. Commons (M64) provides the ecological amplifier — calibrate with it present. |
| M66 | Legitimacy & Ambitions | 8 | Ruler political capital, randomized ambitions, succession mechanisms with failure modes. Wires into existing `politics.py` succession/governing cost mechanics. |
| M67 | Governance Tuning Pass | 8 | Validate secular cycle emergence across 200-seed runs; PSI predicts crisis within calibrated window; ratchet/reset timescale balance; all three PSI sub-indices co-occur in realistic scenarios |
| | **Phase 9 — Culture** | | |
| M68 | Discrete Cultural Traits | 9 | Per-agent memome, dual-inheritance transmission, compatibility matrix, cultural distance |
| M69 | Prestige Goods & Patronage | 9 | Prestige good classification, gift-debt networks, cultural influence projection, endogenous brake via elite dilution. **Research enrichment:** Economic complexity (Hidalgo-Hausmann Product Space) — each good requires a set of capabilities; civs accumulate capabilities through tech, trade imports (knowledge spillover), and GreatPerson births. Prevents unrealistic jumps (desert civ doesn't build ships without coastal knowledge). Creates natural eras. Trade becomes developmental, not just wealth transfer. ~300 lines in `capabilities.py`. Source: Hidalgo & Hausmann, PNAS 2009. |
| M70 | Revolution Cascading | 9 | Granovetter thresholds, cascade through network clusters, bridge agent bottlenecks. `[REVIEW O-7]` Must specify whether revolt awareness uses M59's information propagation channel (architecturally cleaner — one diffusion mechanism, multiple info types) or has its own propagation. Two parallel diffusion processes on the same graph risks inconsistent behavior. |
| M71 | Information Asymmetry | 9 | Per-civ beliefs about others, intelligence sources, decay toward uncertainty, strategic deception. (Phase 7 overflow from M59 — natural extension of info propagation.) |
| M72 | Culture Tuning Pass | 9 | Validate trait transmission rates, prestige economy stability, cascade frequency, cross-system interactions with Phase 8 governance |
| M73 | Phase 8-9 Viewer | 9 | Institutional timeline, PSI dashboard, cultural trait maps, patronage network visualization |

**M63 enrichment (Selectorate Theory — Bueno de Mesquita):** Winning coalition size (W) vs selectorate size (S) drives public vs private goods allocation. `private_goods_share = 1 - (W/S)`. Small-coalition regimes spend on military loyalty; large-coalition regimes spend on infrastructure/trade. Leader survives if loyalty payoff > challenger's offer. This gives each government type mechanically different action weight modifiers — not flavor text. O(n) per turn, ~25ms for 50 civs. Source: Bueno de Mesquita, *The Logic of Political Survival*.

**M63 enrichment (Institutional Evolution — Acemoglu/Robinson):** Institutions change when enforcement costs exceed state capacity. Transitions emerge from structural pressure, not scripted triggers: Chiefdom → Monarchy (external military threat + population growth), Monarchy → Republic (faction conflict + elite competition + economic complexity), Any → Autocracy (crisis + strong individual leader). Source: Acemoglu & Robinson, "Paths to Inclusive Political Institutions" (MIT).

**M63 enrichment:** Legal system emergence (6 types: customary, religious courts, trial by ordeal, merchant law, common law, codified law) is content for M63's enumerated institution set, not a separate milestone. Transition triggers: merchant law when trade_income > threshold, religious courts when clergy_power > threshold, codified law when literacy > 0.6. Education/knowledge system (literacy rates, libraries, guild tiers) is institutional infrastructure that feeds M64's PSI computation. See brainstorm §E5, §E8.

**M68 enrichment (Religious Market Theory — Stark/Finke):** Apply rational choice economics to religion. Agents pick faith maximizing: `U(faith) = commitment_tolerance × (1 - strictness) + prestige_weight × prestige + conformity_weight × neighbor_fraction - switching_cost`. Sects start strict (high commitment), then normalize over time. Free-rider problem: when low-commitment members outnumber committed, faith loses prestige. Add `strictness` parameter to Faith, make conversion depend on utility comparison. ~80 lines on top of existing `religion.py`. Source: Stark & Finke, religious market theory.

**M68 enrichment (Language Vectors):** Per-civ language vector (50-100 features) drifts stochastically. Mutual intelligibility = `1 - normalized_distance`. Trade partners borrow features (prestige-weighted). Lingua franca emerges at trade hubs. O(civs × F) per turn + O(civs²) MI computation every 10 turns, negligible. Narrative payoff: detect lingua franca emergence, linguistic isolation events, language family trees. ~200 lines Python. Source: cultural evolution ABM literature.

**M68 enrichment:** Language drift is a type of cultural trait in M68's memome system. Language features use the same conformist/prestige bias transmission. Lingua francas emerge along trade routes, creoles at cultural boundaries, literary traditions resist drift. Procedural naming with cultural consistency. See brainstorm §E4.

**M71 enrichment (Alliance Formation — Balance of Threat):** Shared rivals boost diplomatic opinion (+15). Alliance probability driven by `opinion + shared_rivals - perceived_threat`. No hardcoded "counter the rising power" rule — natural coalitions emerge from shared threat perception. O(n²), ~250ms for 50 civs. Pairs with Fearon's war bargaining (M60 enrichment) and Power Transition Theory — alliances form to prevent the parity conditions that trigger wars. Source: Stephen Walt, balance of threat theory.

**M71 enrichment (Money Supply & Inflation):** Treasury size ≈ money supply. Track exponential moving average of prices as price index. Inflation = price index change. Agents see inflation via satisfaction penalty (inside the 0.40 non-ecological cap). O(1) per civ, ~50 lines. Could land as early as M47 or as M69 enrichment. Source: ABIDES-Economist (arxiv 2024).

**M71 enrichment:** Espionage (CK3-inspired scheme power vs. resistance) is the active extension of M71's information asymmetry. Scheme types: assassination, sabotage, tech theft, destabilize, fabricate claims. Discovery chance creates diplomatic incidents. Trade networks double as intelligence networks. See brainstorm §E6.

## Cross-System Interactions (Phase 9 payoffs)

The individual systems above are valuable, but their *interactions* produce the emergent historical drama. Most of these require both Governance (Phase 8) and Culture (Phase 9) to be present — they are Phase 9 validation targets:

- **Secular cycle → institutional collapse:** PSI spike triggers fiscal crisis → enforcement of institutions lapses → PROPERTY_RIGHTS becomes dead letter → banditry and land seizures increase → popular immiseration deepens → PSI rises further. The positive feedback loop that turns a crisis into a dark age.

- **Elite overproduction → institutional capture:** Frustrated elites don't just fund instability — they push for institutional changes that benefit their faction. A surplus of military elites pushes for `MILITARY_ACCLAMATION` succession (which favors generals). Merchant elites push for `FREE_TRADE` (which favors them at the expense of artisans). Institutions become the *terrain* of elite competition.

- **Cultural distance → revolution barrier/catalyst:** A conquered region with high cultural distance resists assimilation AND is more susceptible to revolt cascading (shared grievance = lower revolt thresholds). But cultural distance also means foreign ideas can't easily spread — a revolution in a culturally distant province might *not* cascade to the core. Cultural homogenization is both a tool of imperial control and a vulnerability (one cascade reaches everyone).

- **Prestige goods → legitimacy → institutional stability:** A ruler who controls prestige goods distributes them to shore up legitimacy. Legitimacy funds political capital. Political capital enforces institutions. A prestige goods disruption (mine depletion, trade embargo) can cascade through the entire governance stack: lost patronage → legitimacy crisis → institutional collapse → secular cycle crisis phase.

- **Commons overshoot → elite conflict:** When a region degrades below carrying capacity, the material base shrinks but the elite class doesn't — elite positions become even more scarce relative to elite population. Ecological crisis amplifies elite overproduction, compressing the secular cycle's expansion phase. The civilization that manages its commons extends its golden age; the one that doesn't enters crisis a generation early.

## Mechanistic Sketches

Brief implementation-flavored notes on the systems with the most complex internals.

**PSI computation (M65):**
```
MMP = (1/relative_wage) × urbanization_rate × youth_bulge_fraction
EMP = elite_count / elite_positions × conspicuous_consumption_index
SFD = state_debt / state_income × (1 - institutional_legitimacy)
PSI = MMP × EMP × SFD
```

**Turn loop placement:** PSI is computed in Phase 10 (Consequences), after all other phases have resolved. It reads post-tick demographics (MMP), post-Phase 2 treasury (SFD), and the institutional state from whatever phase institutions live in. PSI from turn N affects Phases 2-3 of turn N+1 as a one-turn-lagged signal — same pattern as `AgentBridge._gini_by_civ`. This lag must be stated explicitly to prevent feedback loop confusion.

**Multiplicative calibration cliff:** The multiplicative form means that if any one factor is near zero, PSI collapses regardless of the others. This is historically intentional (Turchin: all three pressures must co-occur for crisis), but it creates a calibration challenge. If the simulation's dynamics tend to produce one dominant stress factor (likely fiscal distress, since treasury is the most volatile stat), the multiplicative form will undercount instability in scenarios where only one or two factors are elevated. M67 must validate that all three sub-indices actually rise together in realistic scenarios, not just that PSI as a whole crosses thresholds. If they don't co-occur naturally, consider a softened form: `PSI = MMP^a × EMP^b × SFD^c` with exponents < 1, or an additive-with-interaction form.

> `[REVIEW O-6]` **Design the exponent form from day one.** The softened form `PSI = MMP^a × EMP^b × SFD^c` should be the starting interface in M65, with exponents defaulting to 1.0 (equivalent to the pure multiplicative form). This avoids a post-M67 rework if the pure form doesn't work. Run an analytical model of the three sub-indices using Phase 7 M61 output data before M65 implementation to determine whether the multiplicative form is viable. The deeper concern: in a simulation with this many interacting systems, the probability that all three sub-indices rise *simultaneously* is low unless there's a common cause. That common cause would be the secular cycle's own feedback — but the feedback is what PSI is supposed to *produce*. Configurable exponents provide the escape hatch.

> `[REVIEW O-4]` **Phase 7 must expose PSI input quantities.** M61's extractor suite should compute and expose: `median_agent_wealth` (for relative wage), `urbanization_rate` (from M56 settlements), `youth_bulge_fraction` (from demographics age distribution). These are cheap to extract and prevent a data gap at Phase 8 start. `state_debt` does not exist yet — Phase 8 M65 or M66 introduces it.

`conspicuous_consumption_index` ratchets upward during elite overproduction (the cost of elite status rises as competition intensifies), creating a positive feedback loop within EMP that accelerates the approach to crisis. **Timescale concern:** the ratchet ticks per-turn (elite competition is continuous) while the demographic reset is slow (population decline takes many turns). M67 must validate that these timescales are balanced — if the ratchet accelerates faster than the reset, the secular cycle becomes one-way (rise, crisis, no recovery). Relative wage = `median_agent_wealth / gdp_per_capita_proxy`. Youth bulge = fraction of agents aged 15-30. All inputs already exist or are cheaply derived from Phase 7 agent pool snapshots.

**Institutional life-cycle (M63):** ABM research (Maudet et al.) identifies three emergent regimes depending on the ratio of endogenized trust to exogenous authority: (1) **ordered/frozen** — institutions form fast, lock society into stable but rigid patterns; (2) **highly fluctuating** — institutions exist briefly, high trust but no stability; (3) **complex cycling** — institutions structure and destructure in irregular waves. M67 should validate that all three regimes are reachable by varying institutional formation/dissolution parameters. The complex cycling regime is the narratively richest — it produces the institutional rise-and-fall arcs that feel like real history. **Integration note:** institutional enforcement costs are not a new fiscal system — they map onto the existing governing-cost-per-region framework in `politics.py`. Each active institution adds to the per-turn governing cost. When treasury cannot sustain enforcement, institutions lose legitimacy (the existing treasury-to-stability link, extended).

**Graduated sanctions (M63, from Ostrom):** Institutions with `COMMONS_MANAGEMENT` or `PROPERTY_RIGHTS` need graduated enforcement: first offense = warning (low cost), repeated offense = escalating punishment. This prevents the brittle failure mode where enforcement is all-or-nothing. Implementation: per-agent `violation_count` (u8) for active institutions, with sanction severity = f(violation_count). Agents with high violation counts and low sanction risk (weak enforcement) model the "institutional ceremonialization" failure pattern — the institution exists in name but lost functional substance.

**DF-inspired villain mechanics (M66 extension):** Dwarf Fortress generates emergent antagonists through multi-step plot-hatching: villains recruit agents via corruption techniques (intimidation, bribery, exploiting grievances, promising revenge on enemies), infiltrate institutional positions, and build criminal/subversive networks. In Chronicler terms: a frustrated elite (EMP-surplus agent) with a grudge memory (M48), high wealth, and faction alignment could become an active conspirator — recruiting bridge agents (M50) into a plot to capture an institution (M63) or destabilize a rival. Not a scripted villain arc, but an emergent one where the system state produces the plot. Flag for Phase 8 spec work — likely a curator enhancement rather than a new simulation system.

**Conformist bias calibration (M68):** The sigmoid `P(adopt) = f^D / (f^D + (1-f)^D)` has one key parameter: D (conformity strength). D = 1 is unbiased copying. D = 3 gives strong majority amplification (60% frequency → ~80% adoption). D > 5 approaches threshold voting. Cultural evolution research shows D ≈ 2-3 produces the most realistic dynamics — fast enough to generate cultural regions, slow enough that novel traits can invade. `[CALIBRATE]` in M72.

## Narrative Examples

These are the kinds of chronicles Phase 8 should produce:

> *"The merchant courts of Velanya resolved disputes without bloodshed for three generations. But when the treasury collapsed under Kiral the Profligate, the courts went unpaid. By the time his daughter restored order, the merchants had already turned to hired swords — and the institution of mercantile law was a memory."*

> *"The court of Ashara grew fat with would-be governors — forty nobles vying for twelve seats. When the treasury could no longer pay the frontier garrisons, three of the passed-over lords raised their own armies."*

> *"For decades, the jade caravans from Tessara bought more loyalty than any army. When the mines ran dry, the southern tributaries — who had worn Tessaran jade as their badge of allegiance — began looking north."*

> *"The rebellion in the northern provinces burned hot but stayed contained — until Davan the Wanderer, a disgraced nobleman turned merchant, carried word to the southern guilds. Within a season, five cities had risen."*

> *"The valley of Tessara fed three cities for a century. No one noticed the soil thinning beneath the wheat until the year the rains came late. The granaries held barely a season's reserve, and the surplus nobles — forty families with ancestral claims to land that could no longer feed them — turned on each other."*

## Phase 7 Dependencies

Phase 8-9 systems are designed to consume Phase 7 outputs:

| Phase 8-9 System | Consumes from Phase 7 |
|------------------|----------------------|
| Institutions | Factions (M22/M38), treasury (Phase 2), agent occupations |
| Elite dynamics | Wealth distribution (M41 Gini), GreatPerson count, dynasty tracking (M39) |
| Legitimacy | Dynasty system (M39), Mule system (M48), artifacts (M52), existing succession/governing cost mechanics (`politics.py` Phase 3) |
| Cultural traits | Agent memory (M48), needs (M49), information propagation (M59) |
| Prestige goods | Goods economy (M42-M43), agent-level trade (M58), settlements (M56) |
| Revolution cascading | Deep relationships (M50), information propagation (M59), spatial positioning (M55) |
| Commons | Ecology (turn loop Phase 9), spatial positioning (M55), settlements (M56) |
| Info asymmetry | Information propagation (M59), diplomacy (Phase 5) |

## Research Sources

- Peter Turchin, *Secular Cycles* (2009) — structural-demographic theory, PSI formalization, elite overproduction dynamics
- Peter Turchin, *Historical Dynamics* (2003) — metaethnic frontier theory (already in Phase 7), fiscal-demographic model
- Mark Granovetter, "Threshold Models of Collective Behavior" (1978) — revolt cascading, tipping points in social networks
- Soren Johnson, *Old World* (Mohawk Games) — orders/legitimacy, ruler ambitions, succession as gameplay, character-driven governance
- *Victoria 3* (Paradox Interactive) — pop needs, interest groups as institutional actors, market simulation
- Richerson & Boyd, *Not by Genes Alone* (2005) — dual-inheritance theory, conformist/prestige bias, cultural trait transmission
- Elinor Ostrom, *Governing the Commons* (1990) — institutional solutions to commons dilemmas, enforcement costs, institutional decay
- *Dwarf Fortress* (Bay 12 Games) — artifact creation chains, grudge inheritance, historical figure motivation, emergent narrative from simulation depth
- BioDynaMo project (arXiv 2301.06984) — cache-efficient agent iteration, space-filling curves (already in Phase 7)
- Maudet et al., "An Agent-Based Model of Institutional Life-Cycles" (MDPI Games, 2014) — three institutional regimes (frozen, fluctuating, complex), trust/authority ratio dynamics
- Janssen & Ostrom, "Empirically Based, Agent-Based Models" (2006) — CPR institutional emergence, ADICO framework, graduated sanctions
- Turchin, "Modeling Social Pressures Toward Political Instability" (2012) — PSI formula, MMP/EMP/SFD decomposition, 2020 crisis forecast
- Soren Johnson, "Old World Designer Notes #9: Events" (2021) — memory→requirement→event chains, subject matching against game state, ambition-driven victory
- Henrich & Boyd, "Dual Inheritance Theory" (2002) — conformist/prestige/payoff bias formalization, sigmoid adoption curves, intermediate conformity optimality
- Fearon, "Rationalist Explanations for War" (Stanford 1995) — commitment problems, information asymmetry, no settlement zone as structural war causes
- Organski, power transition theory — war risk at power parity, revisionist vs status quo powers
- Bueno de Mesquita, *The Logic of Political Survival* — selectorate theory, W/S ratio, coalition dynamics
- Acemoglu & Robinson, "Paths to Inclusive Political Institutions" (MIT) — institutional transitions from structural pressure
- Hidalgo & Hausmann, "Building Blocks of Economic Complexity" (PNAS 2009) — product space, capability accumulation
- Stark & Finke, religious market theory — rational choice religion, strictness-commitment dynamics, free-rider problem
- Axelrod, "The Dissemination of Culture" (1997) — homophily-driven interaction, bounded confidence, stable fragmentation
- Stephen Walt, balance of threat theory — alliance formation from shared threat perception, not just power balancing
- Enhanced Gravity Model (Frontiers in Physics 2019) — endogenous trade route formation from profit signals
- ABIDES-Economist (arxiv 2024) — agent-based economic simulation, Walrasian tatonnement, input-output matrices

## Still Deferred Beyond Phase 9

- **Multiplayer / shared world** — different product architecture entirely
- **Procedural scenario generation** — orthogonal feature, benefits from M55 spatial positioning + Phase 8 institutions
- **Metamodel validation** — parameter space exploration at scale, potentially using Claude API for automated analysis
- **Continuous terrain** — heightmaps, erosion, procedural river generation
- **Seldon Crises / interactive mode** — high-stakes choice points surfaced via viewer. Phase 8 institutions + legitimacy + PSI provide the structural crises worth surfacing. Consider as Phase 9b or Phase 10.
- **Agent-level diplomacy** — individual agents as diplomatic actors. Requires stable institutional diplomacy (Phase 8 governance) as foundation.
