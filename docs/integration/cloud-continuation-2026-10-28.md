# GitHub continuation during the workspace outage

This work starts from published `2f9d618b` on the separate branch
`lead/cloud-continuation-20261028`. It does not replace the newer local
integration recorded at `22a48ffa`, which was inaccessible during the outage.
Preserve that checkout and review/cherry-pick this branch when access returns.
Neither `main` nor `lead/integration-20261028` is updated by this work.

## Changes

- Strict artifact JSON rejects overflowing numeric tokens such as `1e9999`.
  Literal NaN/Infinity and duplicate-key rejection are retained. Finite floats,
  negative zero, underflow and integer parsing retain their previous semantics.
  This intentionally corrects malformed-artifact admission; no existing input
  file is rewritten. The comparator already checked finiteness independently.
- Faction win counting and tie resolution use the existing actor history index.
  They exclude unrelated civilizations' events before the existing checks,
  preserving turn filters, duplicate-actor counting, future-dated entries and
  tie preferences. The cache's existing append-only contract still applies.
  This removes repeated scans of unrelated history; no measured whole-simulation
  speedup is claimed.
- The detached [community capacity diagnostic](community-admissibility.md)
  decomposes saved method-2 observations while preserving oracle verdicts.
- The validation runner checks baseline readability before any simulation.
  Existing parser precedence and later comparison checks remain, including
  detection of a baseline that changes during execution. The workflow performs
  the same admission check before compiling Rust. Cohort comparability still
  requires the newly generated report; this preflight does not promise it.

## Verification scope

The first workflow-only continuation commit is `b2e86fa6`; its run is
[40782236953](https://github.com/YotsuBotfds/Chronicler/actions/runs/40782236953).
Later code changes need their own exact-head run.

New checks cover numeric overflow at root/nested positions, preserved finite
numeric semantics, actual method-2 counters at regional populations 99/100,
unchanged source reports, inconsistent counters, bounded input reads, faction
parity against the old full-scan functions, and rejection before child launches
for invalid baselines across all four profiles. Late baseline corruption tests
remain in the full suite.

Portable cases are registered individually in a new `diagnostics` offline
chunk. Each chunk retains its 110-second limit. Full native/no-native Python,
Rust and viewer lanes remain independent. Local execution is unavailable;
pending remote checks must not be described as passed.
