## Current status

- **Date:** 2026-11-08.
- **`main`:** `c3d752fa` (`c3d752faf0b287b7833bf5d58af470a127c985b2`).
- **Last merged PR:** #100 (`codex/cwr-closeout`, "Close the verified Connected World rework
  ledger and audit reproduction").
- **Last verified Tests run on `main`:** `42431233265` (push, attempt 1, success, head `c3d752fa`).
- **200-seed gate:** not run.
- **Unmerged work:** the streamline-and-deepen roadmap lives at
  [superpowers/roadmaps/streamline-and-deepen.md](superpowers/roadmaps/streamline-and-deepen.md)
  with its board `superpowers/progress/streamline-and-deepen.json`. It and its tooling
  commits are on branch `claude/relaxed-brown-4ozgeg` (and the `sd/*` task branches built on
  it) and are **not merged to `main`**.
- **History split (HYG-1):** the dated checkpoints that followed this block moved byte-for-byte
  to [superpowers/progress/continuation-history.md](superpowers/progress/continuation-history.md).
- Update this block in the ledger commit after each merge.

# 2026-11-08 — external review response (branch `claude/relaxed-brown-4ozgeg`)

The external review of `b0811a73` requested changes, all at P2; all are addressed on the branch:
1. **Oracle `--jobs` and Ctrl-C.** Results go to caller-owned storage; on an exceptional exit
   finished chunks are published, the receipt is built in `finally` with `error: interrupted`
   and `passed: false`. Regression tests at scheduler and runner level fail on `b0811a73`.
2. **COR-1 hash-seed sweep plan.** The child no longer runs with `-I`; it gets an absolute
   `PYTHONPATH`, explicit `cwd` and platform variables, and checks its checkout, its seeds and
   that seed 0 reproduces the pre-fix output.
3. **PIN-2 gate plan.** The native SHA-256 is provenance, not equality; identity is judged by
   output digests within a compatibility class.
4. **DEP-6 tax plan.** `money.pay` is the only settlement step (`MoneyBook` in
   `ClosedMoneyState`); no second treasury credit or separate carry.
5. **DEP-6 tithe plan.** One funded collection pays treasury and priest parts; zero priests,
   insufficient funds, refusals and the escrow residual are specified.

The workstation guide creates `output/` before receipts, saves a native receipt, separates a
local PASS from a reproduction of the reference CI gate run, and states that Python 3.13.5
fails the argparse golden on untouched `main`. The full bounded oracle lane passed on the
code of `567571f`: `--jobs 4` 8,139 passed / 69 skipped / 0 failed in 96.9 s (slowest chunk
37.7 s of 110 s); serial, same per-chunk counts, 339.6 s. Exact-head CI has not run:
`tests.yml` does not run on pushes to that branch.

# 2026-11-08 — workstation tooling (Linux 9950X / 3950X)

Setup is in [workstations.md](workstations.md); tasks ENV-1 to ENV-8 are on the
streamline-and-deepen board. On branch `claude/relaxed-brown-4ozgeg` (no PR yet):
`scripts/check_python_env.py --machine [--json]` (ENV-2, a workstation receipt that never
changes the result) and `scripts/run_python_oracle_checks.py --jobs N` (ENV-3; default 1 is
the serial CI loop, N > 1 uses `scripts/testing/chunk_scheduler.py`, ordered start, no new
start after a failure). `tests/test_oracle_chunk_scheduler.py` is in shard 1, the
`build-provenance` chunk and the additions map (461 modules). Verified in the 4-core cloud
container: focused tests (255 passed); oracle lane serial PASS (76 chunks, 8,135 passed,
69 skipped, 324.6 s) and `--jobs 4` PASS (85.2 s, slowest chunk 33.7 s). Not run: native
and viewer tests, the 200-seed gate, anything on the workstations (ENV-5 to ENV-7). ENV-4 is
lower priority on Linux, where forked workers inherit the seed; set `PYTHONHASHSEED=0`.

# 2026-11-08 — repository scout and streamlining plan (docs only)

The [repository scout](superpowers/audits/2026-11-08-streamlining-scout.md) is a read-only
audit of `main` at `c3d752fa` by 32 area scouts (reports in
`superpowers/audits/2026-11-08-scout/`), spot-checked by the lead. It ran
`pytest --collect-only` (11,972 tests), `cargo check` (0 warnings), the app `tsc --noEmit`
(0 errors), four aggregate 150-turn runs and `refactor_preflight.py` over tracked sources; not
the oracle lane, native or viewer tests, `turn_speed_identity.py` or the 200-seed gate. It
lists ten lead-verified bugs or contract breaches (among them: the EXPAND draw ignores the
world seed; new live worlds miss the governance default; a food debit's order depends on
PYTHONHASHSEED; live integer parsing overflows on `Infinity`; four default-path provenance
decision reads) and eight owner decisions (D1–D8). Its section 8 records errata, including
one retracted bug (the food residual).

The [streamline-and-deepen roadmap](superpowers/roadmaps/streamline-and-deepen.md) turns it
into phases R0–R7 and six milestones; the board holds 81 tasks, with 13 design specs
(`superpowers/specs/2026-11-08-*-design.md`) and 13 plans (`superpowers/plans/2026-11-08-*.md`).
The plans were written without running any gate, so their commands are untested.

# Connected World rework — runtime integrated and verified

The correctness, causal evaluation and performance rework is implemented, independently
reviewed and evaluated. PR #99 merged at `a5ccbbf528de82d8a4fa19dbebe7d6ab805b2b96`, tree
equal to reviewed `72d89dde`; premerge Tests `42426724513` and exact main Tests `42428257952`
passed all nine jobs. Read the
[report](superpowers/progress/connected-world-rework-report.md),
[coverage](superpowers/progress/connected-world-rework-coverage.md),
[machine board](superpowers/progress/connected-world.json) and
[ledger](superpowers/progress/connected-world-rework.md); they supersede all historical
next-task entries. Ports, owned wares and constructed-story scope remain limited; no broader
completion or qualification is implied. All 144 fresh held cases passed under the two-core-hour
cap; seeds 4101–4106 and 4201–4206 are used once and must not be rerun as fresh.
Adverse/null/mixed results and known limits stay explicit. Defaults are unchanged; corrected
use selects explicit rules 3 and density_only. No restricted qualification or default
promotion occurred. The closeout PR (#100, `codex/cwr-closeout`) changed no runtime. Do not
infer an unrun gate from historical reports. No automatic restart after reclamation is promised.

## Historical checkpoints (not current tasks)

Moved to [superpowers/progress/continuation-history.md](superpowers/progress/continuation-history.md)
on 2026-11-08, byte-for-byte.
