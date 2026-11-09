# Audits index

Audits are dated evidence of the source they read, not task lists. Files stay at their
original paths so existing links keep working; this index says which one is current.
The current project status is the
[current status block](../../CONTINUATION.md#current-status).

## Current

| File | What it is |
| --- | --- |
| [2026-11-08-streamlining-scout.md](2026-11-08-streamlining-scout.md) | Read-only audit of `main` at `c3d752fa`: verified bugs (section 4), the streamlining waves, owner decisions and errata (section 8). Per-area reports are in [2026-11-08-scout/](2026-11-08-scout/README.md). It feeds the [streamline-and-deepen roadmap](../roadmaps/streamline-and-deepen.md). |

## Historical

These describe older source. Scout 30 of the 2026-11-08 audit
([30-docs-hygiene.md](2026-11-08-scout/30-docs-hygiene.md)) re-checked their 12
highest-severity findings against `c3d752fa`: 11 are fixed and 1 (2026-04-02 C3) is
partly present. Their severity labels were never updated, so do not work from them.

| File | Date | What it is |
| --- | --- | --- |
| [2026-03-29-full-codebase-audit.md](2026-03-29-full-codebase-audit.md) | 2026-03-29 | 10-agent full audit. |
| [audit-gpt-5-2026-03-31.md](audit-gpt-5-2026-03-31.md) | 2026-03-31 | One of two independent audits before `M60a`. |
| [audit-opus-4.6-2026-03-31.md](audit-opus-4.6-2026-03-31.md) | 2026-03-31 | The other independent audit (commit `d9baf0a`). |
| [audit-crossref-2026-03-31.md](audit-crossref-2026-03-31.md) | 2026-03-31 | Finding-by-finding comparison of the two. |
| [audit-crossreference-gpt-5-vs-opus-4.6-2026-03-31.md](audit-crossreference-gpt-5-vs-opus-4.6-2026-03-31.md) | 2026-03-31 | A second comparison of the same pair. |
| [masteraudit.md](masteraudit.md) | 2026-04-01 | Master audit merging two verified audits. |
| [opusaudit4-1-26.md](opusaudit4-1-26.md) | 2026-04-01 | Comprehensive audit. |
| [2026-04-02-full-codebase-audit.md](2026-04-02-full-codebase-audit.md) | 2026-04-02 | 25-agent full audit. |
| [4-4-26opusaudit.md](4-4-26opusaudit.md) | 2026-04-04 | Verification of the 2026-04-01 audit after the 2026-04-03 remediation pass (the file name does not say so). |

Other files here are milestone records, not audits of the whole repository:
[m-af1-behavior-shift-note.md](m-af1-behavior-shift-note.md) (2026-04-01 200-seed
behaviour shift of M-AF1), [maf.md](maf.md) (M-AF scoping guide) and
[connected-world/](connected-world/) (connected-world program audits and reviews).

## Decisions

- Audits are archived in place: none is renamed or moved, and the 2026-03-29 and
  2026-04-02 audits carry the same "Historical snapshot" banner as `masteraudit.md`.
- `src/chronicler/analytics.py` writes `"version": "post-M18"` in the batch report. It
  is an opaque report tag kept for saved-report compatibility, not a stale milestone
  label to update; changing it would alter serialized report output for no consumer.
