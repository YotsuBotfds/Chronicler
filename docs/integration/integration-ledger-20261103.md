# Integration ledger — 2026-11-03

## Ground truth and preservation

Fresh wildcard fetch (`git fetch origin '+refs/heads/*:refs/remotes/origin/*'`,
without pruning) found 304 remote heads. The initial clone's configured fetch
refspec covered only main, so an ordinary `fetch --all` was insufficient.

- Main: `cb9fe70c81658fb65c6f511b821447f1d7b55b54`.
- Verified development base: `63581a9a1a1297396ce2227ac2683aeefd5ad8a3`,
  `dev/codex-playable-build-20261031`. Fresh ancestry: 523 ahead, zero behind main.
- New integration branch: `integration/crisis-recovery-20261103`, isolated at
  `/workspace/Chronicler-integration`; original clean `/workspace/Chronicler`
  checkout remains on `work` at main. Donor implementation has its own worktree
  and branch `integration/debt-holder-followup-20261103`.
- The inaccessible previous thread's uncommitted work and ability to resume are
  unknown. Nothing here establishes recovery or shutdown of that thread. Existing
  refs/checkouts, private backups and default feature settings are preserved.

The audit used ancestry for all heads, then `git cherry` patch equivalence and
merge-base-to-head changed paths/current blob comparison for all 142 distinct
heads among the 170 divergent refs. 134 heads are exact development ancestors.
Three divergent heads contain only patch-equivalent commits; divergent history
alone does not identify missing functionality. 78 divergent heads have no
changed production-runtime files (they still may contain distinct tools/tests).
This is an inventory with scoped diff review, not certification of every hunk
or an instruction to merge all refs.

## Decisions

