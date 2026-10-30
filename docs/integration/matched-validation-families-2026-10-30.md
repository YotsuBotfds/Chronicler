# Matched scientific validation families — source proposal, 2026-10-30

This isolated workflow child of5122 proposes a way to run the existing scientific gates against exact source commits. It executes no build, test, native import, World, checkpoint, frame analysis or GitHub action during preparation. Publication, ordinary source-contract tests and every scientific dispatch require separate root decisions.

## Controller and measured source

`validation-gate.yml` adds a manual `source_sha` string, empty for the workflow/event commit. A nonempty value must be the full40 lowercase hexadecimal commit; checkout uses that exact value. The actual checkout SHA/tree/native tree is recorded separately from the workflow controller SHA, workflow ref and unchanged `GITHUB_SHA`/`GITHUB_JOB` fields. No GitHub identity is spoofed.

The job still builds its own release locked wheel and installs it in its own fresh environment. Before any World command it checks the real extension loader, public/native class-object aliases and the existing lower-level `native_wheel_receipt.wheel_receipt` link between this wheel and installed native bytes. Its source helper, package digest, compiler, Python/environment and source/native trees are recorded. The standard-lane `native_ci_shards.py record-build` is intentionally not called: it requires the different `python-native-build` job and `HEAD == GITHUB_SHA`. The native source remains5122'sa840 tree in this controller child; choosing701 for a baseline measures701's09ec tree instead.

## Matched cells, all unrun

The controller adds `worldgen` as a template/procedural choice, defaulttemplate, and forwards `--parallel 3`. It adds no seed, horizon, map-size or oracle-tuning input. Existing360-minute job timeout, strict-regression/fail-on-regression switches and scientific thresholds stay unchanged. The runner's existing defaults define the six proposed cells:

| Family | Before source | After source | Seeds | Turns | World |
| --- | --- | --- | --- | --- | --- |
| Template full |701bd3fe960d1761e9aa3c7c5d1d7bf41d00464d|5122fad852535f1f70a281c5b0fbfef06dfa8f69|42–241 (200)|500|existing8-region/4-civ template|
| Procedural subset |same701|same5122|42–61 (20)|200|32 regions,10 civs|
| Procedural full |same701|same5122|42–141 (100)|300|32 regions,10 civs|

Each row has two separately approved first attempts; all run IDs, native ELF hashes, wheel hashes and results areNULL. Historical06d is ineligible as a current701 baseline. Parent standard CI, source review and earlier scientific populations do not replace these runs. Full profiles retain the existing default needs/kin_roots ablation arms; subset keeps its current default without them. No causal-required switch or scientific threshold is changed. Existing strict-regression defaults remain as configured; the selected strictness must match within each pair and be recorded before dispatch.

The current `baseline_report` workflow input remains a local-path compatibility feature. A path string does not acquire an artifact into a fresh runner. The registered pairs should leave it empty, retain each own compact result, then compare the matched reports after their original artifact IDs/ZIP hashes and manifests have been acquired and verified under a separate root decision. Use the existing comparator with `--fail-on-regression`, without exploratory mode; refuse mismatched seeds, turns, worlds, simulation settings, profile, oracle methods or missing verified batch identities. Also check the declared source/native families and matching actual compiler/Python/dependency/thread configuration; comparator cohort matching alone does not authenticate build provenance. Preserve both individual gate outcomes and all negative/incomplete attempts. NO_REGRESSION is not unchanged distributions or mechanism efficacy.

## Complete compact evidence, independent raw retention

The existing full raw artifact upload block, path and30-day retention are byte-exact. A separate always-run export selects only the exact profile's report, run/batch manifests, gate/optional comparison summaries, optional full ablation manifest, actual build identity and own wheel. It copies their original bytes and writes a SHA256/size/path manifest. It neither downloads nor strips the full dataset. Batch source/package/native hashes must join the actual own-build identity.

Compact file bodies plus their manifest are bounded at7MiB, leaving packaging room within the existing8MiB original-ZIP intake ceiling. The consumer must still check the actual ZIP size; packaging size is not preclaimed. If complete required evidence is missing or oversized, export is explicitly incomplete/refused and the job stays unsuccessful; no report is truncated or silently replaced. The full raw upload still runs independently. Actual report/wheel/manifest sizes for these new cells remainNULL until produced. This is a transport bound, not a simulation cap or scientific threshold change.

A later local intake can retain at most8MiB original compactZIP,7MiB extracted bodies and a bounded remainder for API metadata/reconciliation inside the existing24MiB intake envelope. It must not download the multiGiB raw archive locally by default, copy another source checkout into that envelope, or borrow the16/32MiB installed-API protocol. The raw artifact remains the complete remote fallback. Any compact refusal needs a separate concrete follow-up review, never an autonomous cap increase.

## Resources and gates before execution

The profile's3 workers also bound concurrent ablation fork workers to3 through the existing runner. This is not an OS CPU or memory limit; actual runner CPUs, memory/disk availability and thread environment must be recorded/admitted before the scientific grant. The existing360-minute timeout remains. Historical documentation reports multiGiB datasets and multiGiB validation memory; those are source-specific observations, not a fit guarantee for these new runs. No large artifact or dataset is copied into the constrained local workspace.

Root should first finish source review/ordinary source-contract verification of this controller and current701/5122 standard-CI provenance, then approve exact dispatch inputs/resources for each cell. Before World execution, require the fresh own build/classes and actual source/native identity; after execution require verified complete batch manifests, original reports/decisions and exact compact transport identities. A full gate pass validates the existing population/oracle contract, not targeted wealth efficacy, conservation, performance, actual saved Kin frames or a new twenty-turn causal effect. No main merge follows automatically.

Only the workflow, four appended source-contract tests, this dated note and a continuation prepend change. All old test bodies/parametrizations, `tests.yml`,185 Python product files, the entire nativea840 tree, ownership, offline chunk selections/caps, simulation profiles, seeds/horizons, validators/comparator and dependencies remain exact5122. All new tests and workflow/controller actions areUNRUN at this source freeze.
