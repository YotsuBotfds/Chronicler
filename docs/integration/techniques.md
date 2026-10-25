# Technology as diffusing techniques

Branch `feat/techniques`, started on `integrate/wave-3` at `20eeead`
(procedural geography, the contact ledger, causal provenance, campaigns
and governance, fisheries, and default-off epidemiology, finance and
diplomacy) and merged with `integrate/wave-3` at `92b6122` (the food-balance
corrections, with Rust changes), which is the base of every result below.
Code: `src/chronicler/techniques.py` (behavior) and
`src/chronicler/techniques_state.py` (registry and persisted state).

**Status.** Default on for new worlds since the 2026-10 techniques full
gate ([techniques-default.md](techniques-default.md)), behind
`WorldState.techniques` (CLI `--techniques` / `--no-techniques`). On the
current defaults (epidemiology, finance and diplomacy on) the full profile
(200 seeds x 500 turns) passes strict with the switch on, with 0 extinct
worlds and no comparator regression against the current defaults' full
report (`wave3-defaults.md`, section 5). The subset needs-oracle miss on
seeds 62-81 ([Gate](#gate)) recurs on the current defaults, by one seed on
a set whose base sits on the threshold, and is noise (techniques-default.md,
section 2). The results below were measured on the `92b6122` base with the
switch off by default. With the switch off no technique code runs and every
output is byte-identical to `92b6122` (and was to `20eeead` before the
merge; see [Feature-off identity](#feature-off-identity)).

## Why

A civilization's technology was one `tech_era` field. It advanced when the
civ met culture and economy thresholds, paid a treasury cost and held a
fixed set of resource types (`tech.check_tech_advancement`); it fell back by
a dice roll on three M18 triggers (capital collapse, entering twilight, a
black swan while stressed: `emergence.check_tech_regression`). Nothing
spread: neighbours and trading partners never learned from each other, and
a regression had nothing to do with who still knew what. On the subset gate
(base `92b6122`, seeds 42-61) the resource requirement (both ore and timber
in the civ's own land for the first advance) kept 54 of 61 living civs
tribal for 200 turns, and the dice produced 1.9 regressions per run.

## What was built

| Part | Summary |
| --- | --- |
| Registry | 30 techniques over eight domains (agriculture, metallurgy, construction, navigation, writing and administration, medicine, commerce and banking, military), each with a tier (its era), prerequisites and the terrain or resources it needs. Append-only. |
| Practice | Per region and technique, the share of the people who practise it (`TechniqueState.rows`). Grows logistically toward 1 where the region suits the technique (toward 0.2 where it does not), once its prerequisites are practised there. |
| Diffusion | Along the contact ledger's region flows, channel by channel (merchants, migrants, soldiers, pilgrims), plus the shared borders of regions under one ruler; each channel carries some domains more than others. Gains are attributed to the channel and source that carried them. |
| Decay | Always a little; much faster when the connected people who share the craft (the region's own and those of its close contacts, practitioners counting double) fall short of what the technique's tier needs. Plague, famine, collapse or isolation therefore lose the most demanding techniques first. |
| Invention | Driven by the old era advance's research inputs: culture and economy thresholds, a treasury cost, the tech diffusion rate multiplier and the scholarship focus; the tech focus steers the choice and great scientists, writing, law, printing and the telegraph speed it. |
| Era | Derived from the practised technique mix: a quorum per tier, with hysteresis, a three-tick grace and the capital as the seat that keeps an era. Advances and regressions keep the old events, era bonuses, focus selection and named events, so every era consumer keeps working. The M18 random regression does not run while techniques are on. |
| Effects | Battle strength, build costs, trade range, crop and fish yields, and (with those switches) epidemic fatality and quarantine, and credit capacity. |
| Provenance | Inventions, adoptions ("X learned Y from Z's merchants"), losses, advances and regressions cite their causes. |

### Cut, and why

* **Rust agent packets (`InfoType::Technique`).** A later phase, as asked.
  Agents do not carry techniques; the agent pool sees techniques only
  through era and focus (existing bridge fields) and through the economy.
  No Rust was changed.
* **Viewer panels.** `history[n].techniques` and the new event types are
  in the bundle; the viewer does not display them yet. (Since added on
  `feat/viewer-systems`, with an additive `techniques.regions` snapshot
  field: see [viewer-systems.md](viewer-systems.md).)
* **Action-weight contributors.** Techniques add no weight bucket: the
  tech-focus bucket (capped at 1.5) and every other modifier are unchanged.
  Techniques reach actions only through the derived era (for example TRADE
  needs Bronze) and the focus it selects.
* **Trade-range counters.** Routes opened by navigation or roads are not
  counted (the route cache is rebuilt a varying number of times per turn,
  so a counter would not survive a resume identically); the effect is
  covered by tests.
* **Technique-specific great persons and artifacts.** Scientists still
  come from the existing triggers (see [Open items](#open-items)).

## The registry

`techniques_state.TECHNIQUES`, in storage order (rows hold the index):

| Tier (era) | Techniques (needs) |
| --- | --- |
| 1 Bronze | irrigation (river or grain), bronze working (ore), masonry, coastal sailing (coast or fish), writing, herbal lore (forest, jungle, marsh or botanicals) |
| 2 Iron | iron working (ore), coinage (precious metal or ore), horsemanship (plains, steppe, desert), the ox plough (grain), road building |
| 3 Classical | written law, aqueducts, celestial navigation (coast), siegecraft, physicians |
| 4 Medieval | the heavy plough (grain), castle building, the stirrup (plains, steppe, desert), banking, the compass (coast), quarantine lazarets |
| 5 Renaissance | printing, gunpowder (salt), double-entry bookkeeping, ocean navigation (coast) |
| 6 Industrial | steam power (ore or timber), vaccination, railways |
| 7 Information | the telegraph |

Every prerequisite is an earlier technique of the same or a lower tier.
Ore, precious metal, salt and timber may be supplied: any region of the
civ, or a region trading with one of its regions at a decayed flow of at
least 1, supplies them (bronze without mines, through trade). Grain, fish
and botanicals must be local.

## Dynamics

Per turn, in Phase 4, with the contact ledger of the end of the previous
turn and the current populations and controllers:

* **Growth** `0.15 p (1 - p / cap) (1 - s)`, zero without the
  prerequisites at 0.2 in the region, zero in an occupied region and halved
  during a famine; `cap` is 1, or 0.2 where the region lacks the
  technique's needs.
* **Diffusion** `(cap - p) (1 - exp(-0.005 r H))`, with
  `H = sum over partners j and channels c of w[c][domain] * flow_c(j, t) * p_j`
  (undirected ledger flows, plus a shared border of 3 under one ruler, or
  every border while the ledger is off) and `r` the tech diffusion
  multiplier. Weights:

  | Channel | agriculture | metallurgy | construction | navigation | writing | medicine | commerce | military |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | merchants | 0.6 | 0.8 | 0.3 | 1.0 | 0.4 | 0.3 | 1.0 | 0.2 |
  | migrants | 1.0 | 0.5 | 0.8 | 0.4 | 0.5 | 0.6 | 0.4 | 0.3 |
  | soldiers | 0.1 | 0.6 | 0.4 | 0.1 | 0.1 | 0.2 | 0.1 | 1.0 |
  | pilgrims | 0.2 | 0.1 | 0.4 | 0.2 | 1.0 | 1.0 | 0.2 | 0.0 |
  | shared border | 0.5 | 0.5 | 0.5 | 0.3 | 0.5 | 0.5 | 0.5 | 0.5 |

* **Decay** `(0.01 + 0.2 s) p`, with the shortfall
  `s = max(0, 1 - pool / need)`. The pool is the region's people plus those
  of each partner weighted by `min(1, weighted contact / 10)`, a person
  counting 1 when practising and 0.5 otherwise; the need is
  `12 tier^1.5` (12, 34, 62, 96, 134, 176, 222).
* An empty region's practice fades by 5% a turn rather than vanishing: its
  people moved and settlers may return with it. It teaches no one and
  weighs nothing in civ practice while empty, but still counts toward what
  the civ knows, so a few people shuttling between two regions do not make
  the civ forget and relearn everything (they did on the food-balanced
  base: 145 of 184 losses on the subset gate came back within ten turns
  before this rule).
* Rows below 0.002 are dropped; values are rounded to 6 decimals.

**Invention.** At most one per civ per turn. Candidates: techniques the civ
does not know, of at most one tier above its era, whose prerequisites it
knows, with a site (an inhabited, suitable region practising the
prerequisites). The lowest tier is taken first, then the focus's domains,
then the number of sites, then a hash. The civ needs the culture and
economy thresholds of the era advance into that tier
(`tech.TECH_REQUIREMENTS`) and pays half of that advance's treasury cost
(`keep`), divided by the diffusion multiplier and times 0.8 under the
scholarship focus. The chance is
`0.10 * (culture + economy) / 200 * r * research / difficulty[tier]`
(difficulty 1, 1.5, 2.5, 4, 6, 9, 13), research being
`1 + practice-weighted writing (0.1), written law (0.1), printing (0.3), telegraph (0.3)`,
times 1.25 for scholarship and `1 + 0.5` per active great scientist (at
most two). One draw per civ per turn, `stable_hash_int("technique_invent", seed,
turn, civ index)`. The invention starts practice at 0.2 in the capital if it
is a site, else the most populous site.

**Known techniques** (per civ, with hysteresis): taken up when one of the
civ's regions practises it at 0.10, lost when all of them (an empty
region's fading practice included) fall below 0.03. A new polity (secession, restoration, first tick) starts with what
its land practises, silently.

**Era.** Civ practice of a technique is the population-weighted mean over
the civ's regions that suit it, smoothed across ticks (each tick's
measurement weighs 0.25), so people moving between a civ's regions do not
swing it. A civ advances one era when it knows and
practises at 0.25 a quorum of the next tier (3, 3, 3, 3, 2, 2, 1) while
every lower tier is kept. A tier is kept while the quorum is practised at
0.10 either civ-wide or in the capital, so untaught land that was just
taken or settled does not undo an era; losing the capital's practitioners,
or a decline everywhere, does. An era falls one step after three
consecutive ticks below a kept quorum (`era_strain`). Advances replay
`phase_technology` exactly (era bonus, focus reselection,
`tech_focus_selected`, great-person bookkeeping, `tech_breakthrough` and
paradigm-shift named events); regressions replay the M18 consequences
(era bonus removed, focus cleared, `note_tech_era_lost`).

## Effects

| Effect | Where | Rule (with the switch off every value is unchanged) |
| --- | --- | --- |
| Battle strength | `war/battles._side_power`, `action_engine.resolve_war` | x(1 + practice-weighted bonus), at most 1.4: bronze 0.05, iron 0.08, horsemanship 0.04/0.02, siegecraft 0.05 (attack), stirrup 0.06/0.03, castles 0.08 (defence), gunpowder 0.12/0.10. The era multipliers still apply through the derived era. |
| Build costs | `infrastructure.handle_build` | the charged cost x(1 - region practice-weighted discount), at least 0.6: masonry 0.08, roads, aqueducts, castles 0.04 each (castles 0.10 more for fortifications), steam power 0.06, railways 0.04 |
| Trade range | `resources._compute_active_trade_routes` | a region practising celestial navigation at 0.3 trades two hops across a coastal region; road building at 0.3, two hops along a road (the navigation and railways focus capabilities, region by region) |
| Crop and fish yields | `ecology.compute_resource_yields`, the single ecology hook | grain x(1 + irrigation 0.05 + ox plough 0.05 + heavy plough 0.08), fish x(1 + sailing 0.04), by region practice; `yield_multiplier` returns 1.0 with the switch off |
| Epidemic fatality (`--epidemiology`) | `epidemiology.tick_epidemics` | the region's fatality multiplier x(1 - herbal lore 0.05 - physicians 0.10 - lazarets 0.05 - vaccination 0.30), at least 0.5 |
| Quarantine (`--epidemiology`) | `epidemiology._introduce` | efficacy 0.7 + written law 0.05 + lazarets 0.15 (civ practice), at most 0.9 |
| Credit (`--finance`) | `finance._domestic_capacity`, `finance._borrow` | domestic credit capacity and the debt ceiling x(1 + coinage 0.10 + banking 0.30 + double entry 0.20) |
| Navigation (`--maritime`) | `maritime.navigation_level`, through the read-only `technique_level(world, civ, "navigation")` | the navigation techniques the civ knows (sailing, celestial navigation, compass, ocean navigation: level 0-4) add fleet range, quality, the ship cap and storm safety ([maritime.md](maritime.md)); wired 2026-10 ([navigation-famine-labels.md](navigation-famine-labels.md)) |

Civ-wide effects read the civ practice measured at the tick
(`TechniqueState.civ_levels`, saved), region effects the saved practice
rows, so a resumed run reads exactly what an uninterrupted one does.

## Provenance

| Event | Cites |
| --- | --- |
| `technique_invented` | how the civ got each prerequisite (`technique:<civ>|<key>`), and its active great scientist |
| `technique_adopted` | the source civ's invention or adoption of the technique; for land that changed hands, the conquest, occupation, absorption, annexation or secession that moved it (read from the last five turns of the committed timeline, since absorptions are not in the causal index) and the old owner's technique |
| `technique_lost` | decay: pandemics or epidemics (within 30 turns), the open famine and population-collapse episodes, occupation and disasters in the regions that practised it, and the civ's collapse, twilight or secession; land: the transfer |
| `tech_advancement` | the technique events of the tier that completed the quorum |
| `tech_regression` | the losses of the tiers it held, the decay causes above, and a lost capital |

Keys are written with `provenance.remember` (`technique:<civ>|<key>`,
`technique_lost:<civ>|<key>`); `provenance._register` is unchanged, so
flag-off saves keep their causal index bytes.

## Switch and persistence

| Surface | Value |
| --- | --- |
| CLI | `--techniques` / `--no-techniques` (`BooleanOptionalAction`) |
| World field | `WorldState.techniques: TechniqueState \| None` (presence = on) |
| Default | **On** (`techniques.DEFAULT_ENABLED_FOR_NEW_WORLDS = True`, since the full gate in `techniques-default.md`) for `execute_run`, batch and the live server; `--no-techniques` opts out; resumed, forked and caller-supplied worlds keep their own setting. `scripts/benchmark_headless.run` pins it off so the frozen performance oracles replay the same worlds |
| Gate runner | `scripts/m53b_run_validation.py --techniques` forwards the switch to every run and records it in `run_manifest.json` |
| Dormant fields | `WorldState.techniques` and `TurnSnapshot.techniques` are omitted from serialized output while `None`; old saves and bundles load unchanged |
| Switched on mid-history | the first tick seeds, for every civ, the techniques of its era and below at 0.6 where its land suits them |

`TechniqueState` holds the practice rows `(region, technique, level,
source region, channel, source civ)` sorted by region and technique, each
civ's known set, the controller mirror of the last tick, the civ practice
levels, the era strain counters and cumulative counters (`invented`,
`gained:<channel>`, `lost:<cause>`, `era_up`, `era_down`). Region and civ
identity are indices. There are no transient signals: every input is saved
state or read within the tick; the derived lookups (`practice_map`, the
region-name index) are equality-neutral caches rebuilt after each tick and
after a load (tested).

## Determinism and contracts

* One draw per civ per turn, namespaced `technique_invent`; the candidate
  tie-break is `stable_hash_int("technique_choice", seed, civ, technique)`.
  Everything else is a deterministic function of saved state iterated in
  index order.
* Treasury costs and era bonuses go through the accumulator as `keep`, as
  the old era advance did; focus effects mutate directly, as before.
* `TechEra`, `TechFocus`, `ActionType` and every other enum are unchanged;
  `TECHNIQUES`, `DOMAINS` and `CHANNELS` are append-only (pinned by a test).
* No action-weight bucket is added; the capped modifiers are untouched.

## Feature-off identity

1. **Direct runs** (`scripts/diplomacy_identity.py compare`). The base
   export (selected with `PYTHONPATH`) against this branch with the default
   and with an explicit `--no-techniques`, same virtualenv and native build,
   `PYTHONHASHSEED=0`: `--agents off` 150 turns and `--agents hybrid` 120
   turns for seeds 42 and 7. Every output file (`state.json`,
   `chronicle.md`, `memories_*.json`, `agent_events.arrow`,
   `chronicle_bundle.json` minus `metadata.generated_at`) is
   byte-identical: 30 files compared, 0 differences, for both branch
   variants, against `20eeead` before the merge and against `92b6122`
   after it (native extension rebuilt from the merged Rust tree), rerun on
   the final code.
2. **Gate batch.** The base subset gate run from the exported `92b6122`
   tree against this branch's default (switch off) subset gate, 20 seeds x
   200 hybrid turns: 2,164 files compared; every run file (states,
   bundles, agent-event and validation sidecars, memories, chronicles) is
   identical, and the validation report, gate decision and gate summary
   differ only by their batch path. The same comparison against `20eeead`
   before the merge also matched. This batch ran at the merge commit; the
   later source change is inside the switched-on tick only.
3. **In the suite.** The frozen exact-trajectory oracles
   (`test_performance_equivalence` with the rolled-forward
   `corrected_food_balance_2026_10` fixtures, `test_governance_dormancy`,
   `test_turn_artifact_lifecycle`) pass unchanged; no fixture in
   `tests/fixtures/performance/` changed.
   `test_feature_off_never_runs_technique_code` forbids every technique
   entry point during a 40-turn run with campaigns, the ledger,
   epidemiology and finance on. The one hook that always runs,
   `yield_multiplier`, returns 1.0 with the switch off, and multiplying by
   1.0 leaves a float unchanged.

## Tests

`tests/test_techniques.py` (35 tests, also in the bounded offline Python
lane) and `tests/test_wave3_techniques_combined.py` (4 tests):

* registry: storage order pinned, prerequisites earlier and not of a higher
  tier, every tier at least its quorum, resource constants equal to
  `ResourceType`;
* diffusion along each ledger channel, naming the carrier and citing how
  the source civ got it; no contact, no spread; the border fallback with
  the ledger off; prerequisite gating; the unsuited cap; resources imported
  by trade but not by migrants;
* decay and regression: an era holds with enough people; a depopulated
  civ loses its techniques (citing the epidemic) and regresses, with the
  era bonus removed; untaught new land does not undo an era but losing the
  capital does; land lost and taken up (citing the conquest and the
  absorption); the M18 regression not running;
* era derivation: quorum, hysteresis and grace; an advance replaying the
  old events, bonus, focus and named events;
* invention: the research inputs, scholarship, namespaced draws;
* effects: arms, build costs (and the BUILD action paying them), trade
  range across the coast and along roads, fatality, quarantine, credit,
  yields (1.0 with the switch off);
* runs and persistence: same-seed determinism, save/load resume identity
  mid-diffusion (every resumed turn's `model_dump_json` matches the
  straight run), checkpoint replay, cache resets, dormancy (every entry
  point forbidden over 40 turns with epidemiology and finance on), omitted
  fields and old saves, switching on mid-history, the CLI flag, bundle
  history and analytics, new-world default and resume, gate forwarding, the
  report script, native hybrid determinism;
* combined: all four systems running and persisting, resume identity with
  live state in each, determinism, and technique effects reaching the
  epidemiology and finance hooks.

| Check | Result |
| --- | --- |
| `pytest -m "not slow" -n 2` (native extension built fresh from the merged tree's Rust, compiled `AgentSimulator`, `EcologySimulator`, `PoliticsSimulator` verified) | 5,649 passed, 3 skipped. Base `92b6122`: 5,610 (5,597 passed in a source-only export plus 13 that read `viewer/`, `chronicler-agents/` and `.github/` files the export omitted; they pass here); +39 technique tests. Before the merge, on `20eeead`: 5,625 passed, 3 skipped against the base's 5,588 |
| No-Rust lane (fresh virtualenv without `chronicler_agents`, `pytest -n 2`, slow tests included) | 5,454 passed, 198 skipped |
| `scripts/run_python_oracle_checks.py` (PR #19's one-line guard fix applied locally, not committed) | PASS: 1,669 passed, 5 skipped, 2 deselected; guard state PASS, no native module loaded, no blocked I/O |
| Rust | unchanged by this branch (the merge brought `92b6122`'s Rust), so no `cargo test` |

All rows ran on the final source (Linux, Python 3.13).

## Gate

Subset profile (20 seeds x 200 turns, hybrid, `--parallel 2`), base
`92b6122` run from the exported tree, branch with `--techniques`, compared
with `chronicler.validation_compare`. Three seed sets. In the subset only
community, needs and cohort are required; the rest is informational.

| Oracle | 42-61 base / on | 62-81 base / on | 82-101 base / on |
| --- | --- | --- | --- |
| gate | PASS / PASS | PASS / **FAIL** | PASS / PASS |
| comparator | - / NO REGRESSION | - / **REGRESSION** (new required failure: needs) | - / NO REGRESSION |
| community | PASS / PASS | PASS / PASS | PASS / PASS |
| needs (seeds with the expected sign, 12 required; median effect) | 15, 0.82 / 17, 0.95 | 14, 1.00 / **11**, 0.37 | 17, 1.00 / 18, 0.66 |
| cohort (seeds; median effect) | 19, 1.24 / 20, 1.17 | 20, 1.18 / 20, 1.28 | 20, 1.12 / 20, 1.05 |
| era (seeds with inflections; silent collapses, at most 2 allowed) | 20; 0 / 20; 1 | 20; 0 / 20; 0 | 20; 0 / 20; 1 |
| arcs | PASS / PASS | FAIL / PASS | FAIL / PASS |
| artifacts (creation per civ per 100 turns, band 1-3; loss rate) | PARTIAL 1.88, 1.3% / PARTIAL 2.15, 0.9% | PARTIAL 1.82, 3.8% / PASS 2.25, 2.8% | PASS 2.10, 3.0% / PASS 2.26, 3.3% |
| regression | PASS / PASS | FAIL (migration, `civ_survival`) / FAIL (same) | FAIL (`civ_survival`) / PASS |
| satisfaction mean; latest | 0.585; 0.595 / 0.585; 0.611 | 0.596; 0.618 / 0.599; 0.631 | 0.585; 0.579 / 0.583; 0.587 |
| extinct worlds | 0 / 0 | 0 / 0 | 0 / 0 |

**The needs failure.** The needs oracle pairs agents low in one need with
the event that need should drive inside a 20-turn window and counts seeds
where the rate difference has the expected sign. On 62-81 four seeds that
qualified on base (64, 65, 69, 78) do not with techniques on and one (67)
gains; for each of the four the best pairing is the autonomy need with no
rebellion in the window (rate difference 0). The other two sets move the
other way (42-61: +2; 82-101: +1). Over the 60 seeds base and techniques
on both count 46 qualifying seeds. Agent rebellions rise about 12-14% with
techniques on and occupation switches fall 7-9%; nothing ties a mechanism
to that one pairing. It is a required-oracle failure on one seed set,
reported as such; no threshold was changed.

**The era oracle.** It does not read `tech_era`: it detects inflections in
population, treasury, stability, territory and prestige and flags a civ
whose population falls 30% from its peak with no inflection nearby. Era
derivation reaches it only through what eras change (invention costs, era
bonuses, the consumers below). Every set keeps 20 of 20 seeds with
inflections. Two of the 60 techniques-on seeds (46 and 83) have one silent
collapse each (base 0 of 60): slow declines over about 40 turns (in seed 46
a civ falls from 105 to 44 people between turns 135 and 175) in
trajectories that diverged from base. Before the merge, on the `20eeead`
base, an earlier calibration showed two silent collapses on one set that
were single-turn population spikes taken as the peak; the final
calibration there showed none on two sets.

**Before the merge** (base `20eeead`, before the churn fix): seeds 42-61
and 62-81 both PASS with NO REGRESSION, the era oracle 20 of 20 with 0
silent collapses in both; artifact creation 2.99 and 3.11 against base
2.74 and 2.64 (above the band in the second set), carried by scientists
(see [Open items](#open-items)).

## On and off, per run

From the three gate batches above (`scripts/techniques_report.py`; the
base columns are the switch-off simulation, whose eras come from the old
advance and the M18 regression):

| Per run | base 42-61 | on 42-61 | base 62-81 | on 62-81 | base 82-101 | on 82-101 |
| --- | --- | --- | --- | --- | --- | --- |
| Runs | 20 | 20 | 20 | 20 | 20 | 20 |
| Techniques known per civ, t50 | 0.0 | 3.7 | 0.0 | 4.2 | 0.0 | 4.8 |
| Techniques known per civ, t100 | 0.0 | 7.0 | 0.0 | 6.2 | 0.0 | 7.7 |
| Techniques known per civ, t150 | 0.0 | 8.7 | 0.0 | 7.2 | 0.0 | 8.7 |
| Techniques known per civ, last turn | 0.0 | 9.3 | 0.0 | 8.0 | 0.0 | 9.7 |
| Inventions | 0.0 | 12.1 | 0.0 | 12.0 | 0.0 | 12.7 |
| Gained via trade | 0.0 | 4.7 | 0.0 | 3.9 | 0.0 | 5.1 |
| Gained via people | 0.0 | 14.7 | 0.0 | 13.2 | 0.0 | 14.2 |
| Gained via soldiers | 0.0 | 0.0 | 0.0 | 0.1 | 0.0 | 0.1 |
| Gained via pilgrims | 0.0 | 0.1 | 0.0 | 0.0 | 0.0 | 0.0 |
| Gained via neighbours | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Gained via conquest | 0.0 | 0.1 | 0.0 | 0.1 | 0.0 | 0.2 |
| Lost (practice decayed) | 0.0 | 0.7 | 0.0 | 1.8 | 0.0 | 0.4 |
| Lost (land lost) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.1 |
| Tech advances | 2.4 | 6.2 | 2.0 | 5.0 | 2.9 | 6.1 |
| Tech regressions | 1.9 | 0.5 | 1.4 | 0.6 | 2.4 | 0.4 |
| Eras of living civs, t100 (all runs) | tribal 60, bronze 3, classical 3 | tribal 12, bronze 28, iron 25 | tribal 59, bronze 4, iron 1 | tribal 14, bronze 36, iron 13 | tribal 55, bronze 7, classical 1 | tribal 3, bronze 38, iron 18, classical 1 |
| Eras of living civs, last turn (all runs) | tribal 54, bronze 6, classical 1 | tribal 6, bronze 16, iron 26, classical 12 | tribal 55, bronze 5, iron 1, medieval 1 | tribal 10, bronze 22, iron 26, classical 3 | tribal 51, bronze 4, iron 3 | tribal 1, bronze 21, iron 20, classical 15 |
| Extinct worlds | 0 | 0 | 0 | 0 | 0 | 0 |
| Final population | 186.3 | 177.6 | 177.6 | 171.3 | 185.1 | 179.7 |
| Trade actions | 21.5 | 151.8 | 21.3 | 146.3 | 23.6 | 158.4 |
| Wars declared | 2.1 | 2.0 | 3.1 | 2.5 | 2.1 | 2.3 |
| Builds started | 74.7 | 69.8 | 76.5 | 67.9 | 80.6 | 64.4 |
| Expansions | 25.9 | 12.4 | 17.6 | 11.9 | 23.4 | 19.1 |
| Great persons born | 8.0 | 13.1 | 7.5 | 13.7 | 12.2 | 15.8 |
| Artifacts created | 15.1 | 17.2 | 14.6 | 18.0 | 16.8 | 18.1 |
| Epidemic deaths | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Quarantines | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| State borrowing (treasury) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| State defaults | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Treaties signed | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

With epidemiology, finance and diplomacy also on (seeds 42-61, 200 hybrid
turns, techniques off against on, same branch):

| Per run | all three, techniques off | all three, techniques on |
| --- | --- | --- |
| Runs | 20 | 20 |
| Techniques known per civ, t50 | 0.0 | 3.2 |
| Techniques known per civ, t100 | 0.0 | 5.8 |
| Techniques known per civ, t150 | 0.0 | 6.6 |
| Techniques known per civ, last turn | 0.0 | 7.2 |
| Inventions | 0.0 | 10.1 |
| Gained via trade | 0.0 | 5.2 |
| Gained via people | 0.0 | 9.8 |
| Gained via soldiers | 0.0 | 0.0 |
| Gained via pilgrims | 0.0 | 0.0 |
| Gained via neighbours | 0.0 | 0.0 |
| Gained via conquest | 0.0 | 0.2 |
| Lost (practice decayed) | 0.0 | 1.2 |
| Lost (land lost) | 0.0 | 0.2 |
| Tech advances | 1.9 | 5.2 |
| Tech regressions | 1.5 | 1.2 |
| Eras of living civs, t100 (all runs) | tribal 60, bronze 4, iron 1 | tribal 18, bronze 21, iron 24 |
| Eras of living civs, last turn (all runs) | tribal 54, bronze 6, iron 1 | tribal 15, bronze 19, iron 25, classical 4 |
| Extinct worlds | 0 | 0 |
| Final population | 160.5 | 159.9 |
| Trade actions | 19.4 | 120.0 |
| Wars declared | 3.0 | 3.5 |
| Builds started | 72.5 | 71.8 |
| Expansions | 21.4 | 11.7 |
| Great persons born | 10.8 | 13.6 |
| Artifacts created | 16.1 | 17.1 |
| Epidemic deaths | 140.8 | 132.2 |
| Quarantines | 30.8 | 28.4 |
| State borrowing (treasury) | 732.0 | 692.9 |
| State defaults | 1.3 | 1.1 |
| Treaties signed | 15.5 | 14.3 |

Reading the tables:

* **Diffusion channels.** Merchants and migrants carry almost every
  cross-civ gain; on the food-balanced base migrants carry about three in
  four (before the merge merchants carried a little more than half).
  Pilgrims and soldiers almost never do: their ledger flows are small
  (pilgrims are a handful of great persons; armies are in the field only
  during wars, and the soldier channel decays fastest). Shared borders
  carry practice only between regions of one civ, so they almost never
  make a civ gain one; land changing hands (conquest, absorption) brings
  one or two gains per ten runs.
* **Regression.** Regressions fall from the M18 dice's 1.4-2.4 per run to
  0.4-0.6, every one citing its causes (famine episodes, disasters,
  disease and the techniques lost); losses of practice are 0.4-1.8 per run
  and concentrate in small or isolated civs.
* **Eras.** At turn 200 about nine in ten living civs are Bronze or later,
  against about one in eight on base (where the first advance needs both
  ore and timber in the civ's own land). Over 500 turns (seeds 42-47) the
  eras plateau around Iron and Classical with a couple of Medieval civs:
  the connected population the higher tiers need is scarce in 8-region
  worlds of about 180 people.
* **Tech advances.** 5.0-6.2 per run against 2.0-2.9.

## Stories (seed 42, hybrid, 200 turns, `--techniques`)

Recorded chains (`causes`, effect first), from the techniques-on gate run
of seed 42 (`92b6122` base) and, for the third, the same seed over 500
turns.

**1. Writing crosses three borders.** Selurian Republic develops writing in
Ashara Desert (t12). Thornwall Confederacy learned writing from Selurian
Republic's merchants (t16, citing t12); Ashkari Nomads learned it from
migrants out of Thornwall Confederacy (t25, citing t16). With masonry
(invented in Obsidian Shore at t20) and bronze working (learned at t54 from
Thornwall migrants, citing Thornwall's invention in Iron Peaks at t44),
Ashkari Nomads advances to the bronze era (t60, citing t54, t20 and t25). A
great scientist emerges the same turn (citing the advance); Ashkari Nomads
develops coastal sailing in Obsidian Shore (t62) and coinage (t81, citing
the writing it learned at t25 and the scientist), and Thornwall learned
both from Ashkari migrants (t90, t94).

> Thornwall Confederacy learned coastal sailing from migrants out of
> Ashkari Nomads (t90) <- Ashkari Nomads develops coastal sailing in
> Obsidian Shore (t62) <- a great scientist emerges in Ashkari Nomads (t60)
> <- Ashkari Nomads advances to the bronze era (t60) <- Ashkari Nomads
> learned writing from migrants out of Thornwall Confederacy (t25) <-
> Thornwall Confederacy learned writing from Selurian Republic's merchants
> (t16) <- Selurian Republic develops writing in Ashara Desert (t12).

**2. Kethani's iron age.** Kethani Empire learned writing from Selurian
Republic's merchants (t20), masonry from migrants out of Thornwall
Confederacy (t33; Thornwall had it from Ashkari Nomads' invention at t20)
and bronze working from Thornwall migrants (t49): it advances to the bronze
era (t53). Its first great scientist (t53) is cited by its inventions of
horsemanship (t83); the ox plough (t117) cites the irrigation it invented
at t62, road building (t131) the masonry learned at t33 and a second
scientist (t122). Horsemanship, the ox plough and road building complete
the iron quorum: Kethani Empire advances to the iron era (t140), a chain
seven steps deep. Its horsemanship travels on: Thornwall learned it from
Kethani migrants (t102) and Ashkari from Thornwall's (t184).

**3. The famine that cost the aqueducts** (seed 42, 500 turns). A locust
swarm descends on Amber Valley (t196); a food supply shock follows (t198),
then a drought (t206); famine strikes Amber Valley, devastating Kethani
Empire (t208), and the drought intensifies (t209). Famine halves the growth
of practice and the dying thin the people who share the craft:

> Kethani Empire loses the art of aqueducts as its practitioners dwindle
> (t211) <- Famine strikes Amber Valley (t208) <- drought (t206), supply
> shock: food in Amber Valley (t198) <- a locust swarm (t196); the drought
> intensifies around Amber Valley (t209).

Kethani relearns aqueducts and loses them twice more in the same valley,
at t255 and t324, each time citing that turn's famine and its locusts,
drought or soil exhaustion.

## Open items

* **Needs oracle on seeds 62-81** (above): re-measured on the current
  defaults it is again one seed short (11 against 12; the base reads 12),
  with 64 against 64 qualifying seeds over 80 and 7 seeds lost against 7
  gained. No technique mechanism weakens the need-behaviour link
  ([techniques-default.md](techniques-default.md), section 2).
* **Full gate.** Run on the current defaults with the switch on: PASS
  strict, 0 extinct worlds, no comparator regression; the default is now
  on ([techniques-default.md](techniques-default.md)).
* **Scientists and artifacts.** The scientist trigger counts each era a
  civ reaches for the first time, so with eras moving scientists roughly
  double (7 to 15 per run before the merge) and treatises with them.
  Artifact creation stays inside the band on the food-balanced base (2.15
  to 2.26 against 1.82 to 2.10) but was above it on one pre-merge set
  (3.11). Whether a derived era deserves the same trigger, or inventions a
  trigger of their own, is a question for the great-person owners.
* **Era consumers.** Bronze opens the TRADE action: trade actions rise
  about sevenfold, expansions fall by 18-52% and agent rebellions rise
  about 12-14%. These are the existing consumers working on eras that now
  move; they are the main behavioral change of the switch.
* **Remnant polities.** A civ of a handful of people loses its techniques,
  then re-advances within a few turns when migrants from more advanced
  neighbours bring practice in, and may repeat this (one 500-turn seed).
  That is the mechanism working on a degenerate polity.
* **Medicine and banking are modest.** Few civs reach physicians or
  banking by turn 200, so with epidemiology on, epidemic deaths fall about
  6% and quarantines 8%, and with finance on, borrowing changes by a few
  percent (more contact and more trade pull the other way).
* **Parameters are illustrative calibrations** (diffusion, decay, need,
  invention), set against these 8-region worlds and checked over 500
  turns, not fitted. Larger procedural worlds were not gated; a 48-region
  `--agents off` run cost about 14% more wall time with the switch on.
* **Cut and later:** Rust `InfoType::Technique` agent packets, viewer
  panels, technique-specific great persons, trade-range counters.
