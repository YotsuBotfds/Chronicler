# Building an AI-driven civilization chronicle generator

**The architecture for a "one prompt → readable history" system already exists in pieces across game design, academic simulation, and LLM agent research — it just needs assembly.** The most promising approach combines Kevin Crawford's Stars Without Number faction turn system (the cleanest LLM-executable ruleset found) with the memory-stream architecture from Stanford's Generative Agents and the rationalization-first narrative technique from Caves of Qud. This report compiles the reference frameworks, extractable rule sets, and architectural patterns needed to hand Claude Code a single prompt and get back a procedurally generated civilization chronicle.

The core challenge is not generating text — LLMs excel at that — but **maintaining consistent state across hundreds of generation steps**. Every successful project in this space uses external structured state (JSON, databases, files) rather than relying on the LLM's context window alone. GPT-4's accuracy for non-trivial state tracking tops out at roughly 60% without external grounding. The solution is a hybrid architecture: symbolic rules drive the simulation engine while the LLM handles narrative interpretation, ambiguity resolution, and prose generation.

---

## Two fundamental philosophies for procedural history

Research across dozens of systems reveals a crucial fork in design philosophy that determines everything else about the architecture.

**Simulation-first systems** (Dwarf Fortress, WorldBox, Sugarscape) run a zero-player strategy game with agents following explicit rules, then record the log as "history." Tarn Adams describes Dwarf Fortress world generation as "a giant zero-player strategy game going on with somewhat loose turn rules and bad AI (but thousands of agents), and history is just a record of that." The advantages are deep causal consistency and surprising emergent results. The disadvantage is computational cost and the need to post-process output to find interesting moments — **without sufficient dynamics and mechanisms, the output is boring**.

**Rationalization-first systems** (Caves of Qud, Epitaph) invert causality: they decide an event will occur, then fabricate a plausible cause after the fact. Caves of Qud's sultanate system generates 10–22 life events per historical ruler, chosen randomly from a pool of 17 event types, then uses a Tracery-like replacement grammar to produce "gospels" that rationalize each event using the ruler's accumulated state. If the ruler has allied with frogs, a siege event becomes "Acting against the persecution of frogs, Sultan Resheph led an army to the gates of Qathiq." If no relevant state exists, the system **creates new state to rationalize the event** — full causality reversal. This approach is computationally cheap, consistently produces interesting output, and is far easier for an LLM to execute.

**The optimal architecture for Claude Code combines both**: use lightweight simulation rules to advance state (faction stats, population, resources, relationships), then hand that state to the LLM's narrative engine for rationalization into prose. The simulation provides structural coherence; the LLM provides literary quality.

---

## The five reference frameworks worth handing to Claude Code

### 1. Stars Without Number faction turns — the cleanest LLM-executable ruleset

Kevin Crawford's faction turn system from Stars Without Number (and its fantasy counterpart Worlds Without Number) is **the single most directly extractable simulation framework** found in this research. It was designed for a human game master to run between tabletop sessions — making it inherently suitable for LLM execution.

Each faction tracks just **three ratings** (Force, Cunning, Wealth, each rated 1–8), plus HP, treasury (FacCreds), a current Goal, and deployed Assets. The turn sequence has seven phases: Initiative → Maintenance → Goal Check → Income → Action → End of Turn → Rumors and News. Each faction takes exactly **one action per turn** from a menu of ten options (Attack, Buy Asset, Expand Influence, Seize Planet, etc.). Combat between assets uses simple opposed rolls. Goals drive behavior and earn XP when achieved. Roughly 75 asset types across three categories provide variety without overwhelming complexity.

The "Rumors and News" phase is particularly brilliant for chronicle generation — it explicitly calls for summarizing visible events into narrative form. This is exactly where the LLM excels. The system's constraints (one action per turn, explicit action menu, numeric resolution) prevent the LLM from drifting into narrative meandering while still allowing rich emergent dynamics.

### 2. Caves of Qud's sultanate system — the narrative generation template

Jason Grinblat and Brian Bucklew's approach, documented in their 2017 Foundations of Digital Games paper "Subverting Historical Cause & Effect," provides the best model for how to turn simulation state into readable chronicles. The key innovations are **domains as narrative threads** (a sultan with domain "ice" gets icicles, tundra, and frost woven throughout their entire biography), **shared state as narrative glue** (a limited set of properties reused across many events creates emergent micro-narratives), and **deliberate exploitation of apophenia** (the human tendency to perceive patterns in loosely connected events).

