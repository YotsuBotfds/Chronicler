# Needs oracle: autonomy without prior rebels

Branch `fix/needs-oracle-confound` from `integrate/wave-6` (`439f0c5`),
merged with `main` (`b8c1ace`, PR #19's offline-lane guard fix) without
rebase. Only the needs oracle changes (`src/chronicler/validation_io.py`).
The simulation, Rust, thresholds and every other oracle are unchanged. The
same branch splits the offline Python lane into chunks (last section).

## The confound

M53 oracle 2 (`run_needs_oracle`) pairs agents alike in everything but one
need and counts the paired event over the next 20 turns. For autonomy the
event is rebellion. [techniques-default.md](techniques-default.md),
sections 2 and 6, found the autonomy link reads backwards (pooled low/high
0.88 on the 200-turn defaults batches, 1.02 at 500 turns) and passes
through best-of selection.

**Mechanism.** The +0.10 is in Rust only: the apply step of the agent tick
(`chronicler-agents/src/tick.rs`, "4. Apply decisions") sets
`need_autonomy += 0.10` (capped at 1.0) for each rebel, next to its loyalty
reset. Python has no agent autonomy. Within a tick, needs decay and
restoration (step 0.75) run before decisions (3) and their application (4);
the validation sidecar is written after the tick, and agent events carry
the same turn. So a rebellion on the snapshot turn is already in that
turn's reading, and the outcome window `[T, T+20)` also counted it.

Restoration is proportional to the deficit: 0.03 per turn under one's own
civ, 0.03 without persecution, none while displaced; decay is 0.008. A
boost above a non-rebel's level shrinks by 3-6% a turn where restoration
runs and not at all where it does not.

**Measured residual.** Difference in differences on this branch's four
subset batches (80 worlds, 200 turns, below): agents with no rebellion in
the 30 turns before a snapshot and one rebellion, or a burst, in the next
10 turns, against agents of the same civ and region with none, read at the
later snapshots. Autonomy above the non-rebels' change, by turns since the
last rebellion (readings; standard error):

| Turns since | One rebellion | Two or more |
| --- | --- | --- |
| 0-4 | +0.085 (4,088) | +0.224 (4,135) |
| 5-9 | +0.084 (2,040) | +0.190 (642) |
| 10-14 | +0.048 (636) | +0.172 (520) |
| 15-19 | +0.057 (280) | +0.137 (79) |
| 20-24 | +0.035 (118; 0.010) | +0.110 (75; 0.014) |
| 25-29 | +0.035 (58; 0.011) | +0.069 (13; 0.037) |
| 30-34 | +0.024 (23; 0.025) | +0.092 (17; 0.022) |
| 35-39 | +0.015 (19; 0.017) | +0.054 (7; 0.050) |

The first bin is below +0.10 because of the 1.0 cap and because a higher
reading draws less restoration. In the oracle's terms (pairs need a gap
over 0.2), a burst alone can make a pair.

## The change

The autonomy pairing leaves out every agent with a rebellion on or before
the snapshot turn (`NEEDS_AUTONOMY_EXCLUDES_PRIOR_REBELS`; agent IDs are
never reused). Other pairings, the 20-turn window, the snapshot sampling,
best-of selection and the thresholds (60% of seeds, median |d| > 0.10) are
unchanged. The report records `autonomy_excludes_prior_rebels`, and
`run_needs_oracle(runs, exclude_prior_rebels=False)` reproduces the old
result exactly (checked against the saved reports below).

Why not a window ending at the snapshot: one rebellion still reads +0.035
after 20-29 turns, a burst +0.07 to +0.11 after 20-34, and without
restoration the shift does not decay. Exclusion windows of 30 and 40 turns
give the same pairs as the whole history on 42-61 and 62-81; a 20-turn
window keeps a few recidivists and gives 16, 10 and 16 seeds on the first
three sets (whole history: 15, 9, 15).
A pre-event reading is not recorded: needs snapshots are every 10 turns,
so an agent's last reading before its rebellion is from a different turn
than its partner's.

## Results

