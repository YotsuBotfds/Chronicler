# Recovery skills: success and failure examples (RS7)

Two kinds of example are recorded here, and the labels mean exactly this:

- **Constructed** examples are unit or native tests that build the situation on
  purpose. They show the mechanism behaves as declared, not that it happens in real
  worlds.
- **Natural** examples come from ordinary runs of development worlds (never a held
  seed). Each names the command that writes the run and the snapshot turn of the
  instance. `scripts/recovery_skills_examples.py` finds them.

The source is the phase branch at the commit recorded in each natural run's command
section.

## Constructed (reproduce with `pytest <test>`)

| Package | Success | Failure |
| --- | --- | --- |
| RS1 apprenticeship | `tests/test_apprenticeship.py::test_completion_grants_in_train_and_not_in_the_control_with_identical_costs`, `::test_unqualified_operating_site_wears_and_qualified_upkeep_offsets_within_crew_time` | `::test_teaching_lost_while_graduates_elsewhere_keep_their_record`, `::test_interruptions_and_dropout_after_more_than_max_gap`, `::test_lifecycle_endings_are_dated_with_their_reason` |
| RS2 repair projects | `tests/test_repair_projects.py::test_no_work_beyond_the_cap_and_completion_closes_the_project`, `::test_war_damage_is_recorded_once_per_asset_and_turn_with_the_war_identity` | `::test_stalls_record_their_reasons`, `::test_a_timber_residue_too_small_for_one_turn_hires_nobody`, `::test_failed_economy_tick_charges_nothing_and_returns_timber` |
| RS3 veterans | `tests/test_veteran_reintegration.py::test_crew_placements_and_why_others_waited`, `tests/test_apprenticeship.py::test_a_seated_veteran_is_placed_each_turn_in_either_rs3_mode` | `tests/test_veteran_reintegration.py::test_lifecycle_death_migration_control_remobilisation_expiry_and_return` |
| RS4 remittances | `tests/test_remittances.py::test_a_settled_migrant_sends_to_the_spouse_first_with_a_courier_fee` | `::test_unmet_and_ineligible_migrants_are_recorded_with_reasons`, `::test_a_returning_or_dead_sender_sends_nothing`, `::test_a_ceiling_refund_goes_back_to_the_sender_and_balances_exactly` |
| RS5 clearing protection | `tests/test_clearing_protection.py::test_enforced_protection_freezes_cover_and_is_charged_only_while_clearing` | `::test_underfunding_lowers_p_and_an_unfunded_protection_ends`, `::test_conquest_ends_protection_and_the_new_controller_decides_afresh` |
| Lifecycle (all) | `tests/test_recovery_skills_native.py::test_an_all_switch_state_fork_closes_every_saved_id_bound_record` (a fork closes saved id-bound records, dated) | |

## Natural

The world is a development world, never a held seed: procedural 32×10, seed 7, 200
turns, with every recovery-skills switch on (screen arm `ALL3`). The source is
`a4adfde6` and the native extension `6c675042…`. To reproduce:

```sh
PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 PYTHONPATH=src python -m chronicler.main --seed 7 --turns 200 \
  --agents hybrid --simulate-only --grain-reserves --public-grain-shipments --scholarship --techniques \
  --academy-services --grain-storage --worldgen procedural --regions 32 --civs 10 --workshops \
  --apprenticeship --repair-projects --veteran-reintegration --remittances --clearing-protection \
  --output OUT/chronicle.md --state OUT/state.json
python scripts/recovery_skills_examples.py OUT/chronicle_bundle.json
```

The snapshot is the viewer's turn. Each record is dated one turn earlier, at its
completed turn.

| Package | Kind | Snapshot | What happened |
| --- | --- | --- | --- |
| RS1 | success | 80 | Apprentice 406 completed after 10 attended turns (3 interruptions) and was granted a workshop qualification. |
| RS1 | success | 81 | Site 0 (region 13) operated with graduate 406 on its crew; qualified upkeep offset 0.015 of wear. |
| RS1 | failure | 50 | Site 1 lost its last qualified teacher: 570 died, and nobody qualified was left alive. |
| RS1 | failure | 56 | Apprentice 95 died before attending a turn. |
| RS2 | success | 29 | A wear project on granary 27 completed: 10.4 work delivered and credited, for 20.8 coins. |
| RS2 | success | 68 | A war project rebuilt granary 18 after a recorded damage: 19.2 work, for 38.4 coins. |
| RS2 | failure | 17 | Granary 5's project stalled for want of timber (condition 0.59 → 0.58). |
| RS2 | failure | 16 | A conquest at turn 15 damaged granary 5 from 0.84 to 0.59, with the war's identity. |
| RS3 | success | 32 | Demobilised veteran 83 (army-8) was placed after waiting. |
| RS3 | failure | 33 | Scattered veteran 69's eligibility expired with no opening. |
| RS3 | failure | 20 | Veteran 88 was remobilised into army-4 one turn after waiting. |
| RS4 | success | 11 | Migrant 280 (region 13 → 18) sent 112 milli; 96 were credited to kin 481 at home and 16 went to the courier. |
| RS4 | failure | 55 | Sender 191, who last sent at snapshot 21, had no Marriage or Kin bond strong enough left. |
| RS4 | failure | 96 | Recipient 495 was at the wealth ceiling: all 462 milli were refunded and only the fee was lost. |
| RS5 | success | 1 | A funded protection kept 0.02 cover from clearing for 2 coins. |
| RS5 | failure | 29 | Clearing proceeded unprotected in a region whose controller could not afford the warden. |
| RS5 | failure | 16 | A protection ended when its region changed controller. |

Not every package meets every kind in one world. In the same seed's single-package
arm `RS1_train`, no apprentice completed in 200 turns; in template seed 2 no
completion occurred either. Completions need a qualified mentor present for 10
attended turns, so they are rare (see the held screens).
