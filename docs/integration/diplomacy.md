# Diplomacy: memory, treaties and the polity ladder

Branch `feat/diplomacy`, based on `integrate/wave-2` at `db26681` (campaign
warfare, live governance, the world-extinction fix with twilight pacing and
the tributary step, the contact ledger, causal provenance, procedural
geography, fisheries and mutual aid). Code: `src/chronicler/diplomacy.py`
(behavior) and `src/chronicler/diplomacy_state.py` (persisted state).

**Status.** Default off behind `WorldState.diplomacy` (CLI `--diplomacy`).
With the switch off no diplomacy code runs and every output is
byte-identical to `db26681` (see [Identity](#feature-off-identity)). The
subset gate passes with the switch on, with no comparator regression; the
full 200-seed gate was not run.

## Why

`Relationship` held a five-step disposition, a `grievances` list that
nothing ever wrote, `trade_volume` (now the contact ledger's decayed flow)
and a `treaties` list of peace-treaty names. A campaign peace bought a
10-turn truce (`war.runtime._in_truce`) and nothing else; afterwards the
pair drifted toward ALLIED like every other pair. On the subset gate, 93%
of living civ pairs are ALLIED (sampled every 10 turns), and after the
opening wars a 200-turn world sees 0.3 further wars per run. Polities ended
outright: a conquest or capitulation of the last region extinguished the
loser, and twilight absorption (the Rust politics step 9) took declining
states in one turn. The extinction fix's tributary step was meant to soften
that, but it needs a neighbour with stability above 40, which living worlds
rarely have (median civ stability is about 26-29), so it never fired.

## What was built

| Part | Summary |
| --- | --- |
| Memory | Per directed civ pair (`Relationship.memory`): trust, goodwill and six grievance stocks with their own half-lives, fed from state each turn and at the events that cause them. It caps dispositions, nudges drift, draws revanche and enters every utility below. |
| Treaties | `peace` (emitted by the war package), `non_aggression`, defensive `alliance`, `trade_pact` and `tribute` (installments), each with terms, start, expiry, renewal and breach. Offers go through the DIPLOMACY action and stand only when the target's utility is positive. |
| Polity ladder | `client -> vassal -> union -> annexation` on `VassalRelation`, generalizing the tributary step. Subjects pay stage tribute, loosen when the overlord weakens and can still revolt through the existing Rust rebellion. |
| Effects | A pre-clamped diplomacy contributor bucket in the action weights; a treaty guard and a revanche term in WAR target choice; trade pacts keep routes open and guard against embargo; calls to arms; alliance aid convoys. |
| Provenance | Treaties, breaches, calls to arms, aid, ladder steps and revolts cite their causes. |

### Cut, and why

* **Marriage alliances.** Rulers have no cross-civ marriage or inheritance
  mechanism: marriages are Rust-native agent bonds (`formation.rs`), and a
  ruler's `dynasty_id` only exists in agent modes. A personal union is
  therefore modeled without a dynastic marriage: the overlord's ruler wears
  both crowns, and the union may part when that ruler changes.
* **Grievances exported from agent memory.** The Rust memory system records
  the agent's own civilization as `source_civ` for battles, conquests and
  persecution, not the perpetrator, so agent memories cannot say whom a
  grievance is against. No Rust was changed.
* **Embargo lifting.** Embargoes are never lifted anywhere in the code.
  Lifting them by treaty (or once the imposer turned friendly) reopened so
  much trade on the subset that merchant great persons rose by a third to a
  half and their promotion artworks pushed the artifact oracle out of its
  creation band and type diversity (FAIL), with cinderella arcs above their
  dominance limit (arcs FAIL). Embargoes stay permanent; the memory model
  instead stops counting a standing embargo as a fresh hostility once its
  imposer is friendly. Lifting is a follow-up for whoever owns the merchant
  trigger and artifact calibration.
* **Sparing conquered states (`SPARE_LAST_REGION`), built but off.** A
  conquest, capitulation or occupation consolidation that would extinguish
  a state can make it a vassal instead. Measured on 20 hybrid seeds x 500
  turns it ends every conquest extinction but doubles wars (3.85 against
  1.90 per run: spared vassals revolt and seek revanche) and keeps all four
  founders alive in half the worlds (the regression oracle's `civ_survival`
  allows a fifth). See [The sparing lever](#the-sparing-lever).
* **Ruler ambitions.** `DIPLOMATIC_TRIUMPH` still has no live predicate in
  the governance kernel; treaties could supply one. Left to the governance
  owners.
* **Viewer.** `history[n].diplomacy` and the new event types are in the
  bundle; the viewer does not display them yet. (Since added on
  `feat/viewer-systems`, with an additive `diplomacy.pairs` snapshot field:
  see [viewer-systems.md](viewer-systems.md).)

## Switch and persistence

| Surface | Value |
| --- | --- |
| CLI | `--diplomacy` / `--no-diplomacy` (`BooleanOptionalAction`) |
| World field | `WorldState.diplomacy: DiplomacyState \| None` (presence = on) |
| Default | **Off** (`diplomacy.DEFAULT_ENABLED_FOR_NEW_WORLDS = False`) for `execute_run`, batch and the live server; resumed, forked and caller-supplied worlds keep their own setting; `--no-diplomacy` on a resumed world also drops the dormant memory and ladder fields |
| Gate runner | `scripts/m53b_run_validation.py --diplomacy` forwards the switch to every run (and records it in `run_manifest.json`) |
| Dormant fields | `WorldState.diplomacy`, `Relationship.memory`, `VassalRelation.stage/stage_turn/integration/crown` and `TurnSnapshot.diplomacy` are `None` by default and omitted from serialized output while `None`, so saves, bundles and fixtures without diplomacy keep their bytes and old saves load unchanged |

`DiplomacyState` holds the treaties (active and finished), the next treaty
id, offer cooldowns, cumulative counters, and two mirrors of the end of the
previous diplomacy tick: the subject relations `(overlord, vassal, stage)`
and each region's controller. The mirrors let the next tick see what changed
(a revolt, land that changed hands), whichever system changed it. Civ
identity is the index in `world.civilizations`, region identity the index in
`world.regions`; treaty parties, cooldowns, mirrors and ceded regions are
stored as indices. `Relationship` stays keyed by names, as everywhere else.
There are no transient signals: every input is either persisted state or
consumed within the tick that reads it.

## Turn placement

| When | What |
| --- | --- |
| Phase 2, after vassal tribute | Tribute-treaty installments (`collect_treaty_tribute`, `keep` treasury) |
| Phase 5 actions | DIPLOMACY offers; WAR target guard, revanche, breaches and calls to arms; EMBARGO guard; union eligibility; the weight bucket |
| Campaign tick | Peace treaties from `conclude_peace` and `close_external` |
| Phase 10, before politics | The ladder's client step in `prepare_twilight_absorption` |
| After Phase 10 consequences | `tick_diplomacy`: decay, inputs, treaty upkeep, ladder, aid, dispositions, mirrors. It runs after the Rust politics pass, so it sees the turn's revolts and absorptions, and before the second keep flush, so its accumulator changes land the same turn (hybrid) or apply directly (other modes) |

## Memory

`Relationship.memory` of `world.relationships[a][b]` is how *a* regards *b*.
Each stock decays every turn by its half-life; values are rounded to 4
decimals and drop to exactly 0 below 0.01.

| Grievance (`GRIEVANCE_KINDS`, index order) | Half-life | Inputs |
| --- | --- | --- |
| `war` | 40 | +8 when the other side declares war on us; per campaign battle, +2 lost or +1 fought, plus 10 x our losses / our soldiers; instant-war path: +6 to the loser, +1 to the winner |
| `occupation` | 60 | +1.5 per turn a region of ours is occupied; +12 per region that passes to the other civ (+8 more for the capital), read from the region-controller mirror so conquest, annexation, secession and absorption all count; +10 on subjugation |
| `treaty` | 50 | +25 when the other side breaks a treaty with us; +20 to an overlord whose subject revolts; +8 to a subject its overlord did not defend |
| `border` | 12 | +3 to both sides per border incident |
| `faith` | 30 | per turn, 2 x persecution intensity per region where the persecutor's majority faith is not ours and the region's majority belief is our faith; 1 x intensity where the region's people are ours |
| `embargo` | 15 | +4 when embargoed; +1 per turn the embargo stands while its imposer is NEUTRAL or worse toward us |

| Goodwill (half-life 25) | |
| --- | --- |
| Trade | per turn, `min(0.5, F_ab / 20)` once the contact ledger's flow `F_ab` reaches 1 (with the ledger off, 0.3 per turn of an active route) |
| Treaties | alliance +0.5 and trade pact +0.2 per turn; +3 when a treaty runs its course |
| Deeds | +5 for an ally that answered a call to arms; +0.5 per treasury of aid |

| Trust (-100..100, relaxes 1% per turn toward 0) | |
| --- | --- |
| Kept | +0.25 per turn under any active treaty; +5 when it runs its course or a tribute completes |
| Defended | +10 for an answered call to arms; +2 per aid convoy |
| Broken | -35 for the victim of a breach, and -5 with every other living civ (reputation); -10 more for an abandoned ally; -15 for a tribute default; -30 to an overlord whose subject revolts; -10 for a war declared on us |

Effects:

* **Disposition ceiling.** Effective grievance `E = grievance - 0.5 x
  goodwill` caps the disposition: E >= 70 SUSPICIOUS, >= 40 NEUTRAL, >= 20
  FRIENDLY; trust <= -50 NEUTRAL, <= -25 FRIENDLY. A disposition above its
  cap falls one step per turn. A member of a personal union never regards its
  partner below FRIENDLY.
* **Drift.** E >= 20 adds -1 to `disposition_drift` per turn; E <= -10 with
  trust >= 0 adds +1 (the same counter and threshold of 10 that value drift
  and trade warmth use).
* **Revanche.** WAR target scores gain `min(1, (war + occupation + treaty) / 50)`.
* **Utilities.** Every offer, acceptance, renewal, breach, call to arms,
  ladder step and repudiation reads trust, goodwill and grievance.

## Treaties

| Kind | Made by | Term | Effect | Broken by |
| --- | --- | --- | --- | --- |
| `peace` | every campaign peace (`conclude_peace`), and wars ended outside it (congress, an instant war ended by diplomacy) | 20 turns, after the existing 10-turn truce | protects against war; terms record outcome, winner, aim, ceded regions (indices) and payment | a war between the parties |
| `non_aggression` | DIPLOMACY offer between bordering civs | 30 | protects against war | a war between the parties |
| `alliance` | DIPLOMACY offer between mutually FRIENDLY civs with a common bordering enemy | 40 | protects against war; calls to arms; aid convoys in famine; +0.5 goodwill per turn | a war between the parties, or refusing a call to arms |
| `trade_pact` | DIPLOMACY offer between partners with flow `F_ab >= 1` | 30 | the route stays open down to SUSPICIOUS; TRADE weight x1.2; +0.2 goodwill per turn | an embargo between the parties |
| `tribute` | a campaign peace with the tribute aim (instead of the lump sum) | 8 installments of `ceil(total / 8)` | treasury, `keep` category, from the turn after the peace | two missed installments, or a payer grown strong enough to repudiate |

* **Offers.** With diplomacy on, DIPLOMACY first sues for peace when at war
  under campaigns (unchanged), then makes the proposer's best offer
  (`_offers`: non-aggression, alliance, trade pact or clientage) whose
  utility is above 0.05. The proposer sounds the target out first: it only
  offers when the deterministic part of the target's utility is above -0.1.
  The target then accepts only if its own utility, with a private
  +-0.2 draw, is positive (`acceptance_utility`). A rebuffed offer is not
  repeated for 8 turns. With nothing worth offering, the action improves
  relations as before.
* **Renewal.** An expiring non-aggression pact, alliance or trade pact is
  renewed only if both parties would accept it again now (a fresh mutual
  acceptance; alliances also need mutual FRIENDLY, pacts a shared border).
* **War guard.** A target protected by a peace, pact or alliance is not
  chosen unless `breach_utility` is positive (grievance, power ratio,
  trust, aggressive traits; an alliance weighs -0.5). An overlord never
  makes war on its own subject. When the war is actually declared, the
  attacker breaks every protecting treaty with the target, the defender
  records the aggression, and joiners (federation members, allies,
  overlords) bound to the attacker break their treaties with it.
* **Calls to arms.** When an ally is attacked, the other party joins if its
  utility (trust, goodwill toward the defender, grievance toward the
  attacker, the odds, other wars, unrest) is positive; otherwise it breaks
  the alliance. An overlord likewise decides whether to defend its subject.
* **Breach.** The breaker loses 5 stability (`guard-shock`) and up to 10
  prestige (`keep`); the victim gains 25 treaty grievance and -35 trust,
  every other living civ -5 trust in the breaker.
* **Aid convoys.** An ally with treasury >= 60 sends up to 10 treasury
  (`keep`) to an ally at the onset of a famine, at most every 10 turns per
  pair. (This is distinct from mutual aid, which moves food within a civ.)

## Polity ladder

| Stage | Tribute | Constraints | Climbs when |
| --- | --- | --- | --- |
| `client` | 5% of economy | no WAR (as for any vassal) | 15 turns as client, overlord power >= 1.5x and stability >= 25, both sides' utilities positive |
| `vassal` | the existing `politics.vassal_tribute_rate` (15%) | no WAR or FUND_INSTABILITY (existing rules) | 20 turns, integration >= 20, the same power and stability, both utilities positive |
| `union` (personal union) | 25% | no WAR, DIPLOMACY, EMBARGO or FUND_INSTABILITY; dispositions held at FRIENDLY or better; the overlord's ruler is recorded as wearing the crown | 20 turns, integration >= 40, at most 3 regions, adjacent, overlord stability >= 22, the subject's utility positive, and 10 turns since the last absorption world-wide: **annexation** through `politics.absorb_civ` (event `union_annexation`) |

* **Entry.** The twilight step (below); a small threatened state seeking a
  protector (a clientage offer through DIPLOMACY, accepted by the protector's
  utility); a vassalization-aim war's capitulation (`resolve_vassalization`,
  which now keeps both sides' memory); and, only with `SPARE_LAST_REGION`, a
  conquest that would extinguish the loser.
* **Fast track.** A subject the old paths would have absorbed outright
  (structurally unviable for 20 turns, or down to one region) needs 6, 8 and
  6 turns per stage, no integration and an overlord merely stronger than
  itself, so it is annexed on about the old tributary's 30-turn timescale.
* **Integration** (0..100) grows per turn by 0.5, plus 0.5 for a shared
  majority faith, 0.25 for shared values and 0.25 for adjacency, less
  grievance / 40 (at most 1) and 0.5 while the overlord is weak; client 0.5x,
  vassal 1x, union 1.5x.
* **Loosening.** An overlord is weak when in a PSI crisis, defeated in a
  war within 10 turns, below 20 stability, or outgrown (power below 3/4 of
  its subject's; the agent-mode military stat swings with soldier counts).
  A subject at least 5 turns into its stage then loosens one step with
  chance 10% (client), 12% (vassal) or 15% (union), plus grievance / 400:
  union to vassal, vassal to client, client to independence. It gains 5
  stability (`guard-shock`).
* **Crowns part.** When the overlord's ruler changes, a union with
  integration below 40 parts with chance 35% (back to vassal); otherwise the
  crown passes to the new ruler.
* **Revolt.** The existing Rust vassal rebellion (overlord perceived
  stability below 25 or treasury below 10, 15% per turn) still ends any
  stage. The tick sees the relation vanish next to a `vassal_rebellion`
  event: the overlord records 20 treaty grievance and -30 trust.

**How it generalizes the tributary step.** `prepare_twilight_absorption`
keeps its persistence streak, its world-wide pacing and its fallback. With
diplomacy on, a declining or unviable one-region state with a would-be
absorber of stability above 20 (instead of 40) becomes that absorber's
**client** instead of a tributary or an immediate absorption, and a subject
is never handed to the Rust absorption gate: the ladder's annexation step
ends it, sharing `last_twilight_absorption_turn` and its 10-turn spacing.
An absorber too unstable to hold a client still absorbs through the paced
gate, exactly as before. The absorption body is shared as
`politics.absorb_civ` (a behavior-preserving refactor of the two Python
oracle branches).

## Action weights

`weight_modifiers` is one contributor bucket, applied after governance's and
clamped per action to `[1/1.5, 1.5]` before the existing global 2.5x cap
(recorded as bucket `diplomacy` when governance's bucket recording is on):

* WAR x(1 + 0.4 x min(1, g / 60)) for the largest war/occupation/treaty
  grievance against a hostile or suspicious neighbour; x0.7 when every such
  neighbour is bound by a protecting treaty;
* TRADE x1.2 with an active trade pact;
* DIPLOMACY x0.8 for a subject; x1.25 when a bordering hostile civ is at
  least 1.3x stronger.

## Provenance

| Event | Cites |
| --- | --- |
| `treaty_signed` | the motive: the pair's war, border incidents and breaches with the threat (non-aggression, alliance) |
| `treaty_broken` | the treaty's signing event and the war declaration (or nothing more for embargo and tribute) |
| `treaty_expired`, `treaty_renewed` | the signing event (a peace's is its `peace_treaty`) |
| `call_to_arms` | the war declaration and the alliance (or the subjection) |
| `aid_convoy` | the famine onset and the alliance |
| `vassalization` (client entries) | twilight client: its twilight, collapse and the open famine and soil-exhaustion episodes in its land; protection: the threat's war, border incidents and breaches |
| `vassal_promoted`, `vassal_loosened`, `union_annexation` | the previous ladder event (`subject:<vassal>` key); loosening also what weakened the overlord (PSI crisis, the lost war's peace, revolt, its wars) or the leader death |
| `vassal_rebellion` (Rust) | the existing civ-distress rule; with diplomacy on also the subjection and the overlord's distress |

The `CAUSE_RULES` change for `vassal_rebellion` only adds causes when
diplomacy is on. Breaches register `breach:<pair>` so later offers cite them.

## Determinism and contracts

* Draws: `random.Random(stable_hash_int("diplomacy", <namespace>, seed,
  turn, ...))` with namespaces `accept`, `breach`, `join`, `protect`,
  `embargo`, `repudiate`, `ladder`, `loosen`, `crown`; treaty names use the
  existing `named_event` stream with a diplomacy-derived seed.
* Stat changes: treasury and prestige `keep`; stability shocks
  `guard-shock`; through the accumulator in Phase 2, Phase 5 and the hybrid
  Phase 10 tail, directly where Phase 10 runs without one.
* `ActionType`, `Disposition` and the region/civ enums are unchanged;
  `GRIEVANCE_KINDS`, `TREATY_KINDS` and `LADDER_STAGES` are append-only.
* No Rust change.

## Feature-off identity

1. **Direct runs** (`scripts/diplomacy_identity.py compare`, copied from
   `feat/epidemiology`'s epidemiology identity script). The base export
   (`db26681`, selected with `PYTHONPATH`) against this branch with the
   default and with an explicit `--no-diplomacy`, same virtualenv and native
   build, `PYTHONHASHSEED=0`: `--agents off` 150 turns and `--agents hybrid`
   120 turns for seeds 42 and 7. Every output file (`state.json`,
   `chronicle.md`, `memories_*.json`, `agent_events.arrow`,
   `chronicle_bundle.json` minus `metadata.generated_at`) is byte-identical:
   30 files compared, 0 differences, for both branch variants, rerun on the
   final code.
2. **Gate batch.** The base subset gate (run from the exported `db26681`
   tree) against this branch's default (switch off) subset gate, 20 seeds x
   200 hybrid turns: all 2,159 run files (states, bundles,
   agent-event and validation sidecars, memories, chronicles) are
   identical; the validation report, gate decision and gate summary are
   identical apart from their batch path. This batch ran one commit before
   the final one, whose only source change is inside the switched-on
   disposition step (`_apply_dispositions`); the direct runs above were
   repeated on the final code.
3. **In the suite.** The frozen exact-trajectory oracles
   (`test_performance_equivalence`, `test_governance_dormancy`,
   `test_turn_artifact_lifecycle`) pass unchanged; no fixture in
   `tests/fixtures/performance/` changed.
   `test_feature_off_never_runs_diplomacy_code` forbids every entry point
   during a 40-turn run.

## Tests

`tests/test_diplomacy.py` (39 tests, also added to the bounded offline
Python lane):

* memory: every grievance stock's half-life and the drop to zero, directed
  disposition caps and drift, inputs consumed once per turn (land, battles,
  incidents are not re-counted on the next tick), a standing embargo only
  offending while its imposer is unfriendly;
* treaty lifecycle: signing, running its course with trust and goodwill,
  renewal by fresh mutual acceptance, breach by war declaration with every
  consequence, the war guard (and revanche) and an overlord's subject, the
  upkeep fallback breaker and treaties ending with a party, calls to arms
  answered or breached, joiners breaking their treaties, the embargo guard,
  trade pacts keeping a SUSPICIOUS route open, acceptance by the target
  (rebuffed, accepted, not offered), tribute installments completing or
  defaulting, peace and tribute treaties from a campaign peace;
* ladder, both ways: client to vassal to union to annexation, loosening
  union to vassal to client to independence, crowns parting or passing, a
  Rust revolt remembered, vassal rebellion provenance only with diplomacy on,
  the twilight client step (and the gate never handing a subject to the
  absorption pass), the union's action constraints, the sparing lever on
  (capitulation and instant conquest make a vassal) and off (default);
* runs and persistence: same-seed determinism with treaties signed,
  save/load resume identity with live treaties and memory across the save
  point (every resumed turn's `model_dump_json` must match), checkpoint
  replay with diplomacy, feature-off dormancy, omitted fields and old saves,
  disabling dropping memory and ladder fields, the CLI flag, the bundle
  history and analytics section, new-world default and resume, gate
  forwarding, the report script, and a native hybrid determinism check.

## Results

| Check | Result |
| --- | --- |
| `pytest -m "not slow" -n 2` (native extension built fresh from this tree, compiled `AgentSimulator`, `EcologySimulator`, `PoliticsSimulator` verified) | 5,536 passed, 3 skipped (base 5,497 passed, 3 skipped; +39 diplomacy tests) |
| No-Rust lane (fresh virtualenv without `chronicler_agents`, `pytest -q -n 2`, slow tests included, as CI runs it) | 5,344 passed, 193 skipped |
| `scripts/run_python_oracle_checks.py` (with PR #19's one-line guard fix applied locally, not committed) | PASS: 1,634 passed, 4 skipped, 2 deselected; guard state PASS, no native module loaded, no blocked I/O |
| Rust | unchanged, so no `cargo test` |

All rows above ran on the final source.

### Subset gate (20 seeds x 200 turns, hybrid, `--parallel 2`)

Base `db26681` (run from the exported tree) and this branch with
`--diplomacy`, compared with `chronicler.validation_compare`: **PASS** and
**NO REGRESSION**. In the subset only community, needs and cohort are
required; the rest is informational.

| Oracle | Base | `--diplomacy` |
| --- | --- | --- |
| community | PASS (20 of 20 qualifying) | PASS (20 of 20) |
| needs | PASS (18 seeds with the expected sign, effect 0.89) | PASS (17, effect 0.87) |
| cohort | PASS (20, effect 1.24) | PASS (20, effect 1.26) |
| era | PASS (0 silent collapses) | PASS (0) |
| arcs | PASS (cinderella 27 of 80) | PASS (25 of 80) |
| artifacts | PARTIAL: loss 0.5% below the 2% floor; creation 2.74 | **PASS**: loss 2.2% (3 lost, 6 destroyed); creation 2.59 |
| regression | FAIL (informational): `civ_survival`, all four founders alive in 0.25 of worlds (limit 0.20) | FAIL (informational): `civ_survival` 0.30; strict `latest_satisfaction_mean` 0.445 (< 0.45, calibrated floor 0.40 passes) |
| determinism | SKIP | SKIP |

Regression metrics, base against on: satisfaction 0.481 / 0.474, latest
satisfaction 0.454 / 0.445, migration 0.0505 / 0.0508, rebellion 0.051 /
0.049, Gini in range 0.967 / 0.951, occupation violations 0.11% / 0.09%,
final population 207-398-551 / 209-375-526 (min, median, max). **0 of 20
worlds extinct** in either.

### Per-run numbers, diplomacy off against on

Subset gate batches (20 seeds x 200 turns), and the same seeds run for 500
turns (`scripts/diplomacy_report.py`; `off` is identical to the base):

| Per run (mean) | off, 200 turns | on, 200 | off, 500 | on, 500 |
| --- | --- | --- | --- | --- |
| Treaties signed: peace | 0 | 1.50 | 0 | 1.70 |
| non-aggression | 0 | 4.10 | 0 | 6.95 |
| alliance | 0 | 1.80 | 0 | 2.00 |
| trade pact | 0 | 6.20 | 0 | 9.05 |
| tribute | 0 | 0.05 | 0 | 0.05 |
| Treaties broken | 0 | 0.25 | 0 | 0.50 |
| Offers rebuffed | 0 | 2.45 | 0 | 4.60 |
| Renewals | 0 | 19.95 | 0 | 57.10 |
| Aid convoys | 0 | 2.80 | 0 | 4.30 |
| Wars (campaign war records, joiners included) | 1.45 | 1.65 | 1.50 | 1.90 |
| Mean war duration (turns) | 6.24 | 6.39 | 6.27 | 7.16 |
| Subject relations formed | 0 | 1.05 | 0 | 1.25 |
| Subjects alive per turn (client / vassal / union) | 0 | 0.07 (0.03 / 0.03 / 0.02) | 0 | 0.05 (0.02 / 0.02 / 0.01) |
| Ladder promotions / loosenings / Rust revolts | 0 | 0.95 / 0.20 / 0.50 | 0 | 1.10 / 0.30 / 0.75 |
| Twilight absorptions | 0.65 | 0.25 | 0.70 | 0.30 |
| Union annexations | 0 | 0.30 | 0 | 0.35 |
| Conquests (state extinguished) | 0.40 | 0.50 | 0.45 | 0.55 |
| Polities alive at the end | 3.05 | 3.05 | 2.95 | 2.90 |
| Worlds keeping all four founders | 0.25 | 0.30 | 0.25 | 0.25 |
| Extinct worlds | 0 | 0 | 0 | 0 |

At 500 turns the ten breaches are four alliances, two peace treaties, two
trade pacts, one non-aggression pact and one tribute. No allied civ was
attacked in these 40 runs, so no call to arms came up (the mechanics are
covered by the tests).

### The sparing lever

`SPARE_LAST_REGION` (default False) lets the ladder take states that a
conquest, capitulation or occupation consolidation would extinguish. Same
20 seeds; the 200-turn column is the subset gate run with it on:

| Per run (mean) | off (base) | on, lever off (default) | on, lever on |
| --- | --- | --- | --- |
| 500 turns: wars | 1.50 | 1.90 | 3.85 |
| mean war duration | 6.27 | 7.16 | 8.96 |
| conquests (state extinguished) | 0.45 | 0.55 | 0 |
| twilight absorptions / union annexations | 0.70 / 0 | 0.30 / 0.35 | 0.25 / 0.45 |
| polities alive at the end | 2.95 | 2.90 | 3.40 |
| worlds keeping all four founders | 0.25 | 0.25 | 0.50 |
| 200 turns (subset gate): founders kept / wars | 0.25 / 1.45 | 0.30 / 1.65 | 0.55 / 2.35 |

With the lever on the subset gate still passes (arcs and artifacts PASS),
but spared vassals mostly revolt (the Rust rebellion triggers whenever the
overlord's perceived stability is below 25, roughly a quarter of civ-turns
in living worlds) and then fight to recover their land, and `civ_survival`
would very likely fail the full gate. Two embargo-lifting variants were
also measured and dropped (see [Cut](#cut-and-why)): they lifted 2.3
embargoes per run, raised great persons from 20 to 31 per run (merchants
31 to 42) and turned artifacts and arcs to FAIL on the subset.

### Effects on other systems

Subset gate batches, per run (500-turn probe in brackets where it differs
in kind):

* **Dispositions.** ALLIED falls from 92.8% to 79.3% of living pair samples
  (FRIENDLY 4.3% to 13.6%, NEUTRAL or worse 2.9% to 7.1%): grievances and
  distrust keep some pairs from the universal alliance the base world
  converges to [500 turns: 95.8% to 80.5%].
* **Actions.** DIPLOMACY is chosen 81 times per run instead of 56 (the
  all-allied x0.1 suppression no longer applies to every civ, and
  threatened civs seek treaties), mostly at the expense of DEVELOP (301 to
  288), INVEST_CULTURE (127 to 117) and TRADE (31 to 26); EXPAND 34 to 40,
  EMBARGO 4.1 to 5.8. WAR actions are unchanged (8.0 / 7.9).
* **Wars.** +0.2 per 200 turns (+0.4 per 500): aggrieved pairs stay
  SUSPICIOUS long enough to fight again; wars run slightly longer.
* **Polities.** Twilight absorptions fall by about 60%; the ladder's
  annexations replace them. Polity counts at the end are unchanged.
* **Stability, economy, treasury.** Mean civ stability 26.5 / 25.9,
  economy 85.0 / 85.1, treasury 3,541 / 3,521, prestige 46 / 42 (breach
  penalties, fewer TRADE actions). Tribute installments and aid convoys
  move at most a few hundred treasury per run, all `keep`.
* **Other events.** Federations formed 1.2 / 1.15, collapsed 0.15 / 0.15;
  PSI crises 2.55 / 2.65; rebellions 26.8 / 25.7; border incidents 48.6 /
  51.2; merchants 31.3 / 29.1; artifacts 439 / 414 per batch with more
  destroyed in occupation sacks.
* **Gate.** Latest satisfaction -0.009 (0.454 to 0.445, now a strict miss
  of the 0.45 floor, calibrated floor passes), satisfaction -0.007.
* **Runtime.** A 200-turn hybrid seed takes about 7 s either way; the
  subset gate took 118-169 s against 120-153 s off on the shared machine.

## Stories (seed 42, subset gate run with diplomacy on)

**1. A protectorate swallowed (the ladder, end to end).** On base the
one-region Selurian Republic federates with the Thornwall Confederacy at
turn 17 and ends in a twilight absorption at turn 50 ("The Quiet End"). With
diplomacy, menaced by stronger suspicious neighbours, it seeks protection
at turn 2 and climbs the whole ladder on the one-region fast track:

    [t22] union_annexation: The union of Thornwall Confederacy and Selurian Republic
          becomes one realm: Selurian Republic is annexed
      [t16] vassal_promoted: The crown of Selurian Republic passes to Warchief Seren
            of Thornwall Confederacy: a personal union
        [t8] vassal_promoted: Thornwall Confederacy binds its client Selurian Republic
             as a vassal
          [t2] vassalization: Selurian Republic places itself under the protection of
               Thornwall Confederacy as a client

The protection offer has no recorded cause: the threat was a disposition,
not an event.

**2. A peace kept, a grudge outgrown.** Kethani Empire attacks Thornwall at
turn 0 for tribute and loses; The Shadow Convention (turn 12, negotiated)
records the outcome and a 20-turn term. Kethani's grievance against
Thornwall is 30.8 at turn 13, and both sides are SUSPICIOUS (on base they
are NEUTRAL at that point). Both keep the peace to its expiry:

    [t32] treaty_expired: The Shadow Convention between Kethani Empire and Thornwall
          Confederacy runs its course, kept by both.
      [t12] peace_treaty: The Shadow Convention ends the war (negotiated peace): Kethani
            Empire accepts defeat to Thornwall Confederacy.
        [t0] war_declared: Kethani Empire goes to war with Thornwall Confederacy,
             seeking tribute.

Kethani's trust in Thornwall rises from 0.3 to 11.7 by turn 33 and its
grievance fades (23.6 at turn 33, 7.8 at turn 93, 2.8 at turn 151); the
former enemies federate at turn 37 and, after a border incident at turn 80,
sign non-aggression pacts at turns 92 and 133 (each citing the incident) and
keep both to term. At turn 200 each trusts the other at about 17-18.

**3. An alliance against a common enemy.** Ashkari Nomads, which made a
white peace with Thornwall at turn 10, and Kethani sign The Cedar Protocol
(non-aggression, turn 10) and then The Crimson Covenant, a defensive
alliance whose recorded motive is the border incidents each had with
Thornwall:

    [t26] treaty_signed: Ashkari Nomads and Kethani Empire sign The Crimson Covenant,
          a defensive alliance for 40 turns.
      [t25] border_incident (Thornwall Confederacy, Ashkari Nomads)
      [t15] border_incident (Thornwall Confederacy, Kethani Empire)

It is renewed by mutual acceptance at turns 66, 106, 146 and 186; at turn
200 Ashkari and Kethani trust each other at about 63-65 with goodwill
about 44, the warmest pair in the world, while Thornwall's grievance
against Ashkari (the turn-0 war) remains the largest one.

## Follow-ups

* Run the full 200-seed gate with `--diplomacy` before choosing a default;
  watch `civ_survival` and the latest-satisfaction strict floor.
* Embargo lifting together with the merchant trigger and artifact bands.
* Viewer panels for treaties, memory and the ladder; narration of
  `top_grievances`.
* A live predicate for the `DIPLOMATIC_TRIUMPH` ruler ambition.
* Parameters are illustrative calibrations against the subset and a
  20-seed 500-turn probe, not fitted against the 200-seed gate.