| Source / exact head | Classification | Evidence and disposition |
| --- | --- | --- |
| `main` / `cb9fe70c…` | Already included | Exact ancestor of verified development base; no reconciliation merge needed at audit time. Re-fetch before final handoff. |
| PR [#68](https://github.com/YotsuBotfds/Chronicler/pull/68), `feat/viewer-debt-holders` / `62522d4b2a0afe2f0bb9fca00460a9bf74b54c42` | Already included | Exact ancestor of development. GitHub still reports OPEN against main; that does not mean missing from development. Five original commits and author attribution already retained. Historical three-job CI succeeded; this is not new final-head evidence. |
| `dev/codex-kimi-qualification-20261031` / `32ac587908b28167e45ff105f62ace988fbb8e12` | Already included | Exact ancestor. Supported-runtime qualification and reviewed fixes are in current history. |
| `dev/kimi-remediation-20261031` / `1a023126d31e808d2958c026307df956c9f2e7db` | Superseded publication copy | Actual unique log is repeated additive file publication, not complete local history. Its own final handoff warns against blind merge; current qualification branch restores complete history. 11 touched files still differ from current source because of later changes. Preserve it; no whole-tree equivalence claim. |
| `feat/grain-reserves` / `0a3c2503fe6fccac3984a89eacae366b9a9f41e6` | Already included | Exact ancestor of development, with later storage, release and viewer work. |
| `lead/public-grain-shipments-{source,tests,semantics}-20261030` / `b9e3fb11a2391f4ffbfb85a64cb62966b3088eb4` | Superseded composition | Four divergent commits include an old exact-ref CI activation. Current source has `public_grain_shipments.py`, state, CLI admission, real checkpoint tests and documented current-source composition (`19c8e43b…`); do not replace newer sources or activate the historical workflow. |
| `lead/grain-eligibility-diagnostic-{source002,semantics002}-20261030` / `19a97e784a5ccb5f7f9e94246afe8f9e86434fee` (earlier `80cf9ce4…`, `4606cda2…`) | Deferred diagnostic | Actual extra work is passive resource/eligibility tooling plus historical-source workflow admission. Current shipment composition already records the real zero-payment fixture gate. No new simulation feature recovered by merging this diagnostic. |
| `lead/viewer-debt-holders-{source,qa}-20261030` / `18ba7aea91ec8947eb01e2a01a3c3e1753ab8709` | Unique, useful; selectively integrated | One actual donor commit adds holder name identity, accurate common bar scale, unambiguous event-only borrower selection, deduplication, as-of loss amounts and reset handling. Compose with current sparse/mixed-version behavior; retain donor commit and author attribution (YotsuBotfds). Exclude stale CONTINUATION appendix and obsolete exact-ref QA workflow. |
| `lead/cloud-viewer-fixes-20261029` / `eabba5c97d76601c5152d1fa0bc89ec4bccd577f` and draft debt-detail/loss descendants | Superseded | Current development already has snapshot-specific detail, nullable mixed-version loss counters and fallen-borrower strip events. The newer selected donor supplies missing parts without rolling those fixes back. |
| `lead/cloud-runtime-optimization-20261029` / `249a4e1879cf5fbbb070de11f478f19825f51419`; `lead/arc-event-types-draft-20261029` / `2e0bd7f72cd8cd40a46af2d1bfbae05da7aac721` | Already represented / historical tooling | Arc projection is present via `58ba0fad…`; all six commits of the latter ref are patch-equivalent. Historical parity/CI workflows are not a new product backlog. |
| `lead/native-tick-index-reuse-20261029` / `e2b7c940a86911a5ae57a74e0b4df3db6dbd3717`; `lead/native-region-partition-reuse-20261029` / `0900f3d203cc74102809bb871a1a057ba91a951f` | Already represented | Development contains dense tick lookup and post-migration partition through `86772a66…`, `2bc54bd9…` and later staging; preserved historical heads differ from later evolved tick source. No old-file replacement. |
| `lead/validation-turn-index` / `dcf30cc8ea03d2f3d981cb09857fb9d5e9ffdba3`; `lead/live-roundtrip-lifecycle-draft-20261029` / `0fa6a607ab5120b8676172092bf4250c26290580` | Already represented | All branch-unique commits patch-equivalent under `git cherry`. |
| `lead/merchant-tax-ledger` / `7ae9bb3c7fdb1bcc9df577f5e95a54cb8b67290d`; `fix/merchant-tax` / `1506fda5fddde274fa85fcfd4ff585731b2b9a38` | Distinct, deferred | Five/three genuinely divergent commits add Rust merchant debits, bridge fields, Python tax ledger, tuning and tests (14 changed paths, 1,396 additions on latest vs main). This changes economic behavior; donor documentation says confirmatory/default economic gates remain pending. Keep separate from the crisis queue; no claim it was integrated or rejected as useless. |
| Other divergent profiling, proof publication, forkserver metadata, GP context, household-journal, culture-count and workflow-relay refs | Uncertain / deferred | Actual changed paths contain detached tools, historical exact-source controllers or competing optimizations, not just missing named features. No exhaustive semantic or modern performance qualification performed. Preserve refs; require a scoped current-source need and evidence before promotion. |

Only PR #68 was open in the fresh GitHub query. Recent PRs #49–67 are merged
into main; their feature branch heads are already in development ancestry. No PR
was closed, relabeled, commented on, merged or deployed by this audit.

## Debt donor composition and verification

The selected change preserves newer mixed-version notes, missing lender gaps,
nullable cumulative-counter behavior and existing snapshot-based strip records.
The detail table now admits structured, uniquely attributable events at the
selected turn, displaying `Not recorded` until an already available counter
supplies an amount. It does not parse prose or use a future counter. Named
lenders matching category labels remain inspectable; small bar segments no
longer gain fixed-width inflation.

On Node 24.19.0, 81 focused tests passed (the debt helper and systems panel
modules); full viewer ESLint and TypeScript/Vite production build passed. Running
the same panel assertions on the untouched development source produced 9 failures
and 59 passes: eight new defect assertions plus the deliberate unknown-label
change. The baseline negative remains in external scratch evidence. No runtime
simulation source changed. JSDOM's style assertion does not establish practical
browser layout; browser checks remain a separate lead-owned lane. Full final integration checks and exact-head CI must
be recorded by the lead on the final integrated commit. Scientific balance,
held-out efficacy and browser qualification are separate from these UI checks.
