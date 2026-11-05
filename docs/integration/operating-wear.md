# Workshop operating wear (PL2, `--operating-wear`, default off)

Productive-recovery phase, package PL2
([phase plan](../superpowers/roadmaps/productive-recovery-phase.md), sections 1 "D2" and
2 "PL2"). This page records what the switch implements, what it does not, and its
evidence. The same package changed the apprenticeship rules: see
[RS1 rules version 2](apprenticeship.md#rs1-rules-version-2-pl2). Merging it does not
qualify it scientifically.

Enable with `--agents hybrid --workshops --operating-wear` (`--workshops` must be in
`operate` mode, its default). The switch has no modes: its control is the arm without
it. A world that never enabled it has no container, snapshot key, checkpoint flag or
manifest entry. `--no-operating-wear` stops the wear and keeps the record.

## Why a switch

The D2 diagnosis found that the extra repairs RS1 adds come from its own maintenance
assumption, not from training. With `--apprenticeship`, every funded *operating* L1 site
lost `OPERATING_WEAR` of condition a turn. The reference arm `--workshops` alone
(`W_operate`) has no such wear: L1 wears a site only while it is unfunded.

D2 split the TR − W difference in lump repairs (+11.7 template / +15.5 procedural) into:

| Component | Template | Procedural |
| --- | --- | --- |
| Operating wear | +15.5 | +17.2 |
| Qualified upkeep | −4.2 | −2.3 |
| Seats | +0.7 | +1.0 |
| Training | −0.3 | −0.3 |

With the wear at zero, training changed repairs in 0 of 12 worlds.

So the held RS1 screens compared training against a reference that did not wear. This
switch lets the reference carry the same assumption.

| Arm | Flags (with the base flags) |
| --- | --- |
| `W_operate` | `--workshops` |
| `W_wear` | `--workshops --operating-wear` |
| `NQ` (control) | `--workshops --apprenticeship --apprenticeship-mode no_qualification` |
| `TR` | `--workshops --apprenticeship` |

`W_wear`, `NQ` and `TR` share the wear. Training is measured against `NQ`, which keeps
every cost; the maintenance assumption is measured as `W_wear` − `W_operate`.

## Rule

At workshop settlement (the `workshops._operating_wear` seam, after the native economy
tick), a funded **operating** site loses:

```
net wear = OPERATING_WEAR − upkeep offset,    0 <= upkeep offset <= OPERATING_WEAR
```

- An *operating* site is one that is funded, built, in condition (or carrying its repair
  in the bill) and crewed, so that its crew's work replaced the region's craft ceiling
  that turn.
- **Offset only by qualified upkeep.** Only RS1 qualifies anyone. Without
  `--apprenticeship` the offset is 0, and an operating site loses the whole wear every
  turn. With it, the offset is RS1's own (qualified crew members' upkeep,
  `apprenticeship.upkeep_offset`).
- Condition stays in [0, 1]. Below `workshops.OPERATE_CONDITION` (0.5) a worn site stops
  until it is repaired: by the L1 lump (`REPAIR_COST` 20, condition back to 1.0), or by
  RS2 when that is on. This switch never repairs.
- Construction, unfunded and non-operating turns are not worn by this switch.
  Unfunded built sites keep L1's own wear (`CONDITION_WEAR` 0.05).
- The wear is a maintenance assumption only. It takes no crew time, moves no money,
  draws no RNG and touches no person. The crew's craft work and ceiling are unchanged.

### `--apprenticeship` implies it

RS1 applies the same wear itself, exactly as before this switch existed, so every RS1
command keeps its wear. The seam asks the operating-wear module when the switch is
active, and otherwise RS1 when apprenticeship is active. The module then takes RS1's
offset, so adding `--operating-wear` to an RS1 run changes nothing but adds this
package's records. A native test checks this every turn
(`test_the_switch_adds_only_records_to_an_rs1_run`). Without either switch the seam
returns 0 and condition is untouched.

## Records

`snapshot.livelihoods.operating_wear` (schema 1, stage `PL2`) is dated by `source_turn`.

