# Targeted exploration closeout correction — 2026-11-02

Baseline: clean local and refreshed remote `eddad48c736b9bda1e1f7daf177915841bbc5d15`
on `dev/codex-playable-build-20261031`. No newer work was replaced. Main,
Python/Rust source, dependency locks and economic defaults are unchanged.
Reusable environment publication remains deferred.

## Reproduced failures and corrections

- Historical search dropped an exact turn-1 actor match among 750 observations
  because it retained only the latest 200 before querying. It now visits every
  eligible, unambiguous snapshot through the selected turn before bounding
  materialized results (30 in the UI; hard maximum 100 in the query API). Repeated
  names stay separate observations, dated aliases keep their existing clock,
  and future observations stay excluded. The extra index retains snapshot
  references rather than an allocated result per actor; query work still grows
  with recorded history, without silently truncating coverage.
- Controlled localStorage interleaving lost tab A's bookmark and private note.
  A candidate using Web Locks plus localStorage also failed actual two-tab
  checks and was rejected; the failed evidence is retained. The accepted fix uses
  one IndexedDB readwrite transaction for read/check/write, atomically imports
  the validated legacy v1 envelope once, and leaves legacy bytes intact.
  Distinct additions survive; a stale same-key save is refused. The draft stays
  visible; **Review latest saved bookmark**, then a separate save, explicitly
  authorizes replacement. Storage failures retain existing data and the draft.

[Search implementation](../../viewer/src/lib/historicalSearch.ts),
[search regressions](../../viewer/src/lib/__tests__/historicalSearch.test.ts),
[bookmark transaction](../../viewer/src/lib/investigationBookmarks.ts),
[bookmark UI](../../viewer/src/components/InvestigationBookmarks.tsx).

## Executed checks

- **1,112 viewer tests / 101 files**, full ESLint and TypeScript/Vite production
  build passed on Node 20.19.0. The focused integration pass was 51 tests.
- Real Chromium, eight repeated controlled two-tab storage-API trials: distinct
  additions preserved; exactly one competing same-key save refused. Concurrent
  legacy import preserved the original private note and legacy bytes.
- Actual rendered production UI in two tabs: distinct saves, same-key conflict,
  draft preservation, explicit review/replacement, reload, injected synchronous
  quota failure and unavailable-storage retry passed, with zero page errors.
- Search browser evidence uses an explicitly constructed 250-snapshot /
  750-observation fixture, not a scientific simulation. An older exact match is
  found; rewinding excludes future observations; repeated names remain bounded.
- Historical [nine-job CI](https://github.com/YotsuBotfds/Chronicler/actions/runs/41401640607)
  tested `38116fc2`, before these viewer fixes. Its Python/native/Rust checks are
  unchanged-input evidence, not new execution on this correction. No unrelated
  scientific campaign or native rebuild was performed.

External evidence root: `/workspace/shared/chronicler-closeout-correction`.
[Search reproduction](/workspace/shared/chronicler-closeout-correction/search/reproduction.txt),
[original lost-note race](/workspace/shared/chronicler-closeout-correction/bookmarks/original-race-output.json),
[rendered two-tab receipt](/workspace/shared/chronicler-closeout-correction/bookmarks/rendered-two-tabs-result.json),
[combined viewer log](/workspace/shared/chronicler-closeout-correction/combined-viewer-tests.log).
Failed/rejected candidates and harness-only failures remain alongside final receipts.

## Completion scope and recovery

The [36-item matrix](development-lead.md#backlog-outcome) now separates newly
implemented/tested, existing checked/reused, partially covered and deferred
boundaries, with implementation and evidence links for every row. Private native
transport disruption remains audit-only, actual food consumption is unrecorded,
and institution histories remain city-first. This release establishes a bounded
exploration workflow; it does not establish blanket completion or scientific
qualification of all original aspirations.

Backups use the existing private, owner-only
[Chronicler Archives](https://drive.google.com/drive/folders/1NfGQsBD4fvqus3qXM-8-xImPSWOX0gEm).
Three remote evidence parts were independently downloaded and reassembled to
87,816,343 bytes, SHA-256
`4217e8cc7c87fe06f38f4df0b01e78101bfe474cc9e50f501efeca9d093e9576`.
The monolithic redundant upload has verified size/access only; the three verified
parts are the authoritative recovery copy. Stopped browser session tokens were
redacted in the recovery archive; disposable test scratch/cache and nonregular
aliases were excluded. Worlds/checkpoints are unchanged and local originals kept.
Final corrected source, correction evidence and restoration instructions are
being added; final transfer/restoration verification is recorded in the external
release manifest rather than inferred from upload success.

Bookmarks are private to the browser origin/storage partition. Atomicity applies
to tabs running this corrected version. Reload older open tabs to migrate; old
code cannot write the new database but old-code tabs racing with each other are
not protected. Browser eviction/user clearing are not off-machine note backups.
No unsafe localStorage fallback is used if IndexedDB is unavailable.
