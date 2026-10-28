# Fixed cloud full-gate comparison

This is a prospective evidence reader for the separate branch workflow. No
cohorts have been run or qualified by writing this tool. The reader is
`scripts/cloud_full_gate_comparison.py`; its synthetic checks are
`tests/test_cloud_full_gate_comparison.py`.

It accepts exactly four full-cohort lightweight artifact directories from one
GitHub run and attempt. The source pair is fixed:

- Baseline: `2f9d618b70f3304c02dcaeef12996b4a99e074c0`.
- Candidate: `d0281e5f57c508f27cea1676f36e0e6ed1225c9d`.

Each source has a template full cohort (200 seeds, 42–241, 500 turns, eight
regions/four civilizations) and a procedural full cohort (100 seeds, 42–141,
300 turns, 32 regions/ten civilizations). Both use two workers, actual
two-CPU affinity, one-thread numerical caps, the unchanged default requested
simulation configuration and the original strict full gate. The causal
components remain informational under that original policy.

The template cohort has 1,600 forks; the procedural cohort has 1,800. Both use
needs and kin-root arms and design 2. Fork labels are 100, 200, 300 and 400 for
template, and 100 through 260 in steps of 20 for procedural. A label T refers
to checkpoint World T+1; the final fork World is T+22, giving **21 actual
continuation ticks** and the unchanged 20-turn measurement window. The four
full cohorts therefore cover 600 parents and 6,800 forks, totaling 402,800
actual simulated ticks. These are prospective counts, not completed work.

## Actual frozen comparison implementation

Run the detached control script against a **separate detached candidate
checkout**:

```sh
PYTHONPATH=/abs/candidate/src python /abs/control/scripts/cloud_full_gate_comparison.py \
  --candidate-source /abs/candidate \
  --template-baseline /abs/input/baseline-template \
  --template-candidate /abs/input/candidate-template \
  --procedural-baseline /abs/input/baseline-procedural \
  --procedural-candidate /abs/input/candidate-procedural \
  --build-manifest-sha256 BUILDER_MANIFEST_SHA256 \
  --control-sha CURRENT_WORKFLOW_SHA \
  --github-run-id CURRENT_RUN_ID \
  --github-run-attempt CURRENT_RUN_ATTEMPT \
  --retention-index /abs/current-run-retention-index.json \
  --output /abs/new-comparison-output
```

The output's parent must already exist. The script checks the candidate's
detached Git HEAD and SHA-256 of its package initializer, artifact JSON helper,
validation gate and comparator before importing them from that checkout. It
rejects modules already imported from another directory. The four source-file
pins were derived from the exact candidate and independently checked against
the GitHub bytes; they are not a claim about the comparison interpreter's
native runtime. The comparison environment needs the locked Python
dependencies, not the simulation extension. It records its own interpreter and
script identity separately.

The script invokes the original candidate
`compare_validation_reports("full", ..., require_strict_regression=True,
fail_on_regression=True, exploratory=False)` on the **original unmodified
reports**. Incomparability, unverified fields, method changes/rebaseline
requirements and strict regressions cannot qualify. No report metadata is
removed, normalized beyond the existing comparator, or retried on another host.

It also reconstructs each saved original strict gate decision and requires
exact equality, preserving each original PASS or FAIL. Separately it calls
`adjudicate_validation_report` with causal oracles required on those same saved
reports. This changes which existing component decides the separate
adjudication; it performs no simulation or oracle scoring and rewrites no
historical output.

A NO_REGRESSION comparison does not establish that either original gate
passed: two equal failures can compare without a new regression. The explicitly scoped `scientific_comparison_pass` requires every original
strict gate to pass, both fixed comparisons to qualify, and all scientific
evidence admission checks. It does not establish producer-job success or raw
archive publication. `pipeline_qualified` is true only when this scientific
result also has verified current-run publication and successful producer jobs. Causal-required
results have their own `causal_required_all_pass` field and four retained
decision artifacts. Their FAILs remain FAILs under the historical thresholds.

## Lightweight artifact contract and limits

Each input root contains exactly eleven files:

```text
result.json
artifact-index.json
build-manifest.json
provenance.json
raw-inventory.json
report/validate_report_full.json
report/gate_decision_full.json
report/gate_summary_full.md
report/run_manifest.json
report/batch_manifest.json
report/ablation_manifest.json
```

The light index hashes the nine files other than itself and result.json.
The finalized result hashes the index. This avoids a receipt/index hash cycle.
The external builder-manifest SHA and current workflow/run/attempt are
mandatory independent anchors. All four copied build manifests must match
that exact builder artifact. Native extension SHA, wheel SHA, all three native
state schema identities, source revisions/package digests and before/after
stability records must match the declared experiment.

