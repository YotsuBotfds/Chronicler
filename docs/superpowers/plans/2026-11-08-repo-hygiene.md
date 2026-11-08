# Repo Hygiene (Wave 0) — Implementation Plan

> **For agentic workers:** execute task by task; steps use checkbox (`- [ ]`) syntax. Run the
> preflight before touching any file; never rewrite a pinned hash; one PR per numbered PR block.

**Goal:** one current-status record, a smaller and calmer tree, safer CI and a balanced native lane, with no runtime change.
**Architecture:** docs and config edits (PR 1-2), CI edits with reviewed test projections (PR 3, PR 5), script archive with manifest entries (PR 4), evidence offload (PR 6, after DEC-8).
**Tech stack:** markdown, YAML, bash, pytest, `gh` CLI.
**Prerequisites:** start from fetched `main`. PR 6 needs DEC-8 answered. Companion spec: `docs/superpowers/specs/2026-11-08-repo-hygiene-design.md` (copy of the design spec).

Preflight command for every file below: `.venv/bin/python scripts/refactor_preflight.py <paths>`.

## File map

| File | Change |
|---|---|
| `docs/CONTINUATION.md` | add `## Current status`; cut from `## Historical checkpoints` (line 60) to end |
| `docs/superpowers/progress/continuation-history.md` | new, holds the cut text byte-for-byte |
| `README.md`, `AGENTS.md`, `docs/RECOVERY.md`, `docs/README.md` | link to status block, drop PR numbers, repoint anchors |
| `tests/test_docs_status.py` | new drift guard |
| `.gitignore` | new patterns |
| `docs/superpowers/audits/README.md` (new), `2026-03-29-...audit.md`, `2026-04-02-...audit.md` | index and banners |
| `docs/integration/feature-options.md`, `scripts/archive/README.md` | stale text |
| `scripts/cloud_setup.sh`, `docs/DEVELOPMENT.md` | failure summary, strict flag |
| `.github/workflows/tests.yml`, `tests/test_native_build_lanes.py` | concurrency, pins, projection |
| `scripts/archive/*`, `scripts/testing/script_smoke_manifest.json`, `scripts/README.md` | 15 scripts move |
| `docs/workflows/README.md` | new index |
| `scripts/testing/native_shards_manifest.json`, `tests/test_native_ci_shards.py` | shard moves |
| `docs/superpowers/progress/EVIDENCE-OFFLOAD.md` + removed evidence | PR 6 |

## PR 1: Status and docs (tasks HYG-1, HYG-3)

### Task HYG-1: one status block, split CONTINUATION
- [ ] Step 1: Run preflight on `docs/CONTINUATION.md README.md AGENTS.md docs/RECOVERY.md docs/README.md`. Expect REFERENCE only (README has test-pinned strings; keep "Rust 1.85+", "No-Rust Python lane", "Native Python lane" and the other strings at `tests/test_native_build_lanes.py:65-90`).
- [ ] Step 2: Build the history file: `n=$(grep -n '^## Historical checkpoints' docs/CONTINUATION.md | cut -d: -f1)`; `tail -n +$((n+1)) docs/CONTINUATION.md > docs/superpowers/progress/continuation-history.md`; prepend `# Continuation history (moved from docs/CONTINUATION.md on 2026-11-08)` and one intro line. Do not edit any moved line.
- [ ] Step 3: Truncate `docs/CONTINUATION.md` after line `n` and add a pointer line to the history file. Insert at the very top a `## Current status` block: date, `main` SHA (use `git rev-parse --short origin/main`), last merged PR from `gh pr list --state merged --limit 1`, last verified Tests run id, "200-seed gate: not run", and "Update this block in the ledger commit after each merge."
- [ ] Step 4: `README.md:20-24`: replace the PR #69 paragraph with two sentences linking `docs/CONTINUATION.md#current-status`. `AGENTS.md:6-8`: delete the PR chain, keep "Start new work from fetched `main`" plus the link. `docs/RECOVERY.md:1-10`: replace the "Updated ... after PRs" line with the link and mark the entries below "historical source identities". Repoint `docs/RECOVERY.md:305` to `superpowers/progress/continuation-history.md#product-gaps-to-carry-forward`, `README.md:30` and `docs/README.md:13` to describe the split. Do not edit evidence JSON or dated integration notes.
- [ ] Step 5: Write `tests/test_docs_status.py`: README and AGENTS contain no `PR #\d+`; `docs/CONTINUATION.md` line 1 is `## Current status`; every relative `.md` link in README, AGENTS, `docs/README.md`, `docs/RECOVERY.md` resolves to a file. Add it to an oracle chunk with headroom in `scripts/run_python_oracle_checks.py` (do not raise the 110 s limit).
- [ ] Step 6: Verify: `.venv/bin/python -m pytest -q tests/test_docs_status.py tests/test_native_build_lanes.py tests/test_refactor_preflight.py`; `wc -l docs/CONTINUATION.md` is under 100; `diff <(tail -n +2 docs/superpowers/progress/continuation-history.md | tail -n +N) <(git show HEAD:docs/CONTINUATION.md | tail -n +$((n+1)))` is empty (N = lines you prepended).
- [ ] Step 7: Ledger: a CONTINUATION entry is not needed for a correction; add one line under Current status naming the split. Commit: `docs: single current-status block; move CONTINUATION history`.

