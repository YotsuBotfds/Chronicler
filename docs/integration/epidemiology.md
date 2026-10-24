# Epidemiology: one regional disease model

Branch `feat/epidemiology`, based on `integrate/wave-2` at `db26681` (the
extinction fix, the contact ledger, Geography 2.0, causal provenance,
campaigns, governance, and the fisheries/mutual-aid promotion). Code:
`src/chronicler/epidemiology.py`; hooks in `simulation.py`, `emergence.py`,
`provenance.py`, `governance_runtime.py`, `main.py`, `live.py`.

Status: implemented behind `WorldState.epidemics` (CLI `--epidemiology` /
`--no-epidemiology`, saved on the world). **Default off** for new worlds; see
[Default](#default). With the switch off no epidemiology code runs and every
output is byte-identical to `db26681`.

## Why

Disease had two unrelated paths:

* the hazard-rolled **`plague`** event (Phase 1, `phase_environment`): a
  per-civ decaying hazard drew a civ, which lost a fixed toll
  (`min(10, 10% of its people) x severity`, the extinction-fix cap), 3
  stability and gained a 4-turn `plague` condition. Plague also
  cross-excited the plague hazard of civs in contact
  (`events.PLAGUE_CONTACT_ALPHA`). No region, no immunity, no pathogen.
* the M18 **black-swan pandemic** (`emergence.tick_pandemic`): a timer per
  region spread along adjacency or contact-ledger edges, charging every
  infected civ `min(3 x severity, 12) x severity-multiplier` people per turn.
  In agent modes this was a direct region mutation that was **never staged
  for the agent pool**, so in hybrid runs the Rust write-back restored the
  region populations: the M18 pandemic's deaths never reached the agents
  (in the base subset gate, 20.6 nominal deaths per run, all erased). This
  is unchanged with the switch off.

The replacement is one model in which pathogens circulate in regional
populations, spread along the contact ledger's real flows, meet immunity, and
kill people through the same death path the plague used.

## Model

### Pathogens

`PATHOGENS` (index is identity; append, never reorder). Rates are per
season; a turn has `SUBSTEPS = 4` seasons.

| Pathogen | Label | R0 | onset (E->I) | recovery | CFR | immunity (turns) | mutation / escape | spillover / turn | Homelands |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `plague` | the plague | 2.4 | 0.7 | 0.85 | 0.10 | 30 | - | 0.004 | M35b `plague` vector regions |
| `pox` | the pox | 3.0 | 0.6 | 0.8 | 0.08 | lifelong | - | 0.0025 | the more populous half of the land |
| `fever` | the marsh fever | 1.9 | 0.9 | 0.9 | 0.02 | 12 | 0.03 / 0.6 | 0.006 | M35b `fever` (wet fertile) regions |
| `flux` | the bloody flux | 1.8 | 0.9 | 0.9 | 0.04 | 8 | - | 0.007 | M35b `cholera` (desert) regions |
| `pestilence` | the great pestilence | 3.0 | 0.7 | 0.8 | 0.18 | 40 | - | none | black swan only |

### State (`WorldState.epidemics: EpidemicState | None`)

* `rows`: one `RegionInfection` per (region index, pathogen index) that has
  infection or immunity: `n` (population the shares describe), the
  **S/E/I/R shares** (sum 1, rounded to 1e-9), last tick's `burden` (mean
  infectious share, what a region exports) and `cases` (new infections, in
  people), plus the open outbreak's `virgin`/`reported` flags, the event its
  onset cites and a pending contact import (`source`, `channel`).
* `homelands` and `seen`: (region, pathogen) reservoirs, and populations that
  have had an epidemic of the pathogen.
* `strains`, `quarantine` (civ indices), `scarcity` ((civ index, share)),
  `last_deaths` ((region, pathogen, deaths) of the last tick), `deaths_total`.

Region identity is the index in `world.regions`, civ identity the index in
`world.civilizations`; nothing new is identified by name.

### One tick (Phase 1, right after the environment hazards)

