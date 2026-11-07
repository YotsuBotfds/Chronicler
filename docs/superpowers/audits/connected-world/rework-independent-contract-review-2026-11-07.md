# Connected World rework: independent contracts and causal review

Read-only source review of main `2726bf449d0e4d581a72034000ee0861a58ee439`.
The reviewer did not author the original mechanism and owns no shared runtime
edits. This review verifies the new correctness findings; it does not rewrite
the historical CW6 observations or call a source inspection scientific
qualification. No simulation, native build, held seed or paid call was run.

## Verified attribution-to-health path

1. `chronicler-agents/src/behavior.rs:1196` explicitly replaces the dominant
   legacy migration term with `NO_MIGRATION_DRIVER` when
   `choice.adaptive_attribution` is true. Inferring the missing term would not
   recover a justified motive: the decision now contains new signed scores and
   knowledge restrictions that the old attribution basis does not describe.
2. `residence_ledger.py:_turn_moves` converts code 255 to `None`; `_group`
   classifies it as `other`. `_move` opens a spell for known flight/hunger, but
   instantly changes `home` for `other` or voluntary moves when no spell exists.
   Every onward move retains an already-open spell regardless of new driver.
3. `public_health.py:environment_factors` reads the guarded prior-turn X1
   frame, divides `displaced` by `residents`, and installs
   `1 + 0.25 * displaced_share`. `epidemiology.py:573–577` multiplies regional
   susceptibility by that value before introductions and within-region steps.

The resulting difference is physical, not merely a display or motive label.
An otherwise identical first move can produce a factor of 1.25 with a known
flight/hunger reason and 1.0 with unknown attribution. The prior report already
disclosed this feedback, but disclosure does not establish a physical rationale.

## Recommended scientific resolution

Keep the v1 X1 displacement/home definitions as a versioned interpretation of
known motives. Do not relabel every unknown or voluntary migrant as displaced,
and do not fabricate a reason to preserve a mortality multiplier. Their
residence is authoritative even when their reason is unknown.

For the corrected public-health path, neutralize only the added motive-derived
multiplier. Existing epidemiology already models population/capacity density
(`epidemiology.py:_modifiers`), hunger, and a separate urban-density term when
cities are enabled. An additional housing/shelter crowding effect would require
another measured physical authority; none exists here. A reason-independent
recent-arrival observation is useful evidence, but calling it extra disease
exposure would remain a new uncalibrated assumption, not this correctness fix.

Root's proposed `density_only` model is consistent with that resolution:
factor 1 for the extra X1 multiplier, existing density terms retained, legacy
displacement crowding explicitly selectable for historical reproduction.
This is a model correction, not an optimization or an inference that migration
is harmless.

## Physical observation and lifecycle guardrails

- A recent-arrival stock counts living stable IDs, once per person, from actual
  observed residence changes and their dates. It does not depend on `home`,
  spell, cause, household size or reason. Multiple moves may be separate flows,
  but the endpoint stock is unique.
- Returning home is an observed arrival, not evidence of forced displacement.
  First observation and birth are not moves unless an actual move is observed.
  Death removes the person before the endpoint stock. New stable IDs in reused
  native slots inherit no old row; a rebuilt pool clears the epoch.
- Existing `move_turn` also changes for `counted=False` trip/unexplained
  residence relocations. If reused, label the diagnostic recent *residence
  changes/arrivals*, not exclusively native migration. An active merchant trip
  retains residence rather than masquerading as a move.
- Row-limit refusal means partial physical observation. Missing historical
  frame fields, first observation after reset and unobserved epochs are unknown,
  not zero. Do not compute an apparently complete physical share from capped
  rows without exposing coverage.
- The sole writer remains Phase 10. C2 reads only T−1 through `read_frame`;
  same-turn and future reads remain refusals. Do not substitute current native
  location or narration's displaced share in the consumer.

Required adversarial comparisons include the same trajectory under known
flight, known voluntary and unknown reasons; onward and multiple same-turn
moves; return and rehoming; household changes; death after moving; slot reuse;
trip departure/unwind; epoch gaps/reset; forced row cap; and uninterrupted versus
exactly restored continuation. The C2 regression must compare actual exposure
factors and an epidemic transition, not only X1 labels.

## A second verified control defect: D3 inputs depend on A6 mode

`adaptive_livelihoods.py:before_agent_tick` combines A6 penalties with
`war_consequences.movement_rows` under rules 2. It then:

- installs an empty score input whenever A6 is `record_only`, suppressing
  independently active D3 evacuation and return inputs;
- remaps destinations in `shuffled` *after* adding D3. A remembered-home return
  pull can therefore be redirected to another neighbor. Equal evacuation pulls
  may permute to themselves, but a single home-return score does not.

