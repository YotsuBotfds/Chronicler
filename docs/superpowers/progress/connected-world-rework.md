# Connected World correctness, causal evaluation and performance rework

## Current state — 2026-11-07, 23:42 UTC

Implementation, historical audit, performance admission, default identity,
active resume, real browser checks and the fresh bounded CWR1 screen are
complete and independently checked. Final report/diff review, exact final-head
Tests, authorized merge and main CI remain required. This is a pre-merge checkpoint.

- Verified main: `125a69066ea158a973ac5207f393e4eeb330aee8` (#98).
  Tests `42417310582` passed all nine jobs.
- Lead integration branch: `codex/cw-rework`; draft #99 contains the rework.
  Code/evidence head `27074bba` passed all nine jobs in `42424371808`.
  Later changes are closed held evidence, registry records and documentation;
  final-head CI remains a merge gate.
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
The report includes closed held results and remains pending final integration.

## Closed held evaluation — do not rerun as fresh

CWR1 started **2026-11-07T22:41:33Z** and closed **144/144 strict-valid**,
zero failures. All template 4101–4106 and procedural 4201–4206 seeds are used.
The lead performed the standard `mark-run` **once after closure**; both entries
are `run`, complete with 144 rows. Cohort-content hash remains `62ce5aa8…`. Do not mark
again, launch a replacement cohort or reuse these seeds as fresh experiments.

- Output: `/workspace/evidence/cwr-evaluation/held-cwr1-b45c1e99-v1`.
- Identity: `98c7bb2accb18b04e68f0585780ba58f85f03ece77c987d82ff67ceb7d9370a8`.
- Protocol: FROZEN SHA256
  `51b8a336969f48b4beb6f5b3e543062eda71822b98513b337ceb2d010e6efe7a`.
- Metrics: `6c56e3ffa725848c69aecf6f2edfcdf81adb18e5c5f038562e2c9d3c73ace9e0`.
- Unchanged raw report:
  `e5d64f1658265a64ed100d158d650d29eed1f0247d77ea980599c3a145eaf2c3`.
- Sim 2,934.7 + extraction 410.1 = 3,344.8 seconds / 0.92911 core-hours,
  below the unchanged two-hour cap. Descendant CPU and RSS scopes are separate.
- Independent arithmetic passes all 144 rows and six rendered primary cells.
  Raw readback passes 24 retained first-world cases / 2,880 snapshots; bounded
  input samples leave 784 merge-turns explicitly unverified. Exact closure,
  commands, controls and receipts belong to the linked report and audits.
- All 171 registry/extractor tests pass after the single mark-run. The inherited
  generic activation headings have an adjacent erratum: no world was excluded.

AD−RD food shortfall is adverse in 11/12 worlds; recorded epidemic deaths rise
in nine, fall in two and tie in one. Mean differences and rates are adverse in both strata;
world signs, population denominators, nulls and harms remain explicit. Do not
claim one correction explains CW6→CWR1 changes across different rules/seeds.
Food availability is not complete household access, and missing famine/war
causes are not zero. No tuning or favorable-world selection occurred.

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
  the declared workload; most expensive baseline CPU case 105.44→69.55. Small/null/adverse results
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

1. Finish publishing the closed held packet and final report/coverage/board;
   obtain independent review of this final evidence/documentation delta.
2. Push the final reviewed #99 head and require all nine Tests jobs green on
   that exact head. Reconfirm fetched main and its CI before authorized merge.
3. Merge through the PR, verify the merge tree and all nine exact main jobs.
   Freeze further feature merges if main fails; repair or revert through a PR.
4. Record verified integration in a reviewed documentation PR, require its
   exact-head checks, merge and verify final main CI. Report the actual final
   commit, CI links, results and limitations. No direct push to main.

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