For Claude Code, this translates to: give each civilization 2–3 thematic keywords (their "domains") and reference them in every event description involving that civilization. A maritime culture's trade disputes involve harbors and currents; their religious crises involve sea-gods and storms. This creates the perception of deep cultural coherence with minimal mechanical overhead.

### 3. Stanford's Generative Agents — the memory architecture

The 2023 paper by Park et al. established the gold standard for LLM agent simulation. Its three-component architecture — **memory stream** (records all experiences in natural language with timestamps), **retrieval** (scores memories by recency + relevance + importance), and **reflection** (periodically consolidates recent memories into higher-level insights) — solves the fundamental problem of maintaining coherent behavior across many generation steps.

For a civilization chronicle, the equivalent would be: each faction maintains a running memory document. After every few turns, the LLM generates "reflections" — higher-level summaries like "The Kethani Empire has been steadily losing territory for three decades; their military is overstretched and their treasury depleted." These reflections then inform future decision-making and narrative framing. The importance scoring (rating events 1–10 from mundane to poignant) helps the chronicle writer know which events deserve paragraphs and which get sentences.

### 4. Turchin's metaethnic frontier model — the empire dynamics engine

Peter Turchin's asabiya model is the most elegant mathematical framework for the rise and fall of empires. Each grid cell has an **asabiya value** (collective solidarity, 0–1). At frontier zones bordering a different civilization, asabiya grows: S' = S + r₀·S·(1−S). In the interior, far from threats, asabiya decays: S' = S − δ·S. Empire power is projected as P = Area × Average_Asabiya × exp(−distance/h). When attacking power exceeds defending power by a threshold, territory is annexed. When empire-wide asabiya drops below a collapse threshold, the polity shatters.

