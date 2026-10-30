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
final chunk retains all old39 entries, their order and110-second caps. At source
freeze, new tests and actual frame analysis are UNRUN. No native, World,
checkpoint, full-study or efficacy qualification follows.
