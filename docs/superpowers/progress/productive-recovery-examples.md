# Productive recovery, checkpoint 1: success and failure examples (PL6b)

Two kinds of example are recorded here, and the labels mean exactly this:

- **Constructed** examples are unit or native tests that build the situation on
  purpose. They show the mechanism behaves as declared, not that it happens in real
  worlds.
- **Natural** examples come from ordinary runs of development worlds (never a held
  seed). Each names the command that writes the run and the snapshot turn of the
  instance. `scripts/productive_recovery_examples.py` finds them.

The packages are the checkpoint-1 set: PL1 timber supply
([timber-supply.md](../../integration/timber-supply.md)), PL2 `--operating-wear` and RS1
rules version 2 ([operating-wear.md](../../integration/operating-wear.md),
[apprenticeship.md](../../integration/apprenticeship.md#rs1-rules-version-2-pl2)), PL3
recovery crews and the maintenance obligation
([recovery-crews.md](../../integration/recovery-crews.md),
[maintenance-obligation.md](../../integration/maintenance-obligation.md)) and RS2's
`no_people` correction ([repair-projects.md](../../integration/repair-projects.md)).

The source is the phase branch `claude/productive-recovery` at `de9a5699`. This lane's
branch changes no simulation or Rust file. The native extension is `fdcb0ca0…` in
`~/.venvs/native-pl1` (Python 3.13, Linux), built from the Rust of `7c16e9ce`, which
matches the branch's Rust.

## Constructed (reproduce with `pytest <test>`)

Every node id on this page passed on 2026-11-06 on this source:

- the offline ones (36 ids, 0.7 s) with the project environment's `python -m pytest`;
- the native ones (`*_native.py`) with `~/.venvs/native-pl1/bin/python -m pytest` on the
  real extension. The 6 named here ran with
  `tests/test_apprenticeship_v2_native.py::test_the_extension_is_the_compiled_build_with_the_v2_seams`,
  which checks the compiled extension (7 ids, 16.4 s).

| Package | Success | Failure |
| --- | --- | --- |
| PL1 timber supply | `tests/test_timber_supply.py::test_full_schedule_carries_decays_and_feeds_rs2_from_the_store_first` (delivery into the store, then RS2 holds 4.0 from it), `::test_a_partly_lost_crew_goes_on_and_delivers`; native `tests/test_timber_supply_native.py::test_expeditions_cut_carry_deliver_and_feed_rs2_with_closed_books`, `::test_constructed_uninhabited_forest_is_debited_exactly_by_the_crew` | `tests/test_timber_supply.py::test_refusals[no_forest-no_forest]`, `[other_civ-no_forest]`, `[unreachable-no_forest]`, `[too_far-too_far]`, `[depleted-forest_depleted]`; `::test_a_crew_that_dies_out_deposits_its_cargo_at_the_forest[cutting-4-16.0]`, `[returning-6-24.0]`; `::test_an_unpayable_turn_recalls_the_crew_home_with_its_cargo`, `::test_a_recall_on_the_way_out_turns_back_and_one_at_a_home_forest_arrives_at_once` |
| PL2 RS1 rules version 2 | `tests/test_apprenticeship_v2.py::test_completion_grants_in_train_only_and_graduates_keep_the_site` (graduates on the crew; the trained ones offset 0.01 of the wear, the control's none) | `::test_a_migrant_continues_at_the_site_of_the_new_region` (ends `long_absence`), `::test_site_closure_pauses_until_a_transfer_or_a_long_absence`, `::test_long_pauses_end_as_stalled_and_free_the_place`, `::test_on_the_job_counts_only_with_a_qualified_member_aboard_and_a_missed_turn_pauses` (`no_mentor` while no qualified member is aboard) |
| PL2 control (`no_qualification`) | `::test_completion_grants_in_train_only_and_graduates_keep_the_site` (both modes), `::test_the_control_never_takes_its_graduates_on_again_and_costs_match_train` | |
| PL2 operating wear | | `tests/test_operating_wear.py::test_the_switch_alone_wears_every_funded_operating_site_and_nothing_else` (worn with no qualified member, below the floor, then the L1 lump); native `tests/test_apprenticeship_v2_native.py::test_w_wear_against_w_operate_shows_the_wear` |
| PL3 recovery crews | `tests/test_recovery_crews.py::test_granary_crew_is_named_reserved_withheld_and_paid_the_granary_coins`, `::test_crew_covers_the_planned_work_with_urban_farm_shares`, `::test_veteran_priority_on_a_granary_crew_and_the_placement_is_noted`, `::test_the_workshop_pool_widens_to_the_region_and_admits_veterans_first`, `tests/test_repair_projects.py::test_qualified_people_and_veterans_come_first_and_veterans_are_noted`; native `tests/test_recovery_crews_native.py::test_paid_granary_wages_reach_named_people_once_and_the_books_close` | `tests/test_recovery_crews.py::test_a_remainder_below_min_share_is_covered_not_a_labour_shortage` (its second half: three free farmers for four planned work, `short` and `no_labor`), `::test_no_free_adult_farmer_stalls_the_granary_without_holding_timber_or_coins`, `tests/test_repair_projects.py::test_stalls_record_their_reasons` (`no_labor`) |
| PL3 maintenance obligation | `tests/test_maintenance_obligation.py::test_reserve_spends_reservation_and_envelope_and_the_envelope_settles_its_part`, `::test_a_reservation_without_an_envelope_funds_repairs_alone`; native `tests/test_recovery_crews_native.py::test_maintenance_reservations_close_and_split_on_the_real_extension` | `::test_reserve_only_is_held_to_its_envelope_and_returns_the_reservation` (all 5 returned), `::test_a_shortfall_falls_on_reservation_and_envelope_pro_rata` (4 of 5 returned) |
| RS2 `no_people` correction | | `tests/test_recovery_crews.py::test_an_open_granary_project_is_suspended_without_farm_labour_and_resumes`, `::test_suspension_and_resumption_survive_a_turn_without_a_settled_phase2`, `::test_no_granary_project_opens_in_a_region_without_farm_labour` (unmet `no_people`); `tests/test_timber_supply.py::test_a_suspended_no_people_granary_adds_no_need`; `tests/test_maintenance_obligation.py::test_a_suspended_granary_reserves_nothing` |

Three kinds have **no constructed test**:

- **A granary project that completes after a delivery (PL1).** The nearest test is the
  reverse case, `tests/test_timber_supply.py::test_the_asset_completing_mid_expedition_releases_the_delivery`:
  the project completes before the delivery, so the store is released.
- **An apprentice who transferred and then completed (PL2).** The transfer test keeps
  progress but ends in `long_absence`. The native
  `tests/test_apprenticeship_v2_native.py::test_v2_apprentices_living_outside_the_city_attend_and_complete`
  asserts completions and transfers in one run, but not for the same person.
- **A site worn by operation into an RS2 workshop project (operating wear with RS2).**
  The RS2 workshop tests set a low condition directly.

## Natural

The worlds are development worlds, never held seeds: template seed 23 and procedural
32×10 seed 7. Each run is 200 turns.

| Run | World | Switches |
| --- | --- | --- |
| T23 | template 23 | every checkpoint-1 switch |
| P7 | procedural 7 | every checkpoint-1 switch |
| T23-NQ | template 23 | every switch with `--apprenticeship-mode no_qualification` (the PL2 control) |
| T23-W, P7-W | template 23, procedural 7 | `--workshops --apprenticeship --operating-wear` without RS2, so the L1 lump can be billed (below) |

T23 rerun from scratch wrote a byte-identical `state.json` (SHA-256 `d4ed63d9…`) and
identical finder output.

To reproduce (from the repository root; `OUT` is any directory):

```sh
# T23: every checkpoint-1 switch
PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 PYTHONPATH=src ~/.venvs/native-pl1/bin/python -m chronicler.main \
  --seed 23 --turns 200 --agents hybrid --simulate-only --grain-reserves --public-grain-shipments \
  --scholarship --techniques --academy-services --grain-storage --workshops --apprenticeship \
  --operating-wear --repair-projects --timber-stock --timber-supply --veteran-reintegration \
  --recovery-crews --local-budgets --maintenance-obligation \
  --output OUT/chronicle.md --state OUT/state.json

# P7: every checkpoint-1 switch, procedural 32x10
PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 PYTHONPATH=src ~/.venvs/native-pl1/bin/python -m chronicler.main \
  --seed 7 --turns 200 --agents hybrid --simulate-only --grain-reserves --public-grain-shipments \
  --scholarship --techniques --academy-services --grain-storage --workshops --apprenticeship \
  --operating-wear --repair-projects --timber-stock --timber-supply --veteran-reintegration \
  --recovery-crews --local-budgets --maintenance-obligation \
  --worldgen procedural --regions 32 --civs 10 --output OUT/chronicle.md --state OUT/state.json

# T23-NQ: the PL2 control
PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 PYTHONPATH=src ~/.venvs/native-pl1/bin/python -m chronicler.main \
  --seed 23 --turns 200 --agents hybrid --simulate-only --grain-reserves --public-grain-shipments \
  --scholarship --techniques --academy-services --grain-storage --workshops --apprenticeship \
  --operating-wear --repair-projects --timber-stock --timber-supply --veteran-reintegration \
  --recovery-crews --local-budgets --maintenance-obligation --apprenticeship-mode no_qualification \
  --output OUT/chronicle.md --state OUT/state.json

# T23-W (and P7-W with --seed 7 --worldgen procedural --regions 32 --civs 10)
PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 PYTHONPATH=src ~/.venvs/native-pl1/bin/python -m chronicler.main \
  --seed 23 --turns 200 --agents hybrid --simulate-only --grain-reserves --public-grain-shipments \
  --scholarship --techniques --academy-services --grain-storage --workshops --apprenticeship \
  --operating-wear --output OUT/chronicle.md --state OUT/state.json

python scripts/productive_recovery_examples.py OUT/chronicle_bundle.json
```

The snapshot is the viewer's turn. Each record is dated one turn earlier, at its
completed turn. Ids are native stable ids (people), region and civ indices, expedition
`eid`, RS2 project `pid` and L1 site ids.

| Package | Kind | Run | Snapshot | What happened |
| --- | --- | --- | --- | --- |
| PL1 | success: delivered timber used by RS2 | T23 | 30 | Expedition 1 (civ 0, home region 7, forest region 6, 2 hops; crew 13, 16, 19 and 20, with 19 still aboard at the end) delivered 14.30 of its 14.59 cut at snapshot 27. RS2 held 2.0 of it from the store for granary project 0. |
| PL1 | success: a granary completes after a delivery | T23 | 61 | Granary project 0 (region 7, a war rebuild opened at turn 12 at 0.62) completed at turn 60, using 15.2 timber. Expedition 1 had delivered at turn 26, and RS2 held 14.30 from region 7's store while the project was open. |
| PL1 | failure: `no_forest` | T23 | 26 | Region 4 (civ 1) had a gap of 4.0 timber and no reachable forest of its own or of nobody. |
| PL1 | failure: `too_far` | P7 | 16 | Region 5 (civ 9), gap 4.0: every forest was more than 2 hops away. |
| PL1 | failure: `forest_depleted` | T23 | 48 | Region 1 (civ 3), gap 4.8: every forest in range was below half its capacity. |
| PL1 | failure: crew lost, cargo to the forest commons | T23 | 45 | Expedition 6 (home 1, forest 5) had lost its whole crew by turn 44, on the way home: 104 died, 16 and 39 migrated, 82 enlisted. Its 0.13 cut timber was deposited in region 5's stockpile at turn 44. |
| PL1 | failure: recall for want of coins | T23 | 172 | Expedition 26 (civ 0, home 7, forest 6) was recalled while cutting. Crew member 357 walked home unpaid for 2 turns and delivered 2.40 (snapshot 173). |
| PL2 | success: a graduate gives upkeep offset | T23 | 167 | Site 3 (region 7) operated with graduate 446 on its crew of five. Qualified members 444 and 446 offset the whole 0.02 wear, 0.005 of it through 446's apprenticeship. |
| PL2 | success: transferred and completed | T23 | 166 | Apprentice 446 began at site 0 (region 3) at turn 156, transferred once to site 3 (region 7) and completed after 10 attended turns (4 on the crew, 6 attached). The qualification was granted. |
| PL2 | failure: `long_absence` | T23 | 70 | Apprentice 243 (site 1, region 1; 2 attended turns, 2 transfers) ended after more than 4 consecutive absent turns. |
| PL2 | failure: `stalled` | T23 | 188 | Apprentice 502 (began at site 3, then site 0 in region 3; 1 attended turn) ended after more than 20 consecutive missed turns. |
| PL2 | failure: no mentor aboard | T23 | 51 | Site 1 (region 1) operated with crew 235, 237 and 243 and no qualified person in the region. Apprentices 237 and 243 missed `no_mentor`. |
| PL2 | control: completion without a grant | T23-NQ | 166 | The same apprentice 446 completed at the same turn with no qualification granted. No graduate offset was found in the control run. |
| Operating wear | failure: worn to an L1 lump repair | T23-W | 50 | Site 1 (region 1) operated for 25 turns (22–48) from full condition with no qualified member, wore to just under 0.5, and civ 3 paid the 20-coin lump at turn 49. |
| Operating wear | failure: worn to an RS2 project | P7 | 65 | Site 2 (region 23) operated for 13 turns (46–58) from full condition with no qualified upkeep and wore to 0.74. RS2 opened workshop project 18 at that condition at turn 58 and completed it at turn 64 (2.08 work). |
| PL3 | success: wages to a named granary crew | T23 | 14 | Granary project 0 (region 7, payer civ 0): rural farmer 28 worked 0.025 of a turn and was paid 50 milli. |
| PL3 | success: a veteran on a repair crew | T23 | 27 | Veteran 16 led the granary crew of project 4 (region 5, civ 3), with farmers 35, 37 and 39 (8,000 milli in wages). |
| PL3 | failure: a granary crew short of farmers | T23 | 52 | Granary project 9 (region 5, civ 3) planned 4.0 work. The only two eligible farmers, 206 and 257, gave 2.0, and RS2 recorded `no_labor`. |
| PL3 | success: an obligation reservation used | T23 | 14 | Civ 0 reserved 1 coin, and RS2's 1-coin charge was paid from it. |
| PL3 | failure: a reservation returned unspent | T23 | 35 | Civ 3 reserved 1 coin. RS2 charged nothing, so the whole reservation was returned. |
| RS2 `no_people` | failure: suspended, later resumed | T23 | 130 | Granary project 1 (region 1) was suspended `no_people` at turn 127 and resumed at turn 129. |
| RS2 `no_people` | failure: no project for want of people | P7 | 87 | Granary 27 (region 27), just below 0.75, got no project because the region had no farm labour (unmet `no_people`). |

Where each kind was found (snapshot), or not:

| Kind | T23 | P7 | T23-NQ | T23-W | P7-W |
| --- | --- | --- | --- | --- | --- |
| PL1 delivery used by RS2 | 30 | 39 | 30 | — | — |
| PL1 granary completes after a delivery | 61 | 43 | 61 | — | — |
| PL1 `no_forest` / `too_far` / `forest_depleted` | 26 / none / 48 | 29 / 16 / 46 | 26 / none / 48 | — | — |
| PL1 crew lost, cargo abandoned | 45 | 63 | 45 | — | — |
| PL1 recall | 172 | 29 | 172 | — | — |
| PL2 graduate gives upkeep offset | 167 | none | none | 70 | 137 |
| PL2 transferred and completed | 166 | none | 166 (not granted) | 52 | none |
| PL2 `long_absence` / `stalled` | 70 / 188 | none / 182 | 70 / 188 | 60 / none | 46 / 71 |
| PL2 `no_mentor` with no mentor aboard | 51 | 148 | 51 | 40 | 41 |
| PL2 control completion without a grant | n/a | n/a | 166 | n/a | n/a |
| Operating wear to an L1 lump | n/a (RS2) | n/a (RS2) | n/a (RS2) | 50 | 133 |
| Operating wear to an RS2 project | none | 65 | none | n/a | n/a |
| PL3 wages / veteran / short | 14 / 27 / 52 | 20 / 27 / 34 | 14 / 27 / 52 | — | — |
| PL3 reservation used / returned | 14 / 35 | 20 / 26 | 14 / 35 | — | — |
| RS2 suspended then resumed / unmet `no_people` | 130 / none | 113 / 87 | 130 / none | — | — |

"—" marks a package the run does not enable.

### Not found

- **The L1 lump repair cannot occur with every switch on.** While RS2 is active and the
  workshops operate, `repair_projects.legacy_workshop_repair_allowed` is false, so RS2
  owns workshop repair and no lump is billed (`operating_wear` counter `repairs`
  absent). The lump examples therefore come from T23-W and P7-W. The RS2 analogue is the
  row "worn to an RS2 project".
- **Operating wear to an RS2 project in T23.** None under the finder's rule. That rule
  needs an unbroken run of unqualified operating turns from full condition to the
  project's opening condition. Each of T23's 15 completed workshop wear projects missed
  it in at least one way: the decline began below full condition, other wear (such as
  L1's unfunded 0.05 a turn) came between or after the operating turns, or a qualified
  member gave upkeep.
- **`too_far` in T23.** There were 0 such refusals in 200 turns (against 125
  `no_forest` and 236 `forest_depleted`).
- **The PL2 success kinds and `long_absence` in P7.** With every switch on, P7 enrolled
  only 5 apprentices in 200 turns: 2 completed, none transferred, none ended
  `long_absence`. P7-W enrolled 38: 1 completed, none transferred. No transfer followed
  by a completion occurred in a procedural run.
- **Unmet `no_people` in T23.** None (counter 0).
- **The graduate offset in T23-NQ.** None, as the control is built to do: its graduates
  hold no qualification.

## How the finder reads the records

`scripts/productive_recovery_examples.py BUNDLE [BUNDLE ...]` reads only the dated
per-turn records `history[i]["livelihoods"][<package>]`, never the final world state. A
package the run does not record prints "not recorded in this run". A kind with no
instance prints "none found". A kind that cannot occur in the run prints the reason.

Record fields and reasons are the packages' own (`*_state.py`). `check_fields()` checks
each field, declared value and RS2 history event the finder reads against this checkout.

| Kind | Rule |
| --- | --- |
| PL1 delivery used by RS2 | the first `closed` expedition with `status` `delivered` and `delivered` > 0, then a later `stores` row of its home region with `held` > 0 before that region's `store` empties |
| PL1 granary completes after a delivery | a `closed` RS2 granary project `completed` whose region had a delivery with `opened_turn <= ended_turn < closed_turn` |
| PL1 refusals | a `needs` row `refused` with that `reason` |
| PL1 crew lost | a `closed` expedition `abandoned`, `end_reason` `crew_lost`, `abandoned` > 0, with its `deposits` row |
| PL1 recall | a `receipts` row with `recalled`, followed to the expedition's end |
| PL2 graduate offset | an operating `receipts` row with `graduates_on_crew` and `offset_by_graduates` > 0 (rules version 2 only) |
| PL2 transferred and completed | an `archive` record `completed` with `transfers` > 0 |
| PL2 `long_absence`, `stalled` | an `archive` record with that `ended_reason` |
| PL2 no mentor aboard | a `missed` seat with reason `no_mentor` at an operating site whose `qualified_on_crew` is empty |
| PL2 control completion | an `archive` record `completed` with `granted` false |
| Operating wear | from full condition, an unbroken chain of `operating_wear` receipts with no qualified member and no offset (each `condition_before` the previous `condition_after`). For the lump, the chain ends below the workshops' `operate_condition` and is followed by a workshops receipt that `paid` `repair`. For RS2, it ends at the `opened_condition` of a completed RS2 workshop project with cause `wear`. |
| PL3 | `recovery_crews` receipts: a granary crew with `wages_milli` > 0, a member with `veteran`, a granary receipt with `short` (with RS2's receipt reasons); `maintenance_obligation` `uses` with `used` > 0 and with `returned` > 0 |
| RS2 `no_people` | a project `history` with `suspended_no_people` followed by `resumed`; an `unmet` row with reason `no_people` |

`tests/test_productive_recovery_examples.py` (offline, in the oracle chunk
`timber-supply`) runs the finder on a small constructed bundle. It checks each kind's
snapshot and ids, the near misses it must skip, the "none found", "not recorded" and
"not applicable" outputs, that the final state is never read, the printed report of a
written bundle, and `check_fields()` against the source.