- `receipts`: for every funded operating site of the source turn:
  - `wear`, `upkeep_offset` and `net_wear`;
  - `condition_before` and `condition_after`;
  - `qualified_on_crew` (RS1's; `[]` without it);
  - `full_offset`.

  `null` when no Phase 2 completed in the source turn (unknown, not zero).
- `counters` (fixed key set):
  - `turns`, `operating_site_turns`;
  - `wear`, `upkeep_offset`, `net_wear`;
  - `full_offset_site_turns`;
  - `covered_site_turns` (operating site-turns with a qualified crew member);
  - `repairs` (L1 lump repairs paid).
- `parameters.operating_wear` and `with_apprenticeship` (whether RS1 supplied the
  offset).

Identities: `site` is the L1 site id, `region` an index in `world.regions`, qualified
people native stable ids.

## Timing, exactly once and bounds

- The wear is applied once per funded operating site and turn, at settlement, after the
  native economy tick succeeded. A second application to the same site in a turn
  raises.
- Its receipts are held transiently and committed by this package's `finish_phase2`.
  That hook runs after the workshop's, because the switch is last in
  `LIVELIHOODS_SWITCHES`.
- A Phase 2 whose native economy tick fails reaches no settlement, so it applies no
  wear and records nothing (`rollback_phase2` drops anything held).
- Bounds: one frame of at most `workshops_state.MAX_SITES` receipts, and the fixed
  counter keys. Nothing else is kept.
- Exact checkpoints keep the state; nothing is pending at a turn boundary. A native test
  resumes an exact checkpoint taken inside live apprenticeships with the switch on.

## Declared parameter (a modeling choice, not calibrated)

| Constant | Value | Meaning |
| --- | --- | --- |
| `OPERATING_WEAR` | 0.02 | condition a funded operating site loses per turn, before qualified upkeep (moved unchanged from `apprenticeship.py`; `apprenticeship.OPERATING_WEAR` re-exports it) |

With nobody qualified, a site falls from 1.0 to the 0.5 operating floor in 25 operating
turns. Nothing was tuned.

## Registry

- `LIVELIHOODS_SWITCHES` and `livelihoods.LIVELIHOODS_ARG_KEYS` end with `operating_wear`
  (no choices).
- The prerequisite check (`_check_prerequisites`) refuses it without `--workshops` in
  operate mode under `--agents hybrid`.
- `feature_catalog.REQUIREMENTS` declares the same requirements as `--apprenticeship`.
- `batch_manifest.SIMULATION_ARG_KEYS` lists it, and `simulation_config` omits it while
  unset, so feature-off manifests and checkpoint configurations keep their exact shape.
- An exact resume that adds or drops the switch is refused
  (`livelihoods_resume_conflicts`).

## Evidence

### Tests

- `tests/test_operating_wear.py` (offline; oracle chunk `recovery-skills`):
  - the switch alone wears every funded operating site by exactly the wear;
  - construction and unfunded turns are not worn by it, and the crew's craft time is
    untouched;
  - a worn site stops and the lump repair is counted;
  - the reference arm has no wear and no state;
  - RS1 implies the wear, and adding the switch changes neither the workshop nor the RS1
    state (versions 1 and 2), only adds records that equal RS1's offsets;
  - registry, CLI, prerequisites and resume conflicts;
  - JSON and pickle round trips, the dated snapshot, and a failed Phase 2.
- `tests/test_apprenticeship_v2_native.py` (real extension, template seed 7):
  - `test_w_wear_against_w_operate_shows_the_wear`: operating turns never change
    condition in `W_operate`. In `W_wear` every operating site-turn loses exactly 0.02
    with no offset, and the workshop receipts agree. Lump repairs appear only in
    `W_wear`. The two worlds are identical until the first operating turn.
  - `test_the_switch_adds_only_records_to_an_rs1_run`;
  - an exact checkpoint resume with the switch on.

### Development worlds

See [the RS1 version-2 measurement](apprenticeship.md#development-worlds-pl2), which
reports `W_operate`, `W_wear`, NQ and TR side by side on 12 development worlds.

## Limits

- The wear rate is declared, not calibrated. This switch only makes the assumption
  explicit and shared across arms.
- Workshop repair is still the L1 lump or RS2. Timber, not money, binds RS2 (D1).
- The viewer does not read this record yet (PL5).
