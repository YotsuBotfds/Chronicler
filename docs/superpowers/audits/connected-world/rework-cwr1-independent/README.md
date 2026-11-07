# Independent CWR1 arithmetic checker

Prepared against reviewed runtime `8792be88dd36ba4d7c22e480de6a19dd64ea1300`.
The complete timing pilot passed the
[independent readback](pilot-review-2026-11-07.md), and all 144 held runs now
pass the [complete held review](held-review-2026-11-07.md). The
[retained-first-world raw audit](raw/review-first-worlds-2026-11-07.md)
remains a separate 24-case sampling gate with explicit caps. This tool runs
no simulation, imports no Chronicler/native module, spends no seed and edits
no registry. It uses only Python's standard library.

The [checker](check.py) independently derives the twelve-arm matrix and
contrasts from the [protocol](../../../progress/connected-world-rework-prereg-draft.md).
The [source extractor](../../../../../scripts/cw_rework_screen.py) and
[generic runner](../../../../../scripts/screen_runner.py) supplied the receipt
schema; their report and analysis helpers are never imported or called.
The [earlier CW6 audit](../rework-cw6-evaluation-audit-2026-11-07.md) is historical
context, not a source of fresh effect estimates or a control definition.

## Checks and evidence boundary

- Exact enrolled matrix, once per arm/world: pilot 24 on t5/p19 or held 144 on
  template 4101–4106/procedural 4201–4206. All runs must cover 120 turns and the
  declared 8/32 regions. Missing, duplicate, failed, malformed and invalid rows
  remain visible. No comparison selects worlds by observed activation.
- Identity digest reconstructed from `source.txt`; independently supplied
  expected source commit/native hash; clean tracked-file receipt; current
  runner and extractor bytes compared to their recorded hashes. Registry
  cohort-content hashes, CWR1 reservations, collisions and shared pilot
  registration are checked independently. Full registry hash changes caused
  by `mark-run` are allowed; cohort-content changes are not.
- The supplied protocol's primaries and positive compute ceiling are checked.
  Held execution also requires a FROZEN protocol and the producer's exact
  preregistration hash. Pilot source records do **not** require a nonexistent
  preregistration line: the separately supplied draft/frozen file is hashed.
- Raw food-shortfall and epidemic aliases/harms, person-turn and infectious-
  person-turn rates, undefined ratios, Arrow receipt counts, missing access
  coverage, disabled-channel implications, neutral added crowding and
  bounded component-merge coverage. Nonzero D3/combined changes in record-only
  are valid. Positive free food in `no_relief` is valid: this existing mode
  changes the title fraction to 1 and uses L2's free-pool allocation without
  the retail means test. Famine/war causes remain unrecorded/null, never 0.
- Independent per-world levels/differences, means/ranges/sign counts, exact
  paired sign-flip enumeration and 10,000 paired-world bootstrap resamples
  using analysis seed 20261107. All three primaries, marginal channel deletions,
  PH-cost contrasts, joint food-regime contrasts and interactions are retained
  by stratum. Primary rendered table cells are checked against the arithmetic.
- Any unavailable enrolled pair withholds that contrast's aggregate; its
  per-world reason is retained. Legitimate unknown supporting access values
  do not invalidate observed raw primaries. Budget failures retain measured
  timing/projection and are failures, not missing or favorable results.

The control matrix in the receipt is **declared**, not a fresh observation of
per-turn controls. Metric implications and recorded code identities cannot
prove unseen source dates, physical closures or actual native inputs. This
checker does not independently verify the loaded extension's bytes, its
build inputs, the full Git tree or authoritative raw frames. Those remain
separate source/native and raw-bundle reviews. Its PASS is arithmetic and
receipt validation, not qualification, a default-promotion decision or a
clinical/mechanistic inference. Individuals and region-turns are never
treated as independent replicates.

## Reproduction

The approved pilot launcher retains the report command's complete output in
`report.log`; the generic report command prints Markdown and does not create
`report.md`. After the process closes successfully, the evaluation owner may
publish a byte-for-byte copy as `report.md` with a separate copy/hash receipt.
The original launcher receipt must remain unchanged, including its truthful
null `report_sha256`. This publication step reruns no simulation and changes
no source, control, outcome, timing or budget. Check both files' hashes before
using the copy; a missing or changed report remains an artifact failure.

Run only after the producer has completed the entire cohort and written its
report. Supply the commit from independently reviewed freeze evidence rather
than copying it uncritically from the artifact being checked. Example pilot:

```sh
python docs/superpowers/audits/connected-world/rework-cwr1-independent/check.py \
  --directory /workspace/evidence/cwr-evaluation/pilot-8792be88-v1 \
  --cohort pilot \
  --expected-source 8792be88dd36ba4d7c22e480de6a19dd64ea1300 \
  --expected-native-sha b1d3ea5ac858681960b2cb880c534164905501f6ab4f6f3c94f7c9b5f66196cd \
  --checkout /workspace/cwr-final-runtime \
  --protocol /workspace/cwr-final-runtime/docs/superpowers/progress/connected-world-rework-prereg-draft.md \
  --receipt /new/evidence/independent-pilot-arithmetic.json
```

For held data use `--cohort held`, the independently reviewed frozen held
source and the exact frozen protocol. The CLI expects `metrics.jsonl`,
`source.txt` and `report.md`; it writes the independently recomputed receipt
to a new explicit destination and returns nonzero on failure. Existing receipt paths are refused. It never rewrites
the producer's files. Source/shape failures precede effect summaries.

Constructed tests (no native imports, simulations or fresh cohort data):

```sh
python docs/superpowers/audits/connected-world/rework-cwr1-independent/selftest.py
```

Nine test methods pass, including 25 malformed/missing/control mutations,
source/protocol/registry mutations, whole-count cardinality guards, rendered-primary arithmetic, exact 64-way
sign flips, zero-denominator nulls and legitimate unknown access. These are
constructed interface fixtures, not independently simulated worlds. Actual
pilot/held audit receipts must be added only after their data are available.