Thus old FULL−A6R is not a pure adaptive-experience effect even after holding
the extra crowding term fixed. Corrected controls should generate A6 and D3
component rows separately, suppress/shuffle only A6 rows, then add unchanged D3
rows and apply the same declared combined cap. Tests should retain exactly the
same D3-only installed return and evacuation inputs across adapt, record-only
and shuffled A6 modes. Historical rules retain their historical behavior for
old-source/control reproduction; the corrected rules need explicit versioning.

`public_health` cost-only also retains crowding by design. It suppresses care
CFR and sanitation protection, not the added X1 term. It is not a crowding-off
control. New comparisons must explicitly hold or remove that term while
retaining the relevant wage, supply and guard costs. Per-pathogen observed
deaths are outcome splits, not measured deaths averted.

## Compatibility and verification admission

PublicHealthState's current `__setstate__` fills appended fields from their
defaults. A new `density_only` default must therefore not silently migrate old
pickles. Explicitly preserve legacy semantics when the field is missing in old
pickle and JSON state, while the new opt-in enable path chooses the corrected
model. Once a run has observations, conflicting saved rule/model requests must
be refused. New v1 frame fields require missing-field compatibility; historical
bundles must stay readable without inventing recorded zeros.

Feature-off identity needs both original `8abc1acb` and preceding integrated
main `2726bf44`, with each native artifact traced to its actual source. Existing
main's release artifact is `59f536b8…`; a changed native tree needs its own
isolated rebuilt extension. The default path must not acquire active new state,
manifest fields, RNG draws or corrections to the separately recorded legacy
defects.

Enabled exact resume should cover live migration/arrival boundaries, care and
guard carries, work/training, war release/return/wounds, cargo/escrow/restitution
and pool identity. Old-checkpoint migration and new-source straight/resumed
identity are different checks; neither implies cross-version byte identity.
Optimization output identity compares the same model/rules at the same source
inputs. A corrected model's intended physics change cannot be counted as a
performance optimization or neutral evidence reduction.

## Scope disposition

No new ports or owned cross-border wares feature is required for this focused
trust rework. Ports have no maritime service consumer; owned wares remains the
explicit unadopted proposal. The constructed history artifact is a reversible
visibility/redaction illustration, not an alternative simulated history or
independent outcome sample. Existing coefficient, observation-cap, unknown-cost
and cause-specific mortality limits remain explicit.

The current source findings justify correcting the attribution-to-exposure
coupling and A6/D3 control composition. They do not justify tuning model
parameters to make the twelve historical worlds favorable. Fresh bounded,
preregistered matched comparisons, profiling, exact-head CI and verified main
remain separate execution and merge gates. This document contains no approval
of an as-yet-unseen implementation diff.

## Subsequent independent review and focused regressions

Viewer optimization `cf0925d93fe1dff4687326e2d583d3d727d6c0a4` is approved
from the actual two-file diff. It replaces repeated numeric `toLocaleString`
construction with one `Intl.NumberFormat` using the same default locale and
maximum-three-decimal precision. The indexing traversal, values, source dates,
rows, bounds and reading states do not change. The app has no runtime locale
selector; the browser document's default locale is stable for its lifetime.

The reviewer used a separate detached worktree at that exact commit and ran
the actual public-index tests: **10 passed** (including the new signed-zero,
unknown and nonfinite-value regression). An independent Node check compared
156 old/new formatted strings across six locales, including tiny/large,
negative, zero and rounding-boundary values: **zero mismatches**. Complete
saved-index digest equality, repeated browser timings and paired locales remain
the performance owner's distinct evidence; these checks do not establish a
hardware-independent speed guarantee.

The reviewer authored `tests/test_adaptive_controls.py` against the integration
owner's corrected rules-3 implementation. These tests use the real dated D3
return/evacuation builder and a recording native seam. They verify unchanged
D3 inputs across personal modes/channels, personal-only shuffle before the
combined cap, work/trade isolation, legacy rules-2 historical control behavior,
T−1 refusal, pickle/rollback, old JSON/pickle defaults, new-enable rules 3 and
orphan/saved-option refusal before mutation. Full native movement/lifecycle
execution remains a separate integration gate; a recording seam proves input
composition, not actual migration outcomes.

Focused selection: **28 passed** against `/workspace/Chronicler/src`. The
same selection passed the unchanged official offline guard in a sanitized,
one-thread environment: 28 passed, no skips/failures, no loaded/blocked native
imports or I/O attempts, guard PASS; 1.194 seconds including process startup
under the existing 110-second limit. Source hashes were stable during the run.
Compact command/source/guard receipt remains outside the checkout at
`/workspace/evidence/rework-review/adaptive-controls/receipt.json`.

This is approval of the pure viewer diff and focused control regressions, not
an assertion that the complete in-progress rework has passed final source,
compatibility, resume, fresh-screen, profile or exact-head/main CI gates.
