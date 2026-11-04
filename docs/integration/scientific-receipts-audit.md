# Audit institutional science receipts

The read-only [expansion audit](expansion-audit.md) includes dated
`scientific_claims` sections. Its separate helper,
`chronicler.scientific_receipts_audit.ScientificReceiptsAudit`, shares the host's
byte, snapshot, event, receipt, text and detail bounds. It imports no simulation
or native runtime and uses no LLM. Existing JSON/escaped Markdown exports,
source-byte hashing and input/output alias protection apply unchanged.

```sh
python scripts/audit_system_expansion.py path/to/chronicle_bundle.json --json reports/audit.json
python scripts/compare_system_expansion.py path/to/science-study --json reports/comparison.json
```

## What the receipts support

| Recorded evidence | Audit interpretation |
| --- | --- |
| `scientific_trial_funded` event at turn F | One observed funding event; no need to wait for resolution |
| Resolved trial row at actual `resolved_turn` R | A terminal receipt, with its **earlier** funding date and cost |
| `completion_turn` | A plan; it can remain in the future for early failed work |
| Cumulative `trial_spent` | Recorded treasury expenditure; fixed first-slice cost is two per funded trial |
| Current allocation rows | Every paid seat split, including routine payments with no new event |
| Allocation event ID | First/material change report, not every paid allocation |
| Cumulative `evidence_receipts` | Archive count, without a complete archived receipt list |
| Current belief / last-used receipt | Present policy observation, not the complete archive or physical truth |
| `independent_groups` / `dependence_group` | Declared policy bookkeeping, not certified experimental independence |

A section must match snapshot S+1 / source turn S. Proposition, actual funding,
resolution, physical input and last-used evidence dates cannot exceed that source turn.
Unavailable actual rows are flagged and withheld, including their names and
values. Future planned completion dates are allowed. Stable event references
are checked against event kind and actual date; future duplicate IDs cannot
poison an earlier historical reference. When the dated events record dependency
lists, funding must cite its proposition and resolution must cite its funding.
These are recorded dependencies, not proven counterfactual causes.
Completed and cancelled work must satisfy funding < planned completion ≤
actual resolution. Failed measurement at funding is the earlier-resolution
exception; a later publication failure must also wait until planned completion.

The audit checks bounded counts; nonnegative finite quantities; whole counts
and treasury payments; immutable proposition identities within continuous spans;
same-turn unique resolved trial IDs; terminal status/date order; fixed trial
cost arithmetic; funding-context/date agreement; noisy support arithmetic;
belief probability/group bounds; the neutral prior with zero policy-visible
groups; and one treasury unit per paid seat split whose shares sum to one.
Repeated prior resolution rows are diagnostic, rather than new trials. Repeated
proposition summaries are legitimate persistence.
Bounded trial details show the recorded physical diagnostic outputs separately
from noisy observations and their support verdict. They are frozen local model
diagnostics, not realized harvested goods or estimated policy efficacy.

Across consecutive valid snapshots it checks cumulative monotonicity and
reconciles new status totals, effort expenditure, funding events and evidence
receipt events. Gaps break counter and cohort-local identity comparisons;
summaries have no cohort identity with which to prove continuity across gaps.
Distinct proposition integer IDs and declared group strings are descriptive
counts, not independent-unit counts. Detail omissions are explicit and separate
from scan truncation, which prevents a complete-scan claim.

## Strict comparisons

Science supports `normal`, `withheld`, `no_transmission` and `uninformative` arm
labels. Source/native, actual worker environments, checkpoint, flags,
registration, prefix, horizons and complete post-fork receipt tables must meet
the existing comparator requirements. All four source-owned controls are
disclosed: `withhold_information`, `transmission_enabled`, `uninformative_tests`
and `publication_rule`. Legacy serialization omits the last control; this known
source default is normalized explicitly to `current-context-v1`. A new explicit
`funded-context-v2` value is supported but cannot be pooled with a different
publication rule. Treatment-window summaries must agree with their control
receipt, including the publication rule.

Metrics count actual window-dated funding and receipt events, same-turn
resolutions, resolution-attached historical costs and every paid allocation.
Recorded cumulative changes use the valid snapshot immediately before the
fork and the last snapshot of the complete window. A missing boundary remains
`null`. A trial funded before the fork but resolved after it contributes a
resolution receipt and its historical attached cost, while adding zero to
post-fork funding expenditure. No final-world backfill is used.

## Limits on interpretation

The summaries do not carry all running trials, archived evidence receipts,
message routes, institutional proposal receipt dates or full current local
applicability inputs. An omitted last-used receipt date can mean that archived
evidence is currently off-context; it does not prove forgetting. Likewise,
neutral confidence is not proof of no archived evidence. The audit checks the
funded physical context when supplied, without recalculating physical yields,
certifying access survival, or inferring current applicability from final state.

Uninformative controls use ordinary noisy comparator-centered observations;
they can produce unequal observations and unequal institutional confidence.
They are distinct from withholding, which records no new usable receipt.
Forwarded receipt causes are counted as recorded dependencies, without claiming
independent evidence or reconstructing unrecorded remote travel.

Empty eligibility, no funding, no replication, no remote receipt and no paid
adoption must remain visible. Such exposure gaps are not statistical nulls.
Matched descriptive windows do not establish information utility, technique
efficacy, generalized truth, a causal benefit or scientific qualification.
Repeated turns, trial IDs and groups are not independent replications.
