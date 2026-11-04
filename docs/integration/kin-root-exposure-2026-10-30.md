# Kin-root exposure before another calibration

The retained full-population study keeps its original result: all four strict
gates passed, joint-needs causality passed in all four, and the separate
causal-required decision failed in all four on kin roots. Template members'
migration RR is0.9877; procedural RR is0.9956. The registered target stays RR at
most0.85 with a one-sided upper below1. No report, metric or threshold changes.
See [the retained full study](full-population-gates-2026-10-29.md).

The roots switch reaches the decision code. It removes marriage/home-bond roots
from voluntary destination pulls, with a nominal maximum0.06 before f32 rounding under the current
constants. It leaves age roots, distress and need pushes, household wealth
damping, and household followers. The saved reports establish a weak effect
under this narrow intervention; they do not establish an unused-switch defect.

The recorded wealth multiplier can attenuate or amplify delivered dose. For
equal-wealth spouses with personal wealth at least0.01, its source formula is
`0.88 * 2**-1.2`, about0.383. A nominal0.06 removed root term then changes
post-wealth utility by about0.023 when destination and other terms stay fixed,
against a decision temperature of0.3. This arithmetic
example is not a twenty-turn effect bound: target changes, gates, followers,
cooldowns and later catch-up matter. The separate default-off community-anchor
mechanism has already been tried and also did not reproduce the15–30% endpoint.
Another coefficient is not the first missing implementation.

Below that floor the same formula can amplify instead. `behavior.rs` divides
effective wealth by `personal.max(0.01)`, while `tick.rs` clamps actual wealth
to `[0, MAX_WEALTH]`. Personal wealth0 plus spouse wealth0.005 gives ratio0.5
and a multiplier greater than1. This is a source-domain finding, not an observed
frequency or an explanation established for the full study. The reader accepts
finite nonnegative recorded factors and reports amplification separately;
historical records are not rewritten to match a later mechanics correction.

## Existing frames, one bounded reader

`chronicler.kin_root_exposure.summarize_kin_root_exposure` reads existing
decision-delivery wire rows. It reuses that module's field descriptors instead
of introducing another capture schema. It opens no files, imports no Arrow or
native package, constructs no simulator and draws no random numbers.

After an explicit observer capture, use the already retained data:

```python
from chronicler.kin_root_exposure import summarize_kin_root_exposure

readout = observer.read_latest(expected_source_turn=turn)
if readout.status == "captured":
    report = summarize_kin_root_exposure(
        decision_header=readout.decision_header.to_pylist()[0],
        decision_rows=readout.decisions.to_pylist(),
        candidate_rows=readout.candidates.to_pylist(),
        move_header=readout.move_header.to_pylist()[0],
        move_rows=readout.moves.to_pylist(),
    )
```

Inputs are exact builtin dictionaries/lists with current field names and
integer/boolean/null types. Combined bodies have at most65,536 rows. The sum of
canonical JSON+LF header/row bytes is at most32MiB; the aggregate report is at
most64KiB. Record-byte accounting excludes a transport wrapper because rows are
already in memory. The observer's retention limit applies before conversion.

The report distinguishes captured deciders from applied own, spouse, dependent
and unknown move roles; voluntary eligibility from an outward destination;
gross pulls from pulls surviving roots and hysteresis; and selected-destination
root dose before and after the recorded wealth multiplier. Age roots remain in
the relationship-root removal. Source operations replay f32 rounding and check
gross/net and utility-stage joins before projecting a dose at that destination.

Explicit selection keeps a selected denominator, whose retained living count
cannot exceed the number of requested IDs. Retained trip/evaluated/displaced/
mobility counts reconcile with global header counters when capture is complete
and unselected, and never exceed those counters in a subset. Truncation stays
`partial_capture`; missing selected candidates and move origins remain visible.
No unseen rows silently receive zero exposure. Invalid fields, scalar aliases,
NaN, positive infinity, nongated negative infinity, inconsistent joins and active kin ablation refuse with
`ValueError`. The reader does not declare a causal pass, infer community
membership, search for a new target, replay random draws or estimate a temporal
migration effect. Caller-supplied metadata attests no compiled execution. Native
event linkage remains the existing observer's responsibility.

Applied origin joins include `(bucket, agent_id)`, matching native tracking.
An applied row with no valid origin retains unknown role255, null lead and null
origin ordinal; a valid applied origin has a known role and nonnull ordinal.
These flags stay consistent even in a partial capture. A missing partial-frame
ordinal is reported as unavailable rather than invented from another row.
Even when the origin row is absent, a valid applied origin ordinal must precede
its applied row: native tracking stores the earlier `record()` ordinal before
recording the applied move. Missing earlier origins remain allowed in a partial
capture; equal and future origin ordinals refuse.

## Next distinct measurement

Use existing bounded capture to report the exposure funnel before mechanics
change: captured alive → evaluated → non-displaced → voluntary eligible →
relationship-root dose → admitted candidate → selected candidate → post-wealth
dose → own proposal → applied own/follower move. Keep zero-exposure and truncated
rows. This funnel does not replace the original member cohort.

If another mechanism is proposed, preregister its intervention and retain the
original twenty-turn endpoint and every seed. First-decision delivery, move
delay and later catch-up can be separate prospective diagnostics. Community
membership needs its own joined data; a root term does not imply membership.