Each set: 20 worlds x 200 turns, `scripts/m53b_run_validation.py --profile
subset --parallel 2`, hybrid, `PYTHONHASHSEED=0`, current defaults
(techniques and historiography on), Linux, Python 3.13.17, native extension
built fresh from `chronicler-agents` tree `e5d7506` and verified. "Before"
is the unmodified `439f0c5` oracle run on the same batch; "after" is this
branch. Rerunning sets 42 and 62 reproduced all 40 sidecar files per set
byte for byte.

| Seeds | Gate before / after | Needs seeds (12 required) | Median d | Pairs at the chosen candidates | Comparator |
| --- | --- | --- | --- | --- | --- |
| 42-61 | PASS / PASS | 17 / 15 | 1.000 / 1.088 | 48 / 32 | NO REGRESSION |
| 62-81 | FAIL / FAIL | 11 / 9 | 0.321 / 0.316 | 51 / 45 | NO REGRESSION |
| 82-101 | PASS / PASS | 18 / 15 | 1.207 / 1.000 | 59 / 31 | NO REGRESSION |
| 102-121 | PASS / PASS | 18 / 15 | 1.228 / 1.262 | 56 / 25 | NO REGRESSION |
| All 80 | | 64 / 54 | | | |

The "before" column equals the techniques-on column of
[techniques-default.md](techniques-default.md) section 1. Community, cohort
and every informational oracle are identical before and after on all sets.
Seeds lost: 57, 58; 62, 77; 90, 91, 98; 108, 114, 118. All ten had
qualified on an autonomy candidate. None gained.

**Pooled pairs**, every snapshot and pairing the oracle reads, no best-of
selection, 80 worlds (95% seed bootstrap):

| Pairing | Pairs | Events, low-need agents | Events, high-need agents | Low / high |
| --- | ---: | ---: | ---: | --- |
| autonomy -> rebellion, before | 1,732 | 2,312 | 2,315 | 1.00 (0.91-1.09) |
| autonomy -> rebellion, after | 629 | 106 | 82 | 1.29 (0.82-2.15) |
| material -> migration (unchanged) | 287 | 252 | 207 | 1.22 (1.03-1.44) |

The "before" row reproduces techniques-default.md section 2. After the
change the autonomy ratio per set is 1.54, 2.50, 1.57 and 0.74; 50 of 80
worlds have no rebellion among their autonomy pairs.

**Why the link stays weak.** In the agent model autonomy adds rebel
pressure only below `AUTONOMY_THRESHOLD` = 0.25 (`needs.rs`; the same
deficit speeds negative loyalty drift in `behavior.rs`). Among agents
without prior rebellions, 2 of the 629 pairs have the low agent under 0.25
(old pairing: 7 of 1,732). The pairing nearly always compares two agents
above the threshold, where the model gives autonomy no direct effect on
rebellion. The old pairing's events came from recidivists, which is the
confound.

**Seeds 62-81.** The fix does not close the gap: the set goes from 11 to 9
of 20. Its autonomy pairs now hold 14 rebellions in 234 pairs over all
snapshots, and 15 of its 20 worlds have none. The best-of test had found
qualifying windows among recidivists.

**Which pairing carries a seed.** After the change, 35 of the 54
qualifying subset seeds qualify on material and migration (18 on
autonomy, 1 on safety); before, autonomy carried most.

**500-turn probe.** Seeds 142-161 x 500 turns, the same runner with
`--turns 500` (the subset profile's sidecars, which are the full profile's;
not the 200-seed gate):

| | Before | After |
| --- | --- | --- |
| Needs seeds (12 required); median d | 20; 1.03 | 20; 2.00 |
| Seeds carried by autonomy / material | 14 / 6 | 6 / 14 |
| Pooled autonomy pairs; low / high events | 1,710; 2,685 / 2,627 | 473; 51 / 49 |
| Pooled autonomy low / high | 1.02 (0.93-1.13) | 1.04 (0.62-1.77) |
| Pooled material low / high | 1.46 (1.20-1.79) | unchanged |

