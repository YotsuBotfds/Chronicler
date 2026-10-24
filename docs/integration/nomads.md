# Pastoral and nomadic peoples: herds, raids, tribute, hordes, sedentarization

Branch `feat/nomads`, from `integrate/wave-4` at `c5f4df4` (open as PR #21:
procedural geography with steppe, desert, tundra and marsh, the contact
ledger, campaign warfare, diplomacy, finance, epidemiology, causal
provenance, food balance, default-off techniques and maritime, the Rust
politics federation step). `c5f4df4` is the identity and gate base for every
result below. Code: `src/chronicler/nomads.py` (behaviour) and
`src/chronicler/nomads_state.py` (persisted state). No native change.

**Status.** Default off behind `WorldState.nomads` (CLI `--nomads`). With the
switch off no nomad code runs except the food hook, which returns its input
list unchanged, and every output is byte-identical to `c5f4df4` (see
[Identity](#feature-off-identity)). The 20-seed subset gate passes with the
switch on (see [Results](#results)); the full 200-seed gate was not run.

In three procedural 48-region worlds with steppe (300 turns, `--agents off`
and hybrid) the switch produces, per run, 1.8 nomadic and 3.2 pastoral
polities at once, 26 raids that get through and 4 driven off, 5 tribute
pacts, 2.7 hordes (1.8 broken by their khan's death), 4 regions taken by
herders and 1.2 sedentarizations; 16 hordes formed over the six runs. Two
supplementary 20-seed sets were also run: in one of them the needs oracle
fails by one seed with the switch on (the base sat exactly at the
threshold; see [Supplementary seed sets](#supplementary-seed-sets-not-the-gates-the-same-comparison)).

## What was built, and what was cut

| Part | Built |
| --- | --- |
| Subsistence mode | Per civ: `sedentary`, `agro_pastoral` or `nomadic`, seeded when the switch is turned on from the population-weighted pastoral suitability of the civ's land (steppe 1.0, desert and tundra 0.85, hills and mountains 0.5, plains 0.3, river and marsh 0.15, coast and forest 0.1, jungle 0): at least 0.70 nomadic, at least 0.45 agro-pastoral. Polities founded later (secession, restoration) are seeded the same way at their first tick. |
| Herds | Per region (100 head = a full steppe pasture). Pasture is terrain x grass (water against the terrain's normal water, so droughts shrink it) x the disaster capacity modifier, times a seasonal factor (summer grazing in tundra and mountains, winter grazing in desert and lowlands). Logistic growth below it, die-off above it, dzud winters on cold pasture, slaughter on land settled people hold. |
| Food | One hook in the food path: `ecology.compute_resource_yields` returns `nomads.food_yields(...)`. Herders farm less (grain and botanical slots x0.7 nomadic, x0.9 agro-pastoral) and their herd adds milk and meat to the region's first food slot (0.40 harvest index per 100 head for nomads, 0.6 of that for agro-pastoralists, by season 1.0/1.2/1.0/0.8). It feeds the hybrid goods economy (Phase 2 yields) and the Python ecology's famine check. |
| Mobility | Transhumance: each tick a pastoral civ's herds move toward the seasonal pasture across its land (60% of the gap for nomads, 20% for agro-pastoralists), so nomads lose less to the season and the dzud. Loose hold: nomads release outlying land whose pasture has stood empty for 15 ticks (no people to speak of, no buildings, not the capital), and EXPAND reaches desert and tundra for herders in any era. |
| Raids | Pastoral civs raid settled neighbours across land borders (nomads raid agro-pastoralists too): chance 0.10 a turn for nomads (0.03 agro-pastoral) x (1 + 1.5 hunger) x (0.5 + asabiya), doubled in a horde, capped at 0.6. Hunger is the herd shortfall against pasture, or an open famine. Raiders and the garrison fight with the campaign layer's terms (`war.battles.quality`, `garrison_size`, `defense_multiplier`, the tech and technique multipliers), raiders mounted (x1.3 nomads). A raid that gets through takes plunder from the treasury and kills people (through `war.armies.drain_population`, native deaths in agent modes); it shocks the victim's stability; either outcome sours dispositions, and with diplomacy on leaves a border grievance. |
| Tribute | A settled civ raided twice within 12 turns by the same raiders and too weak to fight back (power below 1.5x theirs) may buy peace: a pact paying 8% of its economy a turn, which spares it their raids. It lasts 40 turns; a payer grown 1.4x stronger repudiates it (a treaty grievance with diplomacy on); two missed payments lapse it; war ends it. |
| Hordes | A nomadic khan (asabiya at least 0.55, stability at least 15, reign at least 2 turns) unites weaker pastoral peoples within three land hops whose memory allows a sworn bond, or takes command of the federation he belongs to when he is its strongest member. The horde is a federation in `world.federations` (federation defense, the Python/Rust federation dissolution rule and every federation consumer apply). Its wars on settled peoples aim at conquest; it rides in waves: the khan declares war on a settled neighbour and each member bordering the enemy joins, through the campaign WAR path (`war.runtime.declare_or_press_war`). |
| Fragmentation | When the founding khan dies the horde breaks apart at once: the federation is dissolved, the heirs' bonds go cold (suspicious), the khan's people lose 15 stability and 15% of their regions' asabiya, the clans 5 stability. Secession and collapse soon after cite the break. A horde whose federation sheds its clans, or whose khan's people fall or bow to an overlord, dissolves. |
| Sedentarization | A pastoral people living mostly on farmland (pastoral share below 0.5 for nomads, 0.3 for agro-pastoralists) settles after a generation (25 turns of it, the clock running back two turns for each turn above): nomadic -> agro-pastoral -> sedentary, keeping 90% of its regions' asabiya. Farmland held by herders erodes asabiya every turn; the steppe breeds it for nomads. |
| Provenance | Raids cite the herd loss or famine behind them, the horde and a tribute that just ended; tributes cite the raids; hordes cite the federation, war victories and raids; rides cite the war declarations; fragmentation cites the khan's death and the horde; sedentarization cites the conquests that brought the farmland and the horde; dzuds and pasture die-offs cite the drought. A war declared between a pair cites its latest raid; secession and collapse cite a horde broken within 20 turns. |

**Cut** (and why):

* *Pastoral goods (horses, wool) in the goods economy.* The economy has eight
  fixed goods (`ResourceType`, mirrored in Rust and in every batch schema);
  there is no clean slot, so herds enter only as food.
* *Mounted mobility and terrain bonuses for nomad armies in campaigns.* Nomad
  armies are the campaign layer's armies; their strength already carries
  asabiya. Raids carry the mounted factor.
* *Nomad-on-nomad cattle raiding.* Raiders only raid peoples more settled than
  themselves.
* *Re-nomadization* of settled peoples. Breakaway polities are seeded from
  their own land, so a steppe province seceding from a settled empire comes
  back nomadic.
* *Off-mode herd food with the native ecology runtime.* With `--agents off`
  and the native extension installed, Phase 9 yields come from Rust, so herds
  do not reach the famine check there (they do in the Python ecology and in
  every agent mode's goods economy). One food hook was the constraint; a
  second, off-mode-only hook would be needed.
* *Viewer panels.* `history[n].nomads` is in the bundle; the viewer does not
  display it.

## Turn placement

| When | What |
| --- | --- |
| Phase 2 (agent modes) | `refresh_resource_yields` -> `compute_resource_yields` -> `nomads.food_yields`: herd food in the yields the goods economy reads |
| Phase 5 | the nomad weight bucket (WAR, for raiders and hordes facing a hostile settled neighbour); EXPAND's harsh-terrain filter skipped for herders |
| After Phase 5 and the maritime tick | `tick_nomads` (order below), before campaigns so the wars a horde opens are fought this turn |
| Whenever a war opens | a horde member's new war on a settled people aims at conquest (`war.peace.choose_aim`) |
| Phase 9 (Python ecology) | `compute_resource_yields` -> `food_yields`: herd food in the famine check |
| After Phase 10 (diplomacy on) | this turn's raids (a border grievance of the raided) and repudiated tributes (a treaty grievance of the raiders) enter diplomatic memory |

`tick_nomads`: detect regions pastoral civs took since the last tick (from
the controller list saved at the end of the last tick); seed modes for new
polities; sync hordes with their federations (fragment on the khan's death,
dissolve otherwise); herds (settled land loses them; transhumance, growth,
die-off, dzud); loose hold; asabiya; sedentarization; tribute payments and
ends; raids; new tributes; new hordes; conquest waves; prune old records;
save the controllers.

## Subsistence and herds

**Seeding.** `pastoral_share(civ)` is the population-weighted mean of
`PASTORAL_SUITABILITY` over the civ's regions (a landless civ scores 0).
`seed_mode`: at least `NOMADIC_SHARE` 0.70 nomadic, at least `AGRO_SHARE`
0.45 agro-pastoral, otherwise sedentary. Starting herds: 0.6 (nomadic) or
0.4 (agro-pastoral) of each held region's pasture.

**Pasture.** `capacity(region) = 100 x PASTURE[terrain] x grass x min(1,
capacity_modifier)`, with `grass = min(1.2, 0.3 + 0.7 x water /
normal_water[terrain])`; `PASTURE` steppe 1.0, plains 0.8, river 0.7, hills
0.6, tundra 0.5, mountains 0.4, desert 0.35, coast 0.3, marsh 0.25, forest
0.2, jungle 0.05. Seasonal pasture multiplies it by `SEASON_PASTURE`
(spring, summer, autumn, winter): tundra 0.8/1.4/0.8/0.2, mountains
0.8/1.4/0.8/0.3, hills 0.9/1.2/0.9/0.6, steppe 1.0/1.1/1.0/0.7, desert
1.1/0.6/1.0/1.3, plains and river 1.0/1.0/1.0/0.9, others 1.0/1.0/1.0/0.8.

**Per tick, per region held by herders** (and not occupied by an enemy):

1. *Transhumance* (civs with two or more such regions): the civ's total herd
   `H` is spread in proportion to the seasonal pasture `K_s`; each region
   moves `MOBILITY` (0.6 nomadic, 0.2 agro-pastoral) of the way toward
   `H x K_s(r) / sum K_s`. The total is conserved.
2. *Growth*: below 20% of `K_s`, restocking adds 1% of `K_s`; below `K_s`
   the herd grows by `0.06 h (1 - h / K_s)`; above it `0.35 x (h - K_s)`
   dies (`herds_lost_pasture`; a `pasture_drought` report when a civ loses
   at least 15 head in a drought).
3. *Dzud* (winter turns, on steppe, tundra, hills or mountains or in a
   subpolar latitude band): chance 0.03, x2 in a cooling phase, x1.5 on
   tundra or subpolar land, x1.5 when the water is below 0.25; it kills
   25-50% of the herd (one `dzud` report per civ losing at least 5 head, at
   the worst-hit region).

Herds on land settled people hold fall by 20% a tick (to 0 below half a
head); on land an enemy occupies, by 10%.

## Raids and tribute

**Targets** of a pastoral civ: regions across its land borders (sea lanes
excluded) held by a living civ more settled than itself and not occupied by
a third party; never a member of its federation, its overlord or vassal, a
civ it is at war with (the campaign layer fights that), a tributary, a civ
in a campaign truce with it, one it regards as friendly or allied or that
regards it as allied, or (diplomacy on) one bound to it by a peace,
non-aggression or alliance treaty.

**Resolution.** Raiders: `max(3, 0.25 x military + 60 per mille of the
border region's people)`. Attack power: raiders x `quality(civ, 750)` x
mounted (1.3 nomadic, 1.1 agro-pastoral) x the tech and technique
multipliers x U(0.85, 1.15). Defence: `garrison_size` x `quality(target,
600)` x the tech and technique multipliers x `defense_multiplier` (terrain,
role, river, fortifications, home ground) x U(0.85, 1.15). The raid gets
through when attack >= defence:

* plunder `min(30, 6% of the target's projected treasury) x min(1, ratio /
  1.5)` (keep); 2% of the region's people killed (at least 1); the
  target's stability -2 (signal); the raiders lose 5%;
* otherwise the raiders lose 25% (at least 1);

raider losses are people of the border region and 0.3 military each
(guard-action). The target's disposition toward the raiders falls one step;
the raiders' toward the target falls to suspicious. Records are kept 40
turns.

**Tribute.** After a raid that got through, when the same raiders got
through twice in 12 turns and the victim's power is below 1.5x theirs: chance
0.8 for cautious, shrewd or calculating rulers, 0.2 for aggressive, bold,
stubborn or zealous ones, 0.5 otherwise. The pact pays `clamp(int(0.08 x
economy) + 1, 1, 15)` a turn from the next turn.

## Hordes

**Formation** (per eligible khan, chance 0.06 a turn, x1.5 for aggressive,
bold, ambitious or zealous rulers):

* outside a federation: every pastoral civ within three land hops that is
  free (no federation, no overlord), not at war with the khan or a sworn
  follower, weaker in `diplomacy.power`, neither side hostile, and (with
  diplomacy on) without a memory that caps the bond below friendly, swears
  with chance `min(0.9, 0.3 + 0.3 x (ratio - 1))`. Members become allied to
  each other and a federation named "The <Golden, Blue, ...> Horde" is
  added;
* inside a federation, when the khan is its strongest member: the
  federation is renamed and becomes the horde.

Each tick the horde's members are its federation's members (the federation
code may add an allied neighbour or shed a clan whose bond has cooled).

**Conquest waves.** While the khan is at war with no settled people, chance
0.2 a turn that the horde rides against a settled neighbour of the khan
(weighted by population and treasury over power): `declare_or_press_war`,
with the campaign truce, the diplomacy war guard and `on_war_declared`
applied as the WAR action applies them. Each member bordering a settled
enemy of the khan joins its war with chance 0.6. A horde member's new war on
a settled people aims at conquest (never tribute or vassalization). With
`--no-campaigns` there are no waves; the weight bucket still applies.

**Ends.** The founding khan dead or replaced: `horde_fragmented` (above).
The khan's people extinct: `horde_dissolved`, citing their conquest. The
federation gone, down to one member or without the khan, or the khan a
vassal: `horde_dissolved`.

## Switch and persistence

| Surface | Value |
| --- | --- |
| CLI | `--nomads` / `--no-nomads` (`BooleanOptionalAction`) |
| World field | `WorldState.nomads: NomadState \| None` (presence = on) |
| Default | **Off** (`nomads.DEFAULT_ENABLED_FOR_NEW_WORLDS = False`) for `execute_run`, batch and the live server; resumed, forked and caller-supplied worlds keep their setting; an explicit `--nomads` on a resumed world seeds modes and herds from its current land; `--no-nomads` drops the state |
| Gate runner | `scripts/m53b_run_validation.py --nomads` forwards the switch to every run and records it in `run_manifest.json` |
| Dormant fields | `WorldState.nomads` and `TurnSnapshot.nomads` are `None` by default and omitted from serialized output, so flag-off saves, bundles and fixtures keep their bytes and old saves load unchanged |
| State | per civ: mode, the turn and event that set it, the settling clock; per region: herd, empty-pasture clock, controller at the last tick; raids (40 turns), tribute pacts, hordes, conquests (80 turns); counters. Region and civ identity by index; a horde's federation by its federation name |

The only derived cache (`_CacheSlot`, the region-name index) never
serializes or affects equality. A tick leaves nothing transient on the
world; the only transient it sets is the existing
`_controller_changed_this_turn` flag of an abandoned region, consumed and
reset by the turn as for every other controller change
(`test_abandonment_flag_is_cleared_by_the_turn_and_nothing_transient_is_left`).

## Parameters

All in `chronicler/nomads.py` (illustrative, not fitted to any gate):
`NOMADIC_SHARE 0.70`, `AGRO_SHARE 0.45`, `NOMADIC_FLOOR 0.50`,
`AGRO_FLOOR 0.30`, `GENERATION 25`, `SETTLE_RECOVERY 2`, `HERD_SCALE 100`,
`HERD_GROWTH 0.06`, `HERD_INFLOW 0.01`, `HERD_DIEOFF 0.35`,
`HERD_SETTLED_DECAY 0.8`, `HERD_OCCUPIED_DECAY 0.9`, `HERD_START 0.4/0.6`,
`MOBILITY 0.2/0.6`, `DZUD_CHANCE 0.03`, `DZUD_COOLING 2.0`, `DZUD_POLAR
1.5`, `DZUD_DRY 1.5`, `DZUD_LOSS 0.25-0.5`, `HERD_FOOD 0.40`,
`HERD_FOOD_SHARE 0.6/1.0`, `HERD_FOOD_SEASON 1.0/1.2/1.0/0.8`, `CROP_SHARE
0.9/0.7`, `NOMAD_ASABIYA_GROWTH 0.04`, `SETTLED_ASABIYA_DECAY 0.004`,
`SEDENTARIZATION_ASABIYA 0.9`, `LOOSE_TURNS 15`, `LOOSE_HERD 0.05`,
`LOOSE_POP 10`, `RAID_BASE 0.03/0.10`, `RAID_HUNGER 1.5`, `RAID_HORDE 2.0`,
`RAID_MAX 0.6`, `RAID_MILITARY_SHARE 0.25`, `RAID_POP_PERMILLE 60`,
`MIN_RAIDERS 3`, `MOUNTED 1.1/1.3`, `RAID_MORALE 750`, `RAID_LOOT_SHARE
0.06`, `RAID_LOOT_CAP 30`, `RAID_KILL_SHARE 0.02`, `RAID_STABILITY 2`,
`RAID_WIN_LOSS 0.05`, `RAID_REPULSED_LOSS 0.25`,
`RAID_MILITARY_PER_RAIDER 0.3`, `RAID_MEMORY 40`, `TRIBUTE_RAIDS 2`,
`TRIBUTE_WINDOW 12`, `TRIBUTE_POWER 1.5`, `TRIBUTE_CHANCE 0.5/0.8/0.2`,
`TRIBUTE_RATE 0.08`, `TRIBUTE_MIN/MAX 1/15`, `TRIBUTE_TERM 40`,
`TRIBUTE_REPUDIATE_RATIO 1.4`, `TRIBUTE_REPUDIATE_CHANCE 0.25`,
`TRIBUTE_MAX_MISSED 2`, `HORDE_ASABIYA 0.55`, `HORDE_STABILITY 15`,
`HORDE_CHANCE 0.06`, `HORDE_STRONG_TRAIT 1.5`, `HORDE_REACH 3`,
`SUBMIT_BASE 0.3`, `SUBMIT_SLOPE 0.3`, `SUBMIT_MAX 0.9`,
`HORDE_WAVE_CHANCE 0.2`, `HORDE_RIDE_CHANCE 0.6`, `FRAGMENT_STABILITY 15`,
`FRAGMENT_MEMBER_STABILITY 5`, `FRAGMENT_ASABIYA 0.85`, `NOMAD_WAR_WEIGHT
1.2`, `HORDE_WAR_WEIGHT 1.4`, `WEIGHT_CEILING 1.5`, `CONQUEST_MEMORY 80`.
Diplomacy: `GRIEVANCE_RAID 4.0`, `GRIEVANCE_RAID_REPULSED 2.0` (border),
`GRIEVANCE_TRIBUTE_REPUDIATED 10.0` (treaty).

Contracts: no new accumulator category (treasury `keep`; raid stability
`signal`; fragmentation stability `guard-shock`; raider military losses
`guard-action`); no action type, enum value or Rust change; the weight
modifiers are one contributor bucket clamped to [1/1.5, 1.5] and recorded
like diplomacy's, under the global cap; `SUBSISTENCE_MODES`,
`HORDE_STATUSES`, `TRIBUTE_STATUSES` and `COUNTER_KEYS` are append-only;
all randomness is `random.Random(stable_hash_int("nomads", <namespace>,
seed, turn, ...))` (`dzud`, `raid`, `tribute`, `repudiate`, `horde`,
`submit`, `wave`, `ride`); region asabiya is written directly, as the
existing asabiya dynamics do.

## Feature-off identity

1. **Direct runs** (`scripts/diplomacy_identity.py compare`). The base export
   (`c5f4df4`, `git archive`, run with its own source on `PYTHONPATH`)
   against this branch, same interpreter, same native extension (built from
   this tree; the branch has no Rust change, so it is also the base's
   extension; SHA-256 `2a9861de...548d43`) and `PYTHONHASHSEED=0`: template
   default worlds, seeds 42 / 7 / 1234, `--agents off` 300 turns and
   `--agents hybrid` 200 turns; procedural 48-region x 10-civ worlds, seeds 7
   and 13, off 200 and hybrid 120 turns. Every output file (`state.json`,
   `chronicle.md`, `memories_*.json`, `agent_events.arrow`,
   `chronicle_bundle.json` minus `metadata.generated_at`): **99 files, 0
   differences** with the default switch and **99 files, 0 differences** with
   an explicit `--no-nomads`, on the final head.
2. **Gate batch.** The base subset gate (run from the exported `c5f4df4`
   tree) against this branch's switch-off subset gate (no flag), 20 seeds
   x 200 hybrid turns, at `e401e42` (later commits change nomad
   descriptions and the report script only): all 20 seed directories,
   2,160 run files (states, bundles, agent-event and validation sidecars,
   memories, chronicles), plus the validation report, gate decision and
   both summaries (batch path normalized): 0 differences.
3. **Switch on, nothing pastoral.** In the switched-on subset gate, the 8
   template worlds that never had a pastoral people (seeds 44, 53, 55, 56,
   57, 59, 60, 61) end with exactly the base's state (minus the `nomads`
   field) and chronicle: with no herders the layer is inert.
4. **In the suite.** The frozen exact-trajectory oracles
   (`test_performance_equivalence` with the golden fixtures in
   `tests/fixtures/performance/`, `test_governance_dormancy`,
   `test_turn_artifact_lifecycle`) pass unchanged; no fixture changed.
   `test_feature_off_never_runs_nomad_code` forbids every nomad entry point
   (the tick, seeding, weights, EXPAND reach, war aims, snapshots, pasture
   and share helpers and diplomacy's nomad inputs) during a 30-turn
   procedural campaign run with diplomacy on, and checks that the one hook
   that always runs, `food_yields`, returns its input list itself.

## Tests

`tests/test_nomads.py` (48 tests, also in the bounded offline lane):

* subsistence: modes seeded from terrain (template and procedural), starting
  herds on pastoral land only, polities founded later seeded at their first
  tick, landless ones settled;
* herds: logistic growth toward pasture, drought shrinking pasture and
  killing the overshoot, dzud in winter only (with its report and the
  herd-loss key raids cite), transhumance up to the tundra in summer and
  down to the desert in winter with the total conserved, nomads losing less
  to the winter than agro-pastoralists on the same land, herds slaughtered
  away on settled land;
* the food hook: identity while off and on settled land (the same list
  object, and the same yields as a switch-off world), herders farming less
  and eating from their herds, herd food reaching the famine check and the
  goods economy's per-worker yield;
* raids: plunder, deaths, stability and dispositions; a repulsed raid
  costing the raiders; no raids on friends, allies, federation members,
  tributaries, enemies at war, overlords or truce partners; one border
  grievance per raid (no recount next turn); a war between the pair citing
  the raid;
* tribute: agreed after repeated raids and citing them, paid each turn,
  sparing the payer; repudiated by a payer grown strong (citing the pact,
  with the raiders' treaty grievance);
* hordes: formation as a federation with allied members; a dominant nomad
  taking command of his federation (renamed, citing its formation, and
  dissolved when he dies) and an outranked one not; fragmentation on
  the khan's death (federation gone, heirs suspicious, stability and asabiya
  lost, citing the death and the horde, and a later secession citing the
  break); dissolution when the federation sheds its clans; conquest waves
  through the campaign WAR path (war declared, conquest aim, the bordering
  member riding along, citing the declarations); the conquest aim only
  against settled peoples;
* conquest and settling: conquests by herders recorded with their cause (and
  land settled peoples take not counted); a generation on farmland turning
  nomads agro-pastoral, citing the conquest, with asabiya lost; the settling
  clock running back on the steppe; nomads moving on from empty pasture;
* weights and reach: the bucket within its ceiling; EXPAND into desert and
  tundra;
* switch and persistence: dormancy and omitted fields, old saves, no nomad
  code while off, state round trip with a warm cache, determinism,
  save/load resume identity with live herds, raids and a standing horde (every byte
  of the resumed world after 15 more turns), switching on mid-history, the
  CLI flag, gate forwarding, bundle history, analytics and the report
  script, record pruning, the region flag reset by the turn with nothing
  transient left, and a native hybrid run repeating exactly.

`tests/test_wave3_combined.py` adds nomads with the ledger, epidemiology,
finance, diplomacy, techniques and maritime on one 32-region procedural
world: state round trip, save/load resume identity at the first turn from
30 on where every system is live (herds grazing after six raids and a nomad
conquest, fleets at sea after a naval battle, sea trade, epidemic deaths,
loans and treaties), and determinism.

## Results

| Check (Linux, Python 3.13, shared 4-core host) | Result |
| --- | --- |
| `pytest -m "not slow" -n 2` (extension built from this tree; compiled `AgentSimulator`, `EcologySimulator`, `PoliticsSimulator` verified) | 5,758 passed, 3 skipped (base `c5f4df4`: 5,707 passed, 3 skipped; +48 nomad and +3 combined tests) |
| No-Rust lane (fresh virtualenv without `chronicler_agents`, `pytest -q -n 2`, slow included, as CI runs it) | 5,560 passed, 201 skipped |
| `scripts/run_python_oracle_checks.py` (PR #19's guard line applied locally, not committed) | PASS: 1,768 passed, 8 skipped, 2 deselected; guard PASS, no native module loaded, no blocked I/O |
| `cargo test` | not run: no Rust change |

### Subset gate (20 seeds x 200 turns, hybrid, `--parallel 2`)

Base `c5f4df4` (exported tree, same extension) against this branch with
`--nomads`, compared with `chronicler.validation_compare`: **PASS** and
**NO REGRESSION**, **0 of 20 worlds extinct** on either side. The
regression oracle's `civ_survival` FAIL is the base's own (it is
informational in the subset profile) and is unchanged.

| Oracle / metric | Base `c5f4df4` | `--nomads` |
| --- | --- | --- |
| needs | PASS (17 seeds, effect 0.68) | PASS (16 seeds, effect 1.00) |
| cohort | PASS (20, effect 1.11) | PASS (20, effect 1.25) |
| arcs | PASS (14 seeds with three arc types) | PASS (14 seeds with three arc types) |
| artifacts | PASS (creation 2.01, loss 3.1%, 10 lost or destroyed) | PARTIAL (creation 2.09, loss 1.5%, 5 lost or destroyed) |
| community, era | PASS, PASS | PASS, PASS |
| regression | FAIL (civ_survival) | FAIL (civ_survival) |
| satisfaction / latest | 0.583 / 0.610 | 0.579 / 0.601 |
| migration / rebellion per agent-turn | 0.0586 / 0.0429 | 0.0598 / 0.0435 |
| Gini in range / occupation violations | 0.833 / 0.26% | 0.898 / 0.14% |
| all founders alive | 0.25 | 0.30 |
| final population min / median / max | 97 / 136 / 281 | 84 / 151 / 257 |
| extinct worlds | 0 of 20 | 0 of 20 |

12 of the 20 default template worlds have a pastoral people at some point
(13 founders seeded agro-pastoral or nomadic); the other 8 are
outcome-identical to the base. Over the batch: 20 raids got through and 12
were driven off, 1 tribute was agreed, 1 horde formed and fragmented on its
khan's death (seed 42), 2 regions were taken by herders, 5 peoples settled
and 5 dzuds struck.

**The artifacts PARTIAL.** The oracle needs at least 2% of artifacts lost
or destroyed; the switched-on batch lost 5 of 335 (1.5%). The difference is
seed 48 (4 losses in the base, 0 with nomads) and seed 51 (1 against 0).
Seed 48's only pastoral people is agro-pastoral; it never raided, took land
or joined a horde, so its world diverged from the base through its food and
its EXPAND reach, not through a nomad mechanism that spares or destroys
artifacts. The comparator does not count it as a regression; it is
reported here because the status changed.

### Supplementary seed sets (not the gate's; the same comparison)

Two further sets of 20 template seeds, base against `--nomads`, run to
see whether the gate's oracle movements are systematic:

| Seeds | Gate base / on | Comparator | Oracle changes (base -> on) |
| --- | --- | --- | --- |
| 62-81 | PASS / **FAIL** (needs) | **REGRESSION**: new required failure (needs) | needs 12 -> 11 seeds with the expected sign (12 required; median effect 0.44 -> 0.76); artifacts PASS both (loss 4.4% -> 2.6%); regression FAIL both (the base's own migration floor and civ_survival); 0 extinct both |
| 82-101 | PASS / PASS | NO REGRESSION | arcs PASS -> FAIL (cinderella arcs 41.2% of civs against a 40% dominance ceiling; base 40.0%; informational in the subset profile); needs 18 -> 17; artifacts PARTIAL both; regression PASS (strict) both; 0 extinct both |

Over the three sets (60 seeds) the needs oracle counts 47 seeds with the
expected sign in the base and 44 with nomads: 7 seeds lost it and 4 gained
it, all in worlds with herders (the others are identical). In every seed
that lost it the base's signal was on the material need and rested on one
to three matched agent pairs; I checked whether herd food had removed that
contrast, and it had not: every one of those pairs was on settled peoples'
farmland or coast, so the flips are divergence on a very small sample.
Cinderella arcs were a larger share with nomads in all three sets (29.3 ->
34.1%, 35.8 -> 38.8%, 40.0 -> 41.2%), artifact losses fewer in two of three
(10 -> 5, 14 -> 9, 5 -> 6), and all founders survived in more worlds in all
three (0.25 -> 0.30, 0.25 -> 0.30, 0.15 -> 0.20); these are small numbers
and are recorded, not explained. No world went extinct in any of the 120
gate runs.

### Procedural worlds with steppe (48 regions x 10 civs, 300 turns, seeds 7 / 13 / 29)

`scripts/nomads_report.py`, switch on against off (off is the base: see
identity). Nomadic and pastoral civs are the most alive at once; "got
through / driven off" are raids; hordes are formed / fragmented on the
khan's death / dissolved otherwise; horde wars are the wars a khan opened
plus the wars members rode to; conquests are regions herders took from other
polities.

| Run | Nomadic (pastoral) civs | Raids | Tributes | Hordes | Horde wars | Conquests | Settled | Dzuds | Herds mean / final | Polities alive on / off |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| off, seed 7 | 0 (2) | 22 / 2 | 3 | 0 / 0 / 0 | 0 + 0 | 8 | 1 | 7 | 139 / 151 | 11 / 9 |
| off, seed 13 | 2 (4) | 42 / 14 | 9 | 8 / 5 / 3 | 2 + 1 | 6 | 1 | 8 | 282 / 353 | 19 / 19 |
| off, seed 29 | 4 (4) | 55 / 1 | 15 | 4 / 4 / 0 | 3 + 1 | 7 | 1 | 10 | 164 / 124 | 19 / 18 |
| hybrid, seed 7 | 2 (3) | 16 / 5 | 1 | 0 / 0 / 0 | 0 + 0 | 0 | 0 | 8 | 158 / 203 | 15 / 8 |
| hybrid, seed 13 | 1 (3) | 19 / 4 | 3 | 2 / 1 / 1 | 3 + 3 | 5 | 3 | 16 | 365 / 87 | 19 / 12 |
| hybrid, seed 29 | 2 (3) | 2 / 0 | 0 | 2 / 1 / 1 | 0 + 0 | 0 | 1 | 11 | 209 / 159 | 8 / 12 |
| **mean** | 1.8 (3.2) | 26.0 / 4.3 | 5.2 | 2.7 / 1.8 / 0.8 | 1.3 + 0.8 | 4.3 | 1.2 | 10.0 | 220 / 180 | 15.2 / 13.0 |

All runs finished; no world went extinct (final population 431-1,387 on,
419-1,269 off). Seed 7 has no people that starts nomadic, only two
agro-pastoral ones (plains with some steppe); seed 29's nomads multiply by
secession (four nomadic polities at once). The hybrid seed 13 herds fall to
87 head by the end because two of its three pastoral peoples settled
(three sedentarizations).

Side effects in the same runs (on / off):

| Run | Wars declared | Battles | Expansions | Treasury per civ | Population | Stability | Famines | Plunder / tribute paid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| off, seed 7 | 94 / 76 | 201 / 190 | 4 / 4 | 330 / 194 | 1,024 / 923 | 50 / 43 | 353 / 349 | 337 / 246 |
| off, seed 13 | 157 / 138 | 353 / 281 | 13 / 10 | 452 / 360 | 1,387 / 1,269 | 51 / 45 | 712 / 650 | 371 / 803 |
| off, seed 29 | 159 / 165 | 268 / 262 | 15 / 16 | 496 / 354 | 687 / 688 | 38 / 39 | 576 / 622 | 855 / 738 |
| hybrid, seed 7 | 49 / 16 | 39 / 27 | 34 / 27 | 1,260 / 336 | 598 / 735 | 14 / 30 | 799 / 897 | 59 / 6 |
| hybrid, seed 13 | 92 / 55 | 87 / 43 | 31 / 26 | 666 / 467 | 431 / 419 | 14 / 15 | 1,035 / 888 | 165 / 48 |
| hybrid, seed 29 | 12 / 68 | 41 / 97 | 32 / 31 | 1,114 / 569 | 828 / 825 | 23 / 13 | 805 / 976 | 5 / 0 |

The on and off worlds diverge within the first turns (herd food, raids and
EXPAND's reach act at once), so single-run differences mix mechanism with
divergence. In four of six runs more wars were declared with nomads (raids
sour dispositions into the hostility WAR needs, hordes open wars, and a
horde's wars draw in the enemy's federation); treasury per living civ ended
higher in all six procedural runs, but not in the 20-seed gate (higher in 6
of the 12 seeds that changed, lower in 6), so it is not established.
Plunder and tribute are transfers.

### Stories

Event ids are the runs' own (`<turn>:<type>:<n>`); arrows follow recorded
causes.

**1. The Golden Horde of Elder Begerai** (procedural 48x10, seed 13,
`--agents off`). At turn 8 Elder Begerai of the Sojaki Tribes, nomads of
the Yogur Steppe, unites the clans: the Chakhani Empire swears allegiance to
the Golden Horde (`8:horde_formed:0`). Famine strikes the Yogur Steppe
(`9:famine:1`) and the horde raids Drovagrim Range of the Principality of
Dragremor (`11:raid:0` -> the famine and the horde) and twice the Qeduni
Empire's Jakhadun Downs (`12:raid:0`, `14:raid:0`). At turn 14 the Golden
Horde rides against Dragremor for Kexa Rainforest (`14:horde_rides:0` ->
`14:war_declared:0` -> `11:raid:0`); Qeduni joins in Dragremor's defence
(`14:federation_defense:0`) and the Sojaki go to war with it as well
(`14:war_declared:1` -> `14:raid:0`). Next turn the Chakhani Empire rides
with the horde against Qeduni (`15:horde_rides:0` -> its own declaration and
the khan's). The Sojaki First Warband besieges and takes Dragremor's
capital (`15:siege_begun:0`, `16:war:1`, `16:occupation:0`), ceded in the
Obsidian Truce (`17:annexation:0`, `17:peace_treaty:0`), while Qeduni's
Third Host takes Chumapa Wilds. At turn 19 Begerai dies after a 19-year
reign (`19:leader_death:0`) and the next turn the Golden Horde breaks apart
(`20:horde_fragmented:0` -> his death and the horde): the Chakhani Empire
and the Empire of Thamira (which had joined the horde's federation) go their
own ways, their bonds gone cold. The break runs on: the Empire of Thamira
loses its west at turn 24 (`24:secession:1` -> a rebellion, a war, a plague
and `20:horde_fragmented:0`) and the Chakhani Empire at turn 37
(`37:secession:0` -> famine, crisis, war, plague and the break).

**2. Tribute, default and refusal** (procedural 48x10, seed 29,
`--agents off`). Famine on the Yakhedun Steppe (`70:famine:2`) sends the
Jatain Clans against the Dijaki Kingdom's Khijak Grasslands twice
(`71:raid:0`, `72:raid:0` -> the famine); the kingdom agrees to pay 6 a year
to spare its borders (`72:tribute_agreed:0` -> both raids) and by turn 80
can no longer pay (`80:tribute_ended:0`). A dzud kills 18 head of the
Jatain herds around Khuyejak Prairie (`82:dzud:0`) and the riders come back
(`90:raid:0` -> the dzud and the lapsed tribute; `98:raid:0` -> a famine).
A second pact (`98:tribute_agreed:0`, 1 a year) lapses (`100:tribute_ended:0`)
and the next raid cites the lapse (`104:raid:0`); a third pact follows
(`104:tribute_agreed:0`). Meanwhile Patriarch Lendor of the Lower Diran
Republic, a nomadic breakaway of the Diran Republic, has taken command of
the federation Dijaki belongs to, which rides as the Blue Horde
(`93:horde_formed:0` -> the federation `74:federation_formed:0` and his
raids on the Northern Diran Republic, `78:raid:0` and `85:raid:0`, each
citing a famine). Lendor dies at 80 after 29 years (`107:leader_death:0`),
the Blue Horde breaks apart (`108:horde_fragmented:0`), and at turn 110 the
Dijaki Kingdom, grown strong, refuses further tribute
(`110:tribute_ended:0` -> the pact) and in the same turn loses its steppe
province, which secedes as the Free Dijaki Kingdom (`110:secession:0` -> a
revolt and `108:horde_fragmented:0`). The breakaway is seeded from its own
land at its first tick and is nomadic; from turn 209 it is the one raiding,
and at turn 247 the Dijaki Kingdom pays it tribute (`247:tribute_agreed:0`
-> `242:raid:0`, 30 in plunder, and `247:raid:0`).

**3. The Great Horde and the farms of Savowyn Weald** (procedural 48x10,
seed 13, `--agents hybrid`: real native agents). At turn 80 Regent Bitai of
the Sojaki Tribes, the strongest member of the Iron Confederation (with the
Principality of Dragremor and the Republic of Bemidar), takes command of it;
it rides as the Great Horde (`80:horde_formed:0` -> `10:federation_formed:0`).
At turn 96 the horde rides against the Peterioni League (`96:horde_rides:0`
-> `96:war_declared:10` -> a border incident); Peterioni's federation draws
the Dytilenen League and the Pomapan Kingdom in, so the Sojaki fight three
wars at once. Beaten at Mesiros Shores and besieged at home, they pay
Peterioni 20 in reparations (the Second Amber Truce, turn 100), but they take
Savowyn Weald, plains farmland, from Pomapan (`100:occupation:0`, ceded in
the Golden Understanding, `103:annexation:0`) and Dytilenen's capital
Thudridur Peaks (reparations of 14). Bitai dies "amid the turmoil" after a
25-year reign (`102:leader_death:0` -> `92:rebellion:0`, itself citing two
famines, a local rebellion and a plague), and the Great Horde breaks apart
(`103:horde_fragmented:0`). The farmland stays. A new khan, Sovereign
Medikhan, takes command of the Western Pact as the Red Horde
(`151:horde_formed:0`) and rides against Pomapan, Dytilenen and Linedori
(turns 154-155 and 183) until the clans' bonds cool and it melts away
(`184:horde_dissolved:0`); but at turn 155 the Sojaki, a generation and more
after taking Savowyn Weald, take to the plough (`155:sedentarization:0`,
nomadic -> agro-pastoral, -> `103:annexation:0` and `151:horde_formed:0`),
and at turn 249 they settle in towns and fields (`249:sedentarization:0`).
Their herds, 311 head at turn 200, are gone by turn 271, and within five
turns of settling famine, rebellion and plague split the settled realm three
ways (`251:secession:0`, `254:secession:0`).

## Effects on other systems

* **Food.** Herders' regions eat from their herds (the hybrid goods economy
  and the Python ecology's famine check) and harvest less grain. In the
  hybrid procedural runs famine reports fell in two of three runs; in the
  20-seed gate famines were fewer in 8 of the 12 changed seeds (143.6 against
  149.2 per world). With `--agents off` and the native ecology runtime the
  herd food does not reach the famine check (see "Cut").
* **War.** Raids lower dispositions (the raided one step, the raiders to
  suspicious), which is the hostility WAR needs; a war declared between a
  pair cites its latest raid. The weight bucket raises WAR for nomads and
  horde members facing a hostile settled neighbour; hordes open wars and
  members join them through the campaign WAR path, and their wars aim at
  conquest. A horde's war on a member of a federation brings that
  federation's defence in. Asabiya, high on the steppe, already raises
  campaign battle quality.
* **Diplomacy.** Raids add border grievances, repudiated tributes treaty
  grievances; diplomacy's treaties protect from raids. Hordes set their
  members allied and leave them suspicious when they break, so diplomacy's
  ceilings and drift take over from there.
* **Politics.** Hordes are federations: the federation dissolution rule
  sheds clans whose bonds cool, federation defense and intelligence sharing
  apply, the Rust federation step can append an allied neighbour. A horde
  formed inside a federation renames it. Fragmentation's stability shock
  feeds the existing secession and collapse checks, which cite the break.
* **Territory.** EXPAND reaches desert and tundra for herders in any era;
  nomads release empty pasture (rare: 0 times in the procedural runs, which
  is the honest size of that mechanism here).
* **Asabiya.** Raised on pasture held by nomads, eroded on farmland held by
  herders and cut by a tenth when a people settles and by 15% at
  fragmentation. Civ-level asabiya saturates near 1.0 in these worlds, with
  or without nomads (0.93-0.99 at the end of every procedural run), so the
  horde's asabiya gate (0.55) rarely binds.
* **Treasury and finance.** Plunder and tribute are keep-category transfers
  (plunder 5-855 and tribute 0-803 per procedural run); with `--finance` on
  they move through the same treasuries debt service reads.
* **Population.** Raids kill (2% of the raided region, through the campaign
  layer's population drain; native deaths in agent modes).
* **Provenance.** New event types `raid`, `raid_repulsed`, `tribute_agreed`,
  `tribute_ended`, `horde_formed`, `horde_rides`, `horde_fragmented`,
  `horde_dissolved`, `sedentarization`, `dzud`, `pasture_drought`,
  `pasture_abandoned`; keys `raid:<pair>`, `horde:<civ>`,
  `fragmented:<civ>`, `herd_loss:<civ>`, `settled:<civ>`. In the procedural
  runs 78% of raids cite a cause (mostly a famine, a herd loss or a lapsed
  tribute); every tribute, ride, fragmentation and dissolution does, 13 of 16
  hordes and 6 of 7 sedentarizations.
* **Performance.** A nomad tick costs about 2 ms a turn on a 150-region,
  30-civ world (0.13 s over 60 turns `--agents off`, 0.11 s hybrid; whole
  runs 17 s either way); the food hook about 3 microseconds a call.

## Known gaps

* The full 200-seed gate has not been run with `--nomads`.
* In the supplementary seed set 62-81 the needs oracle fails with the switch
  on (see above). It is a seed-count oracle on a handful of agent pairs per
  seed and its base sat exactly at the threshold; a default change would need
  the full gate.
* Off-mode herd food with the native ecology runtime (see "Cut").
* Template worlds have few herders (13 of 80 founders in the gate) and
  rarely two side by side, so hordes are procedural-world events.
* Civ asabiya saturates near 1.0 in these worlds, so Ibn Khaldun's
  mechanism shows through fragmentation shocks and settling rather than
  through a slow asabiya decline.
* Nomads seldom release land (the loose-hold rule fired 0 times in the
  procedural runs).
* No viewer panels.
