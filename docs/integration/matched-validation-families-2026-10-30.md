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

## Pre-World resource admission hardening

This child adds an inline admission step after the own-build identity and before
the canonical gate. It records the observed counters and fixed bounds, writes
`resource_admission.json` exclusively, fsyncs it and makes it0444, then refuses
before World when any requirement fails. A record-write failure also stops the
job before World. This is an admission policy, **not measured new-source fit**
or an assurance that resources stay available throughout a run.

The policy requires effective available RAM of at least8GiB, output-volume free
space after the build of at least16GiB,100000 available inodes, and at least3
effective CPU slots. RAM is the minimum of Linux `MemAvailable` and applicable
visible process/ancestor cgroup memory headrooms. Finite v2 `memory.high` and
positive v1 soft ceilings are conservatively included. CPU reuses the existing
`cpu_budget._cgroup_limits()` from the selected source, then combines visible,
process and affinity counts with audited v1/v2 quota floors. Unknown,
unreadable, malformed or unsupported required observations refuse. Conventional
visible Linux cgroup hierarchies are supported; hidden host constraints are not
claimed as measured. The snapshot is bounded to128KiB and records its scope.

The resource record links the exact own-build identity SHA256. Compact evidence
now requires that record, links its raw SHA256 and cannot be complete when
admission is absent, negative or joined to a different build. The old full raw
uploader remains byte-exact. The360-minute timeout, three workers, selected
source/controller distinction, scientific seeds/horizons/maps, oracle policy,
strictness defaults and thresholds do not change.

Three new singleton contract tests check source placement/custody plus the
exact pure policy with fake counters, including exact boundaries and nine
low/unknown/cgroup/affinity/type/error variants. They extract only the pure
function AST; no observation, filesystem, native or World collector executes
in those fakes. The whole f808 test prefix, including its four source contracts,
is preserved. All tests and controller actions remainUNRUN at this freeze.

## Aggregate local scientific evidence plan

The separately proposed local plan is a single80MiB aggregate envelope: six
original compact ZIPs at most8MiB each (48MiB), at most512KiB API/packet metadata
per cell (3MiB), at most2MiB derived review per cell (12MiB), one active extraction
lease of at most7MiB, and10MiB margin. This totals80MiB; scientific job logs are
not mandatory inputs. The existing24MiB per-cell ceiling is not reserved six
times simultaneously. No cap is increased and no multiGiB raw archive is
downloaded locally.

Original ZIPs remain immutable evidence. At most one extraction lease is live;
load a baseline report, release its temporary extraction, then load the matched
current report for the existing in-memory comparator API. Original ZIPs preserve
both exact report bodies. Any derived output exceeding its2MiB review budget
refuses that export rather than truncating evidence or changing gates. Root
must still check actual free space above the existing3GiB floor and every
actual artifact size before transfer. This plan and the inline admission do
not grant a dispatch or establish measured fit; all six scientific cells stay
held pending separate source, ordinary-test, build/API and execution decisions.

### Controller-observation correction (source-only successor of902a)

The unrun902a collector treated missing optional cgroup files as an absence of
limits. This successor preserves that source and its independent B1 finding;
it changes only the resource observation/translation seam and adds four pure
fake-reader/source cases. The seven prior workflow/resource cases remain
byte-exact, and all eleven focused cases are prospective and UNRUN.

Each control read is tagged value, missing or unavailable. Selected/enabled v2
controllers require the complete quota or memory max/high/current interface;
selected v1 controls require quota/period or limit/soft/usage. Unknown, denied,
malformed or missing-required data adds a refusal error even when host counters
would pass. Explicit v2 max and v1 quota -1 are separate unlimited observations.
Finite ancestor memory headrooms and integer CPU quota floors remain limiting.

A missing child interface is accepted only when readable parent controller and
subtree metadata establish that the controller is disabled for that child and
all its own control reads are absent. A missing root quota/limit interface is
accepted only with a conventional visible cgroupfs mount rooted at /, no nested
masking mount, and readable root controller availability. Controllers absent at
the root additionally need readable kernel metadata establishing disabled/not
applicable status or separately selected v1 coverage. Unavailable or contradictory
metadata refuses; no generic file-not-found or cgroup-directory exemption exists.
Kernel disabled/absent inference requires a recognizable nonempty validated
/proc/cgroups table; a blank/truncated table cannot authorize host fallback.
Partial v1 process memberships conservatively refuse if CPU or memory hierarchy
coverage is missing. The pure fake cases include both reviewed omissions.
These observations cover the visible process hierarchy and its visible ancestors;
they do not certify inaccessible host ancestry or measured source fit.

The immutable-ish pre-World resource JSON now includes controller translation
states and raw mount/kernel observations. Its existing128KiB bound, exclusive
write/fsync/0444 ordering and refusal behavior remain unchanged. The8GiB RAM,
16GiB output space,100000 inode and3CPU policy, workers/timeouts/seeds/horizons,
strict scientific gates, controller/source identities and compact raw-build hash
joins remain exact902a. No collector, native build/import, World, test or dispatch
was executed during source authoring. Real observations and scientific outcomes
remain unset. New source review and one root-approved focused attempt are held.
