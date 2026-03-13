# Chronicler Phase 2 — Feature Roadmap

> Phase 1 (M1-M6) delivered the core pipeline: world generation → simulation → narrative → chronicle output, fully local inference. Phase 2 expands the simulation depth, adds custom scenarios, workflow automation, and a visualization layer.

## Dependency Graph

```
Phase 1 (M1-M6) — COMPLETE
  │
  ├── M7: Simulation Depth           ── no dependencies beyond Phase 1
  ├── M8: Custom Scenarios            ── no dependencies beyond Phase 1
  │     │
  │     └── M9: Scenario Library      ── depends on M8
  │
  ├── M10: Workflow Features          ── depends on M7 (interestingness scoring needs richer events)
  │
  └── M11: Visualization / GUI       ── depends on M7 + M10 (needs richer data + batch output)
        │
        M12: Interactive Mode         ── depends on M11 (needs GUI for intervention UI)
```

M7 and M8 can run in parallel. M10 and M11 can partially overlap.

---

## M7: Simulation Depth

*Make the simulation produce histories worth reading. Fix the all-DEVELOP problem, add tech progression, named events, and persistent landmarks.*

### M7a: Action Variety Engine
- **Personality-driven action weights:** Each leader trait biases action selection. Aggressive → WAR +40%, cautious → DEVELOP +30%, opportunistic → TRADE +30%, zealous → EXPAND +30%. Applied as a pre-prompt bias or as a deterministic fallback when LLM picks DEVELOP for the 5th consecutive turn.
- **Streak breaker:** If a civ picks the same action 3 turns in a row, force a different action from the weighted pool. Simple but eliminates the monotony problem entirely.
- **Situational overrides:** If stability ≤ 2, bias toward DIPLOMACY. If military > 7 and a neighbor is HOSTILE, bias toward WAR. If treasury > 30, bias toward EXPAND or TRADE. These read from game state, not LLM.
- **Optional: deterministic mode flag** (`--no-llm-actions`) that skips LLM action selection entirely and uses weighted random based on faction state + leader trait. Faster, free, arguably better variety.

### M7b: Technology Progression
- **Tech advancement:** When culture + economy both exceed a threshold (e.g., culture ≥ 6 AND economy ≥ 6 AND treasury ≥ 15), civ advances one tech era. Costs treasury.
- **Tech era effects:** Each era provides stat modifiers. Bronze: +1 military cap. Iron: +1 economy base. Classical: +1 culture, unlocks DIPLOMACY treaties. Medieval: +1 military, fortification defense bonus. Renaissance: +2 economy, +1 culture. Industrial: +2 economy, +2 military.
- **Tech disparity in war:** Attacker tech > defender tech by 2+ eras = 1.5x power multiplier. Simulates the "guns vs. spears" effect.
- **Tech-gated actions:** Certain actions only available at certain eras (e.g., formal alliances require Classical+, trade routes require Bronze+).

### M7c: Named Events & Persistent Landmarks
- **Named battles:** When WAR produces an attacker_wins or defender_wins result, generate a battle name from the contested region + era (e.g., "The Siege of Thornwood," "The Battle of Iron Peaks"). Store in a `named_events` list on WorldState.
- **Named treaties:** DIPLOMACY successes produce named treaties ("The Sapphire Accord," "The Pact of the Twin Peaks"). Stored and referenced in future chronicle entries.
- **Cultural works:** When a civ hits culture 10, generate a named cultural achievement ("The Codex of Ashkari Songs," "The Great Lighthouse of Kethani"). Persists in chronicle as a landmark.
- **Historical callbacks:** The chronicle prompt includes the 3 most recent named events so the LLM can reference them. "Forty turns after the Siege of Thornwood, the Dorrathi Clans once again marshaled their forces..."

### M7d: Leader Depth
- **Leader succession events:** When a leader dies, generate a succession event with the new leader's name, trait, and relationship to the predecessor (child, general, usurper, elected). Use a larger name pool or LLM-generated names to avoid duplicates.
- **Leader legacy:** A leader who reigned 20+ turns gets a "legacy modifier" that persists after death (+1 culture for a scholarly leader, +1 military for a warrior, etc.).
- **Rival leaders:** Track personal rivalries between leaders of hostile civs. Reference in chronicle prose.

**Test criteria:** Run 50 turns with 4 civs. Verify: at least 3 different action types chosen per civ, at least 1 tech advancement, at least 2 named events generated, no leader name duplicates.

---

## M8: Custom Scenarios

*Define scenario configs that override default world generation with specific geography, factions, and starting conditions.*

