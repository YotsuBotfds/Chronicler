# Chronicler remediation — final Codex/Claude handoff

## Exact state

- Repository: `yotsubotfds/Chronicler`.
- Development branch: `dev/kimi-remediation-20261031`.
- Base: `dev/claude-handoff-20261030` at `2e7425f4f863274c2a973ceba5f9cfb89b857ffb`.
- Exact runnable checkpoint: `cd4b3809924798ba1bdef796f42ceab233472102`. Its product tree is identical to final code handoff `05fdd541757e6b23efee3d9b32b796c975a2b258`; the later handoff commits are documentation-only. Use the delivery report or `git rev-parse HEAD` for the final branch tip.
- `main` remains untouched at `cb9fe70c81658fb65c6f511b821447f1d7b55b54`. No PR, merge, branch deletion, force-push, paid narration, or bulk experiment consolidation occurred.
- No unfinished product edit, untracked source, separate WIP commit, active worker, or active command remains. Finalization stopped remote file transfer, not a code change.
- Detailed ledger: `docs/integration/kimi-remediation-2026-10-31.md`.

## Completed work

All tracked remediation items are complete: exact population-loss apportionment; recoverable failed/interrupted batch evidence; resolved-action entropy/persistence and empty-sample reporting; atomic artifact-write coverage; Node 20 viewer hashing; checkpoint hash-seed semantics; a real simulate/view/exact-resume walkthrough; duplicate scenario-name rejection; and completed-turn checkpoints when Ctrl-C arrives during live pacing. Earlier branch work also covers checkpoint identity, politics bridge corrections, viewer codec safety, native unresolved-exile guards, artifact-budget admission, and dependency/evidence triage.

There is no separate experimental code hidden in this branch tip. Optional-system defaults and simulation decisions were not changed except for proven defect fixes.

## Setup, build, test, and launch

Required supported runtime is Python 3.13 or later. Viewer verification used Node 20.20.2; the workflow floor is Node 20.19.0. Native/Rust qualification requires Cargo and a freshly built matching `chronicler_agents` extension.

```sh
cd /mnt/agents/work/chronicler-remediation
python3.13 -m venv .venv
.venv/bin/python -m pip install -e . pytest pytest-asyncio

# Focused final Python regression lane:
PYTHONHASHSEED=0 .venv/bin/python -m pytest -q \
  tests/test_scenario.py \
  tests/test_live_checkpoints.py tests/test_live.py \
  tests/test_main.py tests/test_run_checkpoint.py \
  tests/test_state_checkpoints.py

# Aggregate/no-native real launch; do not install chronicler_agents in this lane:
.venv/bin/python -c "import importlib.util; assert importlib.util.find_spec('chronicler_agents') is None"
PYTHONHASHSEED=0 .venv/bin/python -m chronicler.main \
  --seed 42 --turns 8 --civs 2 --regions 5 \
  --agents off --simulate-only \
  --output output/kimi-e7/reference/chronicle.md \
  --state output/kimi-e7/reference/state.json \
  --checkpoint-every 4 \
  --checkpoint 'output/kimi-e7/reference/ckpt/turn_{turn:04d}.ckpt'

# Exact pre-final resume:
PYTHONHASHSEED=0 .venv/bin/python -m chronicler.main \
  --resume output/kimi-e7/reference/ckpt/turn_0004.ckpt --turns 8 \
  --output output/kimi-e7/resumed/chronicle.md \
  --state output/kimi-e7/resumed/state.json

# Viewer build/test/launch:
cd viewer
npm ci
npm test -- --maxWorkers=2 --reporter=dot
npm run lint
npm run build
npm run dev
```

Open the Vite URL, choose **Open Existing**, and select `output/kimi-e7/reference/chronicle_bundle.json`. The complete output-comparison script and limits are in `docs/local-simulate-view-resume.md`.

Native qualification commands for a capable fresh environment, currently UNRUN here:

```sh
cargo test --locked --manifest-path chronicler-agents/Cargo.toml
.venv/bin/python -m pytest -q
```

## Checks and evidence

- E8/final affected source: 103 scenario tests passed; 38 live checkpoint/pause tests passed; 98 main/exact-checkpoint tests passed; 8 state-checkpoint tests passed; 19 focused existing edge-case regressions passed. Both new defects had failing pre-fix reproductions and independent PASS reviews.
- E1: 302 affected tests passed, 6 native skips. E2: 57 batch tests passed. E3: 55 analytics tests passed. E4: 29 artifact-I/O tests passed.
- Viewer on Node 20.20.2: three sequential 745-test runs, lint, and production build passed after the lockfile correction. One earlier concurrent test invocation failed without retained diagnostics; it is undiagnosed, not a demonstrated current product failure.
- E7 real aggregate/no-native sample: six artifacts matched byte-for-byte after exact turn-4 resume; decoded bundles matched except `metadata.generated_at`; Chromium rendered the real bundle without viewer/page errors.
- Final base-to-handoff `git diff --check` passed. The final checkpoint/handoff commits are documentation-only, so unchanged-source test evidence was reused and no redundant suite was run.
- UNRUN, not qualified: fresh supported-install and complete current-tip Python suites; fresh CI; all Rust/native execution; full determinism/checkpoint matrix; scientific gates. Specifically B5 `test_restoration_skips_unresolved_original_identities`, genuine native economy coupling, and the native `PYTHONHASHSEED` probe remain UNRUN.
- Viewer audit retains 12 moderate minimatch/ESLint-family advisories. No force/downgrade was applied. Rust/Cargo is unavailable. Earlier portal filesystem `st_nlink` failures were mount-specific; the affected module passed on a normal filesystem.

