# Connected World correctness, causal evaluation and performance rework

## Current state — 2026-11-07, 23:05 UTC

The rework is active. Implementation, historical audit, performance admission,
default identity, active resume and real browser checks are complete. The fresh
CWR1 held evaluation is running; its results, final independent review and
final-head/main CI are still required. This is not a completion checkpoint.

- Verified main: `125a69066ea158a973ac5207f393e4eeb330aee8` (#98).
  Tests `42417310582` passed all nine jobs.
- Lead integration branch: `codex/cw-rework`; draft #99 contains the rework.
  Complete code head `4502fdc1` passed all nine jobs in `42419454116`.
  Later changes are evidence/docs and a valid test-fixture reason; final-head
  CI remains a merge gate.
- Corrected runtime: `8792be88dd36ba4d7c22e480de6a19dd64ea1300`, published
  `codex/cwr-final-runtime`, checkout `/workspace/cwr-final-runtime`.
- Held source: `b45c1e99572d4d6a60fb01fbd75cb7688aa54e93`, published
  `codex/cwr-held-runtime`, checkout `/workspace/cwr-held-runtime`.
  Production Python/Rust/scripts are identical to the corrected runtime.
- Compiled extension: `b1d3ea5ac858681960b2cb880c534164905501f6ab4f6f3c94f7c9b5f66196cd`;
  57 native inputs digest `f55df55d453ac37694410246c4a9728c56f3f6148f679fde8efc21ffd8775acf`.
  CPython 3.13.5; native crate pyproject is separately pinned. Each lane verifies
  actual import paths and artifact identity.

The [report](connected-world-rework-report.md), [reconciled coverage](connected-world-rework-coverage.md)
and [machine board](connected-world.json) contain the evidence and limitations.
The report is explicitly pending held closure and integration.

## Continue the existing held run

CWR1 started **2026-11-07T22:41:33Z**. All template 4101–4106 and procedural
4201–4206 seeds are potentially spent from that start. **Do not start a fresh
run of this cohort.** The registry stays reserved until the lead performs its
single standard `mark-run` after closure; that label does not mean unspent.

- Output: `/workspace/evidence/cwr-evaluation/held-cwr1-b45c1e99-v1`.
- Identity: `98c7bb2accb18b04e68f0585780ba58f85f03ece77c987d82ff67ceb7d9370a8`.
- Generic start ledger: `/workspace/cwr-held-runtime/output/held-runs/ledger.jsonl`;
  durable copies are in `connected-world-rework/held/start.json` and
  `../audits/connected-world/rework-cwr1-held/`.
- Active execution belongs to `rework_evaluation`, session 93595. A running
  process is not an assurance of container retention or automatic recovery.
- Last reported progress: 37/144 cases, zero failures; all twelve arms on
  p4201–p4203 completed. Budget-counted 1,314.4 seconds. Read the actual output
  before acting; this count is a dated checkpoint, not a final result.

The protocol is FROZEN at SHA256
`51b8a336969f48b4beb6f5b3e543062eda71822b98513b337ceb2d010e6efe7a`.
It specifies twelve arms, twelve worlds, 120 turns, one sequential job, fixed
controls/outcomes and a **two-core-hour ceiling**. The complete 24-case pilot
passed; its 553.2 seconds projects 1.383 core-hours with the fixed 1.5 margin.
Before start, 63 registry references / 14 versions had no collisions or spent
CWR1 reservation. Source, native, protocol, compatible pilot, seed and ledger
guards passed. No default, horizon, control, budget or seed replacement may be
changed in response to held outcomes.

The evaluation worker must not edit the registry. The lead records the actual
closed run once, including failure/incomplete state if applicable. Preserve
all unrun cases and failures. If execution is interrupted and its environment
is available, use only the same output, identity and immutable source with the
documented resume guard. Do not promise an automatic restart after reclamation.

## Verified work

- Attribution-to-health coupling is reproduced: the same physical moves got
  extra susceptibility 1.25 for known hunger/flight versus 1 for unknown reason.
  Explicit `density_only` removes that unsupported multiplier and retains
  existing physical density, hunger, urban and sanitation terms. New X1
  residence-arrival diagnostics are unique living IDs, not housing pressure or
  inferred motives. Twenty-turn coverage, gaps/caps/death/return/slot reuse and
  T−1 guards are tested. The real epidemic-dynamics regression fails with the
  old reader and passes corrected inputs/cases.
- Explicit A6 rules 3 keeps D3 inputs independent of personal record/shuffle and
  component controls. Actual combined inputs, components and would-be rows are
  distinguished. Defaults remain rules 2 / `legacy_displacement`.
- Historical CW6 arithmetic is reaffirmed: food shortfall and recorded epidemic
  deaths increased in all twelve worlds. The old contrast mixes personal
  decisions, D3 ownership and legacy feedback. Famine/war cause-specific deaths
  remain unrecorded. The earlier fixed-enrollment wage result is preserved.
- Final performance admission matches ten corrected-source pairs: 760 raw
  output pairs, complete timestamp-normalized typed bundles, 36 checkpoint pairs
  and all 37 private livelihood components. FULL CPU 318.28→265.89 seconds in
  the declared workload; largest case 105.44→69.55. Small/null/adverse results
  and residual FULL/OFF overhead remain. No evidence or world size is removed.
- Final default identity: nine cases / 399 files, zero differences against both
  original `8abc1acb` and preceding integrated main `125a6906` (verified retained
  source-equivalent baseline). See `connected-world-rework/verification/identity-final*`.
- Enabled resume: 14 branches plus two checkpoint-neutrality checks, 202 file
  comparisons, zero differences; 18 Arrow outputs match the pilots. Actual
  missing activations and checkpoint-zero limits are explicit.
- Browser: 372 real desktop/phone assertions; all 3,840 PH rows match T−1 X1.
  Corrected same-turn difference count 2,163, independently checked against
  3,808 adjacent rows. The invalid 2,392 counter receipt is preserved.
- Offline: 76 chunks, 8,119 pass / 69 conditional skips, max 31.99 s within
  unchanged 110 s cap (before final exact-floor delta). Its 70 focused tests,
  nine native lifecycle checks and complete-code CI pass. Rust: 1,339 pass,
  two existing manual timing benches ignored. All source pins remain intact;
  the appended cwr1 exact inverse is independently reviewed.

## Exact next work

1. Continue the existing 144-case CWR1 run, with periodic count/failure/budget
   checks. The raw first-world audit and independent arithmetic run separately;
   bounded per-input traces remain explicitly unverified where samples cap.
2. After closure, validate the full matrix and all world-level contrasts,
   source/native identities, report arithmetic, activation, nulls and harms.
   Preserve raw first worlds and compact controls/results. Do not tune outcomes.
3. The lead marks the registry once using the actual closed ledger and rows;
   update this ledger, board and report with verified results and limitations.
4. Obtain independent whole-PR review, green Tests on the final reviewed head,
   merge authorized #99, then verify exact main CI. Reconcile final reporting
   through the same reviewed/green-PR process; no direct push to main.

Resources are four cgroup CPUs / 16 GiB RAM. One held simulation and a bounded
readback job fit; there are no native builds running. Preserve other worktrees
and source. The report distinguishes regional availability from household
access: retail “all” is an eligibility recipe, not guaranteed realized coverage.
Recent arrivals are diagnostics; motives remain uncertain. Keep a single
spendable wealth balance and the existing mortality authorities.

Ports still lack a maritime service consumer. Owned cross-border wares are an
unimplemented/unadopted proposal. The constructed visibility example is not a
separately simulated alternate story. Full 200-seed/procedural qualification,
default promotion, paid narration, deployments, purchases and credential/sharing
changes remain outside authorization.