The "before" autonomy ratio equals the full gate's 1.02
(techniques-default.md section 3). Community, cohort and the comparator
are as on the subsets: identical, NO REGRESSION. With about 48 snapshots
per world every seed still qualifies (14 on material, 6 on autonomy), so
the full gate's needs oracle is unlikely to fail on this change; it has
not been run.

**Thresholds** stay as the M53 spec set them. The data show a per-seed
best-of test with less power, not a miscalibrated cut; lowering the seed
fraction until 62-81 passes would fit the gate to its result.

## Offline lane chunks

`scripts/run_python_oracle_checks.py` ran its whole selection in one
guarded pytest process with a 110-second limit, at about 76 s on this
machine. It now runs four chunks, each a separate pytest process with its
own offline guard and receipt and the same 110-second limit, and stops at
the first failing chunk. The selection (`--list`) is unchanged. A fresh
guard per process keeps every guarantee (native imports, network and child
processes blocked; runtime factories replaced), and the bound per process
is unchanged; growth is handled by moving files between chunks, not by
raising the limit.

| Chunk | Node IDs | Tests | Seconds (of 110) |
| --- | ---: | --- | ---: |
| core (simulation, politics, ecology, validation, bundle, CLI, checkpoint replay) | 59 | 1,054 passed, 2 deselected | 21.8 |
| governance (institutions, elites, governance, bridge contract) | 7 | 567 passed, 3 skipped | 15.4 |
| systems-1 (diplomacy, techniques, maritime) | 3 | 114 passed, 4 skipped | 16.9 |
| systems-2 (agendas, nomads, snapshot pruning, historiography) | 4 | 160 passed, 3 skipped | 21.8 |

Totals equal the single-process run: 1,895 passed, 10 skipped,
2 deselected. Wall time 75.8 s against 77.5 s for one process measured
earlier the same session (4 cores shared with other agents' runs); the
three extra interpreter starts cost little. Every chunk's guard reports
PASS, no native module loaded and no blocked I/O. A copy with a 5-second
limit stopped after the first chunk with "5-second chunk limit exceeded"
and exit 1. Raising the single limit was the alternative: one process,
but every added suite eats the same margin.

## Verification

Linux, Python 3.13.17; the oracle code as at `c51d5f4`.

| Check | Result |
| --- | --- |
| `pytest -m "not slow" -n 2`, native extension built fresh and verified | 5,890 passed, 3 skipped, 526 subtests (the wave-6 base records 5,887 passed, 3 skipped; three new tests) |
| `pytest -m slow -n 2`, native | 11 passed, 3 skipped (the skips are unconditional or agents-gated in the M36/M38b regression files) |
| No-Rust virtualenv without `chronicler_agents`, `pytest -n 2` (slow included) | 5,690 passed, 203 skipped, 526 subtests |
| `scripts/run_python_oracle_checks.py` | PASS, 1,895 passed, 10 skipped, 2 deselected, four chunks, 75.8 s |
| Rust | unchanged, so no `cargo test` |

The new tests (`tests/test_validate.py`): a seed where recent rebels read
high and keep rebelling, so the old pairing finds low/high = 1/3 and fails,
and the exclusion (which also catches a burst 48-50 turns earlier) restores
the expected sign; the exclusion's boundary (a rebellion on the snapshot
turn counts, one a turn later does not, migrations never do); and a
material pairing among recent rebels that is identical with and without
the exclusion.

## Open

* The per-seed needs test has little power for autonomy once prior rebels
  are out: first rebellions are rare. A test that pools each pairing's
  pairs across a seed's snapshots, or a longer outcome window, is a
  calibration for the needs owners, with its own effect on the base.
* The autonomy pairing rarely tests the mechanism: it needs a 0.2 gap,
  and autonomy acts on rebellion only below 0.25, where 2 of 629 low
  agents sit. Pairing on the deficit below the threshold, or reading
  autonomy's loyalty-drift effect instead, is for the needs owners.
* 62-81 fails the subset needs gate before and after (11, now 9).
* The 200 x 500 full gate has not been run with this oracle.
