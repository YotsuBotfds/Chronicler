# Great-person agendas

Branch `feat/great-person-agendas`, started on `integrate/wave-4` at
`1a6cacb` (live governance with ruler ambitions and PSI, great persons,
causal provenance, and default-off epidemiology, finance, diplomacy,
techniques and maritime) and merged with `integrate/wave-4` at `705fe2e`
(the living-world oracle recalibrations; epidemiology, finance and
diplomacy on by default for new worlds; viewer panels), which is the
identity and gate base for every result below. Code:
`src/chronicler/gp_agendas.py` (behavior),
`src/chronicler/gp_agendas_state.py` (persisted state) and an additive
extension of the M66b kernel `src/chronicler/ruler_ambitions.py`. No Rust
changed.

**Status.** Default off behind `WorldState.gp_agendas` (CLI
`--gp-agendas`). With the switch off no agenda code runs and every output is
byte-identical to `705fe2e` (see [Feature-off identity](#feature-off-identity)).
With the switch on, on top of the new defaults (epidemiology, finance and
diplomacy on), the subset gate passes with no comparator regression on seeds
42-61 and 62-81, and 0 of 40 worlds go extinct (see [Gate](#gate)). The
full 200-seed gate was not run. The default stays off.

## Why

Great persons were mostly decorative. Achievements spawned them
(`great_persons.py`) or the agent pool promoted them; they carried a role,
an arc and deeds, led armies (campaign generals), went on pilgrimage and
could be crisis candidates, then retired after 20-30 turns. Apart from a
flat faction-influence bonus per role and a research bonus per scientist,
none of them wanted anything, so nothing in the world happened because of
one of them.

## What was built, and what was cut

| Part | Built |
| --- | --- |
| Framework | The ruler-ambition kernel resolves every agenda. Ten great-person kinds are appended to `AmbitionType`; each agenda is one `Ambition` in a one-objective `RulerAmbitions` record keyed by the person, fed `EvidenceEvent`s from the turn's events and settled by `evaluate_ambitions`: state predicates (ownership, the trade-route surface, belief shares), on-time evidence (a coup, a completed temple, an era advance, an invention), the deadline, and, for great persons only, thwarting evidence (a crushed coup, a broken route, the holder's departure). |
| Generals | `lead_campaign` against a war enemy's or hostile neighbour's region (hot-headed generals also a neutral neighbour's): WAR weight, renown and prestige from victories, agitation for war in peacetime; completes when the civ holds the region. `seize_throne` against a weak ruler: a coup through the existing GP-to-throne succession path, citing the grievance or ambition that drives it. |
| Merchants | `open_trade_route` to a bordering civ (trade missions warm relations), `protect_trade_route` to a partner (kept to the deadline; interceding when relations sour), `found_trading_house` (a trade-good artifact and merchant influence; one house per region) and, with `--finance`, `lend_to_crown` (deeper domestic credit; completes on the crown's next domestic loan). |
| Prophets | `spread_faith` to a region where the civ's faith is weak (preaching adds to the region's conversion signal; agent modes) and `found_shrine` (commission a temple that becomes a pilgrimage shrine). |
| Scientists | `advance_learning` (the civ's next era) or, with `--techniques`, `invent_technique` (steers and speeds the civ's next invention). |
| Bonds | Alliances (`loyalty` to the ruler, `conspiracy` behind a plotting general, `partnership` of merchants courting each other's civ) and rivalries (`opposition` to the ruler, `feud` between persons whose agendas collide). They change coup odds, shift faction influence and decide who backs whom in a succession crisis. |
| Weights | Each open agenda's action bias joins the governance bucket and its 1.5x clamp; at most two agendas of one kind count per civ. |
| Provenance | Declarations cite the person's rise and the motive; deeds cite the declaration and what occasioned them; outcomes cite the declaration and their evidence; coups cite the grievance or ambition and the conspirators; bonds cite both declarations. |

**Cut**, and why:

* **Artists.** The simulation has no artist role: aggregate births and the
  agent pool make generals, merchants, prophets and scientists only.
  Patronage would need a new role with a birth trigger and its consumers
  (artifact mapping, succession, viewer); the ruler's `patron_of_arts`
  ambition stays the only patronage objective. Cultural works and
  artifacts are reached through merchants' trading houses and prophets'
  shrines.
* **Persecution and toleration.** Persecution intensity is a per-region
  signal that only militant faiths set, only in agent modes, and only
  inside `compute_persecution`, which never resets regions it does not
  visit. A prophet's push would need an owner for that reset; without one
  it would leave stale intensity in the region batch. Cut rather than
  leak a bridge signal.
* **Rust.** Nothing. Preaching uses the existing conversion signal; a
  crushed agent-backed general's death uses the existing targeted-death
  queue.
* **Viewer panels.** `history[n].gp_agendas` is in the bundle; the viewer
  does not display it.
* **Ruler legitimacy from great persons.** Agendas use a neutral
  calibration (completion and failure legitimacy 0): governance alone owns
  legitimacy. A loyal general's conquest does not count as the ruler's.

## The framework: the ruler-ambition kernel, extended

`ruler_ambitions.py` stays a pure kernel (no simulation imports). The
change is additive:

* `AmbitionType` gains, after the seven ruler types (declaration order is
  the canonical sort order, append only): `lead_campaign`, `seize_throne`,
  `open_trade_route`, `protect_trade_route`, `found_trading_house`,
  `lend_to_crown`, `spread_faith`, `found_shrine`, `advance_learning`,
  `invent_technique` (`GP_AGENDA_TYPES`).
* `generate_ambitions` never builds a pool for them, so ruler reigns draw
  exactly what they drew before (pinned by a test with huge weights on the
  new kinds).
* Their window is 10-40 turns (great persons live 20-30); the ruler window
  stays 20-40 and is validated as before.
* Completion: event goals are a table (`_EVENT_GOALS`) holding the two
  roadmap entries (`build_monument`, `patron_of_arts`) unchanged plus the
  great-person goals; state goals reuse the ownership, route and belief
  predicates; `protect_trade_route` is sustained (the route must stand on
  the deadline itself).
* Failure: at the deadline as before, or earlier on on-time thwarting
  evidence (`GP_THWARTING_EVENTS`: `holder_gone` for every kind,
  `gp_coup_failed`, `trade_route_broken`). Completion wins in the same
  evaluation. Ruler ambitions never fail early.

The adapter (`gp_agendas._evaluate`) builds the `AmbitionSnapshot` from the
holder's civ (owned regions, fresh trade-route partners, the target
region's belief share), numbers this tick's evidence on one world cursor,
and maps the outcome back to the event that settled it.

## Turn placement

`tick_gp_agendas` runs once per turn after Phase 10 (politics, factions,
governance) and diplomacy, before the Phase 10 accumulator flush, and reads
the turn's events (the pre-Phase-10 commit plus Phase 10's own). In order:

1. Holders who left (death, retirement, a throne, captivity, a change of
   allegiance, a fallen civ): this turn's evidence first, then
   `holder_gone`; the record is retired.
2. Each active person (civ, then roster order): its agenda's deed, then
   the kernel's verdict; or, after a three-turn cooldown and with at least
   ten turns of life left, a new declaration.
3. Opposition agitates: the faction of a person set against the ruler
   gains 0.01 influence per turn.

What other phases read is persisted state, effective the next turn: the
governance weight bucket (`agenda_weight_factors`, Phase 5), domestic
credit (`crown_credit_factor`, Phase 3b), invention steering
(`invention_targets`, Phase 4) and the crisis candidates (`back_candidates`,
whenever a crisis is triggered; `note_succession` when it resolves).

## Agendas

A person declares one agenda at a time. The pool is what their role could
vow now; kinds are weighted (base 1.0; `seize_throne` and `lend_to_crown`
1.5; trait leanings double or raise some), targets are drawn uniformly from
the sorted candidates, and the duration is 10 to min(25, remaining life).
Two persons of one civ never hold the same vow (kind and target).

| Kind | Pool | Deed each turn | Completes | Fails early | Weight bias |
| --- | --- | --- | --- | --- | --- |
| `lead_campaign` | regions of a war enemy next to the civ, else of a hostile or suspicious neighbour, else (aggressive, bold, zealous or ambitious generals) of a neutral neighbour | a victory of the civ: +1 renown (+2 if he commanded), +1 prestige, `campaign_victory`; in peace, 10%: sour relations one step (`war_agitation`; with diplomacy also a border grievance) | the civ holds the region | - | WAR x1.1 |
| `seize_throne` | ruler weak (stability < 30, or legitimacy < 0.35 or in crisis), or uneasy (< 45 / < 0.5) and the general already opposed; military influence >= 0.2; reign >= 5 turns; no crisis; >= 2 regions; one plot per civ; not a loyalist | 20% (+5% per conspirator): a coup attempt | `gp_coup` | `gp_coup_failed` | - |
| `open_trade_route` | bordering living civs that are not partners, not at war, not embargoed | 15% (x2 with a partner across the border): warm both dispositions one step up to neutral (`trade_mission`; with diplomacy also goodwill 5 each way) | the pair has a route | - | TRADE x1.1, DIPLOMACY x1.05 |
| `protect_trade_route` | current partners | 30% if the route lapsed by sour relations: talk it back | the route stands on the deadline | war, war declaration or embargo between the pair, or no route | DIPLOMACY x1.1, WAR x0.95 |
| `found_trading_house` | two partners and a region of the civ without a house | 25% with two partners and treasury >= 30: pay 15 (keep), a trade-good artifact, merchant influence +0.03 (`trading_house_founded`) | `trading_house_founded` | - | TRADE x1.1 |
| `lend_to_crown` | `--finance`: fiscal stress >= 0.25, a shortfall, or debt | (state) domestic credit capacity x1.5 per lender, at most two | `crown_loan` (the crown's next domestic `loan_taken`) | - | - |
| `spread_faith` | agent modes: own or adjacent regions where the civ's faith is below 40% | +0.02 to the region's conversion signal for that faith (when no other faith holds the slot); the first time `preaching` and the prophet moves there | the faith reaches 50% there | - | INVEST_CULTURE x1.1 |
| `found_shrine` | own regions without a temple where one can be built | once: commission the temple (the BUILD cost, keep) as a pending build (`shrine_commissioned`) | the temple is completed there: +10 temple prestige (a pilgrimage magnet), `shrine_consecrated` | - | BUILD x1.05 |
| `advance_learning` | techniques off: the next era | - | `tech_advancement` to that era | - | DEVELOP x1.1 |
| `invent_technique` | techniques on: the civ's lowest-tier invention candidates | (state) the candidate's score +2 in `_invent`; chance x1.25 when it is chosen | `technique_invented` of it | - | DEVELOP x1.05 |

Every kind also fails early when its holder leaves (`holder_gone`).

**Outcomes.** Fulfilled: renown +2, the role's faction +0.03 (generals,
military; merchants, merchant; prophets, clergy; scientists, cultural), +2
prestige for a taken region, and loyalty to the ruler when the vow served
the ruler's own faction (or lent the crown money). Failed: renown -1. Both
are events (`agenda_fulfilled`, `agenda_failed` with the reason: time ran
out, the road was cut, the coup was crushed, cut short by death,
retirement, captivity, a throne, a change of allegiance, the fall of their
people) and go to a bounded log (`GPAgendaState.log`, 200 entries).

**Renown.** Every active general gains it from the civ's victories (+1, +2
when he commanded); any person from fulfilled vows. It weighs on coup
success.

### The coup

The existing path, reused piece by piece: the ruler is deposed
(`alive = False`, `apply_leader_legacy`, `check_rival_fall`); the
successor is generated with the existing `general` succession type
(stability -10 x severity and military +10 as guard-shock); the existing
GP-to-throne bridge `_apply_gp_successor_winner` gives the throne the
general's name, trait, lineage and agent id and retires him as
`ascended_to_leadership`; the military faction gets the pending succession
shift; the deposed ruler goes into exile through `create_exiled_leader`
(an exile pretender, as after a crisis); a `coup` named event excites the
coup hazards (rebellion, border incidents, migration). Governance sees the
accession on its next tick (contested: `general`).

Success chance: 0.3 + 0.5 x military influence + 0.05 x renown (at most
four) + 0.1 x (conspirators - loyalists, at most two each) - 0.3 x the
ruler's standing (legitimacy with governance, else stability / 100),
clamped to [0.1, 0.85]. A crushed coup kills the general (an agent-backed
one also through the native targeted-death queue), costs the ruler 3
stability (signal) and credits the loyalists who betrayed it.

The `gp_coup` event cites the declaration, the motive and the conspiracy
bonds. The motive is the grievance (the civ's legitimacy crisis, PSI
crisis, a recent revolt, the ruler's failed ambition, the general's own
failed vow, his opposition bond) or, with none, his ambition (a vow
fulfilled in the last 30 turns) or, with neither, the distress that drained
the ruler's stability (open famines, wars, recent revolts and plague).

### Bonds

| Bond | Formed | Effect |
| --- | --- | --- |
| `opposition` | a general declares `seize_throne`; a winning crisis candidate's feuding rival | the person's faction +0.01 influence per turn; enables plots under an uneasy ruler |
| `conspiracy` | when a general plots: up to two other persons of the civ who are generals, failed a vow, or oppose the ruler (never loyalists) | coup attempt +5% and success +10% each; back the plotter in a crisis |
| `loyalty` | a vow fulfilled in the ruler's own faction, or a loan to the crown; a crisis winner's backers | coup success -10% each; betray the plot when it fails; back the ruler's faction in a crisis |
| `partnership` | merchants of two civs each courting the other's civ | trade mission chance x2 |
| `feud` | a general campaigning against the civ a merchant of his own civ trades with or courts; two generals of two civs campaigning against each other | oppose each other in a crisis |

A person holds at most one bond of each kind; a ruler accepts at most
three loyalists. Bonds lapse when a person leaves or the ruler changes.

**Who backs whom.** When a succession crisis builds its candidates
(`factions.generate_faction_candidates`), each great-person candidate gains
0.05 weight per ally (conspiracy or partnership) in the civ and loses it
per feuding rival; the outgoing ruler's loyalists back the internal
candidate of the ruler's faction. Backers and opponents are written on the
candidate. When the crisis resolves (`resolve_crisis_with_factions`), a
backed winner gets a `succession_backed` event, the backers become its
loyalists and a crowned great person's rivals its opposition.

## Contracts

* **Determinism.** Every draw is `stable_hash_int` on a `gp_agenda.*`
  stream (`declare`, `coup`, `mission`, `intercede`, `agitate`,
  `trading_house`) keyed by world seed, turn and person; nothing reads the
  action RNG. Iteration is civ index then roster order; records are a
  dictionary in insertion order.
* **Accumulator.** Treasury and prestige go through `keep`; a crushed
  coup's stability cost through `signal`; the coup's succession effects are
  the existing `general` succession's guard-shock. With `--agents off` the
  tick mutates directly, as Phase 10 does.
* **Enums.** `AmbitionType` is appended to; no other enum changes.
* **Capped modifiers.** No bucket is added: agenda biases multiply inside
  the governance bucket before its clamp to [1/1.5, 1.5], and the global
  2.5x cap applies after. With governance off they move no weight.
* **Transient signals.** The only bridge signal touched is a region's
  conversion signal, after its builder (`compute_conversion_signals`) and
  only when this turn's agent rows exist; the builder rewrites it every
  Phase 10, so nothing carries over once the vow ends (multi-turn test).
  No other transient state is created.
* **Identity.** Records are keyed by name and birth turn (the pair
  `artifacts._find_gp` uses), plus the agent id for an agent-backed
  person: promotion can give two agents the same name in one turn (found
  in seed 46, where a merchant and a scientist shared one). Civs are
  indices, region targets are names (as in `civ.regions`), route targets
  are civ indices as strings (as the kernel takes them).
* **Diplomacy.** With diplomacy on (now the default) its memory caps
  dispositions, so a mission also leaves goodwill (5) in both memories and
  agitation a border grievance (5) in the civ's memory; diplomacy's own
  drift carries them on.

## Switch and persistence

| Surface | Value |
| --- | --- |
| CLI | `--gp-agendas` / `--no-gp-agendas` (`BooleanOptionalAction`) |
| World field | `WorldState.gp_agendas: GPAgendaState \| None` (presence = on) |
| Default | **Off** (`gp_agendas.DEFAULT_ENABLED_FOR_NEW_WORLDS = False`) for `execute_run`, batch and the live server; resumed, forked and caller-supplied worlds keep their setting; `--no-gp-agendas` drops the state |
| Gate runner | `scripts/m53b_run_validation.py --gp-agendas` forwards the switch to every run and records it in `run_manifest.json` |
| Dormant fields | `WorldState.gp_agendas` and `TurnSnapshot.gp_agendas` are `None` by default and omitted from serialized output, so flag-off saves, bundles and fixtures keep their bytes and old saves load unchanged; crisis candidates carry `backers`/`opponents` only with the switch on |
| State | records (agenda, cursors, renown, cooldown, declaration and motive ids), bonds, the evidence cursor, counters, the outcome log, trading houses |
| Report | `scripts/gp_agendas_report.py report` (per-run numbers from saved runs) and `measure` (conversions and active trade routes counted live; output-neutral) |

## Feature-off identity

Base: `integrate/wave-4` at `705fe2e` (epidemiology, finance and diplomacy
on by default), exported and run from its own `src` with the same Python
environment and native build (no Rust changes; extension built from the
`chronicler-agents` tree of `1a6cacb`, which `705fe2e` keeps).
`PYTHONHASHSEED=0` throughout; compared with `scripts/diplomacy_identity.py
compare`.

| Comparison | Runs | Result |
| --- | --- | --- |
| base vs branch default | seeds 42 and 7; `--agents off` 150 turns and `--agents hybrid` 120 turns; `--simulate-only` | 30 files (state, bundle, chronicle, memories, hybrid `agent_events.arrow`), **0 differences** |
| base vs branch `--no-gp-agendas` | same | 30 files, **0 differences** |
| base gate batch vs branch gate batch, switch off | subset profile, seeds 42-61, 200 turns, hybrid with the narrative sidecar | 2,164 files; the three gate reports differ only in the batch directory they name (checked with the path normalised); every run output identical |

Golden fixtures and the snapshot, RNG and performance-equivalence tests are
unchanged and pass on the branch (no fixture file is touched). With the
switch off no agenda code runs past the `world.gp_agendas is None` check
(a test replaces the tick and the read hooks with functions that raise).

## Tests

| Lane | Base `705fe2e` | Branch |
| --- | --- | --- |
| `pytest -m "not slow" -n 2` (native build) | 5,707 passed, 3 skipped | 5,759 passed, 3 skipped |
| `scripts/run_python_oracle_checks.py` (PR #19 one-line guard fix applied locally, not committed) | - | 1,771 passed, 8 skipped, 2 deselected; guard PASS, no native module loaded, no blocked I/O |
| No-Rust environment (no `chronicler_agents` installed), `pytest -n 2`, no marker filter | 5,510 passed, 200 skipped | 5,561 passed, 201 skipped (the extra skip is the hybrid determinism test, which needs the extension) |

The 52 new cases: 41 in `tests/test_gp_agendas.py` (added to the oracle
lane), the existing `test_ruler_ambitions.py` generation check
parametrised over the 10 appended kinds (rulers never draw them), and
`test_save_load_resume_identity_with_agendas_and_all_five_on` in
`tests/test_wave3_combined.py` (all five systems, epidemiology, finance,
diplomacy, maritime and techniques, plus governance and agendas: the world
is saved on the first turn from 30 with an open agenda and resumed for 15
turns; the result is byte-identical to a straight run).

`tests/test_gp_agendas.py` covers:

* **Kernel.** Kinds appended after the ruler types; window and target
  validation; evidence after the cursor and on target only; thwarting
  fails early, completion wins the same evaluation; a protected route is
  sustained to its deadline and broken by evidence.
* **Generals.** A campaign vow takes WAR weight, gains renown from a
  victory and is fulfilled by the region changing hands; a peacetime general
  agitates against the neighbour he covets; a road soured by that agitation
  cites it; a coup cites its grievance, puts the general on the throne
  through the `general` succession and exiles the ruler; without a
  grievance it cites the ambition, without either the realm's distress; a
  crushed coup kills the general and credits the loyalist; no plot against
  a strong ruler, without the army, or early in a reign.
* **Merchants.** A trade mission opens a route and fulfils the vow; with
  diplomacy missions leave goodwill and agitation a grievance; a protected
  route completes on the deadline or breaks on an embargo; a trading house
  is paid for and leaves a trade good (one per region); a crown lender
  deepens domestic credit and completes on a domestic loan.
* **Prophets.** Preaching abroad raises the conversion signal and the vow
  is settled by the region's faith; the signal is rebuilt every turn and
  leaves nothing once the vow ends (multi-turn reset check); a commissioned
  temple becomes a pilgrimage shrine.
* **Scientists.** An era vow is settled by the advance or fails at the
  deadline; with `--techniques` the vowed technique is steered and drawn.
* **Lifecycle and bonds.** Retirement cuts an agenda short; one vow per
  civ and target; war and trade parties feud and merchants partner across
  borders; allies back and rivals oppose a succession candidate and the
  winner inherits them; flag-off candidates carry no backing; open agendas
  ride the capped governance bucket.
* **Switch.** Determinism; save, load and resume identity with live
  agendas and bonds; the switch off is dormant and omitted; the feature
  off never runs agenda code; CLI flag, gate forwarding, snapshot field and
  report; hybrid runs are deterministic.

## Gate

Subset profile (20 seeds x 200 turns, hybrid, `--parallel 2`, the new
defaults: epidemiology, finance and diplomacy on), base `705fe2e` run from
the exported tree, branch with `--gp-agendas`, compared with
`chronicler.validation_compare`. Two seed sets. In the subset only
community, needs and cohort are required; the rest is informational.

| Oracle | 42-61 base / on | 62-81 base / on |
| --- | --- | --- |
| gate | PASS / PASS | PASS / PASS |
| comparator | - / NO REGRESSION | - / NO REGRESSION |
| community (qualifying seeds, 15 required) | 20 / 20 | 20 / 20 |
| needs (seeds with the expected sign, 12 required; median effect) | 17, 0.68 / 18, 0.98 | 12, 0.44 / 15, 1.00 |
| cohort (seeds; median effect) | 20, 1.11 / 20, 1.35 | 20, 1.34 / 20, 1.55 |
| era (seeds with inflections; silent seeds) | 20; 0 / 20; 0 | 20; 0 / 20; 0 |
| arcs (seeds with three arc types; families) | 14; 5 / 17; 6 | 16; 6 / 15; 6 |
| artifacts (creation per civ per 100 turns, band 1-3; loss rate) | PASS 2.01, 3.1% / PASS 2.59, 3.4% | PASS 1.98, 4.4% / **PARTIAL** 2.29, 1.1% |
| regression | FAIL (`civ_survival`) / PASS (strict) | FAIL (`civ_survival`) / PASS (calibrated) |
| satisfaction mean; latest (60 turns) | 0.583; 0.610 / 0.577; 0.592 | 0.598; 0.605 / 0.601; 0.617 |
| agent rebellion rate per agent-turn | 0.043 / 0.052 | 0.023 / 0.029 |
| extinct worlds | 0 / 0 | 0 / 0 |

* **Regression.** `civ_survival` asks that no seed lose every initial civ
  and at most 20% keep all four. The base keeps all four in 5 of 20 seeds
  (0.25) in both sets, the branch in 4 (0.20): one seed fewer, which is
  inside the threshold. No seed lost every civ in either arm.
* **Artifacts on 62-81.** The loss rate (artifacts lost or destroyed per
  artifact) falls below its band: 4 of 366 against 14 of 317 on the base.
  Creation is in band. Informational.
* **Before the trading-house cap** (the first branch gate on 42-61) the
  artifact creation rate was 3.38, above the band, with 9.7 trade goods per
  run: agent worlds promote dozens of merchants and each could found
  another house. One house per region brought it to 2.59 (3.6 trade goods
  per run). The gate was rerun on the final code.
* The last change after these gates adds one citation (a trade road soured
  by a general's agitation cites the agitation). It is outcome-neutral:
  seed 42 rerun (hybrid with the sidecar, and `--agents off` 300 turns)
  gives states and bundles identical to the gated ones apart from `causes`
  and the causal index, and an identical agent-event log.
* **Not run:** the 200-seed x 500-turn full gate. Default stays off.

## On and off

Per run, mean of 20 runs, from `scripts/gp_agendas_report.py` (agendas and
coups from the saved state; conversions and active trade routes measured
live with its `measure` mode, which is output-neutral: a measured base run
is byte-identical to an unmeasured one). Off is the base `705fe2e` (equal
to the branch with the switch off). Hybrid: seeds 42-61, 200 turns, the
gate configuration without the sidecar. Agents off: seeds 42-61, 300 turns.

| Per run | hybrid off | hybrid on | agents-off off | agents-off on |
| --- | --- | --- | --- | --- |
| agendas declared: generals | - | 2.55 | - | 5.10 |
| merchants | - | 18.25 | - | 17.85 |
| prophets | - | 18.50 | - | 0 (no prophets are born without agents) |
| scientists | - | 4.80 | - | 12.25 |
| fulfilled (generals / merchants / prophets / scientists) | - | 21.90 (0.60 / 13.55 / 7.35 / 0.40) | - | 14.60 (1.05 / 12.10 / 0 / 1.45) |
| failed (generals / merchants / prophets / scientists) | - | 21.65 (1.90 / 4.35 / 11.15 / 4.25) | - | 19.55 (3.85 / 5.10 / 0 / 10.60) |
| great-person coups: seized / crushed (attempts) | - | 0.20 / 0.40 (0.60) | - | 0.30 / 0.15 (0.45) |
| all coups (named `coup` events, including the leader-mortality hazard) | 7.05 | 7.25 | 9.50 | 10.60 |
| wars declared | 2.95 | 2.95 | 9.85 | 11.15 |
| war events (battles and instant wars) | 12.70 | 12.80 | 45.35 | 47.90 |
| active trade routes (mean per turn) | 2.65 | 2.72 | 2.65 | 2.88 |
| conversions (agents changing faith) | 734 | 959 | - | - |
| artifacts | 16.10 | 20.70 | 31.15 | 32.45 |
| of which trade goods | 0.25 | 3.60 | 0.00 | 2.35 |
| bonds formed | - | 10.65 | - | 6.45 |

Totals over the 20 hybrid runs: 21 campaign victories, 15 agitations, 69
trading houses, 17 crown loans, 226 preaching missions, 68 shrines, 12 coup
attempts (4 seized, 8 crushed); bonds: 112 loyalty, 82 partnership, 13
opposition, 3 conspiracy, 3 feud. By kind (hybrid): protect a route 184
fulfilled / 42 failed; trading house 69 / 10; shrine 68 / 5; spread the
faith 79 / 218 (170 ran out of time); lend to the crown 17 / 35; campaign 8
/ 29; seize the throne 4 / 9; advance learning 8 / 85 (71 ran out of time);
open a route 1 / 0 (hybrid civs rarely border a civ they do not already
trade with). Agents off: 26 trade missions, 46 agitations, 73 campaign
victories.

## Stories

Seed 42, recorded chains (`causes`, effect first). The first two are from
the hybrid gate run (seed 42 of the 42-61 set), the third from an
`--agents off` 300-turn run, all on the final code.

**1. The betrayed plot (Thornwall Confederacy, hybrid).**

* Turn 28: Thornwall's treasury can no longer pay for its institutions
  (`fiscal_crisis`). Turn 36: Consul Proofwind, merchant, vows to lend to
  the crown, citing the fiscal crisis.
* Turn 45 famine in Thornwood; turn 50 the crown borrows 40 from its
  merchant houses (`loan_taken`, citing the famine). Proofwind underwrites
  it (`crown_loan`, citing the loan and his vow), fulfils the vow and
  becomes a loyal servant of Empress Pelago (`gp_alliance_formed`, citing
  the fulfilment).
* Turn 29 the Siege of Obsidian Shore is won; turn 41 a great general,
  Chancellor Imperator, emerges, citing that victory.
* Turns 54-57: a locust swarm, the bloody flux and exhausted soil bring
  famine to Verdant Plains and Obsidian Shore. Turn 57 Imperator vows to
  seize the throne, citing his rise and both famines (no legitimacy crisis
  or failed vow was on record, so the distress that drained Pelago's
  stability is the grievance), and turns against Pelago.
* Turn 62: "The coup of Chancellor Imperator against Empress Pelago of
  Thornwall Confederacy fails, betrayed by Consul Proofwind; Chancellor
  Imperator is put to death." The event cites his vow, the two famines and
  Proofwind's loyalty bond.

**2. A general's campaign for a capital (hybrid).**

* Turn 8 the Second Raid on Amber Valley (Thornwall wins); turn 23
  Sovereign Chalkstone emerges, citing it. The same turn he vows to take
  Obsidian Shore, the Ashkari capital, citing his rise and the border
  incident of turn 21.
* Turn 24 he agitates for war against the Ashkari Nomads; relations sour
  (and, diplomacy being on, a border grievance enters Thornwall's memory).
  Turn 25 Thornwall goes to war with the Ashkari "seeking conquest of
  Obsidian Shore" (the declaration's recorded causes are the frictions the
  WAR weight reads: the border incident of turn 24, an old embargo and a
  proxy detection; the agitation is not among them).
* Turn 26 the Third Warband lays siege; turn 29 "The Siege of Obsidian
  Shore ... attacker_wins ... Sovereign Chalkstone commands". His
  `campaign_victory` deed cites the battle; the capital is occupied and
  ceded; the vow is fulfilled, citing the vow, the battle, the annexation
  and the deed. That victory is the one Imperator's rise cites in story 1.

**3. The war party and the trade party (Thornwall Confederacy, agents off).**

* Turn 5 Empress Dayir emerges from a war win and vows to take Frostholm
  Tundra (citing her rise and the war of turn 0). Turns 7-9 she shares in
  one victory and commands two at Amber Valley; turn 9 the vow is
  fulfilled (citing the annexation and her last victory).
* Turn 8 Thornwall takes High Priestess Wavecrest hostage from Kethani; by
  turn 10 she serves Thornwall as a merchant and vows to keep the trade road
  to the Ashkari Nomads open.
* Turn 12 Dayir vows to take Obsidian Shore from the Ashkari: "Empress Dayir
  and High Priestess Wavecrest of Thornwall Confederacy quarrel: one wants
  war on Ashkari Nomads, the other its trade" (a feud, citing both vows).
* Turn 13 Dayir agitates for war; relations sour and the road closes. The
  same turn Wavecrest fails her vow ("the trade road was cut"), citing her
  vow and Dayir's agitation. Turn 16 she vows the road to the Selurian
  Republic instead and keeps it to turn 31; Dayir's second campaign runs
  out of time at turn 23.

## Effects on other systems

Hybrid, seeds 42-61, 200 turns, per run, off / on (same runs as the table
above):

* **War.** Unchanged in hybrid: 2.95 / 2.95 wars declared, 12.7 / 12.8 war
  events. Agents off (300 turns): 9.85 / 11.15 declared (+13%), 45.4 /
  47.9 events; agitation (46 over 20 runs) and the WAR bias of campaigns.
* **Coups and succession.** Great-person coups add about one every five
  runs (0.20 seized, 0.40 crushed); all coups 7.05 / 7.25 (the
  leader-mortality hazard's coups dominate). Succession crises unchanged
  (0.65 / 0.65); governance legitimacy crises 0.75 / 0.60.
* **Religion.** Conversions +31% (734 / 959), about half of it the
  preaching signal; pilgrimages 2.95 / 3.50; active temples at the end
  6.0 / 6.5; completed infrastructure 70.9 / 78.4 (shrines).
* **Agent unrest.** Agent rebellions 1,504 / 1,871 per run (+24%; rate
  0.043 / 0.052 per agent-turn, and 0.023 / 0.029 on 62-81). The rise is
  carried by a few worlds: on 42-61 only 9 of 20 seeds rise (median ratio
  0.91; seed 60 goes from 1,168 to 2,777), on 62-81 eleven seeds have none
  in either arm and seed 70 goes from 611 to 3,209. Ablations (constants
  zeroed, same 20 seeds): no preaching 1,712; preaching only in own regions
  1,754; no faction shifts 1,701; no weight bias 1,828; no crown credit
  1,825; no shrines 1,909; no coups 1,929. Preaching is the largest single
  part; the rest is spread over the levers. Satisfaction is not lower
  (above). Civ-level rebellion events 16.2 / 18.5.
* **Finance.** Crown lenders deepen domestic credit: loans 11.0 / 10.4,
  state defaults 1.30 / 0.80.
* **Diplomacy.** Treaties signed 12.7 / 11.6, embargoes 16.4 / 15.0;
  missions leave goodwill, agitation border grievances.
* **Factions.** Dominance shifts 14.6 / 13.9; power struggles 9.9 / 9.2.
* **Artifacts.** 16.1 / 20.7 (trade goods from trading houses; temple
  relics); in band.
* **Arcs.** More seeds show three arc types (14 / 17 on 42-61): executed
  bold generals become tragic heroes; deposed rulers go into exile.
* **Population.** 160.9 / 166.8 at turn 200 (agents off, 300 turns: 188.5
  / 211.9; living civs 3.75 / 4.05). No world went extinct in any run.
* **Narration.** About 90 new events per hybrid run (declarations,
  outcomes, deeds, bonds), importance 3-5 except coups (7-8) and
  `succession_backed` (6). Every one names its person, so arcs and the
  curator see them.

## Open

* **Full gate not run.** The 200-seed x 500-turn gate is required before
  any default flip; the default stays off.
* **Agent rebellion tail.** Decide whether a few worlds tipping into heavy
  rebellion is acceptable; if not, preaching abroad (into foreign-held
  regions) is the first lever to narrow.
* **Scientists rarely succeed** (0.4 fulfilled per hybrid run): eras and
  inventions seldom come inside a 10-25 turn window. Their only levers are
  a DEVELOP bias and (with techniques) steering; a stronger lever would
  touch the era or invention costs.
* **Generals in peaceful hybrid worlds** mostly sit idle (2.55 agendas per
  run): campaign targets need a hostile or war neighbour unless the general
  is hot-headed.
* **Artists and persecution/toleration** are cut (above).
