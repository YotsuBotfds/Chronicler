# Fresh independent Sol review

Reviewer: fresh `gpt-6.1-sol` agent `independent_sol_review`, without inherited
conversation context. Scope: the four detached modules, harness and joint tests,
against the supplied authoritative source-backed contract and baseline roadmap.
Review was read-only; no G05 source access or GitHub writes occurred.

Final reviewer result: **No unresolved correctness findings remain in the reviewed
detached four-kernel scope.** Actual updated combined validation: **467 passed**.

Concrete findings, owner corrections, and reviewer adversarial rechecks:

| Finding | Correction | Final status |
| --- | --- | --- |
| Previously consumed event evidence could be replaced after the pending buffer cleared | Persist the evidence log; reject contradictory or unseen records below the committed cursor | Original two-frame reward-forgery probe rejects |
| Deferred accession allowed an accession boundary behind the carried observed cursor | Explicit boundary check against durable evidence cursor | Backward accession rejects |
| G04 trade targets accepted display names or unregistered civ IDs | Validate canonical registered IDs on active/attainable observations and current/archived trade objectives | Generation and load probes reject |
| Persisted terminal objectives could lose their contribution or reverse its sign | Require terminal-objective/contribution bijection and signed consistency | Actual JSON deletion and negative-sign probes reject |
| Deferred events could be removed from the pending queue while remaining in the log | Require pending queue to equal the unevaluated log suffix | Actual JSON omission rejects; completion survives reload without resubmission |

The reviewer additionally checked complete-batch acknowledgement reconciliation,
rollback, exact Fraction persistence, retained ambition evidence, enum-index
selection and runtime inactivity; no further defect was found. These are synthetic
harness results, not production calibration or acceptance.

Final-HEAD runs are recorded separately by the implementation owner. No claim is
made that the review inspected production governance integration or G05.