### Task HYG-3: audits and stale docs
- [ ] Step 1: Preflight `docs/superpowers/audits/*.md docs/integration/feature-options.md scripts/archive/README.md`. Expect REFERENCE only. Do not rename or move any audit file.
- [ ] Step 2: Create `docs/superpowers/audits/README.md`: table of the 2026-11-08 scout (current) and the nine older files (historical: `2026-03-29`, `2026-04-02`, `masteraudit`, `opusaudit4-1-26`, `4-4-26opusaudit` = verification of the 04-01 audit, the four 03-31 files), with the scout-30 "11 of 12 fixed" note. Add to the top of the 03-29 and 04-02 audits the same "Historical snapshot" banner as `masteraudit.md:3-7`.
- [ ] Step 3: `docs/integration/feature-options.md`: ~line 40 add `health_care` to the prerequisite list; ~93 replace "No exclusion is declared yet" with the real exclusions (find them: `rg "_excludes\(" src/chronicler/feature_catalog.py`); ~106 replace "25 switches, 300 pairs" with counts from `.venv/bin/python -c "from chronicler import feature_catalog as c; print(len(c.PREREQUISITES))"` and the matrix script's own output (state the date); ~260 correct "health care is not in the catalog". Re-read the file for line drift first.
- [ ] Step 4: `scripts/archive/README.md:3-5`: say `scripts/testing/script_smoke.py` runs the safe manifest entries and `tests/test_script_smoke_manifest.py` checks the manifest; no workflow runs them.
- [ ] Step 5: Do not change `analytics.py:1313`; add a sentence to the audits README "Decisions" section that `"post-M18"` is an opaque report tag kept for saved-report compatibility.
- [ ] Step 6: Verify: `.venv/bin/python -m pytest -q tests/test_script_smoke_manifest.py tests/test_feature_catalog.py` (confirm the second file exists with `ls tests | grep feature_catalog`, else use `tests/test_feature_matrix.py`); link check from `tests/test_docs_status.py`. Commit: `docs: index audits, correct feature-options and archive README`.

## PR 2: Ignore rules (task HYG-2)
- [ ] Step 1: Append to `.gitignore`: `*.log`, `!docs/**/*.log`, `*.cpuprofile`, `!docs/**/*.cpuprofile`, `.coverage`, `htmlcov/`, `.mypy_cache/`, `.ruff_cache/`, `.hypothesis/`, `*.so`, `*.pyd`.
- [ ] Step 2: Verify: `git ls-files -ci --exclude-standard` prints nothing; `git status --short` shows no change besides `.gitignore`; `touch /tmp/x.log` is irrelevant, instead `git check-ignore -v pytest.log docs/superpowers/progress/x/new.log` shows root ignored and docs not ignored. `.venv/bin/python -m pytest -q tests/test_refactor_preflight.py`. Commit: `chore: ignore logs, profiles and tool caches`.

