## Current status

- **Date:** 2026-11-08.
- **`main`:** `c3d752fa` (`c3d752faf0b287b7833bf5d58af470a127c985b2`).
- **Last merged PR:** #100 (`codex/cwr-closeout`, "Close the verified Connected World rework
  ledger and audit reproduction").
- **Last verified Tests run on `main`:** `42431233265` (push, attempt 1, success, head `c3d752fa`).
- **200-seed gate:** not run.
- **Unmerged work:** the streamline-and-deepen roadmap lives at
  [superpowers/roadmaps/streamline-and-deepen.md](superpowers/roadmaps/streamline-and-deepen.md)
  with its board `superpowers/progress/streamline-and-deepen.json`, the owner's
  [decisions](superpowers/progress/streamline-and-deepen-decisions.md) (DEC-1–DEC-8, 2026-11-08)
  and the lead's [integration ledger](superpowers/progress/streamline-and-deepen-ledger.md).
  Reviewed tasks are integrated on branch `claude/exciting-mayer-nolksw` (built on the plan
  branch `claude/relaxed-brown-4ozgeg`) and are **not merged to `main`**; no PR is open.
- **History split (HYG-1):** the dated checkpoints that followed this block moved byte-for-byte
  to [superpowers/progress/continuation-history.md](superpowers/progress/continuation-history.md).
- Update this block in the ledger commit after each merge.

# 2026-11-09 — streamline-and-deepen integration (branch `claude/exciting-mayer-nolksw`)

Owner decisions DEC-1–DEC-8 (2026-11-08) are in the
[decision record](superpowers/progress/streamline-and-deepen-decisions.md); every merge, its
reviewed heads and its gates are in the [integration ledger](superpowers/progress/streamline-and-deepen-ledger.md).
Behaviour-neutral work (R1/R2 hygiene, dead code, neutral fixes, tooling, PIN-2 and PIN-1 under
DEC-1 option A, the Rust consolidation CON-5/6/7, the CON-1 switch registry and the live fixes
FIX-1/3/10/11) compared identical on all nine identity cases. Corrections (owner go-ahead
2026-11-08), each with a [baseline report](superpowers/progress/streamline-and-deepen-baselines/):
COR-9 (Rust `stable_hash_int` repr parity) and COR-7 (Rust politics step 11 deleted) give 0
differences; COR-6a/6b (war early-return flush, drained-only soldier deaths) give 0 differences
on the identity cases and a 40-seed agents-off batch; COR-10 (`gp_agendas` projected treasury
respects the keep watermark) changes `proc48_hybrid_s42` (first divergence turn 33) and gate
case `g_learning_s42` only, whose native golden was re-captured. COR-8a/8b/8c (explicit hills
and river ecology rows, warnings for unread tuning keys, tithe parity test) give 0 differences;
FIX-14 (any `--tuning` file changes the run) is a new investigation item. COR-6c waits for its
own PR now that PIN-1 is in. Not merged to `main`, no PR, 200-seed gate not run; goldens were captured
locally (CI capture pending); tag `pin-freeze-2026-11` not yet created. The superseded
2026-11-08 review-response entry is verbatim in the history file.

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
