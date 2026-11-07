# CW6 integrated Connected World bounded screen

Status: DRAFT. No held run has started. Freeze after actual integrated-source
pilots, strict extractor validation, native blocker fixes and independent review.

Compute ceiling: 1.0 core-hours

Primary outcomes: cw6_balance, cw6_deaths, cw6_service

This is the integrated A–E program screen, not either restricted qualification
gate. It promotes no defaults, uses no narration API and makes no claim of
isolating every mechanism. Original reserved, still-unrun CW6 worlds are
template 781–786 and procedural 881–886 (32 regions, ten initial civilizations).
The shared development/timing pilots are template 5 and procedural 19. The
lead schedules execution only after source and native identities are stable.
Use one simulation process at a time, `RAYON_NUM_THREADS=1`, for 200 turns.

The exact executable flags are in `scripts/cw_integrated_screen.py`. All arms
use hybrid simulation, all-region household retail rules 2, the same existing
wealth balance, campaigns, health care, the maintained infrastructure/native
paid crew chain, D1 institutions, C2/C4 public health, X1 and complete A1
observations. The common retail boundary `all` fixes the enrollment rule;
enrollment changes must not be mistaken for wages lowering household credits.

| Arm | Difference from FULL | Interpretation |
| --- | --- | --- |
| FULL | all integrated opt-in effects | integrated program |
| A6R | adaptive livelihoods `record_only` | total personal-score, information, work/training and trade-choice contrast |
| D3R | war consequences `record_only` | total casualty/injury, release and dated movement contrast |
| D4C | war requisition `cost_only` | real food costs retained, legacy ration credits retained; no requisition kit benefit |
| SUP | timber orders off and harvest cover `record_only` | joint procurement/canopy control; the two effects cannot be separated |

Five arms × twelve held worlds = 60 bounded runs. The pilot is the same five
arms on the two registered timing worlds. Freeze only if its 1.5-margin
projection fits the one-core-hour ceiling. The runner stops rather than
exceeding its compute ceiling; remaining runs are explicitly unrun. No held
search for activation, outcome-dependent seed replacement or restricted full
200-seed/procedural qualification is included.

Three primaries include every enrolled world; mechanism activation never
selects a comparison:

1. FULL minus A6R actual household wealth balance change per 1,000 world
   end-of-turn person-turns, summing A1's exact opening/closing changes. This
   is a balance change, not marginal income, welfare or globally conserved
   cash. Income, transfers, decay, ceilings, births and estates are itemized
   separately in A1 and the diagnostics.
2. FULL minus D3R observed whole-world native deaths per 1,000 world person-
   turns, using A1's opening/closing stable-id death observation. Battle
   casualties, wounds, releases and injury episode-turns remain separate
   mechanism observations, not incompatible quantities added to this rate.
3. FULL minus SUP service asset-turns per whole-world region-turn. Each
   serving/failed irrigation or road asset contributes its actual service
   fraction; a region with no such asset contributes zero service. This total
   includes changes in asset stock and condition, not condition alone.

The generic runner's control tree is rooted at FULL. Screen-specific outcomes
negate both observations so their labeled contrasts are FULL minus control.
The generic fixed harm table keeps its ordinary control minus FULL sign.
Raw per-world values are retained to make both signs checkable. Report stratum
means, ranges and sign counts with descriptive paired sign-flip enumeration;
twelve worlds do not establish scientific qualification or a universal effect.

Fixed harms include population, actual household closing wealth, Gini,
treasury, food shortfall after relief, priced-out person/child-turns, epidemic
mortality, all migration and forest stand. Missing mortality-by-famine cause
remains explicitly unrecorded. Added observations include army actual meals,
unfed ration demand, physical refill/requisition food removed and destroyed,
restitution/arrears, infrastructure work/timber/public money, whole-world
native gross/applied income, paid wages and income withheld, repeated refusal
samples, separation pairs, wound/release/return counts, and timber delivery.
Native closures validate every completed turn. Food source removal must close
to carried ration credit plus recorded destruction; one army consumes once,
at most demand, with adequacy derived from actual consumption. Truncated D4
event evidence fails extraction rather than appearing as complete closure.