## PR 3: CI hardening (task HYG-4)
- [ ] Step 1: Preflight `.github/workflows/tests.yml`; read `tests/test_native_build_lanes.py:270-334`. Record that jobs `python-native-build`, `python-native-tests`, `python-native-shard-aggregate`, `python-native` are compared to `docs/workflows/native-two-shards-v2.yml.in`.
- [ ] Step 2: Add top-level `concurrency` after `permissions:` in `tests.yml`: group `tests-${{ github.ref }}`, `cancel-in-progress: ${{ github.event_name == 'pull_request' }}`.
- [ ] Step 3: Resolve SHAs: `gh api repos/<owner>/<action>/git/ref/tags/<tag> --jq .object.sha` (annotated tags need one more `git/tags/<sha>` hop) for setup-python v5, setup-node v4, download-artifact v4, cache v4, rust-toolchain. Replace each `uses: x@tag` in all four of `tests.yml`, `validation-gate.yml`, `workflow-semantics.yml` with `x@<sha> # <tag>`. For rust-toolchain use the SHA and add `with: {toolchain: "1.85.0"}` at `tests.yml:193` and `:488` and the other files.
- [ ] Step 4: In `tests/test_native_build_lanes.py` `test_standard_native_delegation_keeps_the_qualified_v2_bodies`, add a reviewed map from each old `uses` string to its SHA form, and for the rust step the extra `with`, applied to `expected` the way the `python-version` exception is (`:284-300` area). Add a negative case: an unlisted `uses` change still fails. Do not touch `docs/workflows/*.yml.in` or `.github/workflows/native-two-shards*.yml`.
- [ ] Step 5: Verify: `.venv/bin/python -m pytest -q tests/test_native_build_lanes.py tests/test_native_ci_shards.py tests/test_native_wheel_receipt.py` passes; `actionlint` runs on the PR via `workflow-semantics.yml`; the PR's Tests run is green on all nine jobs, including `cargo` on 1.85.0 (if the lock needs a newer compiler, pin the lowest stable that builds and say so in the PR). Commit: `ci: concurrency group, pinned toolchain and action SHAs`.

## PR 4: Setup script and script archive (tasks HYG-5, HYG-6)

### Task HYG-5
- [ ] Step 1: Edit `scripts/cloud_setup.sh`: keep line 6 and `step()` shape (pinned at `tests/test_check_python_env.py:212`). Add `FAILED=()`; in `step()` append the name on failure. Replace `|| exit 0` (line 7) with `|| { echo "!! cannot enter repo root"; exit 1; }`. Before use add `command -v uv npm cargo` checks that record a failure. End with a `== setup summary` list and `[ "${CHRONICLER_SETUP_STRICT:-0}" = 1 ] && [ ${#FAILED[@]} -gt 0 ] && exit 1`; otherwise exit 0.
- [ ] Step 2: `docs/DEVELOPMENT.md` cloud section (~line 337): document the summary and `CHRONICLER_SETUP_STRICT`.
- [ ] Step 3: Verify: `bash -n scripts/cloud_setup.sh`; `PATH=/nonexistent CHRONICLER_SETUP_STRICT=1 /bin/bash scripts/cloud_setup.sh; echo $?` is 1 with a summary; without the flag it is 0; `.venv/bin/python -m pytest -q tests/test_check_python_env.py`.

### Task HYG-6
- [ ] Step 1: Preflight the 15 scripts (list in the spec 3.6) and the files that cite them: `src/chronicler/watershed.py`, `src/chronicler/provenance.py`, `scripts/build_learning_fixture.py`, `scripts/bundle_v6.py`, `scripts/cities_identity.py`. Expect REFERENCE only. Also `rg -n "<name>" scripts/seed_registry.json scripts/testing/*.json` must print nothing for each.
- [ ] Step 2: `git mv scripts/<name>.py scripts/archive/` for each. In each, change repository-root lookups (`parents[1]`, sibling `parent` imports) to the archive depth, as the existing archive scripts do (`scripts/archive/m53_social_probe.py:16` uses `parents[2]`).
- [ ] Step 3: For each, run `.venv/bin/python scripts/archive/<name>.py --help` and record exit status; add a sorted entry to `scripts/testing/script_smoke_manifest.json` with the schema keys `invocation, expected_exit, safe_to_run, mutates, native, network, inputs, fixture_outputs, note` (copy a neighbouring entry). The file's keys must stay sorted.
- [ ] Step 4: Update `scripts/README.md` rows and the docstring/comment path in cited files only where the preflight shows no enforced pin. Leave `build_movements_fixture`, `build_transport_fixture`, `testing/livelihoods_layer_tool` and the whole `wealth_floor_*` cluster in place.
- [ ] Step 5: Add `docs/workflows/README.md` marking `tests.yml`, `validation-gate.yml`, `workflow-semantics.yml` live and the other six as one-run records that tests or scripts hash (cite the pins in the spec).
- [ ] Step 6: Verify: `.venv/bin/python -m pytest -q tests/test_script_smoke_manifest.py tests/test_screen_runner.py tests/test_wealth_floor_outcome_checkpoints_v2.py tests/test_refactor_preflight.py`; `.venv/bin/python scripts/run_python_oracle_checks.py` (full lane; expect pass). Commit: `scripts: archive 15 doc-only scripts; cloud setup failure summary`.

