# Prospective frozen full-gate qualification — 2026-10-28

Status: DRAFT. No active workflow and no gate worlds have been launched by this
draft. The proposed workflow is stored under docs/experiments/, outside the
active GitHub workflow directory. Activation requires internal lead review of
the combined controller, comparison reader, tests and workflow.

## Question and immutable sources

The baseline simulation source is 2f9d618b70f3304c02dcaeef12996b4a99e074c0.
The candidate is d0281e5f57c508f27cea1676f36e0e6ed1225c9d.
Every generation job uses a separate clean checkout of its exact source.
Qualification controls come from the actual workflow commit in another checkout.
Tracked source bytes, executable modes and clean standing are checked before
and after work. No simulation source, fixture, threshold or oracle is patched.

These sources bound the claim. This study does not compare the complete lead
branch against main, recover the inaccessible later local research integration,
or qualify held native prototypes. The completed default-output study at
control db7ec48b738fa841f1b951c3ae810aa121ef1918 is a separate 18-case,
3,200-turn exported-file identity result, not a substitute for these gates.

## One fresh shared binary

One builder checks crate-tree, uv.lock and pyproject equality between the frozen
sources, then compiles the candidate once with maturin build --release --locked
into a fresh external Cargo target and wheel directory. No compiled build cache
is restored. Source and lock inputs stay unchanged. A fresh external UV
environment uses the frozen lock without installing either simulation project;
explicit PYTHONPATH selects the intended source.

The loaded native submodule must be compiled, located inside that environment,
and byte-identical to the single compiled member of the retained wheel.
AgentSimulator, EcologySimulator and PoliticsSimulator must be the actual
classes exported by that compiled submodule. All three checkpoint schema
identities are recorded. The wheel hash, native hash, source identities, actual
Python patch, package versions, compiler/tool versions and build manifest are
retained before any simulation.

All downstream generation jobs download that same immutable wheel artifact,
check its manifest SHA and wheel SHA against builder outputs, and independently
verify the installed .so and classes. The exact Python 3.13 patch reported by the
builder is used in every downstream job. The build manifest is bound to the
actual GitHub run ID, run attempt and control commit; unrelated runs or attempts
cannot supply its wheel.

The builder has a 90-minute job limit and 80-minute aggregate controller budget.
Its disk/RAM admission is 12 GiB/2 GiB before compilation and 6 GiB/2 GiB after;
runtime command monitoring requires 3 GiB/1 GiB. These are build controls,
distinct from the full-cohort 330-minute execution budget.

## Real schema smoke before expensive full cohorts

Synthetic tests run before compilation or worlds, including consistent smoke
artifacts that the full comparison reader must reject as full evidence.

After the shared build, four fixed schema-smoke jobs run the unchanged source
runner, one for each source/world combination:

    python scripts/m53b_run_validation.py --profile subset \
      --seed-start 42 --seeds 2 --turns 125 --ablation-oracles \
      --worldgen template|procedural --parallel 2 --output-root FRESH

The worldgen argument is one literal value per job, never the displayed union.
No arbitrary argument passthrough is offered. Template smoke uses the default
8 regions/4 starting civilizations; procedural smoke uses the supported default
32 regions/10 civilizations. The sole fork label is T=100, with its checkpoint saved at World turn 101.
Needs and kin_roots each resume there to absolute turn T+22=122, for 21 actual
physics ticks and a separate 20-tick measured window.

Each smoke cohort requests two parents and four forks: 334 expected physics
ticks. Across four cohorts that is eight parents, 16 forks and 1,336 expected
physics ticks. The earlier nominal tally of 1,352 treated the fork label as the
resume World turn; source inspection corrected it before data. Failures retain
actual completion and unattempted work without relabelling it complete.

Smoke checks must confirm actual execution, complete horizons, expected cohort
and fork coverage, native/source/environment identities, report schema and
complete light/raw inventories. The original subset gate verdict is retained
whether PASS or FAIL. Smoke success means schema/execution admission only.
It does not establish full qualification, calibrate any oracle, select seeds,
or replace any full cohort.