A6's new information/experience score cannot honestly retain a dominant cause
computed from unsupported legacy terms that inspect foreign truth. The native
runtime records affected move causes as unknown (255). Read the untruncated
`agent_events.arrow` sidecar, preserve its hash/size, compare all-migration
counts to aggregate snapshots and report unknown cause count/share alongside
X1 other moves, opened spells and displaced person-turns. A decrease in X1
flight/displacement classification is measurement loss and cannot establish a
decline in actual displacement. Bounded personal refusal/work/event samples
show dropped counts and are never substituted for untruncated world totals.

Schema/source checks require every completed source date, complete native A1
balance closure, correct arm modes and A6 information neutrality, T−1 family
separation dates, physical ration closure, timber cargo and real escrow
closure with prior price dates, all institutional frames, and correct canopy
neutrality in SUP. Strict extractors are validated on constructed failures and
the actual pilot bundles before held seeds are spent. Unknown personal title
costs remain null and are reported, never converted into an invented zero.

After the stable integrated pilot, retain exact source/extension/import,
runner/module/registry identities, commands, timing, extraction diagnostics,
nulls, adverse outcomes and compact metrics/reports. Preserve first-world
bundles outside the checkout for reproducible examples, browser journeys and
active-transition exact resume; the other successful bundles may be deleted
by the existing runner. Preserve failures, including the historical CW3 disk-
full failure. Reclaim only this run's explicitly expendable outputs.

Enabled exact resume is a separate gate. Select checkpoints from real FULL
pilot events at active army meals/requisition, injury/release, paid repair,
escrowed moving timber, dated reports/guards and A6 personal memory. Record
which categories activated and which did not, compare uninterrupted versus
checkpointed output and each resumed branch byte for byte using the existing
checkpoint identity comparator, and retain the actual selected source turns.
Do not claim an inactive lifecycle was tested merely because a clock turn was
resumed.

Reproducible commands from the final integrated checkout, using its verified
native interpreter (the examples use `python`):

```sh
PYTHONPATH=src python scripts/cw_integrated_screen.py check --screen CW6
PYTHONPATH=src python scripts/cw_integrated_screen.py run /workspace/evidence/cw6/pilot --screen CW6 --cohort pilot --jobs 1 --keep-first
PYTHONPATH=src python scripts/cw_integrated_screen.py check --screen CW6 --cohort pilot --metrics /workspace/evidence/cw6/pilot/metrics.jsonl
PYTHONPATH=src python scripts/cw_integrated_resume.py plan /workspace/evidence/cw6/pilot/runs/FULL-p19/chronicle_bundle.json /workspace/evidence/cw6/resume-p19-plan.json --stratum procedural --seed 19
PYTHONPATH=src python scripts/cw_integrated_resume.py run /workspace/evidence/cw6/resume-p19-plan.json /workspace/evidence/cw6/resume-p19
# After actual pilot review, source/extension freeze and preregistration freeze:
PYTHONPATH=src python scripts/cw_integrated_screen.py run /workspace/evidence/cw6/held --screen CW6 --cohort held --jobs 1 --pilot /workspace/evidence/cw6/pilot/metrics.jsonl --keep-first
PYTHONPATH=src python scripts/cw_integrated_screen.py report /workspace/evidence/cw6/held/metrics.jsonl --screen CW6
PYTHONPATH=src python scripts/cw_integrated_screen.py check --screen CW6 --cohort held --metrics /workspace/evidence/cw6/held/metrics.jsonl
```

Use the equivalent template-5 resume plan as needed to cover categories absent
in procedural 19. The resume tool preserves the exact JSON bundle and Arrow
sidecar identities, checks the actual seed/stratum and complete 200-turn run,
reconstructs the declared FULL CLI and selected active states, and refuses an
edited plan. Categories observed only at the final turn are explicitly not
resumable within that same run; they are not counted as checked lifecycles.