1. **Demography.** Population change since the last tick: newcomers (births,
   immigrants) are susceptible; losses leave the shares unchanged.
2. **Introductions** (the only randomness; for each pathogen and each
   populated region where it is not circulating, one spillover draw in a
   homeland, otherwise one import draw when contact pressure exists):
   * *spillover* in a homeland: hazard `spillover x susceptibility x
     min(3, endemic_severity / disease_baseline)`, so M35b disease flares
     (crowding, armies, bad water, season) make spillover likelier;
   * *imports* along the contact ledger: hazard `0.1 x R0 x susceptibility x
     S x sum_j contact(j, r) x burden_j`, where `contact` is
     `contact_ledger.region_contact` (decayed trade, migrant, soldier and
     pilgrim stock, both directions) and `burden_j` the source's infectious
     share last turn. A quarantined state stops 70% of the pressure coming
     from regions of other polities.
   Each introduction exposes one person.
3. **Within-region SEIRS**, four seasons, no randomness:
   `new_E = S (1 - exp(-beta I))` with `beta = R0 x recovery x susceptibility`,
   `new_I = onset E`, `leave = recovery I`, `dead = CFR_eff leave`,
   `wane = (1 - exp(-1 / (4 x immunity))) R`.
4. **Deaths.** Expected deaths per row become integers (floor plus one hash
   draw on the fraction), bounded at 25% of a region per turn (deaths above it
   recover instead). They leave through the plague's death path:
   `utils.drain_region_pop` on the region, `utils.stage_region_catastrophe_deaths`
   when `simulation._agent_pool_tracks_population` (demographics-only, shadow,
   hybrid), and `sync_civ_population`. In hybrid mode the next
   `build_region_batch` hands the staged deaths to the Rust tick
   (`collect_catastrophe_deaths` kills that many agents of the region) and
   clears the transient.
5. **Extinction.** An outbreak with fewer than half an exposed+infectious
   person ends (they join R). Rows with no infection and under 1e-4 immunity
   are dropped.
6. **Reports.** An outbreak whose new infections reach `max(2, 3% of the
   region)` reports an `epidemic` event (region, `shock_category` = pathogen).
7. **Mutation.** A circulating pathogen with `mutation > 0` may produce a new
   strain (`pathogen_mutation`): `escape` of everyone's immunity to it is lost.
8. **Civ responses** (below), then **quarantine decisions** for next turn.

### Susceptibility, severity and first contact

* Famine (`famine_cooldown > 0`): susceptibility +0.2 and CFR x1.25.
  Crowding: susceptibility `+0.5 x clamp(pop / carrying_capacity - 0.8, 0, 1)`.
  Both are read only; nothing in ecology or the economy is changed.
* **Virgin soil.** A population that never had an epidemic of the pathogen
  (`seen`) has no immunity, so its attack rate is the full SEIR final size,
  and its fatality is x1.5 for that first outbreak. Homelands start with half
  their people immune, so the same pathogen is mild where it lives and
  devastating where contact first carries it. When an outbreak subsides the
  population is `seen`; a later flare-up is a return, not an arrival.
* A black-swan pandemic (`emergence._apply_pandemic_origin`, same eligibility,
  origin choice and RNG) seeds a **new strain of the great pestilence** at the
  origin instead of an M18 timer: nobody is immune and no population has met
  it, so it is virgin soil everywhere.
* An injected plague (`apply_injected_event`) seeds the plague in the civ's
  capital (5% exposed) and keeps the old immediate effects (3 stability, the
  `plague` condition) but no fixed toll.

### Civ responses and second-order effects

* **Civ outbreak.** When a civ has a reported epidemic whose effective CFR is
  at least 8% (plague, pox, pestilence, or a famine-struck or virgin-soil
  flux) and no `plague` condition, it suffers what the hazard plague did: a
  `plague` event (`signal` stability `-3 x severity multiplier`), an
  `ActiveCondition("plague")` (refreshed to 2 turns while the epidemic runs;
  the existing ongoing drain, hardship and great-person rules read it) and
  the event joins the hazard cascade (`record_hazard_event`: rebellion,
  migration and leader-death excitation). Mild fever and flux epidemics kill
  people but do not register as a state crisis.