### M8a: Scenario Config Format
- **ScenarioConfig** Pydantic model:
  ```
  name: str
  description: str
  seed: int | None  # None = random
  regions: list[RegionConfig]  # Named, with terrain/capacity/resources
  civilizations: list[CivConfig]  # Named, with starting stats, domains, values, leader, goal
  starting_relationships: dict  # Optional preset relationships
  starting_conditions: list  # Optional active conditions at turn 0
  event_probability_overrides: dict  # Optional — tune event likelihoods per scenario
  turn_count: int
  reflection_interval: int
  ```
- **CLI flag:** `--scenario path/to/scenario.json` that loads the config and bypasses default world generation.
- **Scenario validation:** Verify regions ≥ civs, all civ starting regions exist in region list, relationship pairs are symmetric.

### M8b: Scenario Templates
- **template_fantasy.json** — Default behavior wrapped as a scenario (4 civs, 8 regions, standard events). Proves the format works.
- **template_two_empires.json** — 2 powerful civs, 6 contested border regions, high starting military, HOSTILE relationship. Designed to produce war-heavy chronicles.
- **template_golden_age.json** — 4 civs, all FRIENDLY, high culture/economy, low military. Designed to produce cultural/trade chronicles that eventually destabilize.

**Test criteria:** Load each template, run 10 turns, verify world state matches template config at turn 0.

---

## M9: Scenario Library

*Pre-built scenarios for specific worlds and settings. Depends on M8 scenario format.*

### M9a: Post-Collapse Minnesota
- **Regions:** Willmar, Benson, Montevideo, Marshall, Granite Falls, New London, Spicer, Litchfield, Olivia, Redwood Falls. Terrain mapped to actual geography (plains/fertile for farm country, river for Minnesota River towns).
- **Factions:** 4-6 emergent groups — Farmer Cooperatives (agriculture/resilience), River Towns Alliance (trade/waterways), National Guard Remnant (military/order), Prepper Networks (survival/self-reliance), Church Communities (faith/community), Roaming Scavengers (adaptability/opportunism).
- **Starting conditions:** Grid-down active condition affecting all factions (severity 7, duration 20 turns). Low starting tech (Tribal). High starting event probabilities for migration, rebellion, and border incidents.
- **Custom events:** Harsh Winter (Minnesota-specific — population/stability hit scaled by season), Harvest (economy boost for agricultural factions), Supply Cache Discovery.

### M9b: Dead Miles / Port Junction
- **Regions:** Gasoline Alley, The Terminal, The Gulch, The Grid, Showroom Row, The Docks, Rustborn Quarter, Chrome Heights, Industrial Flats, Port Junction Central.
- **Factions:** Geargrinders (workshop/craft, Honor/Skill), Haulers Union (logistics/labor, Solidarity/Strength), Chrome Council (prestige/preservation, Heritage/Order), Rustborn (survival/community, Freedom/Resilience), Electrics (technology/progress, Innovation/Efficiency).
- **Starting relationships:** Chrome Council SUSPICIOUS of Rustborn. Haulers FRIENDLY with Geargrinders. Electrics NEUTRAL to all.
- **Custom events:** The Recall (targeted compliance action against heritage vehicles), Dock Strike, Parts Shortage, Showroom Scandal.
- **Output use:** Generated backstory for the game universe — 200-500 turn history that becomes canonical lore.

### M9c: Sentient Vehicle World (pre-Dead Miles)
- **Deep history scenario** — 500 turns, 5 original factions, starts at Tribal era. Designed to generate the mythic pre-history of the vehicle world before the events of Dead Miles. The chronicle becomes the "ancient history" that characters in the game reference.

**Test criteria:** Each scenario loads, validates, and runs 20 turns without errors.

---

## M10: Workflow Features

*Batch runs, interestingness ranking, forking, and intervention hooks.*

### M10a: Batch Runner
- **CLI flag:** `--batch N` runs N chronicles with sequential seeds (base_seed, base_seed+1, ..., base_seed+N-1).
- **Output:** Each run gets its own directory: `output/batch_42/seed_42/chronicle.md`, `output/batch_42/seed_43/chronicle.md`, etc.
- **Summary file:** `output/batch_42/summary.md` — one-line summary per run with key stats (wars, collapses, tech advancements, dominant faction).