Full source/platform/kernel/executable/affinity/image evidence stays in the
controller provenance. Across VMs the additional semantic runtime equality
checks use Python patch, implementation, machine, package versions, the full
thread-environment mapping and actual affinity count. The eight numerical
thread caps must each be one, PYTHON_CPU_COUNT two and PYTHONHASHSEED zero.
Executable prefixes and host-specific CPU numbers/kernel strings are retained,
not equated across separate VMs. Within each cohort the original checkpoint
identity/environment rules remain unchanged. The existing comparator receives
the original reports and retains its own stricter refusals.

The reader verifies complete parent and fork tuple coverage, final horizons,
seven core parent validation hashes, raw-inventory links for every declared
parent/fork validation input, verified report/manifest hash crosslinks and the
original unmodified report copies. **Raw data is stored in separate artifacts**:
its hashes are controller attestations copied into the lightweight inventory.
The comparison reader does not reopen or independently revalidate absent raw
Arrow streams, checkpoint histories or simulation outcomes.

Bounds are 64 directory entries/files, 32 MiB per input/derived file and
128 MiB total per input/output root; raw inventory metadata is limited to
100,000 entries. Noncanonical paths, symlinks, hard links, overlapping input
roots, existing destinations and output inside any input/frozen source are
rejected. Inputs are inventoried and rechecked before output and again before
a final success receipt. Failure leaves the original inputs untouched. An
interrupted or failed write without the final receipt is incomplete.

## Current-run retention evidence

The optional `--retention-index` accepts a separate bounded read-only GitHub
Actions API capture. The workflow collector fetches exactly the current run's
artifact endpoint once, with at most 100 entries and a 1 MiB response. It
retains the original UTF-8 response and SHA-256, collection time, source
endpoint, run/attempt/control anchors, and the aggregate conclusion of the four
cohort jobs. Its token is scoped to that collector step and removed before
executing frozen source.

The comparison reader independently verifies the verbatim response hash,
metadata copy, nonpaginated cardinality, and four exact registered raw artifact
names. Each needs a positive official ID/size, SHA-256 archive digest,
nonexpired status/future expiry, and matching workflow run/control source.
The envelope has a 3 MiB read cap. No raw archive is downloaded or re-scored.

`pipeline_qualified=true` additionally requires all four registered raw
archives and a successful producer-job aggregate. A known missing archive or
failed/cancelled/skipped producer prevents pipeline qualification. Omitted,
unavailable, malformed or mismatched retention evidence keeps an otherwise
passing scientific comparison's pipeline standing unknown. In either case
the scientific readout and all original verdicts remain retained, and the
final command exits nonzero. API collection failure is explicit sanitized
metadata, never a green fallback.

This proves publication metadata at collection/read time, not permanent
retention or an independent inspection of archive contents. Original raw-file
hashes remain controller attestations. The final pipeline standing cannot be
inferred solely from a NO_REGRESSION or scientific-comparison PASS.

Outputs include the combined comparison, two original-policy comparisons and
their Markdown reports, four causal-required decisions, a summary and a
hash-indexed final receipt. Exit 0 requires scientific comparison, all original
strict gates, raw publication and producer jobs to qualify. Exit 2 retains a
known scientific or pipeline failure; exit 1 means admission failure or unknown
pipeline retention. Unknown retention still produces the scientific readout.
There is no unscoped `qualification_pass=true` field. No alternate thresholds, source selectors,
exploratory mode or simulation launch API is exposed.

## Smoke and test boundary

The prerequisite schema smoke is a different experiment: two seeds at 125
turns for each source/world shape, subset policy and four forks per cohort.
Its eight parents plus sixteen 21-tick continuations total 1,336 actual
simulated ticks. It is execution/schema evidence only. Its controller kind,
requested profile, horizons, filenames and qualification standing differ;
the full reader rejects smoke artifacts, including internally consistent
smoke metadata repackaged under full-report filenames. Original smoke subset
gate failures remain recorded.

Synthetic tests use the existing report fixtures and actual comparison/gate
functions. They cover admitted full-size metadata, preserved causal failures,
unchanged original failures despite NO_REGRESSION, incomplete/mixed identities,
wrong runtime/schema/build anchors, missing raw parent/fork links, duplicate
forks, requested-default overrides, immutable input bytes, alias/overwrite
refusal, fixed-source bootstrap and bounded JSON/file admission. The suite also proves
that all original gates PASS plus NO_REGRESSION cannot hide a missing raw
archive, unsuccessful producer jobs or unavailable API evidence. They run no
worlds, native pools, child processes, network or oracle scoring.

```sh
PYTHONPATH=/abs/candidate/src python -m pytest -q \
  -o pythonpath=/abs/candidate/src \
  /abs/control/tests/test_cloud_full_gate_comparison.py
```

The managed workspace was unavailable during authoring. No local test result,
actual smoke execution or full-cohort qualification is claimed here. The
workflow must run these checks before any worlds, retain failures, then complete
the registered smoke prerequisite before full sampling.
