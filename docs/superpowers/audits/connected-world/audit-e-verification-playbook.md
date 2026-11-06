# Audit E: the verification playbook, the seed registry and the Program E design

Audit lane E of the connected-world program. Written 2026-11-06 against the shared checkout
`/home/user/Chronicler` on branch `claude/connected-world` at `a955e426` (the lead's plan of
record on top of `main` `8abc1acb`; `src/` and `chronicler-agents/` equal `8abc1acb`). This lane
was read-only: it ran no simulation, no oracle lane and no build. Commands it did run:
`scripts/refactor_preflight.py` (read-only), `sha256sum` on the reference extension, a
catalog-only matrix prototype (no runs; `proto/compat_matrix.py` here), `node -e
"require('playwright')"`, and GitHub MCP reads (`actions_list`, `get_job_logs`).

How to read this file. **Evidence** is `path:line` in the repository unless another location is
named. **UNVERIFIED** marks a statement nobody has checked on this source. **PROPOSAL** marks
something this audit recommends and nobody has built.

Files written by this lane (all under
the audit session's scratch directory, not retained):
`AUDIT-E.md` (this file), `preflight.json` and `preflight-summary.txt` (the 12 requested paths),
`preflight2.json` and `preflight2-summary.txt` (about 50 more paths an edit is likely to touch),
`proto/compat_matrix.py` and `proto/compat_matrix.json` (the catalog matrix prototype).

---

## Part 1: the per-slice verification playbook

Every slice (a PR into `main`) goes through the steps below in this order. A step is either
**run and recorded**, or **listed as unrun in the PR with the reason**. A gate that was not run
is never called complete (AGENTS.md, "Verification"). The table says when each step applies.

| Step | What | Required when |
| --- | --- | --- |
| V0 | lane clone, venvs, identities | always |
| V1 | preflight before editing; pinned-file plan | always (before the first edit of each file) |
| V2 | enrollment of new tests and modules | a test module, source module, switch or Rust module is added |
| V3 | focused tests, then the bounded offline lane | always |
| V4 | native build, environment check, native pytest, `cargo test` | any change under `src/` or `chronicler-agents/`, or any `*_native.py` test |
| V5 | feature-off identity against `8abc1acb` **and** the preceding integrated `main` | any change under `src/` or `chronicler-agents/` |
| V6 | enabled exact resume (`checkpoint_identity`), all switches, plus resume points at live events | any new or changed switch or persisted state |
| V7 | feature catalog and compatibility matrix | any new or changed switch or mode |
| V8 | viewer tests, lint, build; desktop and phone browser journey; old bundles | any change under `viewer/`, or a new snapshot record |
| V9 | narration provenance audit (no paid narrator) | stories, narration or new citeable records |
| V10 | held screen: pilot, preregistration freeze, held run, report, check | each integrated evaluation (sections 5 and 10) |
| V11 | profile at the declared scale | each slice that adds per-turn work or snapshot/checkpoint bytes |
| V12 | PR, independent review, premerge CI, merge, main CI | always |
| V13 | ledgers | always |

### Variables used below

```sh
LANE=<lane-name>                                  # e.g. s1-accounting
WT=/home/user/wt/$LANE                            # the lane's own clone (cp3's held run used /home/user/wt/held3)
EV=/home/user/evidence/$LANE                      # evidence outside every repository
NATIVE=$HOME/.venvs/native-$LANE                  # the lane's own native venv
PY=$NATIVE/bin/python                             # the interpreter of every native step
REF=8abc1acb3adf978ea212a570fb1dfbbfe9723ec3      # the original reference (the board's reference.original)
PREV=$(git -C $WT rev-parse origin/main)          # the preceding integrated main, read at slice start
REF_NATIVE_SHA=101a4cd5b928b14f43539f925fa565036b94e38d91b9698071c80fa3656e0df3
```

### V0. Lane clone, venvs and identities

Never edit, switch or stash in `/home/user/Chronicler` (shared; other agents work there).

```sh
git clone --branch main https://github.com/YotsuBotfds/Chronicler.git $WT
cd $WT && git switch -c claude/$LANE
git status --short --branch; git log --oneline -1
uv sync --frozen --python 3.13                     # .venv: the no-native lane
.venv/bin/python scripts/check_python_env.py --expect no-native
cd viewer && npm ci && cd ..                       # only if the slice touches the viewer
```

Native venv (at most two native builds at a time on the 4-core machine; plan section 1):

```sh
UV_PROJECT_ENVIRONMENT=$NATIVE uv sync --frozen --python 3.13
uv pip install --python $NATIVE/bin/python "maturin>=1.5,<2"
VIRTUAL_ENV=$NATIVE $PY -m maturin develop --release --locked --manifest-path chronicler-agents/Cargo.toml
PYTHONPATH=$WT/src $PY scripts/check_python_env.py --expect native    # prints the extension SHA-256
```

Two traps found by this audit:

- The shared native venv's editable install points at the shared checkout:
  `~/.venvs/chronicler-native/lib/python3.13/site-packages/_editable_impl_chronicler.pth`
  holds `/home/user/Chronicler/src`. A native venv's editable install follows the last checkout
  that synced it (docs/DEVELOPMENT.md, "Python environments"). Give every lane its own `$NATIVE`
  and always export `PYTHONPATH=$WT/src` for native steps.
- `scripts/checkpoint_identity.py` records neither the imported `chronicler` nor the extension
  (it only makes `PYTHONPATH` entries absolute: `scripts/checkpoint_identity.py:150-159`).
  `scripts/turn_speed_identity.py` does record both and refuses a wrong tree
  (`scripts/turn_speed_identity.py:105-121`). Record identities yourself for every native step:

```sh
mkdir -p $EV
{ git -C $WT rev-parse HEAD; git -C $WT status --porcelain --untracked-files=no | wc -l;
  PYTHONPATH=$WT/src $PY -c "import hashlib,chronicler,chronicler_agents.chronicler_agents as m;print(chronicler.__file__);print(m.__file__,hashlib.sha256(open(m.__file__,'rb').read()).hexdigest())";
  $PY -VV; rustc -V; node -v; } > $EV/identity.txt
```

### V1. Preflight before editing

```sh
cd $WT
.venv/bin/python scripts/refactor_preflight.py <every path you plan to change, move or delete>
.venv/bin/python scripts/refactor_preflight.py --git-diff origin/main      # before every PR (plan section 1)
.venv/bin/python scripts/refactor_preflight.py --git-diff origin/main --fail-on-enforced --json > $EV/preflight.json
```

An **enforced** finding means the edit breaks a witness chain unless a reviewed exact-inverse layer
lands with it (V2, "Edit to a pinned file"). Which commonly edited files are pinned, from this
audit's preflight runs (section 3.5): `simulation.py` (11 witnesses), `main.py` (9), `models.py`
(4), `agent_bridge.py` (3), `ecology.py` (1), `batch_manifest.py` (18), `tests/test_batch_manifest.py`
(14), `run_checkpoint.py` (4), `tuning.py` (4), `grain_reserves.py` (9), `economy.py` (5),
`grain_storage.py` (2), `live.py` (2), `chronicler-agents/src/{ffi/mod.rs (15), ffi/batch.rs,
ffi/ecology_sim.rs, ffi/schema.rs (3), economy.rs (6), ecology.rs, pool.rs (7), tick.rs (8),
lib.rs (6), region.rs}`, `viewer/src/types.ts` (5), `viewer/src/hooks/useLiveConnection.ts` (3),
`viewer/src/lib/granaries.ts`, `viewer/src/components/systems/GranaryStorage.tsx`;
`health_care.py` has a literal digest in `tests/test_health_care_policy.py:1023`. Not pinned:
`feature_catalog.py`, `household_retail.py`, `epidemiology.py`, `infrastructure.py`,
`livelihoods.py`, `livelihoods_state.py`, `war.py`, `politics.py`, `action_engine.py`,
`narration_provenance.py`, `narration_audit.py`, `bundle.py`, every viewer reader of the chain
except `granaries.ts`, and the screen and identity scripts.

### V2. Enrollment (what each kind of change requires)

**A new test module `tests/test_X.py`:**

1. Add it to exactly one shard of `scripts/testing/native_shards_manifest.json` (lists sorted).
   The native CI collects every module and refuses an unowned one ("assigned module absent from
   collection", `scripts/native_ci_shards.py:96-102`; "missing or unknown source module", `:88`).
2. Add `'tests/test_X.py': '<shard>'` to the `additions` map in
   `tests/test_native_ci_shards.py:191-293` and raise `assert len(owners) == 401` (`:294`) by one.
   `old_owners` (300) and its digest (`:297-301`) must not change: never move an old module.
3. If it is offline-safe (no native import, network or child process; the guard blocks them),
   add it to a chunk of `scripts/run_python_oracle_checks.py` (`CHUNKS`, `:20-443`; a node may
   be listed once, `:444-446`). PROPOSAL: one new chunk per program (`connected-world-a`, `-b`,
   `-c`, `-d`, `-e`); every existing chunk has large headroom anyway (section 3.2).
4. Do not use `subTest`/`subtests` unless you also change `expected_successful_subtests` (623),
   which `tests/test_native_ci_shards.py:315` pins and the CI aggregate checks
   (`scripts/native_ci_shards.py:261`). Prefer `pytest.mark.parametrize`.
5. Balance: CI shard 1 is the long pole (9 min 57 s of pytest against shard 0's 4 min 13 s on
   run 42176103870). The historical pattern puts `*_native.py` in shard 1 and Python tests in
   shard 0; PROPOSAL: put new heavy native modules in shard 0.

**A new source module `src/chronicler/Y.py`:**

1. Tests that walk `src/` must still pass: no module outside the allowed set may import
   `historiography` (`tests/test_historiography.py:570-583`; the same rule for `languages`,
   `tests/test_languages.py:476-490`); no file under `src/` may contain the strings
   `governance_sequence` (`tests/test_governance_sequence.py:505-509`) or
   `campaign_snapshot_adapter` (`tests/test_campaign_snapshot_adapter.py:1226-1230`). A story
   module that reads historiography must sit in that allowed set, which is an edit to the test.
2. A livelihoods package is found by name: `livelihoods._module(name)` imports
   `chronicler.<name>` (`src/chronicler/livelihoods.py:356-357`) for each name in
   `LIVELIHOODS_SWITCHES` (`src/chronicler/livelihoods_state.py:44-51`). It needs a state field on
   `LivelihoodsState`, `<name>_active`, `snapshot_summary`, a `COUNTERS` declaration in
   `<name>_state.py`, the parser entries (`LIVELIHOODS_ARG_KEYS`, `LIVELIHOODS_CHOICES`, `_HELP`
   in `livelihoods.py`), `feature_catalog.REQUIREMENTS` (V7) and the batch manifest keys (next item).
3. Every new CLI switch and mode goes into `batch_manifest.SIMULATION_ARG_KEYS`
   (`src/chronicler/batch_manifest.py:56-140`) **and** into the omit-when-None list of
   `simulation_config` (`:240-260`), so feature-off manifests keep their bytes; and into the
   expected key set of `tests/test_batch_manifest.py:141-143`. Both files are pinned: each
   livelihoods landing so far carried them in its layer (e.g. `pl1`, `pl3`, `pl4`).
4. A new Rust module needs a `mod` line in `chronicler-agents/src/lib.rs` (pinned, 6 witnesses);
   a new FFI method touches `ffi/mod.rs` (pinned, 15). Both need a layer. A change to the native
   checkpoint layout changes the schema fingerprint and old checkpoints are refused
   (docs/integration/checkpoint-continuation.md, sections 3-4); retail avoided this by keeping
   every native addition transient (docs/integration/household-retail-design.md:44).
5. Import compatibility: none for a new module; moving a helper must keep historical import paths
   (`tests/test_import_compatibility.py`) and string monkeypatch targets (DEVELOPMENT.md).

**An edit to a pinned file** (the reviewed exact-inverse procedure, docs/DEVELOPMENT.md
"Before refactoring"):

```sh
# after the edits are in the work tree, before committing the layer (lead-owned: plan section 1)
.venv/bin/python scripts/testing/livelihoods_layer_tool.py cw<slice><n> $(git merge-base HEAD origin/main) <pinned paths...>
#   writes tests/fixtures/livelihoods_cw<..>_source_inverse.json: read every hunk
# append the name to LAYERS (append only; never edit a landed layer):
#   scripts/testing/livelihoods_sprint_witness.py:25
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_livelihoods_sprint_witness.py \
  tests/test_restoration_candidate_witness.py tests/test_scenarios_candidate_witness.py \
  tests/test_information_qualification_witness.py tests/test_information_candidate_witness.py \
  tests/test_academy_candidate_witness.py tests/test_household_mobility_witness.py \
  tests/test_crisis_candidate_witness.py tests/test_food_accounting_witness.py \
  tests/test_grain_release_policy.py tests/test_public_grain_shipments.py \
  tests/test_regional_population.py tests/test_health_care_policy.py \
  tests/test_practice_observer_runner.py tests/test_native_ci_shards.py tests/test_refactor_preflight.py
```

Every historical witness projects current source through `before_livelihoods_sprint` first
(13 witness modules import it), so one appended layer serves all chains. The layer tool's
`PARENT_REV` is the source the layer inverts to: the bytes the previous layer produced (the
current `main` for the first layer of a slice). Never rewrite a fixture hash. The witness chunks
run first in the offline lane, which stops at the first failing chunk, so a broken layer hides
everything after it.

### V3. Focused tests, then the bounded offline lane

```sh
cd $WT
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_<slice>*.py tests/test_feature_catalog.py tests/test_batch_manifest.py
.venv/bin/python scripts/run_python_oracle_checks.py --list | grep test_<slice>        # enrolled?
.venv/bin/python scripts/run_python_oracle_checks.py --output-dir $EV/oracle             # about 4 min on the 4-core container
```

Keep the 110-second limit (`scripts/run_python_oracle_checks.py:19`). A timeout is investigated
and rerun under controlled load (plan section 1). The receipt (`$EV/oracle/receipt.json`) holds
the commit, the source hashes and each chunk's seconds. Passing it does not qualify native
execution or POSIX persistence.

### V4. Native

```sh
cd $WT && export PYTHONPATH=$WT/src
$PY scripts/check_python_env.py --expect native
$PY -m pytest -q -p no:cacheprovider tests/test_<slice>*_native.py tests/test_livelihoods_closure_native.py
cargo test --locked --manifest-path chronicler-agents/Cargo.toml      # about 1.5 min
sha256sum $NATIVE/lib/python3.13/site-packages/chronicler_agents/*.so >> $EV/identity.txt
```

Rerun after every Rust change; a previously installed extension is not evidence for the branch.

### V5. Feature-off identity (both references)

Byte identity of every output of the 9-case matrix (`scripts/turn_speed_identity.py:42-58`),
each side with its own source tree and its own extension. The reference side can be reused across
slices (same tool, same interpreter); keep its `which.txt`.

```sh
# once per reference
mkdir -p $EV/../ref-$REF/src-tree $EV/../ref-$REF/native
git -C $WT archive $REF src | tar -x -C $EV/../ref-$REF/src-tree
cp -a $HOME/.venvs/chronicler-native/lib/python3.13/site-packages/chronicler_agents $EV/../ref-$REF/native/
sha256sum $EV/../ref-$REF/native/chronicler_agents/*.so        # must be $REF_NATIVE_SHA (checked 2026-11-06)
$PY scripts/turn_speed_identity.py run $EV/../ref-$REF/out --source-root $EV/../ref-$REF/src-tree \
    --native-root $EV/../ref-$REF/native
# PREV (if not REF): the same with git archive $PREV and that main's extension (build it into
# its own venv when its Rust differs from REF's; copy chronicler_agents as above)

# the head under test (the committed tree; never a dirty work tree)
mkdir -p $EV/head/src-tree $EV/head/native
git -C $WT archive HEAD src | tar -x -C $EV/head/src-tree
cp -a $NATIVE/lib/python3.13/site-packages/chronicler_agents $EV/head/native/
$PY scripts/turn_speed_identity.py run $EV/head/out --source-root $EV/head/src-tree --native-root $EV/head/native
$PY scripts/turn_speed_identity.py compare $EV/../ref-$REF/out $EV/head/out    # expect: 9 cases, 399 files compared, 0 differences
$PY scripts/turn_speed_identity.py compare $EV/../ref-$PREV/out $EV/head/out
cat $EV/../ref-$REF/out/which.txt $EV/head/out/which.txt                     # retain
```

Then, for each new switch, the same with every prerequisite on and the switch absent, and with the
explicit `--no-<switch>` (livelihoods switches are `BooleanOptionalAction`:
`src/chronicler/livelihoods.py:318-327`), on hybrid cases only (an `off` case refuses a hybrid
switch), as `docs/integration/timber-supply.md:474-485` did:

```sh
P=(--cli-arg=--grain-reserves --cli-arg=--public-grain-shipments --cli-arg=--grain-storage --cli-arg=--workshops <prereqs of the switch>)
$PY scripts/turn_speed_identity.py run $EV/../ref-$REF/prereq --case hybrid_s42 --case proc48_hybrid_s42 \
    --source-root $EV/../ref-$REF/src-tree --native-root $EV/../ref-$REF/native "${P[@]}"
$PY scripts/turn_speed_identity.py run $EV/head/prereq --case hybrid_s42 --case proc48_hybrid_s42 \
    --source-root $EV/head/src-tree --native-root $EV/head/native "${P[@]}"
$PY scripts/turn_speed_identity.py run $EV/head/prereq-no --case hybrid_s42 --case proc48_hybrid_s42 \
    --source-root $EV/head/src-tree --native-root $EV/head/native "${P[@]}" --cli-arg=--no-<switch>
$PY scripts/turn_speed_identity.py compare $EV/../ref-$REF/prereq $EV/head/prereq
$PY scripts/turn_speed_identity.py compare $EV/../ref-$REF/prereq $EV/head/prereq-no
```

Any intended default-path change (a bug fix included) goes behind a switch or a rules version
(owner amendment); the identity must then still be 0 differences with the switch off, and the
change is recorded for the owner. Durations of a full matrix run are not recorded anywhere in
the repository (UNVERIFIED; the lead's baseline run should record them).

### V6. Enabled exact resume

The all-switch case as earlier phases ran it: every livelihoods switch with its prerequisites,
retail in every region (`--household-retail-boundary all`), on `hybrid_s42_long` (200 turns, the
19-turn spread, `scripts/checkpoint_identity.py:96-97,118`) and `proc32_hybrid_s11` (40 turns).
The exact flag list of earlier runs is not recorded; the list below is the catalog's all-on set
(it validates: section 2.3), plus the program's new switches.

```sh
cd $WT && export PYTHONPATH=$WT/src                 # required (V0)
ALL=(--grain-reserves --public-grain-shipments --grain-storage --scholarship --academy-services --workshops
     --food-allocation --timber-stock --grain-convoys --commons-rules --learning-cohorts --workshop-payroll
     --relocation-costs --local-budgets --apprenticeship --repair-projects --veteran-reintegration --remittances
     --clearing-protection --operating-wear --timber-supply --recovery-crews --maintenance-obligation
     --household-retail --household-retail-boundary=all <every program switch>)
A=(); for f in "${ALL[@]}"; do A+=("--cli-arg=$f"); done
$PY scripts/checkpoint_identity.py run $EV/ckpt-long --case hybrid_s42_long --jobs 2 "${A[@]}"
# straight run kept to choose resume points at live events:
$PY scripts/checkpoint_identity.py run $EV/ckpt-probe --case proc32_hybrid_s11 --ks 20 --keep --jobs 2 "${A[@]}"
#   read $EV/ckpt-probe/proc32_hybrid_s11/straight/chronicle_bundle.json for turns with a live
#   transaction, shipment in flight, infrastructure work, outbreak, war start/end/occupation;
#   then:
$PY scripts/checkpoint_identity.py run $EV/ckpt-proc --case proc32_hybrid_s11 --ks <k1,k2,...> --jobs 2 "${A[@]}"
grep -h '"pass"' $EV/ckpt-*/*/report.json
```

`--cli-arg` must use the `=` form (a bare `--cli-arg --x` is read as an option). `--ks` applies to
every case of one invocation, so run cases with chosen points separately. Each `report.json`
also holds `checkpoint_bytes` per turn (`scripts/checkpoint_identity.py:245`): keep it for V11.
A case passes when writing checkpoints changes nothing and every resume equals the straight run,
file by file (`run_manifest.json` and `*.log` ignored: `scripts/cities_identity.py:29,68-85`).

The owner asks for resume points *inside* live transactions, shipments, infrastructure work,
outbreaks and war transitions. The existing cases rarely guarantee these; PROPOSAL (E-owned): a
small `scripts/resume_points.py BUNDLE --kinds expedition,shipment,works,outbreak,war` that lists
the turns where each kind is live, read from the dated snapshot records, so `--ks` is chosen from
evidence, plus a procedural 200-turn case on a development world (procedural 21 or 31) added to
`CASES` for war and outbreak coverage. Unit tests carry the rest: rollback, duplicate and stale
receipts, stable-id lifecycle (death, birth, migration, conquest, roster rebuild) and the refusal
of unsupported resumes (a legacy JSON state file with a program switch on; a checkpoint with a
prerequisite off: `livelihoods_resume_conflicts`, `src/chronicler/main.py:2526-2527`).

### V7. Feature catalog and compatibility matrix

```sh
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_feature_catalog.py
PYTHONPATH=src .venv/bin/python <matrix script> --json $EV/compat_matrix.json   # PROPOSAL: tests/test_feature_matrix.py (section 2.3)
```

Every new boolean feature declares `REQUIREMENTS` (`src/chronicler/feature_catalog.py:94-120`);
`test_catalog_requirements_agree_with_the_run` then checks catalog and run agree on every
minimal selection and its neighbours on both the CLI and live paths
(`tests/test_feature_catalog.py:219-315`). Refresh `viewer/src/__fixtures__/featureCatalog.json`
when the served shape changes (`tests/test_feature_catalog.py:637-653`).

### V8. Viewer

```sh
cd $WT/viewer
npm test -- --maxWorkers=2 && npm run lint && npm run build        # about 2 min
# the slice's own browser QA (modelled on scripts/qa-recovery-chain.mjs), development worlds only:
PYTHONPATH=$WT/src PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 node scripts/qa-<slice>.mjs \
    --out $EV/qa-<slice>-t23 --python $PY --seed 23 --turns 60
PYTHONPATH=$WT/src PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 node scripts/qa-<slice>.mjs \
    --out $EV/qa-<slice>-p31 --python $PY --worldgen procedural --seed 31 --turns 120
# old bundles and the shell, before (main) against after (branch) production builds:
mkdir -p $EV/main-viewer && git -C $WT archive $PREV viewer | tar -x -C $EV/main-viewer
(cd $EV/main-viewer/viewer && npm ci && npm run build)
node scripts/qa-shell-journeys.mjs --build before=$EV/main-viewer/viewer/dist --build after=$WT/viewer/dist \
    --bundle src/__fixtures__/sample_bundle.json --bundle src/__fixtures__/faiths_legacy_bundle.json --out $EV/qa-shell
```

The QA must cover 1440x900 and 390x844 (touch), no console or page errors, no NaN/undefined
text, no horizontal page overflow at 390 px, and the off / unknown / malformed / recorded-zero
wording (section 6). Whether `qa-shell-journeys.mjs` loads those two fixtures as given is
UNVERIFIED (it expects complete bundles; use two saved development-world bundles of `main` if not).

### V9. Narration provenance (no paid narrator)

```sh
cd $WT && export PYTHONPATH=$WT/src
$PY -m chronicler.main --seed 23 --turns 60 --agents hybrid <switches> --simulate-only --narrator mechanical \
    --output $EV/story/chronicle.md --state $EV/story/state.json
$PY -m chronicler.main --narrate $EV/story/chronicle_bundle.json --narrator mechanical \
    --narrate-output $EV/story/narrated.json
$PY -m chronicler.narration_audit $EV/story/chronicle_bundle.json --narrated $EV/story/narrated.json \
    --json $EV/story/audit.json          # exit 1 on any flag
.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_narration_provenance.py tests/test_narrative.py
```

Never pass `--narrator api` or `gemini` (paid), and do not rely on the default `local`
(LM Studio). Tests use `ScriptedClient` fakes (`tests/test_narration_provenance.py:207`).

### V10. Held screens

```sh
cd $WT                                                       # a clone at the frozen commit, clean
$PY scripts/<program>_screens.py check --screen <S>          # extractor, seeds, arms
$PY scripts/<program>_screens.py run $EV/pilot-<S> --screen <S> --cohort pilot --jobs 2
$PY scripts/<program>_screens.py check --screen <S> --metrics $EV/pilot-<S>/metrics.jsonl --cohort pilot
$PY scripts/<program>_screens.py report $EV/pilot-<S>/metrics.jsonl --screen <S>   # projected core-hours
# lead: write "Status: FROZEN" with the commit into the preregistration; merge it first
$PY scripts/<program>_screens.py run $EV/held-<S> --screen <S> --cohort held --jobs 3
$PY scripts/<program>_screens.py report $EV/held-<S>/metrics.jsonl --screen <S> > $EV/held-<S>/report.md
$PY scripts/<program>_screens.py check --screen <S> --metrics $EV/held-<S>/metrics.jsonl --cohort held
```

The runner is a PROPOSAL (section 5.2); the commands mirror `scripts/productive_recovery_screens.py`
(`:1-35`). Retain `metrics.jsonl`, `report.md` and `source.txt` under
`docs/superpowers/progress/<screen>/` as cp3 did
(`docs/superpowers/progress/productive-recovery-screens-cp3/`); delete raw outputs.

### V11. Profiling at the declared scale

Section 8.2. Record CPU (wall and process), peak RSS, bundle, state and output bytes, and
checkpoint bytes and write/read time, for switches off against on, at the declared worlds.

### V12. PR, review, CI, merge

1. `refactor_preflight.py --git-diff origin/main`; the PR lists every unrun check and why.
2. Independent review from the actual source, diff, specification and tests (not from the PR
   text); fixes carry regression tests; the review names the head it reviewed.
3. Premerge CI on the reviewed head: Tests triggers on `pull_request` (pushes trigger only for
   `main` and some old lead branches: `.github/workflows/tests.yml:3-7`). Verify with MCP:

```text
mcp__github__actions_list  method=list_workflow_runs owner=YotsuBotfds repo=Chronicler resource_id=tests.yml
                           workflow_runs_filter={"branch": "<head branch>", "event": "pull_request"}
   -> the run whose head_sha == reviewed head SHA; status completed, conclusion success
mcp__github__actions_list  method=list_workflow_jobs resource_id=<run id>
   -> total_count 9, every conclusion success: Python bounded offline, Python no-Rust,
      Build one current-source native wheel, Python native module shard 0, shard 1,
      Python native execution, Rust, Python native, Viewer
mcp__github__get_job_logs  run_id=<run id> failed_only=true return_content=true tail_lines=200   (on failure)
```

4. Merge through the PR only (no direct push, no force-push). Check that the merge tree equals the
   reviewed head's tree (`git rev-parse <merge>^{tree} <head>^{tree}`), as every prior record did.
5. Main CI: `list_workflow_runs` with `{"branch": "main", "event": "push"}`, the run whose
   `head_sha` is the merge commit, completed and success, 9 jobs. If main goes red, freeze feature
   merges until it is repaired or reverted through a PR (owner amendment).

### V13. Ledgers

Board `docs/superpowers/progress/connected-world.json` (slice status, native SHA, verification,
merges, `next`), `docs/CONTINUATION.md` (a dated top section like the cp1-cp3 ones),
`docs/superpowers/progress/phase-6-progress.md`, and the slice's integration page.

---

## 2. Question 1: identity tooling

### 2.1 `scripts/turn_speed_identity.py`

- Cases (`:42-58`), each `(CLI args, starting-agent target)`:

| Case | Arguments | Turns |
| --- | --- | --- |
| `off_s42` | `--seed 42 --agents off` | 300 |
| `off_s7` | `--seed 7 --agents off` | 300 |
| `hybrid_s42` | `--seed 42 --agents hybrid --validation-sidecar` | 200 |
| `hybrid_s7` | `--seed 7 --agents hybrid --validation-sidecar` | 200 |
| `hybrid_s1234` | `--seed 1234 --agents hybrid` | 200 |
| `proc48_hybrid_s42` | `--seed 42 --regions 48 --civs 10 --agents hybrid --validation-sidecar` | 150 |
| `proc48_off_s7` | `--seed 7 --regions 48 --civs 10 --agents off` | 200 |
| `scaled22k_s42` | `--seed 42 --regions 12 --civs 4 --agents hybrid --validation-sidecar`, 18,800 agents | 30 |
| `scaled52k_s7` | `--seed 7 --regions 12 --civs 4 --agents hybrid`, 43,700 agents | 20 |

  Scaled cases multiply capacities and populations in the child (`:60-78`). Every run uses
  `PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 CHRONICLER_QUIET=1` (`:81-95`), `--simulate-only`, and
  writes `chronicle.md`, `chronicle_bundle.json`, `state.json` and sidecars into `OUT/<case>`.
- `--source-root` must be a checkout root holding `src/chronicler/__init__.py`; the tool
  refuses otherwise and refuses when the runs would import `chronicler` from elsewhere
  (`:109-121`). That refusal was added after #74's evidence compared one tree twice
  (docs/superpowers/roadmaps/recovery-skills-phase.md:373-374). `--native-root` is a directory
  holding a saved `chronicler_agents` package, put first on `PYTHONPATH` (`:86-92`).
  `which.txt` at the output root records the imported tree and extension SHA-256 (`:113-116`).
- `compare BASE NEW` compares every file of every case byte for byte (bundles decoded, without
  `metadata.generated_at`), plus each bundle's raw bytes with only `generated_at` blanked
  (`:142-154,314-341`); the `"9 cases, 399 files compared, 0 differences"` line is its output.
  `--faith-ids` is for the permanent-faith change only.
- **How prior checkpoints ran it**: each side an exported tree (`git archive`) with its own
  extension, via `--source-root`/`--native-root` (docs/integration/dev-lead-2026-10-28.md:95-97;
  CONTINUATION.md:166-167 "each with its own extension, checkout roots";
  docs/integration/timber-supply.md:474-485). Exact commands: V5 above.
- **How new switches enter**: never into `CASES` (they are the default path). `--cli-arg`
  (repeatable, `:352-353`) appends an argument to every case run, which is how "prerequisites on,
  switch off" and "explicit `--no-<switch>`" variants were run (timber-supply.md:479-482;
  domestic-credit.md:1062).

### 2.2 `scripts/checkpoint_identity.py`

- Ordinary cases (`:75-114`): `off_s42`, `off_s7_scholarship`, `off_s42_minimal` (every default
  system off), `hybrid_s42`, `hybrid_s7_scholarship`, `hybrid_s1234_fast`, `demographics_s42`,
  `shadow_s42`, `proc32_hybrid_s11` (`--regions 32 --civs 8 --worldgen procedural`, 40 turns),
  `proc48_hybrid_s42_scholarship`, and the long ones `off_s42_long` (300), `hybrid_s42_long`
  (200), `hybrid_s7_long_scholarship` (200), `proc48_off_s7_long`, `proc48_hybrid_s42_long`
  (150), `scaled22k_s42`, `scaled52k_s7`, `proc32_hybrid_s42_recycling` (200). Short cases
  resume at every turn 1..N-1; long ones at `SPREAD = (1, 2, 3, 5, 8, 13, 21, 34, 35, 40, 46,
  55, 89, 99, 100, 101, 110, 144, 233)` below N plus N/2 and N-1 (`:118-124`).
- Live cases `live_hybrid_s42`, `live_proc32_hybrid_s11`, `live_off_s42` (`:293-304`) and
  interactive cases `interactive_hybrid_s42`, `interactive_off_s42` (`:593-604`).
- Per case: `plain` (no checkpoints), `straight` (a checkpoint every turn, non-K pruned), then
  one `resume_k` per k; compares plain with straight and every resume with straight
  (`:196-283`); writes `report.json` with `checkpoint_bytes` per turn (`:245`). `--jobs` is 1 or
  2 (`:772`); `--keep` keeps the runs; `--resume-hash-seed` varies the resumed hash seed.
- It has **no `--source-root`/`--native-root`**: it runs `sys.executable -m chronicler.main`
  with the caller's `PYTHONPATH` (`:150-172`) and records no identities. Run it from the lane
  clone with `PYTHONPATH=$WT/src` and record identities (V0).
- **How prior checkpoints ran "all-switch"**: `--cli-arg=<flag>` per switch on
  `hybrid_s42_long` (19 resume points) and `proc32_hybrid_s11` with chosen `--ks` (9 resume
  points at cp1, five inside a live expedition; 10 at cp2 with retail in every region)
  (CONTINUATION.md:97-98,168-169; productive-recovery.json `verification` fields). Earlier
  sprints recorded full commands, e.g. `checkpoint_identity.py run OUT --case hybrid_s42 --ks
  10,17,19,21,30,45,59 --jobs 2 --cli-arg=--grain-reserves ... --cli-arg=--grain-convoys`
  (docs/superpowers/progress/livelihoods-sprint1-screens.md:159-161) and with
  `--cli-arg=--seed=1` to move the world (docs/integration/commons-rules.md:377-379). The exact
  cp2/cp3 flag list and `--ks` values are not recorded (UNVERIFIED); V6 gives the reconstruction.

---

## 3. Question 3: test enrollment, witnesses and pins

### 3.1 The offline runner

63 chunks, 296 node entries (counted from `CHUNKS`, `scripts/run_python_oracle_checks.py:20-443`;
cp1 recorded 62, cp2 added `household-retail`). Each chunk is one pytest process with the guard
`python_oracle_guard` (`-p python_oracle_guard`), `PYTHONPATH=src:.:scripts/testing` (`:468`),
`-k` deselecting the two cross-process determinism cases (`:447-448`), a 110-second limit, and the
lane stops at the first failure (`:490-516`).

### 3.2 Chunk timings (headroom)

From the CI log of main run 42176103870 (merge `c4c17c98`, job 127754814297; GitHub runner):
lane 210.7 s. Largest chunks: `systems-2` 21.3 s, `core` 20.4 s, `live-checkpoints` 16.4 s,
`systems-1` 11.7 s, `governance` 9.7 s, `validation-tooling` 9.0 s, `narration` 5.3 s,
`grain-storage-contracts` 5.3 s; every other chunk is under 5 s, including `livelihoods` 4.2,
`recovery-skills` 3.3, `household-retail` 2.2, `timber-supply` 1.6, `productive-recovery-pl3`
1.9, `feature-options` 2.5, `checkpoint` 3.3, `expansion-wiring` 2.3. Every chunk has more than
80% headroom on CI. On the shared 4-core container the lead's run in progress at 16:00 UTC
(`output/python-oracle/20261106T155936425643Z/`, pytest's own times) showed `core` 30.4 s and
`systems-2` 29.2 s, so local times are about 1.5x CI's; still large headroom. Historical
largest-chunk records: 18.5-32.4 s of 110 s (phase-6-progress.md:1907, 2421, 2462, 2511).

### 3.3 Native shard manifest

`scripts/testing/native_shards_manifest.json`: schema 1, two shards, 208 modules in shard 0 and
193 in shard 1 (401), 6 expected skips, 623 expected successful subtests. Enforced by
`scripts/native_ci_shards.py:77-102,261` and pinned by
`tests/test_native_ci_shards.py:187-315` (the `additions` map of 101 modules, `len(owners) ==
401`, the 300 old owners' digest, `historical_module_counts == [159, 140]`, the skip list, 623).

### 3.4 Witness layers

`scripts/testing/*_witness.py` project current source back through each reviewed candidate's
patches (`tests/fixtures/*_source_inverse.json`) and compare hashes at each step. The livelihoods
sprint layers (`scripts/testing/livelihoods_sprint_witness.py:25`, 26 layers `l0` ... `pl4`,
baseline `64863f1`) are applied newest first by every historical witness, so a new reviewed
layer drafted by `scripts/testing/livelihoods_layer_tool.py` (`:1-15`) is the standard route.
`tests/test_livelihoods_sprint_witness.py` checks the layers are well formed, chain to each other
and reach the baseline. `scripts/testing/reviewed_main_witness.py` is the earlier hand-written
form for `main.py` repairs.

### 3.5 Preflight results (the requested paths)

From `refactor_preflight.py --json` (files listed above under "Files written").

| Path | Level | What a change requires |
| --- | --- | --- |
| `src/chronicler/simulation.py` | enforced: 11 source witnesses (academy, crisis, food accounting, household, livelihoods `l0`/`rs5`/`rv2`/`s1r`, public grain shipments source and composition, regional population); 124 importers, 8 string targets | a reviewed livelihoods-style layer; read the string monkeypatch targets |
| `src/chronicler/main.py` | enforced: 9 (academy, crisis, food accounting, household, information, `r3`, public grain shipments x2, regional population); 155 importers, 26 string targets | layer; `reviewed_main_witness.py` history; many patch targets |
| `src/chronicler/models.py` | enforced: 4 (food accounting, household, `l0`, regional population); 366 importers | layer |
| `src/chronicler/agent_bridge.py` | enforced: 3 (household, `rs5`, `rv1`); 120 importers, 10 string targets | layer |
| `src/chronicler/feature_catalog.py` | reference only (5 importers) | tests; `featureCatalog.json` fixture |
| `src/chronicler/household_retail.py` | reference only | tests; screens cp2/cp3 extractors read its fields |
| `src/chronicler/ecology.py` | enforced: 1 (`rs5`); 74 importers | layer |
| `src/chronicler/epidemiology.py` | reference only (15 importers) | tests; `scripts/epidemiology_identity.py` exists |
| `src/chronicler/infrastructure.py` | historical only; 18 importers | tests |
| `chronicler-agents/src/ffi` (directory) | the tool takes files: see rows below | |
| `ffi/mod.rs` | enforced: 15 | layer |
| `ffi/batch.rs`, `ffi/ecology_sim.rs` | enforced: 1 each (`rs5`) | layer |
| `ffi/schema.rs` | enforced: 3 (academy, crisis, food accounting) | layer |
| `ffi/politics_sim.rs`, `ffi/*_tests.rs` | reference only | |
| `chronicler-agents/src/economy.rs` | enforced: 6 (academy, crisis, food accounting, `l1a`, `pl1`, `pl4`) | layer |
| `chronicler-agents/src/ecology.rs` | enforced: 1 (`rs5`) | layer |

The tool cannot see runtime-built paths, `inspect.getsource`, whole-tree digests, behavioural
goldens or TS/Rust module graphs beyond literal imports (its own `not_covered` list), so "no known
pins" is not a safety proof.

---

## 4. Question 4: CI

### 4.1 The nine jobs (`.github/workflows/tests.yml`)

Durations from main run 42176103870 (`c4c17c98`, 2026-11-06), whole run 06:42:06-06:55:32
(about 13.5 min wall):

| Job (`id`, name) | What it runs | Duration |
| --- | --- | --- |
| `python-offline` "Python bounded offline" (`:13-66`) | `uv sync --frozen`, asserts no native, `run_python_oracle_checks.py` | 3 m 43 s (lane 210.7 s) |
| `python-no-rust` "Python no-Rust" (`:67-166`) | turn-wrapper preflight under the guard (110 s), then `python -m pytest -q` (full suite without the extension) | 5 m 21 s (pytest 5 m 06 s) |
| `python-native-build` "Build one current-source native wheel" (`:167-339`) | module-assignment admission, wrapper preflight, `maturin build`, build record | 2 m 32 s (build 1 m 52 s) |
| `python-native-tests` "Python native module shard 0" (`:340-410`, matrix) | verifies and installs the wheel, full collection, runs the shard's modules | 4 m 32 s |
| same, "Python native module shard 1" | same | 10 m 21 s (the long pole) |
| `python-native-shard-aggregate` "Python native execution" (`:411-470`) | exact-once parent and subtest ownership across shards | 20 s |
| `rust` "Rust" (`:471-514`) | `cargo test --locked` | 1 m 19 s |
| `python-native` "Python native" (`:515-530`) | requires aggregate and Rust success | 4 s |
| `viewer` "Viewer" (`:531-559`) | Node 20.19.0, `npm ci`, `npm test -- --maxWorkers=2`, `npm run lint`, `npm run build` | 2 m 31 s |

Baseline main is green: run 42179473371 on `8abc1acb` (push, success, 07:13-07:28 UTC).
Verification procedure: V12.

---

## 5. Question 5: screens, the seed registry and cohorts

### 5.1 How `scripts/productive_recovery_screens.py` is built

- **Checkpoints** are namespaces (`CP1` = module globals via `_ModuleCheckpoint`, `CP2`, `CP3`
  classes; `CHECKPOINTS = {1: CP1, 2: CP2, 3: CP3}`, `:62-77,1303,1750,1836`) offering the same
  names: `BASE`, `ARMS`, `PACKAGES`, `OPTIONS`, `MODE_KEYS`, `PILOT`, `HELD`, `NEVER_RUN`,
  `RESERVED`, `DEVELOPMENT`, `PRIOR_HELD`, `OUTCOMES`, `PAIRED`, `DECLARED_PAIRS`, `LABELS`, and
  the functions `declared_counters`, `source_problems`, `metrics_row`, `annotate_pairs`,
  `report_extra`.
- **Arms**: `ARMS: {arm: (flags added to BASE, control arm)}`, a tree rooted at `ROOT`
  (`:92-106`, CP3 `:1768-1777`). Each arm's flags must configure exactly the packages and modes
  `PACKAGES` names (`check_arm_flags`, `:351-396`, on a constructed world through the real parser
  and `configure_livelihoods`).
- **Outcomes**: `OUTCOMES` lists package counters read, each validated against the package's
  declared `COUNTERS` (`check_extractor`, `:294-348`); `PAIRED` is the executable list of
  `(label, arm, control, function)` with primaries marked (CP3: 81 outcomes, 2 primary); every
  pair must be declared. A missing or malformed outcome makes the run rc 3, never zero (`:1-35`,
  `run_one` `:1869-1896`).
- **Seeds**: `check_seeds` (`:260-291`) asserts per stratum that pilot and held are disjoint
  from every earlier cohort and pilot (it also reads the sprint 1-3 strata from
  `livelihoods_screens.py`), from reserved cohorts and development worlds, and that earlier
  checkpoints' held cohorts are in `NEVER_RUN`.
- **Freeze**: a held run refuses unless the preregistration has a `Status:` line containing
  FROZEN and not DRAFT (`preregistration_frozen`, `:1841-1848`; `run_main` `:1948`).
- **Timing pilot and budget**: `report` on pilot rows prints the projected held core-hours
  (`projected_held_core_hours`, `:2104-2115`, mean pilot seconds per arm and stratum times held
  worlds). The budget itself (2.0 core-hours, 3 processes, 6 GiB disk) lives in the
  preregistration and is not enforced by code.
- **Run/report/check**: `run` writes `source.txt` (commit and dirty flag, imported `chronicler`,
  extension SHA-256, interpreter; `livelihoods_screens.source_identity`,
  `scripts/livelihoods_screens.py:570-582`) and one `metrics.jsonl` row per run as it finishes;
  `--resume` refuses another source, extension, interpreter, checkpoint or cohort (`:1932-2021`);
  `report` prints per-world tables, sign counts and activation funnels (`:2030-2097`); `check
  --metrics` requires exactly one passing row per arm and world (`:2145-2166`).
- The preregistration (docs/superpowers/progress/productive-recovery-screens-cp3.md) has the
  sections: status/freeze line, purpose and limits, units (worlds), source and budget, seeds,
  arms, outcomes (definitions, primaries, structural zero vs unknown, quantities the snapshot does
  not hold), extractor validation, incomplete runs and stopping rules, timing pilot, amendments,
  lead decisions, results.

### 5.2 A runner for this program (PROPOSAL)

A new script, not an extension of `productive_recovery_screens.py`: that file (2,205 lines) and
its three test modules are frozen evidence of three preregistrations, and its package checks are
tied to `LIVELIHOODS_SWITCHES`, which B, C and D packages may not join. Suggested shape:

- `scripts/screen_runner.py`: the generic `run`/`report`/`check`/`--resume` skeleton, lifted from
  `productive_recovery_screens.py:1841-2166` and `livelihoods_screens._run_env`/`source_identity`,
  parametrised by a `Screen` namespace.
- `scripts/connected_world_screens.py`: one `Screen` per program screen (`--screen CW1`...).
- `scripts/seed_registry.json` (data) with every historical cohort of section 5.3, each entry
  `{source, use, stratum, world, seeds, turns, status}`; `check_seeds` derives `NEVER_RUN` from it
  and refuses any held or pilot seed in it, in the gate ranges, in a development world or in
  another program screen's cohort.
- Generalised package validation: a package is any registered switch with a `COUNTERS`
  declaration and a dated snapshot record (`schema_version`, `source_turn`); the screen lists
  `(snapshot path, counters module)` per package.
- Enforced preregistration: 2-3 primaries per screen (check refuses otherwise); a fixed **harm
  panel** shared by every screen (population, treasury, food shortfall after relief, priced-out
  persons and children, deaths by authority (famine, epidemic, war), migration out, wealth Gini,
  forest stand share of capacity); activation per world (did the mechanism act?) reported before
  any effect; non-activated worlds reported as such, never as zeros.
- Identities per run: the existing four lines plus the runner's own SHA-256 (extractor identity),
  the registry's SHA-256, and the schema versions read (bundle version, livelihoods schema, each
  package record's `schema_version`).
- Budget enforcement: the preregistration's ceiling is machine-read; `run --cohort held` refuses
  when the pilot projection times 1.5 exceeds it, and stops starting runs when the ceiling is
  reached (the unfinished runs then show as `not run`).
- Uncertainty without significance claims: per stratum mean, min/max, sign counts (as now) and
  the exact paired sign-flip distribution over the 6 worlds (64 assignments) as a descriptive
  interval; nulls stated as nulls; harms beside every effect.

### 5.3 The historical seed registry

Seeds are per stratum: template `--seed N` (CLI default 8 regions x 4 civs unless noted) and
procedural `--worldgen procedural --regions 32 --civs 10 --seed N` are different worlds.

| Source (evidence) | Use | Template | Procedural 32x10 | Turns |
| --- | --- | --- | --- | --- |
| `scripts/livelihoods_screens.py:43-44`; livelihoods-sprint1-screens.md:19-20 | sprint 1 held (run) | 101-106 | 201-206 | 200 |
| livelihoods-sprint1-screens.md:17-18; livelihoods-commons-sprint1.json | sprint 1 development | 1-3 | - | |
| `scripts/livelihoods_screens.py:79-80`; livelihoods-sprint2-screens.md:27-28 | sprint 2 held (run) | 301-306 | 401-406 | 200 |
| livelihoods-sprint2-screens.md:19-26 | sprint 2 timing pilot; development | 2; 1-3 | 7 | 200 |
| `scripts/livelihoods_screens.py:115-118`; recovery-skills-screens.md | sprint 3 / recovery skills held (run); pilot | 501-506; 2 | 601-606; 7 | 200 |
| recovery-skills-screens.md (development cohort) | development | 3, 7, 9, 11, 23, 42 | 7, 11, 13, 17, 21, 31, 302, 303 | |
| `scripts/productive_recovery_screens.py:131,1334,1792` | productive-recovery timing pilot (cp1-cp3) | 5 | 19 | 200 |
| `scripts/productive_recovery_screens.py:132` | cp1 held (run) | 701-706 | 801-806 | 200 |
| `:1335` | cp2 held (run) | 711-716 | 811-816 | 200 |
| `:1793` | cp3 held (run) | 721-726 | 821-826 | 200 |
| `:142-143`; plan section 7 | development (inspected freely) | 1, 3, 7, 9, 11, 23, 42 | 7, 11, 13, 17, 21, 31, 302, 303 | |
| productive-recovery-screens-cp3.md (seeds table) | viewer QA batches only | 12, 13, 14 | - | |
| productive-recovery-examples.md:63,235; recovery-skills-examples.md:28 | natural examples (development) | 23 | 7, 21, 31 | 200 |
| `viewer/scripts/qa-recovery-chain.mjs:82` | QA allow-list (development) | 1, 3, 7, 9, 11, 23, 42 | 7, 11, 13, 17, 21, 31 | |
| `scripts/crisis_held_evaluation.py:21,47-51`; crisis-held-evaluation-2026-11-03.md | held seeds in constructed families (care: 8 regions x 4 civs with edited resources; forecast: 4 x 2) | 202, 303, 404 (constructed) | - | |
| `scripts/shortfall_priority_evaluation.py:52,214` | scaffold | 42 (8x4) | - | 60 |
| `scripts/m53b_run_validation.py:100-105,857` | 200-seed gate (restricted): full; subset; determinism pair | 42-241; 42-61; 42 x2 | - | 500; 200 |
| `scripts/m53b_run_validation.py:120-125` | procedural gate (restricted): full; subset | - | 42-141; 42-61 | 300; 200 |
| population-entities.md:268, techniques-default.md:47, wave3-defaults.md, money-credit.md:304 | gate subsets used in development | 62-81, 142-161, 42-121 (inside 42-241) | | 200/500 |
| spec-communities.md:182-183 | out-of-gate holdout probes | 1000-1019 | 1000-1019 | 500; 300 |
| domestic-credit.md:1000-1004 | development; confirmatory | 282-301; 42-81 | 42-51; 52-71 | 300/500; 200 |
| health-care.md:117-118 | development probe | 900-909 | 900-904 | 100 |
| scientific-claims.md:213 | measurement-only sham check | 1000-1999 (stratum unclear: treat as used in both) | | |
| phase-6-progress.md:4051,4148 | tuning passes | 10-29 | | 200 |
| expansion-experiments.md:80-92; docs/experiments/* | development: scientific claims, harvest target, wealth floor (8x4 and 32x10) | 42-43 | 42-43 | 40-60 |
| docs/experiments/mutual-aid-aggregate-gate.md:46 | gate seeds | 42, 77, 1337, 2026 | | |
| docs/experiments/campaign-order-preview.md:147, memome-candidate-preview.md:141 | previews | 0, 42, 101 | | |
| `scripts/turn_speed_identity.py:42-58`, `scripts/checkpoint_identity.py:75-114,293-304,593-604` | identity matrices | 42, 7, 1234 (8x4); 42, 7 (12x4 scaled) | 11 (32x8); 42 (32x10, recycling); 42, 7 (48x10, `auto`) | |
| `scripts/create_example_worlds.py:21-26` | example worlds | 7, 42, 11 | | |

Union of used numbers. Template: 0-3, 5, 7, 9, 10-29, 42-241, 282-306, 404, 501-506, 701-706,
711-716, 721-726, 900-909, 1000-1999, 1234, 1337, 2026 (11, 12, 13, 14, 23 are inside 10-29).
Procedural (32x10 and other sizes): 7, 11, 13, 17, 19, 21, 31, 42-141, 201-206, 302, 303,
401-406, 601-606, 801-806, 811-816, 821-826, 900-904, 1000-1999.

### 5.4 Proposed cohorts (verified unused)

| Screen (PROPOSAL; slice) | Template 8x4 | Procedural 32x10 |
| --- | --- | --- |
| Timing pilot (shared, never held; as productive recovery did) | 5 | 19 |
| CW1: S1 accounting and wages (A1-A2) | 731-736 | 831-836 |
| CW2: S2 workshop economics and owned-stock lifecycle (A3, A5) | 741-746 | 841-846 |
| CW3: S3 watershed and infrastructure (B1-B3) | 751-756 | 851-856 |
| CW4: S3 quarantine and public health (C1; reused for C2/C4 only if not yet run) | 761-766 | 861-866 |
| CW5: S4 trade, forest-water, care, attribution, requisition | 771-776 | 871-876 |
| CW6: S5 adaptive decisions, cross-border organisation, war; the integrated evaluation | 781-786 | 881-886 |
| Reserve (a held-run failure fix needs a new cohort: cp3 prereg, "Incomplete runs") | 791-796 | 891-896 |

Checks made: none of these numbers is in the union of section 5.3; all lie outside both gate
ranges (template 42-241, procedural 42-141) and the 1000-1999 range; a repository-wide search
for `seed`/`--seed`/`--seed-start`/`range(...)` with any of 731-799 or 831-899 found only
SciPy's vendored tests under `.venv/` (`seed = 831`). Each cohort is assigned before any program
run and must be listed as RESERVED by every other screen until run, then as NEVER_RUN.

---

## 6. Question 6: the viewer

### 6.1 The recovery chain view

- Reader `viewer/src/lib/recoveryChain.ts` (729 lines) composes the packages' own strict readers;
  view `viewer/src/components/systems/RecoveryChain.tsx` (431 lines), mounted first on the
  Livelihoods tab by `LivelihoodsPanel.tsx` when a snapshot records RS2, PL1, PL3 or PL4
  (`ANCHOR_PACKAGES`, `recoveryChain.ts:66`). Contract and tests:
  docs/integration/recovery-chain-view.md. Fixture
  `viewer/src/__fixtures__/recovery_chain_natural_records.json` (11 natural snapshots of template
  23, 60 turns) plus labelled constructed variants (`recoveryChainFixture.ts`).
- States per package per snapshot (`readPackage`, `recoveryChain.ts:100-145`): **off** (no
  snapshot of the run carries it), **unknown** (on, but this snapshot has no livelihoods record,
  no package record, or a null frame), **malformed** (record present, reader refused; reason
  shown when the reader gives one), **known** (an empty value reads "on, nothing happened").
  Totals over a link with an unknown snapshot read "at least".
- Joins are labelled per link: stable id or region only (recovery-chain-view.md, "The links and
  how they are joined").
- QA `viewer/scripts/qa-recovery-chain.mjs`: runs the real simulation on a development world
  only (refuses other seeds, `:82,116-117`; refuses an `--out` inside the repository, `:636-642`), serves the production build on 127.0.0.1, opens the
  bundle with "Open saved world file", checks 1440x900 and 390x844 touch (`:78-79`), reads the
  expected chain independently from the bundle with `chronicler.bundle_codec`, checks no
  console/page errors, no NaN/undefined, no overflow at 390 px; parts `chain`, `variant`
  (constructed, labelled), `subset`. Last runs: template 23 chain 329/329, variant 10/10,
  subset 26/26; procedural 31 chain 323/323.

### 6.2 The five readers that cannot tell absent from malformed

Each returns `null` both when the record is absent and when it is malformed:

| Reader | Evidence | Panel | Pinned? |
| --- | --- | --- | --- |
| `repairProjectsAt` | `viewer/src/lib/repairProjects.ts:155` ("null when absent, from another schema, misdated or malformed") | `components/systems/RepairProjects.tsx` | no |
| `timberStockAt` | `viewer/src/lib/timberStock.ts:55` | `TimberStock.tsx` | no |
| `remittancesAt` | `viewer/src/lib/remittances.ts:115` | `Remittances.tsx` | no |
| `foodAllocationAt` | `viewer/src/lib/foodAllocation.ts:59` | `FoodAllocation.tsx` | no |
| `granaryStorageAt` | `viewer/src/lib/granaries.ts:85` | `GranaryStorage.tsx` | **yes** (both: crisis_candidate witness) |

The chain view tells them apart with a presence test before calling them (`carries`,
`recoveryChain.ts:77-81`). The readers that return a `{status: absent|malformed|ok}` reading are
`readTimberSupply` (`timberSupply.ts:202`), `readRecoveryCrews` (`recoveryCrews.ts:136`) and
`readHouseholdRetail` (`householdRetail.ts:250`). Disposition proposal for RL8: a new, unpinned
helper (for example `viewer/src/lib/recordReading.ts`) that combines the presence test with the
null reader into the same three-state reading, used by the four unpinned panels; the two pinned
granary files either get a reviewed layer or keep their reader while a wrapper supplies the
state. Tests per panel: absent, malformed, recorded zero, recorded.

### 6.3 Versioning and old bundles

- Bundle: `BUNDLE_VERSION = 6` (`src/chronicler/bundle_codec.py:44`), history written as deltas
  and decoded to the version-5 layout (`:1-15`); the viewer accepts versions 1-6 and unversioned
  JSON (`viewer/src/lib/bundleValidation.ts:118-120`) and validates known fields only.
- Snapshot fields are optional and omitted when None (`TurnSnapshot.livelihoods: dict | None`,
  `exclude_if=_is_none`, `src/chronicler/models.py:1504`; world state `:1232`), so feature-off
  bundles keep their bytes. The livelihoods container carries `schema_version: 1` and one record
  per active package (`livelihoods_snapshot_fields`, `src/chronicler/livelihoods.py:555-561`);
  each record carries its own `schema_version`, `stage`, `mode`, `source_turn` (= snapshot turn -
  1) and is a copied completed-turn observation, never final state (e.g.
  `household_retail.snapshot_summary`, `src/chronicler/household_retail.py:1513-1535`, with null
  frames when not observed and bounded samples/logs with `*_dropped` counts).
- Readers refuse unknown schema versions and misdated records; an absent record in an old bundle
  reads as off or unknown. The viewer reads livelihoods records through
  `Record<string, unknown>` casts in its own lib modules: `viewer/src/types.ts` has no
  livelihoods type and is pinned (5 witnesses). Keep that pattern for program records.
- Legacy fixtures in tests: `faiths_legacy_bundle.json`, `bundle_v2/`, `sample_bundle.json`,
  `cities_bundle.json` and `cities_bundle_v6.json` (`viewer/src/__fixtures__/`).

### 6.4 Desktop and phone journeys with Playwright

Playwright is pre-installed (`node -e "require('playwright')"` from `viewer/` works). Pattern of
every QA script: `npm run build`, a local `node:http` server on port 0 serving `dist/`,
`chromium.launch()`, one browser context per viewport (`{viewport: {width: 1440, height: 900}}`
and `{viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true}`), load the bundle via
`page.getByLabel("Open saved world file").setInputFiles(file)`, drive with keys and labelled
controls, collect `console` and `pageerror` events, compare text with values read independently
from the bundle, check `document.documentElement.scrollWidth <= innerWidth + 1` on the phone,
save screenshots and `report.json` to a new `--out` directory outside the repository.
`qa-shell-journeys.mjs` compares two builds step by step (DOM, ARIA snapshot, screenshots) and is
the regression check for "old bundles stay loadable" (V8).

---

## 7. Question 7: narration provenance

- `src/chronicler/narration_provenance.py`: fact ids scoped to one bundle (`:15-47`): events
  `e<i>`, named events `n<i>`, accounts `<chronicler>/e<i>`, characters `p<id>`, artifacts
  `art<id>`, snapshot values `s<S>.<what>.<key>` (`ruler`, `war`, `movement`, `reform`, `city`,
  `guild`, `burghers`, `seat`, `food`, `urban`, `settlement`), changes `d<S1>-<S2>.<key>`, windows
  `w<a>-<b>`, observations `o<T>.<what>`, language names `L.<k><ref>`, and legacy links `k<j>`.
  Each chronicle entry records the facts given, the names they mention and per-sentence spans
  (`ChronicleEntry.provenance`; docs/integration/narration-provenance.md sections 1-2).
- Causal links come only from the simulation's recorded `causes`; the curator's `CAUSAL_PATTERNS`
  are a fallback for bundles without provenance and are marked `pattern`, not `recorded`
  (docs/integration/causal-provenance.md:125-141). The mechanical narrator writes "because" only
  along recorded chains.
- `python -m chronicler.narration_audit` flags unsupplied, unknown and future citations,
  unsupplied names, stray markers, unresolved facts, bad spans and (mechanical) uncited
  sentences (narration-provenance.md section 6).
- **Gap for stories**: the audit resolves an `s<S>.<anything>` id only to "snapshot S exists"
  (`src/chronicler/narration_audit.py:185-188`); it does not check that the key names a real
  record. A story citing livelihoods or program records needs key-level resolution (section 9.3).
- **Testing without a paid narrator**: `--narrator mechanical` (also with `--simulate-only` and
  for `--narrate BUNDLE`), scripted fake clients (`ScriptedClient`,
  `tests/test_narration_provenance.py:207`), and the audit CLI; the existing evidence is 143
  mechanical entries with 0 flags and planted faults all flagged (narration-provenance.md
  section 6). Narration only adds narration fields: simulation outputs are byte-identical
  (narration-provenance.md, "Identity").

---

## 8. Question 8: profiling

### 8.1 How it was measured before

- `src/chronicler/cpu_budget.py`: conservative automatic worker counts from affinity and cgroup
  quotas (it is not a profiler).
- Screen timing: seconds per run from the pilot (cp3: template 6.9 s + 1.5 s extraction,
  procedural 18.5 s + 3.4 s), projected core-hours, disk (a procedural CH run: 33 MB, 22 MB
  bundle), extraction memory (about 380 MB) (productive-recovery-screens-cp3.md, "Timing pilot").
- Checkpoints: `scripts/archive/checkpoint_cost.py` (size, native and Python sections, write and
  read time; 22k agents 2.51 MB, 0.17 s write, 0.18 s read; 52k 5.40 MB) and growth over a run
  (procedural 48x10 hybrid 1.46-4.04 MB at turns 60-150) (checkpoint-continuation.md section 7);
  `checkpoint_identity` reports bytes per turn.
- Per-turn CPU: `scripts/agent_scale_benchmark.py` (wall and process CPU of the native tick and
  the whole turn by agent count, `--source-root`/`--native-root`; it has no option to pass
  feature switches) and `scripts/benchmark_headless.py` (tracemalloc peak, cProfile, no native).
- Bundle size guard: `tests/test_bundle.py:770` (`< 10.5 MB`, a 500-turn default world).
- Gate scale: the procedural full profile about 45 minutes on three workers, 5 GB batch, 2.5 GB
  validation peak (DEVELOPMENT.md).

### 8.2 Declared scale (PROPOSAL)

- **Screen scale** (the scale the program's claims are made at): template 8x4 and procedural
  32x10, 200 turns, hybrid, the screen base, switches off against all program switches on, on the
  pilot worlds (template 5, procedural 19) and one development world each (template 23,
  procedural 31). Per run: wall and process CPU and peak RSS of the child (from
  `resource.getrusage(RUSAGE_CHILDREN)` in a small wrapper; `/usr/bin/time` is not installed),
  bundle, `state.json` and output-directory bytes, metrics-row bytes, and checkpoint bytes and
  write/read time at turns 50, 100, 150 and 199.
- **Stress scale**: `scaled22k_s42` (30 turns) and `scaled52k_s7` (20 turns) worlds and
  procedural 48x10 hybrid 150 turns, off against on: per-turn wall and process CPU (extend
  `agent_scale_benchmark.py` with a `--cli-arg`, or wrap `turn_speed_identity`'s scaled runner),
  checkpoint size and time (`checkpoint_cost.py`).
- Report relative overhead against switches off on the same world; flag any slice adding more
  than 25% CPU per turn, doubling bundle or checkpoint bytes, or more than 500 MB of peak RSS, for
  the lead's decision (thresholds are a proposal). The default path must leave
  `tests/test_bundle.py`'s guard world unchanged (V5 already proves it byte for byte).

---

## 9. Question 9: the Program E design (PROPOSAL)

### 9.1 Linked histories: data contract

**Entities and identities** (no invented ids: AGENTS.md):

| Entity | Identity | Exists today |
| --- | --- | --- |
| person | native agent stable id, bound across pool rebuilds by `bind_native_pool` (`livelihoods.py:571`) | ids in PL3 crews, RS2/PL1 receipts, the 24-person retail sample |
| household | the smaller id of a co-resident couple; a child takes a parent's key (recovery-chain-view.md) | retail sample rows (`household` column) |
| firm | PROPOSAL: a checkpointed, never-reused firm id from A3 (a workshop site today is keyed by kind and asset) | partial |
| shipment | expedition `eid` (PL1), convoy and voyage ids where recorded, public shipment ids | yes, per package |
| infrastructure asset | `(kind, asset)` with granary asset = region index (repair-chain join); roads, irrigation, ports: PROPOSAL from B, stable ids | granaries and workshops |
| region | index in `world.regions` | yes |

**Every history row** carries `entity {kind, id}`, `turn` (the snapshot), `source_turn`, the
observed value, `join` (`id`: a record of this entity names it; `region`: a regional total shown
beside the entity, never attributed to it; `inferred`: derived by a named rule, e.g. household
key, store attribution by elimination), `source` (a bundle JSON pointer, e.g.
`/history/27/livelihoods/repair_projects/receipts/3`, the convention of `historicalSearch.ts`),
and `state`, one of:

| State | Meaning | Display |
| --- | --- | --- |
| `disabled` | the switch is off in this run (no snapshot records the package) | "Off in this run" |
| `unknown` | the package is on, but this snapshot has no record or a null frame (the phase did not run) | "Unknown, not zero" |
| `malformed` | a record is present and its reader refused it (reason) | "Rejected as malformed: reason" |
| `not_sampled` | the entity is outside a bounded sample (e.g. retail's 24 people) | "Not in the sample; no evidence" |
| `truncated` | a cap dropped rows (`*_dropped > 0`) or a frame hit its row limit | totals read "at least" |
| `recorded_zero` | a valid record says nothing happened or the value is 0 | "Recorded: none" / "0" |
| `recorded` | a valid record with a value | the value |

Producer obligations for every new program record: dated (`source_turn`), versioned
(`schema_version`), copied completed-turn observations, stable ids for entity rows, explicit
`null` (not 0) when unobserved, caps with `*_dropped` counters, counters declared in `COUNTERS`
and closing against the frames (as the cp3 extractor checks). Person-level purchase evidence
(RL5) needs a bounded per-household or per-person purchase frame keyed by the household key or
agent id; the region totals stay.

**Viewer**: `viewer/src/lib/entityHistory.ts` composing the packages' strict readers (as
`recoveryChain.ts` does) into per-entity timelines; `components/systems/EntityHistory.tsx`
reached from any stable id in the chain view, the region inspector and historical search; the
timeline states the join and state of every row; regional rows sit in a separate band labelled
"Regional context; not this person's record" (the `regionHistory.ts` convention "Recorded
region" / "Controller context; region unrecorded"). Fixtures: natural records from development
worlds plus labelled constructed variants; tests for all seven states per package.

### 9.2 Story worlds

- **Natural**: an ordinary CLI run of a development world (never a held or reserved seed), with
  the exact command, source commit and extension SHA recorded, found by a finder script (as
  `scripts/productive_recovery_examples.py --chain`) that names the snapshot turn of each
  instance. Required set per slice: an adaptation, a failure (e.g. an underfunded public work for
  B5) and a mixed outcome, each traced by stable id where the records allow and by region
  otherwise, saying which.
- **Constructed**: built on purpose by tests or by editing a natural bundle; the file name and a
  marker (PROPOSAL: `metadata.constructed = {"from": "<sha256 of the source bundle>", "edits":
  [...]}`) label it, the viewer shows a "Constructed demonstration" banner, and no constructed
  instance is counted as natural activation. Whether the viewer tolerates the extra metadata key
  is UNVERIFIED (it validates known keys only: `bundleValidation.ts:110-120`; test it).

### 9.3 Stories and narration provenance

- New fact-id kinds for program records within the existing grammar (`s<S>.<what>.<key>` already
  matches `ID_PATTERN`, `narration_provenance.py:98`), e.g. `s28.lh.repair_projects.p0`,
  `s28.lh.timber_supply.x3`, `s28.lh.household_retail.r5`; each resolves to one JSON pointer.
- Extend `narration_audit` to resolve these keys (flag `unresolved_fact` when the record is not
  there; today only the snapshot's existence is checked: `narration_audit.py:185-188`).
- Composition rule (mechanical story narrator): a causal connector ("because", "so", "led to")
  only along a recorded link (event `causes`, or an id join between two records); a regional join
  is told as co-occurrence ("in the same region that turn"); an inferred join is never told as a
  cause; unknown and malformed facts are not cited. Tests: planted regional and inferred links
  phrased causally must be flagged.
- Stories are written post hoc from saved bundles (`--narrate`), so they cannot change state; a
  test compares a simulate-only bundle's simulation fields with and without story narration.

### 9.4 The per-slice checklist

Part 1 is the checklist. For Program E's own slices add: viewer readers for every new record with
the seven states; a QA script per new view at desktop and phone; a natural and a constructed
example per story; the narration audit with 0 flags on the story bundles; the resume-point list
used for V6; the profiling table of V11.

---

## 10. Open questions and risks

1. **Catalog scope.** `feature_catalog` covers the 5 expansion prerequisites and the 19
   livelihoods switches only (`feature_catalog.py:53-59,183-203`). Will B, C and D switches be
   livelihoods packages (then the registry, catalog and screens work unchanged) or a new group
   (then `_features` needs a second registry and the viewer catalog its group)?
2. **No exclusion condition.** The catalog has requirement kinds `agents`, `feature`, `choice`,
   `setting`, `any` only; the viewer refuses any other kind (`viewer/src/lib/featureCatalog.ts:80`).
   Mutually exclusive switches (e.g. two water models) need a new kind (`not`/`conflicts`), a
   `CATALOG_SCHEMA_VERSION` bump (`feature_catalog.py:44`), viewer support and fixture update. The
   prototype found 0 refused pairs among 276 (the catalog cannot express a conflict today) and
   every single-prerequisite drop refused (24/24); all-on validates under hybrid.
3. **Layer ownership.** `batch_manifest.py` and `tests/test_batch_manifest.py` change with every
   switch and are pinned; parallel lanes will collide there. The lead should own one layer per
   landing (as `pl1`-`pl4`).
4. **Prior all-switch flag lists and `--ks` choices** for cp2/cp3 are not recorded; V6's list is
   a reconstruction from the catalog.
5. **Identity run durations** are unrecorded; the lead's baseline should time each case so lanes
   can schedule around the 4 cores.
6. `checkpoint_identity.py` records no source/extension identity; PROPOSAL: give it the same
   `which.txt` check as `turn_speed_identity.py`.
7. Template held cohorts of earlier phases (101-106) lay inside the 200-seed gate range; this
   proposal avoids the gate ranges entirely. Confirm the lead accepts reusing the pilot worlds
   5/19 (never held) for the program's timing pilots.
8. `qa-recovery-chain.mjs`'s development list omits procedural 302 and 303 (registered
   development worlds); harmless, but a new QA script should read one shared list.
9. The no-Rust full suite (`python-no-rust`, 5 minutes on CI) is not part of the local playbook;
   CI runs it. Locally, run it only in a clean `.venv` (`.venv/bin/python -m pytest -q`) when the
   slice changes Python outside the offline selection.
