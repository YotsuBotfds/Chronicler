# Read-only system expansion audit

Run this against a run's existing `chronicle_bundle.json`, including an arm
written by the expansion experiment runner:

```sh
python scripts/audit_system_expansion.py path/to/chronicle_bundle.json
python scripts/audit_system_expansion.py path/to/chronicle_bundle.json --as-of 20 --phase start --json reports/turn20.json --markdown reports/turn20.md
```

The default view ends at the run's declared last completed turn. `--as-of T
--phase end` includes records through T; `--phase start` includes through T−1.
A snapshot labelled S describes completed turn S−1. A section must carry that
same `source_turn`; missing, stale, malformed and future-stamped sections are
withheld. Coverage lists both continuously recorded spans and unknown intervals
through the requested boundary. Unknown history is never filled from final
world state or interpreted as zero activity or a disabled feature.

The reusable API is `audit_bundle(mapping, as_of=AsOf.after(T), limits=Limits())`
or `audit_path(path, ...)` in `chronicler.expansion_audit`; `render_markdown`
renders its JSON-compatible result. Bundle v6 uses the shared decoder. Legacy
bundles without the new sections return an explicit evidence gap. The module
does not validate/reconstruct a `WorldState`, run a turn, load a native runtime,
query an LLM or alter its input. File analysis hashes and parses the same single
byte read. The SHA identifies those input bytes; it is not a producer signature.

The report separates these categories:

| Category | What it establishes |
| --- | --- |
| Verified checks | Arithmetic/chronology agrees within the supplied records |
| Observed mechanisms | Dated receipt counts, quantities, identities and event links |
| Unobservable facts | Claims the bundle alone cannot independently establish |
| Scientific claims requiring interventions | Effects needing matched controls and qualification |

The fourth system, [institutional science receipts](scientific-receipts-audit.md),
checks paid trial/status/counter arithmetic, funded versus actual resolution
dates, immutable proposition context, current belief records and every paid
allocation. Archived evidence counts remain separate from current applicability;
declared dependence groups do not establish independent experiments.

Health checks cover nonnegative finite work/count quantities, whole episode
counts, unique regional IDs, sums of regional metrics against totals, and cared
recovery-work progress as a subset of all progress. Active episodes summed over
snapshots are labelled **episode-turns**, not unique patients. `recoveries` is
reported as episode retirement, without clinical interpretation. Optional
`censored_episodes` stays separate, and is unknown when unrecorded. Work time is
not converted into clinical benefit, measured grain loss, currency or deaths.
If any included health section has unknown units, the combined work/care totals
are withheld rather than relabelled as worker-turns; unit-independent counts
remain available.

Forecast chains are indexed by their recorded stable report ID. Persistence
of a pending/delivered report or retained resolved outcome across snapshots is
legitimate and does not multiply report counts or scores. The audit checks
issuance/delivery event IDs against exact event kinds/dates and finds preparation
and resolution event IDs only through recorded dependency references and region,
never matching prose. Missing IDs remain unavailable; duplicate or dangling IDs
are diagnostic. Planned delivery, target, expiry and next-calendar dates may
lie in the future. Actual issue, delivery, resolution, occurrence and payment
evidence may not. Premature actual outcomes are flagged and withheld, including
their numerical values and future-issued report names/IDs.
An event ID is ambiguous only among copies dated at or before the receipt's
source turn. A future duplicate cannot invalidate an earlier historical view.

Preparation is a per-turn `(source_turn, forecast_id, region)` observation,
not a new simulated purchase ID. Duplicate rows in the same turn are rejected.
Identical amounts on different turns remain distinct legitimate purchases.
Where the same snapshot records granary flows, the audit reconciles total
grain/cost bought for the warned region against its actual `bought` flows.
These are all purchases **during** the warning, not causal excess spending.
Resolved score arithmetic is checked against the recorded probability and
boolean outcome; the normalized ratio is checked against its recorded sum/count.
No score alone establishes skill versus seasonal baselines or shuffled/withheld
reports. Report closures and scored reports are counted separately.

Gathering receipts retain recorded host/faith names, selected stable attendee
IDs, expense balances and arrival membership receipts. Checks cover ≤32 unique
IDs, no ID selected in two simultaneous local regional gatherings, positive real
hosting costs, before−after expense arithmetic, bond-attempt counts
≤min(8, floor(attendance / 2)),
≤8 contact units bounded by selected arriving IDs, and zero attendance/expense/
effects on cancellation. A held gathering requires a host. The additional contact
cannot exceed all recorded pilgrimage-channel inflow when that summary exists.
Earlier occurrence receipts cannot be replayed as new turn activity. Repeated
identical snapshots count once; conflicting snapshots are withheld.

These checks do not independently prove native presence, eligible age/occupation,
merchant reservations, submitted pair identities/disjointness, successful friend
formation or disease imports. They
cross-examine claims in the receipts. The report declares the first-slice
contracts it checks: grain `0.05 × attendees`, funds `1 + ceil(attendees / 16)`,
the 32/8/8 caps, and forecast shortfall at production/demand below 0.6. A later
mechanism version that changes those formulas needs a corresponding audit update.

Cumulative counters may only be compared across consecutive, valid recorded
turns. A gap, rejected section or conflicting snapshot breaks that comparison.
For continuously recorded gathering and warning-purchase counters, increments
are also reconciled against that turn's receipts. No implicit zero baseline is
invented at the beginning of a resumed or partially retained history.

Descriptive observations surface unexercised pathways: all gatherings cancelled,
held gatherings with no arrival-based contact, delivered reports without positive
warning-period payments, reports without a scored outcome, or impairment without
recorded caregiver work. They describe the inspected coverage and do not count
as efficacy evidence or a statistical null.

`--format json` selects stdout JSON; Markdown is the default. `--json` and
`--markdown` also write reviewable exports with escaped record text. Output
paths cannot alias the input, including hardlinks/symlinks, and the two formats
cannot overwrite one another. The source and runtime remain untouched.

Exit codes are 0 for no detected violations within recorded coverage, 1 for
invariant errors, 2 for input/output errors and 3 for a partial scan or no recorded
expansion history. Warnings, unavailable checks and unknown spans remain visible
even with exit code 0. This is not a global PASS, authenticity proof, full suite,
performance qualification or scientific milestone gate.

Default scan bounds are 10,000 snapshot rows, 200,000 section/flow rows, 100,000
timeline events and 128 MiB of source bytes. Limits have finite absolute caps.
Delta history is capped before expansion; legacy histories scan a bounded input
prefix, then process its dates in order. The decoder still materializes the
selected history, so expanded-memory cost depends on snapshot size. Event
dependency lookups are indexed once. Repeated granary-flow reads spend the same
global row budget. At most 200 findings and 100 report/occurrence detail rows are
exported; missing detail rows are counted separately. A 500-character text bound
and defensive counter/cause caps prevent unbounded labels or unexpected maps.

Any scan/text/finding truncation sets `scan_complete=false`, identifies its
reason and prevents a clean-coverage status. Detail display limits alone do not
stop invariant scanning. Use `--max-snapshots`, `--max-rows`, `--max-events`,
`--max-findings`, `--max-details`, `--max-text-chars` and `--max-file-bytes` to set
explicit bounds. A byte-limit failure produces no partial hash/audit.

## Initial cross-examination

The real seed-42 combined 60-turn hybrid bundle from source `527a9ff8` had
SHA-256 `aca05f31fdb5faa3892716bb003a053089770273727c87e640857b9a15d20011`.
All three sections continuously recorded completed turns 0–59; the audit found
no arithmetic/chronology violations or warnings and did not truncate. Its
40 gathering occurrences included only four held gatherings and 36 cancellations;
one held gathering recorded arrival-based contact. There were 29 delivered
report IDs, 22 scored reports and 145 preparation receipts, but just six receipts
with positive payment. These sparse pathways constrain interpretation of any
later outcome comparison. Censoring counts were unrecorded in this older source
and remained unknown.

Of 24 real parent/control bundles in the two-seed, 40-turn development studies,
23 had no detected violations in recorded coverage. The seed-43 shuffled forecast
arm recorded one actionable anomaly at completed turn 32: report
`harvest:2:0:6`, Stormbreak Cliffs, had `base_target=4.126938305182808` and
`extra_target=-1.126938305182808`. The reported warning reduced its target to
3.0 and recorded zero purchases/payment there. This is a material negative
increment, not rounding noise. It was sent to the forecast owner for a runtime
correction; the audit reader does not alter the historical artifact.

These runs are development evidence, not full scientific qualification. Their
arm bundles retain pre-intervention parent history; whole-bundle totals cannot
be interpreted as treatment-only quantities. The associated exact source,
native/control metadata and fork boundaries must accompany cross-study claims.

Focused verification passed 56 tests under Python 3.13.5 with native imports,
network and child processes blocked (zero attempts). This covers v6/legacy
decoding, start/end cutoffs, future-body withholding, gaps, duplicate and
conflicting receipts, counter/expense/flow/score arithmetic, malformed optional
data, finite JSON, deterministic escaped exports, source hashing and alias
protection. It also includes a minimal regression for the actual negative-target
receipt above. These are reader tests and recorded-run audits, not a simulation
or scientific gate.