Smoke jobs use two allowed CPUs via affinity, explicit parallel 2 and native/BLAS
thread caps of one. They have a 90-minute job limit and 80-minute aggregate
controller budget, with the same 20 GiB disk/6 GiB RAM pre-simulation and
3 GiB/1 GiB runtime floors as full generation. Their outputs and artifact names
are separate from all full-cohort inputs.

The four full jobs depend on successful completion of the entire smoke matrix,
including successful light and raw artifact collection. Matrix fail-fast is
disabled, so one smoke failure does not erase the other three outcomes. Any
incomplete smoke blocks all full jobs; no full seed, horizon or gate policy
changes to accommodate a smoke outcome.

## Four unchanged full cohorts

| Source | World | Parents | Parent turns | Regions / starting civs | Fork labels T | Forks |
| --- | --- | ---: | ---: | --- | --- | ---: |
| Baseline | template | 200 | 500 | defaults 8 / 4 | 100, 200, 300, 400 | 1,600 |
| Candidate | template | 200 | 500 | defaults 8 / 4 | 100, 200, 300, 400 | 1,600 |
| Baseline | procedural | 100 | 300 | defaults 32 / 10 | 100, 120, 140, 160, 180, 200, 220, 240, 260 | 1,800 |
| Candidate | procedural | 100 | 300 | defaults 32 / 10 | 100, 120, 140, 160, 180, 200, 220, 240, 260 | 1,800 |

The first seed is 42, as in the frozen full runner. Both registered arms are
needs and kin_roots. For each table label T, the checkpoint World turn is T+1,
the requested absolute endpoint is T+22, actual continuation is 21 physics ticks,
and the measured window is 20 ticks. Actual checkpoint filenames use T+1.
Across all full jobs this is 600 parents and 6,800 forks: 260,000 parent ticks
plus 142,800 fork ticks, or 402,800 expected physics ticks if complete. This is
separate from schema-smoke exposure.

Each full job invokes exactly the existing runner:

    python scripts/m53b_run_validation.py --profile full \
      --worldgen template|procedural --parallel 2 \
      --require-strict-regression --output-root FRESH

No baseline report is supplied during generation. Defaults supply the registered
full seeds, horizons, world sizes, ablation arms and checkpoint points. No
scenario, feature, threshold or method-version override is added. The original
strict gate policy decides; causal components remain informational under that
policy. A later separate adjudication does not replace it.

Each full job has a 360-minute job limit and a 330-minute aggregate controller
budget across installation, probes, generation, validation and finalization;
the budget is not reset between children. Two actual allowed CPUs are selected
through affinity. Python CPU visibility is two, the runner has explicit
parallel 2, and Rayon/OMP/OpenBLAS/MKL/BLIS/VECLIB/NUMEXPR/GOTO caps are one.
PYTHONHASHSEED is zero. No speed comparison is claimed.

Before simulation each job requires 20 GiB free disk and 6 GiB available RAM.
During execution the floors are 3 GiB and 1 GiB. Availability is constrained
by visible cgroup-v2 limits; missing declared nonroot visibility refuses
admission. Exempt hierarchy-root resource interfaces are recorded explicitly.
Charged cache receives no speculative reclaim credit. Bounded host/cgroup
visibility is printed and retained before admission. Floors and budgets are
prospective and are not reduced after observation.

## Checkpoints, failures and physical completion

The same original production checkpoint loader and complete native binary/schema/
environment identity checks apply within every cohort. No allow-mismatch,
fresh-pool substitution, checkpoint rewrite or saved-ID reassignment is used.
The frozen runner's ordinary checkpoint retirement after successful forks stays
unchanged. This controller adds no deletion, compaction or archive-retirement
operation.

The existing ablation manifest retains fork identities and output hashes but
does not retain an individual checkpoint SHA for every fork. Successful strict
checkpoint loading is execution evidence; this study does not invent a retained
per-checkpoint hash lineage after the source's normal retirement.

Commands run in owned private sessions. Leaders remain unreaped until verified
same-session processes are quiescent; pidfds protect signal targets. Cleanup
uncertainty prevents qualification and withholds stable inventory claims.
Timeouts, resource refusals, oracle failures, schema failures and partial work
are retained. No sample substitution, horizon reduction or preferred-host retry.