This produces the historically observed pattern where empires form on contested frontiers (Roman Republic forged by conflict with Gauls and Samnites), expand during their period of high solidarity, then decay from the center as generations of peace erode collective will. **Multiple implementations exist**: NetLogo (mbyim/turchin_metaethnic_frontier_theory on GitHub), Unity (Paul Kanyuk), and R (Mesoudi's cultural evolution tutorial, Model 12). The equations are simple enough for an LLM to evaluate qualitatively turn-by-turn without exact computation.

### 5. Epitaph's cascading probability system — the lightweight event engine

Max Kreminski's Epitaph (fully open source in ClojureScript at github.com/mkremins/epitaph) demonstrates that a compelling civilization history can emerge from just **two entity types**: technologies and events. Each technology has an `event_chances` map that modifies probabilities of future events. Discovering agriculture increases the probability of famine events. Developing nuclear technology increases the probability of nuclear war. The "history" is nothing but probability chains — no spatial simulation, no individual agents, just cascading likelihoods.

For Claude Code, this is the fallback model when full simulation is too expensive: maintain a probability table of possible events, modify it whenever something happens, and roll against it each turn. Combined with the SWN faction system for the strategic layer and the Qud narrative system for prose, this provides event variety without requiring complex simulation mechanics.

---

## The minimum viable simulation for emergent storytelling

Research across game design theory, complexity science, and dozens of implemented systems converges on a surprisingly consistent answer: **you need 5–8 interlocking subsystems with 3–5 parameters each**. The combinatorial explosion from their interactions produces emergent complexity; the small parameter count keeps state manageable for an LLM.

**Each civilization needs roughly these parameters**: Population (1–10 scale), Military (1–10), Economy (1–10), Culture (1–10), Stability (1–10), Technology Era (Tribal through Industrial, 7 levels), Treasury (abstract wealth units), 2–3 Cultural Values (keywords like "Honor," "Commerce," "Faith"), a named Leader with one personality trait, a current strategic Goal, and a relationship disposition toward every other civilization (Hostile / Suspicious / Neutral / Friendly / Allied) with a list of specific grievances and bonds.

**The turn structure that creates interesting chronicles has six phases**: (1) Environment — check for natural events like drought, plague, or disaster; (2) Production — generate wealth based on economy and territory, grow or shrink population based on food and stability; (3) Action — each civilization takes one major action from a fixed menu (Expand, Develop, Trade, Diplomacy, or War); (4) Events — roll for 0–1 random external events; (5) Consequences — resolve all cascading effects; (6) Chronicle — generate narrative summary.

**What makes this produce stories rather than spreadsheet updates** is the interlocking between subsystems. Investing in military weakens the economy (resource trade-off). Expansion creates border friction with neighbors (unintended consequence). A plague weakening one civilization creates opportunity for its rivals (cascading effect). A brilliant leader dying triggers a succession crisis (personality matters). Trade dependency creates both alliance incentive and vulnerability (double-edged sword). From Tynan Sylvester's design philosophy for RimWorld, the key insight is that **spiraling event chains** — where one disruption triggers others in connected cascades — produce the most compelling emergent narratives.

---

## Existing LLM world simulation projects that prove the concept

Several projects have already demonstrated pieces of this architecture. **WarAgent** (Hua et al., 2023; github.com/agiresearch/WarAgent) simulates World War I, World War II, and the Chinese Warring States period using GPT-4 or Claude-2 as country agents. Each country has a profile, reacts to situations by generating actions from a constrained action space, and a "Secretary Agent" verifies each proposed action for format, content, and logical coherence through up to four rounds of revision. The system successfully replicated macro-historical outcomes like alliance formation sequences, demonstrating that LLM-driven historical simulation produces plausible results.

**AI Town** (a16z-infra, MIT License on GitHub) is the most deployable open-source implementation of Stanford's Generative Agents architecture, rebuilt in TypeScript with Convex for the backend. Its core agent logic fits in roughly **200 lines of code**, proving the architecture can be lightweight. Community forks have adapted it for various scenarios, establishing that the pattern generalizes.

**The Neural Civilization Simulator** (github.com/Boyyey/-Neural-Civilization-Simulator) combines deep reinforcement learning agents with language models, featuring emergent language evolution, social networks, episodic and semantic memory, dynamic tech trees, and cultural diffusion. It runs on a Streamlit dashboard with real-time visualization. **NovelGenerator** (github.com/KazKozDev/NovelGenerator) demonstrates autonomous long-form narrative generation — expanding brief concepts into full manuscripts without human intervention while tracking multiple character perspectives, maintaining knowledge states for each character, and synchronizing independent plot threads.

A crucial finding from academic research: the 2024 paper "Can Language Models Serve as Text-Based World Simulators?" found that **GPT-4 accuracy for non-trivial state changes does not exceed 59.9%**. This definitively establishes that the LLM cannot be the simulation engine alone — it needs external structured state. The neurosymbolic approach (LLM generates code or follows explicit rules, with a formal system tracking state) consistently outperforms pure LLM simulation in both consistency and diversity of output.

---

## The worldbuilding data model from Azgaar and Eigengrau

For geographic and cultural coherence, **Azgaar's Fantasy Map Generator** (MIT License, 5,500+ GitHub stars) provides the most complete open-source data model. Its 19-stage sequential pipeline — Heightmap → Climate → Rivers → Biomes → Cultures → States → Religions → Settlements → Provinces → Routes → Military — demonstrates the layered generation architecture that nearly every successful system uses. Each layer constrains and informs the next. The key data structures are: `cultures[]` (with name, type, origins, expansionism, naming base), `states[]` (with government type, diplomacy arrays, military, coat of arms), `religions[]` (with a tree-branching model where organized religions split from folk religions), and `settlements[]` (with population, culture, religion, and location).

**Eigengrau's Essential Establishment Generator** contributes a critical pattern: **reciprocal relationship creation**. When an NPC mentions a family member, that person is created as a full NPC with back-references. This produces webs of interconnected characters that feel organic. For a civilization chronicle, the equivalent is: when an event mentions a treaty between two civilizations, both civilizations' relationship records are updated; when a leader is assassinated, the assassin becomes a named historical figure with their own motivations that influence future events.

The synthesis of these tools suggests a world data schema for Claude Code:

```
World { name, seed, geography{regions[], rivers[], climate_zones[]} }
  ├── Civilizations[] { name, stats, values[], leader, goal, treasury, tech_era }
  ├── Relationships[][] { disposition, treaties[], grievances[], trade_volume }
  ├── Historical_Figures[] { name, role, traits, civilization, alive, deeds[] }
  ├── Events_Timeline[] { turn, type, actors[], description, consequences[] }
  └── Active_Conditions[] { type, affected_civs[], duration, severity }
```

---

## Academic models that provide calibrated simulation rules

Beyond game systems, academic agent-based models offer rigorously tested rule sets. **Sugarscape** (Epstein & Axtell, 1996) remains the foundational reference, with fully documented rules for resource gathering, trade via marginal rate of substitution, cultural transmission through binary tag strings, and combat based on relative wealth. Multiple implementations exist in Python (langerv/sugarscape on GitHub), NetLogo, and Julia (Agents.jl). **Mesoudi's cultural evolution tutorial** provides **19 complete, runnable models** with R source code covering unbiased transmission, prestige bias, conformist bias, migration, cultural group selection, and Turchin-style empire dynamics (bookdown.org/amesoudi/ABMtutorial_bookdown/).

For modeling civilizational collapse, **Schunck et al. (2024)** published in *Entropy* the most rigorous computational implementation of Tainter's theory. Agents are classified as laborers, coordinated laborers, or administrators. Administrators increase productivity but consume energy, with diminishing returns as complexity grows. A ratchet effect prevents administrators from reverting to laborers. External shocks force the addition of more administrators, increasing complexity until the energy surplus hits zero and the system collapses. This maps directly to a "bureaucratic overhead" mechanic: as civilizations grow, their maintenance costs escalate until they become fragile.

Turchin's **Structural-Demographic Theory** provides the most complete model of internal civilizational dynamics via three variables: Mass Mobilization Potential (popular immiseration), Elite Mobilization Potential (intra-elite competition), and State Fiscal Distress, combined into a Political Stress Indicator (PSI = MMP × EMP × SFD). The secular cycle runs: Expansion (population grows, wages stable) → Stagflation (population hits carrying capacity, wages decline) → Crisis (elite overproduction, fiscal crisis, instability peaks) → Depression/Resolution (population collapse, reset). These dynamics can be tracked qualitatively by an LLM: "The Kethani Empire is in its Stagflation phase — population pressure is mounting, the nobility has swelled to three times its historical average, and the treasury is depleted from border wars."

---

## Practical architecture for the Claude Code prompt

The recommended architecture, synthesized from all research, has **four layers that Claude Code should build as a single Python program**:

**Layer 1 — World State (JSON files)**: Structured data for every entity. Geography defined as named regions with terrain types and carrying capacities. Civilizations with the ~12 parameters described above. A relationship matrix. An events timeline. This is the source of truth — the LLM reads and writes to these files but never relies on memory alone.

**Layer 2 — Simulation Engine (deterministic rules)**: A Python loop that advances time turn by turn. Each turn executes the six-phase sequence (Environment → Production → Action → Event → Consequence → Chronicle). Actions are chosen by querying the LLM with the faction's current state, goal, and relationships, constrained to the SWN-style action menu. Combat and trade are resolved using the simplified Lanchester and comparative-advantage models. Random events drawn from a weighted table modified by the Epitaph-style cascading probability system.

**Layer 3 — Narrative Engine (LLM rationalization)**: After each turn's simulation resolves, the LLM receives the updated state and list of mechanical outcomes, then generates a chronicle entry using the Caves of Qud technique: weave each civilization's thematic domains through the prose, reuse shared state (character names, cultural touchstones, geographic landmarks) for coherence, and let apophenia do the rest.

**Layer 4 — Memory and Reflection**: Every 5–10 turns, the system generates Generative Agents-style reflections — higher-level narrative summaries that consolidate recent events into era-defining themes. These reflections become the "eras" or "ages" of the chronicle and help prevent consistency drift by giving the LLM condensed context to reference.

The key design principles for LLM execution: keep numeric parameters minimal (5–8 per entity, since LLMs track text better than large numeric state spaces), use categorical descriptors alongside numbers, make rules qualitative where possible ("high military + low stability = risk of military coup"), maintain a running state document the LLM references each turn, and **separate the simulation engine from the narrative engine** — run the rules first, then narrate.

---

## Conclusion: what makes this tractable now

Three developments make the "one prompt → chronicle" goal achievable in 2026 in a way it wasn't before. First, **200K+ token context windows** allow Claude Code to hold a substantial world state, simulation ruleset, and accumulated chronicle simultaneously — though external state files remain essential for reliability. Second, **code execution capability** means Claude Code can write and run a Python simulation loop rather than trying to simulate numerically in its head, sidestepping the ~60% state-tracking accuracy ceiling for pure LLM simulation. Third, the **reference architecture is now well-established**: the SWN faction turn for strategic simulation, Turchin for empire dynamics, Caves of Qud for narrative rationalization, and Generative Agents for memory management.

The five reference frameworks (SWN faction turns, Caves of Qud sultanate system, Stanford Generative Agents, Turchin's metaethnic frontier model, and Epitaph's cascading probabilities) together provide a complete template. The prompt to Claude Code should instruct it to: (1) generate an initial world state with 4–6 civilizations on a map of named regions, (2) implement the six-phase turn loop in Python with SWN-derived rules, (3) run 50–100 turns of simulation with state tracked in JSON files, (4) generate chronicle entries each turn using domain-threaded narrative rationalization, and (5) produce era-level reflections every 10 turns that become chapter breaks in the final chronicle. The output should be a single Markdown document reading like a mythic history — named ages, legendary rulers, decisive battles, cultural renaissances, and inevitable collapses — all emergent from the interaction of simple rules with LLM narrative intelligence.