Contract cases use synthetic builtin rows and the existing offline guard. A new
final chunk retains all old39 entries, their order and110-second caps. The first
focused execution of source `90e4a1b4` passed all99 synthetic current-wire-format
cases, with no failures or skips. JUnit recorded99 cases and the existing offline
guard passed: no native modules loaded, no native import attempts blocked, no
ecology/politics factory calls and no blocked I/O attempts. This docs-only child
keeps the reader, cases and all40 chunk selections byte-exact to that tested
source. The full standard CI run remains a separate pending check.

Earlier sources `fcd616c4` and `ace9ae8a` remain unexecuted and source-blocked in
their preserved packets. The first excluded valid historical wealth factors
above1; the second missed origin ordering when an origin was absent from a
partial capture. Their source-review negatives remain evidence of those drafts.

The99-case result qualifies synthetic row validation and arithmetic only. No
actual saved frame was analyzed, and no native, World, checkpoint, full-study or
twenty-turn efficacy qualification follows. The retained cohort results and all
scientific thresholds remain unchanged.

## Opt-in first-fork acquisition driver

`scripts/capture_kin_root_exposure.py` prepares the next distinct measurement.
Its default invocation is disabled and imports no simulation runtime. The source
and fake-driver cases were UNRUN at the original `8919f03d` freeze.

That source's first focused execution subsequently passed all 30 pure fake-driver
cases, with no failures or skips. The existing offline guard passed with no
native imports, ecology/politics factory calls or blocked I/O attempts. The
retained flat JUnit contains 30 cases; no detailed per-phase event stream is
claimed. This docs-only child keeps the driver, all 30 cases, the original 99
reader cases and all 40 chunk selections byte-exact to the tested source. The
full standard Tests workflow remains a separate pending check.

The focused result covers synthetic checkpoint/readout stand-ins, membership
selection, argument/call-order contracts for the ordinary APIs and failure handling. Actual checkpoint
decode, native or World execution, saved-frame acquisition and the proposed
102-tick experiment remain held until separate whole-worker/native/resource
admission. No temporal effect or scientific qualification follows from this pass.

The input is one fresh current-source/native exact checkpoint: template seed42,
8regions/4civilizations, world turn101 and the original500-turn configured
horizon, local simulation-only hybrid mode with validation sidecars and no decision ablation. The
existing strict loader keeps mismatch overrides disabled. The checkpoint's own
retained `SidecarWriter` rows supply fork100 membership through existing
community method2/cohort method6, intersected with that snapshot's living IDs.
This binds membership to the same checkpoint instead of trusting unrelated
sidecar files. Identity and run configuration are retained in the output context.
No historical member IDs are recovered by this current-source acquisition.

After separate whole-worker and native admission, invocation is explicit:

```sh
PYTHONPATH=src:. python scripts/capture_kin_root_exposure.py \
  --enable-acquisition --checkpoint /absolute/current/checkpoint_turn_101.ckpt \
  --output /absolute/fresh/kin-capture
```

Checkpoint generation remains a separate dependency. Reuse the full chosen
validation profile's flags, keep its500-turn horizon and request checkpoint101.
The existing `execute_run(..., quit_check=...)` can stop after101 completed ticks:
the scheduled checkpoint is written before that callback. Setting `--turns101`
would force final settlement detection on tick100 and create a different prefix.
This driver accepts the checkpoint and resumes exactly one ordinary turn with
the original500-turn horizon, stopping through `quit_check` after that turn.

Native `selected_agent_ids` receives the fixed member IDs, including members
with zero root dose. The original five captured batches pass unchanged to the
reader. `cohort.json` keeps the fixed cohort size separate from current selected
living counts; nonmembers have a fork count but no captured decision rows.
An empty valid community set stays empty. An unavailable graph snapshot refuses
instead of claiming an empty cohort. Partial captures, adapter refusals, reader
refusals and cleanup failures stay visible in `receipt.json`; captured wire rows
are retained before the reader runs. The existing reader's membership flag stays
false because the cohort evidence is carried separately by this driver.

Input caps are64MiB compressed checkpoint,128MiB declared raw sections,
262,144 checkpoint sidecar rows scanned and65,536 projected fork rows. Observer
limits remain4,096 agents/16,384 candidates/16,384 move rows and8MiB Arrow
retention. Driver artifacts have individual caps: wire32MiB+64KiB, cohort1MiB,
and context/exposure/receipt64KiB each. An unavailable readout's retained headers
have a separate64KiB cap. Combined driver artifacts stay below34MiB. These limits do not
bound total process RSS or the ordinary resume's exports. Existing
`ArtifactBudget` rejects exact resumes/checkpoints; the driver adds no bypass.
Whole-worker disk/RSS/wall admission remains required before execution. The
3GiB `/tmp` floor is checked before acquisition, before stepping and afterward;
it is not a continuous disk reservation.

The ordinary resume retargets outputs into the fresh capture directory before
observer attachment. Failure cleanup cannot flush restored sidecars into the
parent directory. No new simulation hook, native capture schema, checkpoint
format, scientific threshold or calibrated effect is introduced. A future
paired20-turn experiment must retain the original window101–120 and its21
executed ticks. This one-turn acquisition cannot establish that temporal effect.