* **Leader deaths.** A ruler whose capital lost a share `d` of its people this
  turn dies with probability `min(0.5, d)` through the ordinary leader-death
  path (`_apply_event_effects("leader_death")`: legacy, rival fall,
  succession crisis or successor), as a `leader_death` event "dies of the
  plague".
* **Quarantine.** A state with stability >= 30 and treasury >= 2, in ledger
  contact with a region of another polity that has a reported epidemic,
  closes its borders for the next turn: 70% of foreign import pressure on its
  regions is stopped, and it pays 2 treasury per turn (`keep`).
* **Labour scarcity.** Each civ keeps the share of its people killed by
  epidemics, decayed x0.9 per turn. Governance divides popular immiseration
  (`mmp_raw`, proportional to 1 / relative wage) by `1 + 5 x scarcity`: after
  a plague that killed 10%, MMP falls by a third and relaxes with a
  half-life of about 7 turns.
* **Stress.** `compute_civ_stress` counts epidemic regions like M18 pandemic
  regions.

Cut on purpose (no cheap, real version): trade embargoes or route closures
from quarantine (the treasury cost stands in for lost commerce), agent wages
in Rust (only the governance MMP reads scarcity), per-agent infection state,
and any change to the endemic M35b layer in `ecology.py` (for example its
"no flare during an M18 pandemic" mask, which does not see epidemics), left
alone while the food-balance work owns that module.

## Determinism and contracts

* Draws: `stable_hash_int` streams `epidemic_spillover`, `epidemic_import`,
  `epidemic_deaths`, `epidemic_mutation`, `epidemic_leader`, each keyed by
  world seed, turn and region/pathogen/civ index. No global `random`, no
  shared stream, so no draw-order coupling. Homelands use
  `epidemic_homeland` (seed, pathogen, region).
* Accumulator: the outbreak stability hit is `signal` (as the plague);
  quarantine treasury is `keep`. Population deaths are direct mutation plus
  the existing cleared-per-turn catastrophe transient, as the plague.
* With the switch off: `phase_environment` still rolls the hazard plague,
  `tick_pandemic` still runs, and every hook is a guarded no-op.

## Provenance

Epidemics are chronic episodes (`provenance.CHRONIC["epidemic"]`, keyed by
region and pathogen; `quarantine` likewise per closed state):

* `epidemic` onset (one kept report per outbreak; repeats fold) and an
  automatic `epidemic_ended` with its duration;
* `epidemic_arrival`, emitted with the onset of an imported outbreak: "Migrants
  from Verdant Plains carry the bloody flux to Frostholm Tundra, a land that
  has never known it." It names the ledger channel that carried most of the
  pressure and cites the source region's outbreak that was exporting when the
  pathogen crossed (its open episode at import; nothing for a quiet
  reservoir or an unreported smoulder); the onset cites the arrival;
* an onset also cites the pandemic event (black swan), the injection, the
  region's previous outbreak (a return) and the open famine when famine raised
  susceptibility;
* civ `plague`, disease `leader_death`, `quarantine` and `pathogen_mutation`
  cite the epidemic onset they respond to.

`_register` stores an onset under `epidemic:<region>|<pathogen>` and
`pandemic:<region>`, so the existing famine and flight rules cite epidemics,
and the `plague` civ key feeds the rebellion/secession/collapse distress
rule.

## Switch, defaults, persistence

| Surface | Value |
| --- | --- |
| CLI | `--epidemiology` / `--no-epidemiology` (`BooleanOptionalAction`) |
| World field | `WorldState.epidemics: EpidemicState \| None` (presence = on) |
| Default | **off** (`epidemiology.DEFAULT_ENABLED_FOR_NEW_WORLDS = False`); resumed, forked and caller-supplied worlds keep their own setting |
| Ledger | an explicit `--epidemiology` needs the contact ledger (`ValueError` otherwise); a default-on setting would stay off on a ledger-less new world |
| Live server | new live worlds follow the CLI default |
| Gate runner | `scripts/m53b_run_validation.py --epidemiology` forwards the switch |
| Frozen oracles | `scripts/benchmark_headless.run` pins `epidemiology=False` |