A full runner exit 0 or 2 may be inspected for structured physical completion.
Exit 2 is never converted into a full-gate pass: the controller preserves the
strict gate status and returns its original failing result. Execution completeness
and gate success are separate fields. Other failures stop the job. All four full
matrix jobs proceed independently with fail-fast disabled.

## Lightweight records first, complete raw output separately

Each cohort produces a bounded exact allowlist: at most 64 files, 32 MiB each
and 128 MiB total. Known full light artifacts have 11 fixed relative files, including the
unchanged validation report, gate decision, gate Markdown, run/batch/ablation
manifests, build manifest, cohort provenance, final receipt and artifact index.
The index hashes nine nonreceipt files; the final receipt pins the complete
index SHA. Neither the receipt nor index hashes itself. Missing required files,
extra files, index ambiguity, exceeded bounds or incomplete finalization refuse
light qualification. The original reports are copied byte for byte.

Light artifacts upload first, then complete raw evidence uploads separately on
success and failure. Full inventories hash raw files, logs and provenance
without deleting excluded comparison files. The shared wheel and builder
evidence are retained separately. Build caches and installed environments are
not scientific raw outputs and are not uploaded.

Artifact names include source role, world type, actual run ID and attempt.
Smoke artifacts have their own smoke prefix; the full reader never selects
them. No cross-run downloads or reusable report cache substitutes for fresh work.

A failed raw upload leaves the job/workflow failed. The scientific reader may
still preserve a valid comparison of retained light reports, but light records
alone cannot certify server-side publication. A separate standard-library
collector makes exactly one read-only current-run artifacts API request, with
per_page=100, a 1 MiB response cap, no redirects, no pagination and no retries.
Its job has actions:read only in addition to contents:read. The API token exists
only in that collector step, is removed from its environment before the request,
is never printed, and is absent from the frozen-reader step. Exact response text,
SHA, bounded metadata and any collection failure are retained.

The reader independently binds the index to the fixed repository, actual run,
attempt and control SHA. It checks the four exact full raw artifact names,
positive IDs/sizes, valid digests, nonexpired archives and matching workflow
identity. The workflow aggregate cohort result is separately recorded from
needs.cohorts.result; success proves all four generation/upload jobs succeeded.
No raw archives are downloaded by this metadata check.

Results distinguish scientific_comparison_pass from pipeline_qualified. The
latter can be true only after the scientific criteria, four raw publications
and successful cohort-job aggregate all verify. Missing API evidence yields
unknown retention/pipeline status; known missing publication or failed jobs
yield a false pipeline result. Neither can produce a green qualification exit.
A self-consistent all-scientific-PASS/raw-missing counterexample is tested.
Original oracle reports and comparisons remain unchanged in every outcome.
Root also reviews the actual artifact IDs/digests and workflow conclusions.

## Frozen comparison and separate causal adjudication

After all four full jobs finish, even if a strict oracle failed, a detached
reader imports the comparator and gate functions from an independently checked
clean candidate checkout at exact d0281e5f57c508f27cea1676f36e0e6ed1225c9d.
It accepts exactly four source/world-labelled light roots, with external
builder-manifest SHA, exact workflow control SHA and actual GitHub run/attempt anchors.

Before comparison, additional cross-VM admission requires identical Python patch,
implementation, machine architecture, thread environment, relevant package
versions, affinity count two and actual shared native/wheel/schema identities.
Full platform/kernel, executable, actual affinity mask, GitHub image and package
metadata remain in provenance. This additional admission cannot weaken the frozen
comparator. Reports reach it unmodified with strict full-profile and
non-exploratory settings and fail-on-regression. Missing fields, incomparable
cohorts, rebaseline requirements and unverified verdicts remain non-qualification;
no metadata scrubbing, reinterpretation or host retry repairs them.

Template compares only template; procedural compares only procedural of the
same registered size. Original gate decisions and comparisons remain intact.
A separate causal-required adjudication evaluates these same report bytes,
without rerunning worlds or replacing any original verdict. Its evidence and
status are explicitly separate from the original-policy outcome.

This is an outcome qualification on fixed sources, scenarios and one shared
compiled artifact. It does not establish natural efficacy of optional systems,
independence of observed groups, successful household optimization, full
checkpoint byte parity across sources, or a wall-clock speedup. Resource
accounting and exported evidence retain their actual limits.