## PR 5: Native shard rebalance (task HYG-8)
- [ ] Step 1: Collect durations: `gh run list --workflow Tests --branch main --status success --limit 5 --json databaseId`; for three runs `gh run download <id> -p '*native*'` (the `native.xml` junit files, 14-day retention). Sum `testcase@time` per module with a scratch script outside the repo; save `module,seconds,shard` to a scratch CSV.
- [ ] Step 2: Choose moves. Load `additions` from `tests/test_native_ci_shards.py` (the dict in `test_checked_in_partition_preserves_historical_assignment_with_explicit_new_test`, ~line 189). Only modules in that dict may move; never touch the 300 old owners (digest `:364`). Pick shard-0 additions, largest first, until the sums are within 10 percent. Expect ~3.5 minutes to move.
- [ ] Step 3: Edit the two lists in `scripts/testing/native_shards_manifest.json` and the owner values in the `additions` dict identically. Leave `historical_*` fields and `expected_skips` alone.
- [ ] Step 4: Verify: `.venv/bin/python scripts/native_ci_shards.py check-manifest` (read its `--help` first; use the form without `--execute` if that flag implies a run) passes; `.venv/bin/python -m pytest -q tests/test_native_ci_shards.py tests/test_native_build_lanes.py`; the PR's Tests run shows both shards within about 10 percent and the aggregate job green with unchanged skip and subtest counts; re-run Tests twice on the PR to see the spread before merging. Commit: `ci: rebalance native shards by recorded duration`.

## PR 6: Evidence offload (task HYG-7; blocked on DEC-8 answer "yes")
- [ ] Step 1: Confirm DEC-8 host and rewrite policy are recorded in the PR body.
- [ ] Step 2: List candidates: `git ls-files 'docs/**/*.log' 'docs/**/*.cpuprofile' 'docs/**/metrics.jsonl'` minus `docs/superpowers/progress/connected-world-screens-cw3b/held/` (read by `tests/test_infrastructure_condition.py:1337`) and minus every `*.md` preregistration. Re-run `rg -n "<path>" tests scripts` for each directory; any hit stays.
- [ ] Step 3: Build `evidence-offload-2026-11.tar.zst` in the scratchpad, compute SHA-256 per file, write `docs/superpowers/progress/EVIDENCE-OFFLOAD.md` (path, bytes, sha256, how to restore: `gh release download <tag>` then extract at repo root). Upload with `gh release create evidence-2026-11 <tarball>` (owner approval required).
- [ ] Step 4: `git rm` the listed files; remove the `!docs/**/*.log` and `!docs/**/*.cpuprofile` negations from `.gitignore`. Do not edit any JSON receipt.
- [ ] Step 5: Verify: restore the tarball into a temp clone and `sha256sum -c`; `.venv/bin/python -m pytest -q tests/test_infrastructure_condition.py tests/test_productive_recovery_screens_cp2.py tests/test_productive_recovery_screens_cp3.py tests/test_screen_runner.py tests/test_cw1_screen.py`; `.venv/bin/python scripts/refactor_preflight.py --git-diff origin/main` shows no enforced pin. Commit: `docs: move raw run output to a release asset`.

## Done when
- [ ] README, AGENTS and RECOVERY carry no PR numbers; `docs/CONTINUATION.md` opens with one status block and is under 100 lines.
- [ ] `git ls-files -ci --exclude-standard` is empty.
- [ ] `tests.yml` has `concurrency`, a pinned toolchain and SHA pins, and the native-job equality test passes with the reviewed projection.
- [ ] `cloud_setup.sh` prints a failure summary and exits non-zero under `CHRONICLER_SETUP_STRICT=1`.
- [ ] 15 scripts are archived with manifest entries; nothing under `wealth_floor_*` or the nine workflows is removed.
- [ ] Native shards differ by under 10 percent in a green main run.
- [ ] `scripts/run_python_oracle_checks.py` passes; no pinned hash was rewritten; evidence JSON bytes unchanged.
- [ ] PR 6 merged only after DEC-8 is answered.