`None` is omitted from `state.json` and the bundle's `world_state`, and
`TurnSnapshot.epidemics` is omitted while `None`, so old saves and bundles load
with the feature off and feature-off outputs keep their bytes.

Viewer bundle (only with the switch on): `history[n].epidemics` (`active`
outbreaks with prevalence, immunity, cases, deaths and virgin flag; `deaths`,
`deaths_by_pathogen`, `deaths_total`, `quarantine`, `strains`), and epidemic
regions are listed in the existing `pandemic_regions`. `analytics.generate_report`
adds an `epidemiology` section (`extract_epidemic_metrics`).

## Evidence

### Feature-off identity

1. **Direct runs.** The base export (`db26681`, selected with `PYTHONPATH`)
   against this branch with the default and with an explicit
   `--no-epidemiology`, same virtualenv and native build,
   `PYTHONHASHSEED=0`: `--agents off` 150 turns and `--agents hybrid` 120
   turns for seeds 42 and 7. `scripts/epidemiology_identity.py compare`:
   every output file (`state.json`, `chronicle.md`, `memories_*.json`,
   `agent_events.arrow`, `chronicle_bundle.json` minus
   `metadata.generated_at`) is byte-identical, 0 differences in all 8
   comparisons, rerun on the final head.
2. **Gate batch.** The base subset gate against this branch's default
   (switch off) subset gate, 20 seeds x 200 hybrid turns: 2,161 run files
   (states, bundles, agent-event and validation sidecars, memories,
   chronicles) identical; the validation report, gate decision and gate
   summary are identical apart from their batch path.
3. **In the suite.** The frozen exact-trajectory oracles
   (`test_performance_equivalence`, `test_governance_dormancy`,
   `test_turn_artifact_lifecycle`) pass unchanged; no fixture in
   `tests/fixtures/performance/` changed. `test_feature_off_never_runs_epidemiology_code`
   forbids every entry point while a 60-turn run still rolls the hazard plague.

### Tests