## Remote publication state and smallest remaining reproduction

Immediately before handoff-only publication, verified additive remote head was `18e0d7adc9a3850e4b789672328df13208477654`. A delayed completion of the already-initiated `analytics.py` publication advanced the remote from checkpoint head `e5969a65710fb9069378053cd4e66dd5b9508d40`; its remote blob matches required local blob `11a16023d85a99457746d46a44656427255c7e8d`. No new product transfer was started. Forty-one of 47 nonworkflow changed-path entries now match local content or required absence. These five non-handoff files remain known mismatches and are deliberately unpublished:

```text
src/chronicler/main.py
src/chronicler/models.py
tests/test_main.py
tests/test_scenario.py
viewer/package-lock.json
```

`.github/workflows/tests.yml` also remains mismatched because GitHub returned 403 for missing OAuth `workflow` scope; local required blob is `95ce8b76a78a168c34b38a39c3a3e8940c5f5b3d`. Do not bypass that scope or claim whole-tree equivalence, exact-final-tree CI, or commit-for-commit local/remote history. The remote history is additive file publication and intentionally divergent from local Git history; do not pull/merge it blindly.

`tests/test_economy_oracle.py` was verified present at blob `a53f0a822757d06dcbe4c2521321131d95cf451e`; `tests/test_economy_parity.py` was verified absent.

## Preservation and restoration

The complete local branch, including all unpublished commits and this handoff, is preserved as:

```text
/mnt/agents/output/chronicler-kimi-remediation-2026-11-01.bundle
/mnt/agents/output/chronicler-kimi-remediation-2026-11-01.bundle.sha256
```

Verify and restore:

```sh
cd /mnt/agents/output
sha256sum -c chronicler-kimi-remediation-2026-11-01.bundle.sha256
git clone --branch dev/kimi-remediation-20261031 \
  chronicler-kimi-remediation-2026-11-01.bundle chronicler-recovered
cd chronicler-recovered
git status --short --branch
git rev-parse HEAD
```

Retained evidence is in the remediation tracker, `docs/local-simulate-view-resume.md`, branch history, and ignored local `output/kimi-e7/` artifacts. Earlier patches/archives remain under `/mnt/agents/work/`; none is required to restore this branch when the bundle is available.

## Next three priorities

1. **Finish exact-tree publication and CI.** Exact first action: read `AGENTS.md`, this handoff, and the tracker; run `cd /mnt/agents/work/chronicler-remediation && git status --short --branch && git rev-parse HEAD`; re-fetch the remote head and audit before writing. Publish only actual mismatches from the exact local blobs, including the workflow solely through an authorized workflow-capable channel, then verify every changed path and run exact-head CI/determinism/checkpoint gates.
2. **Qualify native execution freshly.** On Python 3.13+ with Rust/Cargo and a matching fresh extension, run complete no-native/native lanes and `cargo test --locked --manifest-path chronicler-agents/Cargo.toml`, explicitly including B5, native economy coupling, and native hash-seed checks. Keep skips separate from passes.
3. **Review independent experiments separately.** Do not bulk merge or promote defaults. Useful separate pointers observed on 2026-11-01:
   - Viewer `lead/cloud-viewer-fixes-20261029` — `eabba5c97d76601c5152d1fa0bc89ec4bccd577f`.
   - Grain eligibility `lead/grain-eligibility-diagnostic-semantics002-20261030` — `19a97e784a5ccb5f7f9e94246afe8f9e86434fee`.
   - Public grain shipments `lead/public-grain-shipments-semantics-20261030` — `b9e3fb11a2391f4ffbfb85a64cb62966b3088eb4`.
   - Merchant tax `lead/merchant-tax-ledger` — `7ae9bb3c7fdb1bcc9df577f5e95a54cb8b67290d`.
   - Runtime optimization `lead/cloud-runtime-optimization-20261029` — `249a4e1879cf5fbbb070de11f478f19825f51419`.
   - Native tick-index reuse `lead/native-tick-index-reuse-20261029` — `e2b7c940a86911a5ae57a74e0b4df3db6dbd3717`.
   - Native region-partition reuse `lead/native-region-partition-reuse-20261029` — `0900f3d203cc74102809bb871a1a057ba91a951f`.