### M10b: Interestingness Scoring
- **Score each run** on: number of wars (×3), number of collapses (×5), number of named events (×1), number of distinct actions chosen across all civs (×1), number of era reflections with importance ≥ 7 events (×2), number of tech advancements (×2), max faction stat swing (how much a faction's stats changed from start to end, ×1).
- **Rank batch output** by interestingness score. Summary file sorted best-to-worst.
- **Auto-flag "boring" runs** where every civ picked the same action >60% of the time.

### M10c: Fork Mode
- **CLI flag:** `--fork output/state.json --seed 999 --turns 50`
- Loads a mid-run state, applies a new seed for the RNG, and continues. Same starting conditions, different future.
- **Use case:** Find an interesting turn-50 state, fork it 5 times with different seeds, see which future is most dramatic.

### M10d: Intervention Hooks
- **CLI flag:** `--interactive` pauses at each era boundary (every N turns).
- At pause: prints current state summary (faction standings, relationships, recent events), then prompts the user:
  - `continue` — resume simulation
  - `inject <event_type> <target_civ>` — force an event (e.g., `inject plague "Kethani Empire"`)
  - `set <civ> <stat> <value>` — manually adjust a stat (e.g., `set "Dorrathi Clans" military 9`)
  - `fork` — save current state and continue (creates a save point for later forking)
  - `quit` — stop and compile chronicle from what's been generated so far
- **Creative director mode** — you shape the broad strokes, the simulation fills in the details.

**Test criteria:** Batch mode produces N output directories. Fork mode loads state and continues. Interactive mode pauses and accepts at least `continue` and `quit`.

---

## M11: Visualization / GUI

*Web-based chronicle viewer. Reads state.json and chronicle.md, no backend required.*

### M11a: Chronicle Viewer (React)
- **Single-page React app** that loads `state.json` and `chronicle.md`.
- **Timeline sidebar:** Horizontal or vertical timeline with turn markers. Click a turn to scroll to that chronicle entry. Era boundaries highlighted.
- **Chronicle pane:** Rendered Markdown with era headings, turn entries, and epilogue.
- **Reading mode:** Clean typography, dark/light mode, comfortable line width.

### M11b: Faction Dashboard
- **Faction cards:** One card per civilization showing current name, leader, domains, values, and a sparkline of each stat (population, military, economy, culture, stability) over time.
- **Relationship matrix:** Grid showing disposition between all faction pairs, color-coded (red=hostile, yellow=suspicious, gray=neutral, green=friendly, blue=allied). Updates as you scrub the timeline.
- **Event log:** Filterable list of all events, sortable by turn, type, or importance.

### M11c: Territory Map
- **Node-based map:** Regions as nodes, connections based on shared-border inference (or manual adjacency in scenario configs). Nodes colored by controlling faction. Uncontrolled regions in gray.
- **Animated playback:** Play button that advances through turns, showing territory changes as faction colors shift. Speed control.
- **Click a region:** Shows region details (terrain, resources, carrying capacity, control history).

### M11d: Stat Graphs
- **Recharts line graphs:** One graph per stat (population, military, economy, culture, stability, asabiya, treasury) with one line per faction. Scrub-synced with the timeline.
- **Event overlay:** Vertical markers on graphs showing when wars, collapses, plagues, and discoveries occurred.
- **Comparison mode:** Select 2 factions to overlay their stats directly.

**Test criteria:** App loads a sample state.json and chronicle.md. Timeline navigation works. Faction cards render. At least one graph displays correctly.

---

## M12: Interactive Mode GUI

*Web-based intervention interface. Depends on M11 viewer + M10 intervention hooks.*

### M12a: Live Simulation Dashboard
- **Real-time updates:** Instead of reading a completed state.json, connect to the running simulation via a local WebSocket or polling endpoint. The chronicler process exposes turn-by-turn state updates.
- **Live chronicle:** New turn entries appear as they're generated, auto-scrolling the chronicle pane.
- **Live map:** Territory map updates each turn.

### M12b: Intervention Panel
- **Era pause UI:** When simulation hits an era boundary, the dashboard shows an intervention panel.
- **Event injection:** Dropdown to select event type + target civ, click to inject.
- **Stat override:** Slider controls for each faction's stats.
- **Fork button:** Saves current state and opens a new tab with the forked simulation.
- **"What if" mode:** Fork silently, run 10 turns in the background, show a preview of what happens, then let the user decide whether to commit the fork or revert.

### M12c: Scenario Editor
- **Visual scenario builder:** Place regions on a canvas, draw connections, assign terrain/resources. Create factions with drag-and-drop stat sliders. Set starting relationships via the matrix.
- **Export:** Saves as a scenario.json compatible with M8 format.
- **Import:** Load existing scenarios for editing.

**Test criteria:** Dashboard connects to a running simulation. At least one intervention type (event injection) works end-to-end. Scenario editor exports valid JSON.

---

## Implementation Notes

- **M7 and M8 are the highest priority** — they make the core simulation worth running repeatedly. Everything else builds on richer simulation output.
- **M9 scenarios are content work** — can be authored in parallel with any other milestone since they're just JSON configs once M8 is done.
- **M11 visualization is a separate codebase** — a React app in a `viewer/` directory that reads output files. No coupling to the Python simulation beyond the JSON/MD file formats.
- **M12 is the stretch goal** — it requires a communication layer between the Python simulation and the web UI. WebSocket or simple HTTP polling. Build it last.
- **Each milestone follows the standard session workflow:** read → plan → review plan → implement → review implementation.