`tests/test_epidemiology.py` (25 tests, plus 2 slow): registry identity;
SEIRS recursion conservation (each season moves or kills people; final size
and deaths match SEIR at R0 2.4); famine and crowding modifiers; whole-run
share conservation and death accounting; determinism; **save/load in the
middle of an epidemic continues identically**; the dormant switch and old
saves; the switch replacing the hazard plague, the M18 pandemic (novel
pestilence strain, no `pandemic_state`) and injected plague; CLI, bundle and
analytics; new-world default, resume and the ledger requirement; gate-runner
forwarding; homelands; **first contact** (an import along a migrant edge
into a never-exposed region: virgin-soil arrival, onset citing it, larger
attack than the immune source, x1.5 fatality, no epidemic without contact);
virgin soil killing more for the same attack; imports needing and scaling
with contact; deaths through the plague death path with a civ outbreak
(stability `signal`, condition, hazard cascade, labour scarcity); the
per-turn mortality bound; labour scarcity easing the governance MMP;
quarantine (closure, cost, cause, reopening, imports cut); strain escape;
resolvable provenance chains; and, native, **hybrid epidemic deaths killing
agents** of the region (with the catastrophe transient cleared and carrying
only the current tick's deaths on the next turn) and hybrid determinism.
Slow: 6 seeds x 200 turns survive with epidemics, off and hybrid.

`pytest -m "not slow" -n 2`: base `db26681` 5,497 passed, 3 skipped (no
failure: `test_contact_ledger::test_save_load_round_trip_continues_identically`
passes); this branch 5,522 passed, 3 skipped. Slow epidemiology and hazard
tests: 4 passed. The guarded offline lane (`run_python_oracle_checks.py`
selection, run without `-x`) gives the same result on base and branch on
this Linux machine: 1,568 passed, 3 skipped, 28 failed, all in
`test_checkpoint_replay.py`, where the guard blocks the `uname -p`
subprocess behind `platform.processor()` (pre-existing, not addressed here).
Viewer and Rust are untouched; the native extension was built fresh from
this tree (`maturin develop --release`) and its compiled
`AgentSimulator`/`EcologySimulator`/`PoliticsSimulator` classes verified.

### Subset gate (20 seeds x 200 turns, hybrid, `--parallel 2`)

Base `db26681` (default features) against this branch with `--epidemiology`
(final head; a rerun after the last outcome-neutral commit produced an
identical report). Both gates **PASS**; `validation_compare`: **NO
REGRESSION**.

| Oracle / metric | Base | Epidemiology on |
| --- | --- | --- |
| regression (informational) | FAIL: `civ_full_survival_fraction` 0.25 > 0.20 | FAIL: same, 0.25 |
| satisfaction mean / latest | 0.4813 / 0.4544 | 0.4905 / 0.4594 |
| migration rate (strict 0.05, calibrated 0.045) | 0.0505 | 0.0484 |
| rebellion rate | 0.0513 | 0.0493 |
| Gini in range | 0.967 | 1.000 |
| occupation violations | 0.11% | 0.16% |
| extinct worlds / zero-survival worlds | 0 / 0 | 0 / 0 |
| all-initial-civ survival | 0.25 | 0.25 |
| arcs | PASS (cinderella 27 of 80) | PASS (29 of 80) |
| artifacts (informational) | PARTIAL, loss 0.46% | PARTIAL, loss 1.18% |
| cohort, community, era, needs | PASS | PASS |

### Disease before and after (per run, same 20 runs)

Base deaths come from an in-process census of the base runs
(`epidemiology_stats.py census`; its `state.json` files are byte-identical
to the gate's).

| Per run | Base (hazard plague + M18) | Epidemiology |
| --- | --- | --- |
| civ disease strikes (`plague` events) | 16.0 | 16.4 civ outbreaks |
| regional epidemics (episodes) | n/a | 70.4 (fever 27.5, plague 17.8, flux 12.7, pox 11.8, pestilence 0.7) |
| deaths applied to the population | 72.1 (hazard plague toll) | 158.8 (plague 73.1, pox 33.8, flux 22.6, fever 21.8, pestilence 7.5) |
| M18 pandemic toll | 20.6 nominal, never reached the agents | none (the pandemic is a pestilence strain) |
| black-swan pandemics | 0.1 | 0.1 |
| peak prevalence (mean of per-run maxima, infectious share) | n/a | 0.158 |
| regions with an epidemic (of 8) | 0.7 (M18 pandemic regions) | 6.55 |
| contact arrivals / virgin-soil arrivals | n/a | 52.9 / 16.0 |
| border closures / closed civ-turns | n/a | 19.7 / 80.7 |
| new strains | n/a | 1.55 |
| rulers dead of disease | 0.15 (M18) | 3.35 |
| final population (mean; min over runs) | 393.1; 171 | 351.9; 135 |

Long run, outside the gate (the calibration harness: the same template
worlds and default features, in process, 40 seeds x 500 hybrid turns):
disease deaths 292 per run in base (applied plague toll plus nominal M18
toll) and 370 with epidemiology; mean population 341 / 364 / 391 / 406 /
433 / 435 (turns 50 to 500, every 100) in base against 310 / 337 / 371 / 409
/ 434 / 431; minimum final population 249 against 251; no extinct world in
either; all-initial-civ survival 0.28 against 0.25. The deficit is front
loaded: early epidemics meet populations with no immunity.

### Outbreak stories (seed 42, hybrid, `--epidemiology`, recorded chains)

1. **War, famine, fever, first contact.** t0 the Ashkari Nomads go to war
   with the Thornwall Confederacy and occupy Thornwood -> t3 food shortage in
   Thornwood -> t28 famine -> t31 *the marsh fever breaks out in Thornwood*
   (famine raised susceptibility) -> the Ashkari Nomads and the Kethani
   Empire close their borders -> t33 *migrants from Thornwood carry the marsh
   fever to Verdant Plains, a land that has never known it*, t34 to Iron
   Peaks likewise -> virgin-soil epidemics in both -> t35 the Thornwood
   epidemic ends after 4 turns; it returns at t37 alongside the pox. The
   fever later mutates (strains 1 and 2 at t50 and t52 in Verdant Plains).
2. **Flood, famine, pox across three polities.** t161 flooding devastates
   Obsidian Shore -> t164 famine -> t166 *the pox breaks out in Obsidian
   Shore* -> the pox spreads through the Ashkari Nomads (civ outbreak); the
   Kethani Empire and the Thornwall Confederacy close their borders -> t168
   *migrants carry the pox to Thornwood* -> it spreads through the Thornwall
   Confederacy -> t169 Iron Peaks and Verdant Plains -> t171 Frostholm
   Tundra, *a land that has never known it* -> the pox spreads through the
   Kethani Empire.
3. **The plague reaches the mountains.** t108 *migrants from Amber Valley
   carry the plague to Iron Peaks, a land that has never known it* -> the
   plague spreads through the Thornwall Confederacy; the Ashkari Nomads and
   the Kethani Empire close their borders -> t109-110 it jumps to Verdant
   Plains, and to Obsidian Shore and Thornwood, both virgin soil -> the
   plague spreads through the Ashkari Nomads -> t116 Chieftain Camelorn of
   the Thornwall Confederacy dies amid the turmoil (the plague's leader-death
   excitation). Iron Peaks then catches the bloody flux (t121), and t122
   Chieftain Borte of the Thornwall Confederacy dies of it.

## Calibration

`[CALIBRATE]` values were set with a harness of 20 template worlds x 200
turns (default features; base: 16 civ strikes per hybrid run). The first
draft gave 68 civ outbreaks per `--agents off` run (base 17) and, after a
first cut, still 26 outbreaks and 3.6x the base deaths per hybrid run with
populations near half of base by turn 100. The changes that brought it to
16 outbreaks and about twice the deaths:
mild fever and flux epidemics no longer count as a state crisis
(`MAJOR_CFR`), the endemic-severity spillover factor is capped at 3 (M35b
severity flares to 15x its baseline), contact imports scaled down
(`IMPORT_SCALE` 0.25 -> 0.1), lower spillover rates, longer fever and flux
immunity, and lower fatality (plague 0.16 -> 0.10, famine fatality x1.5 ->
x1.25). A second seed set (62-81, harness) gives 158 disease deaths against 129 in
base, with mean population 0.5-11% below base at turns 50 to 200.

## Default

Off. The subset gate passes with no regression and the long-run harness
loses no world, but the switch is a deliberate, front-loaded mortality
change for every new world: disease kills about twice the old capped toll
in 200 turns (159 against 72 applied deaths per run) and mean final
population falls 10% (393 to 352; the 500-turn harness converges). That
calls for the documented 200-seed x 500-turn full gate on this base before
a flip, and the famine and crowding inputs that drive susceptibility and
fatality are being rebalanced by the concurrent food-balance work, so a
calibration now would be against food dynamics that are about to move.
Flip `DEFAULT_ENABLED_FOR_NEW_WORLDS` in its own commit after that work
lands and the full gate passes with 0 extinct worlds.

## Follow-ups

* Calibrate against the 200-seed full profile before any default flip.
* Per-pathogen viewer layer (the bundle already carries the data). Panels
  and a region-inspector block are since added on `feat/viewer-systems`
  ([viewer-systems.md](viewer-systems.md)); a map layer is not.
* Quarantine could close goods routes and suspend merchant trips.
* Disease-specific treatment by great persons (the M18 scientist rule is not
  carried over).
