# Connected World A–E coverage after the correctness rework

This reconciles the [original program and owner amendment](../roadmaps/connected-world-program.md)
and every row of the [adopted final coverage matrix](connected-world-final-coverage.md)
with the correctness, causal-evaluation and performance rework. The original
matrix remains the inventory of implemented authorities and historical evidence;
this document records what the rework changes, verifies and leaves limited.
The [scope audit](../audits/connected-world/rework-scope-disposition-2026-11-07.md)
retains the distinction between adopted implementation and broader proposals.

Coverage checkpoint: reviewed runtime and closed bounded evaluation;
physical runtime `8792be88dd36ba4d7c22e480de6a19dd64ea1300`, native artifact
`b1d3ea5a…` with reviewed native-input digest `f55df55d…`; held freeze
`b45c1e99`, production-equivalent to that runtime. Fresh CWR1 is **complete**:
144 of 144 cases pass, zero failures, independently checked within the fixed
two-core-hour cap. The cohort is recorded as used once. This is a bounded
screen, not qualification or a favorable-result claim. Final reviewed-head/main
CI closure remains required before integration.

## Original rows and rework disposition

Each original row is named below, with closely related rows explicitly grouped.
“Retained” means its adopted implementation remains; it does not mean this
rework newly implemented it or independently established benefit.

| Original coverage rows | Rework disposition and authority | Evidence or remaining limitation |
| --- | --- | --- |
| A1 package accounting; A1-2 native sources/sinks | Retained itemized native income, withholding, decay, clamps, birth endowment, estates, inheritance and typed payer closure through the one spendable wealth balance. No new balance or cash-conservation model. | Full-output/performance and enabled-resume comparisons preserve these records. Endpoint `births`/`deaths` are opening/closing stable-ID set differences, not all biological events or cause partitions. Native birth-endowment wealth is a separate observation. |
| A2 wages versus enrollment | Retained fixed-enrollment household/cohort accounting and schedule replay. Fresh controls separate regional availability from observed household access. | CW1 still finds wages raise household credits at fixed enrollment; the priced-out-rate effect remains null. Old CW6 does not supersede that wage result. Missing provisioning coverage prevents a complete world-access claim. |
| A3 firms and demand | Retained paid local inputs, actual local household purchases, firm cash/inventory and owned-output exclusion. | No cross-border owned-wares capability follows from local sales or native commons traffic. No new firm-efficacy claim is made. |
| A4-1 titled food; A4-2 custody; A4-3 timber; A5 lifecycle and RL1–RL7 | Retained stable food/timber title, real purchases, escrow, delivery/loss/seizure/refund, owner/heir/escheat lifecycle and funded restitution. Performance work removes redundant planning and exact-arithmetic overhead while keeping live wallets, claims, stock, ordering and settlement. | Final admission preserves 760 non-bundle/Arrow output pairs, complete encoded bundles apart from timestamp, and 36 native/private-state checkpoint pairs. Seventy focused trade tests and nine compiled-native lifecycle tests pass. Old economic floor calculations were correct; their computational cost was the defect. Cargo location remains distinct from residence; liabilities are not wealth. |
| A4-W owned cross-border wares | **Unimplemented, unadopted audit proposal.** The adopted roadmap food/timber contract does not implement carrier-to-firm wares purchase and household-to-holder foreign resale. | This is not a technical port-style dependency deferral. The rework neither implements it nor counts commons trade/local A3 sales as its completion. |
| A6 migration experience; A6 work/training; A6 information/trade | Explicit rules 3 separates personal component controls from D3 movement inputs, suppresses/shuffles only the intended personal inputs and retains the combined cap. Existing native movement, dated own information, work/training consumers and food/timber memory remain authoritative. Rules 1/2 retain historical behavior. | Control and lifecycle regressions, strict fresh extractors and actual enabled resumes verify the changed contract. Unknown motives, bounded samples and unavailable personal opportunity costs remain unknown. Recording a crew experience is not itself a completed training/work decision. |
| B1/B2 water; B4 cover/wood/water | Retained procedural drainage/conserved water and actual standing-timber/cover feedback through existing ecology. No new physical parameters or forest outcomes were manufactured to improve a screen. | The original CW3 disk-full failure and historical nulls remain. Templates still lack the elevation authority for watershed mode. The old joint timber/cover contrast cannot identify either mechanism alone. |
| B3 condition/repair; B5 connected environment | Retained irrigation/road condition, named opted-in paid work, shared resources, finite envelopes and asset/work/person/region history joins. Timber planning optimization preserves actual commitments and payments. | Paid work and moving escrow activate in procedural resume evidence. Roads retain service-gated range without an invented transport discount. Granary/irrigation-only timber procurement can remain unfunded without justified benefit. |
| B3 ports | **Technical dependency deferral retained.** Maritime treats controlled coastal geography as ports and has no port-infrastructure service consumer. | No port-condition, repair or shipping-service effect is claimed. Adding a cosmetic port record would not close that missing consumer. |
| C1 protection costs; C2 supplies/sanitation; C4 informed choices | Retained named guards, real supplies/costs, dated care capacity/reports and informed versus shuffled policy choices. Irrigation remains the stated sanitation proxy. Cost-only display now correctly says care/sanitation benefits are disabled while quarantine controls remain. | Fresh cost-retaining controls preserve relevant wages, supplies, guards and the selected crowding basis; responsive realized spending need not be equal. Food access and public-health interactions have explicit controls. The common care coefficient remains uncalibrated; no measured causal deaths-averted claim follows from pathogen outcome splits. |
| C2 displacement/crowding; C3 mortality separation | Explicit `density_only` removes the unsupported extra susceptibility multiplier derived from motive-classified X1 spells. Existing epidemic population/capacity and urban density remain. Separate dated physical residence-arrival diagnostics do not alter exposure or infer forced displacement. | Identical physical known/unknown-attribution trajectories now have equal corrected exposure; explicit legacy mode retains the old coupling for reproduction. Forty-one exposure/downstream regressions and the real complete-window viewer witness pass. Regional epidemic fractions/deaths, individual injury-care episodes, native mortality and campaign casualties remain separate authorities. |
| D1a relief; D1b leagues; D1c abroad branches | Retained actual funded relief, merchant-linked leagues and dated paid branch permission through existing native recruitment/lapse. | Historical sparse relief activation, withdrawn delivery lower bounds and mixed league outcomes remain. Whole-output/resume evidence preserves the systems; no new institutional efficacy or equal-enrollment claim is made. |
| D2 attribution | Retained actor/victim/cause and transfer/mint/destruction/restriction observations, including distinct war-condition damage. Physical arrivals are observed independently of motive uncertainty. | Default-path provenance consumers, merchant origin/current-region income mismatch and natural deaths booked as army casualties remain explicit default defects. They were not silently corrected in feature-off runs. |
| D3 separation/injury; D4 army supply/restoration | D3's evacuation/return scores survive personal A6 controls under rules 3. Native movement remains sole mover. Existing wound/health, army-ration, service-census, actual custody and funded restitution authorities remain. | Actual before/after wound/release/evacuation/return resumes pass across the two development worlds. Army meals, positive seizure and restitution are covered. Severe ration shortage remains a possible adverse modeled outcome; existing Soldier income remains modeled. Battle losses are not a complete war-cause mortality register. |
| E linked histories; E stories/provenance | Corrected readers distinguish physical arrivals, motive spells, prepared legacy proposals, actual rules-3 inputs, configured current neutral factors and prior observations. Old bundles and optional gzip retain strict decoding/provenance. Formatter reuse speeds indexing without deleting rows. | Real desktop/phone journeys, legacy/gzip compatibility and complete-index/query identity are retained. The constructed example is a reversible visibility/redaction demonstration, not an alternate simulation, independent outcome sample or full per-slice story suite. Regional context remains distinct from an individual's causal record. |
| E whole-program evidence | Source/native isolation, catalog/compatibility, historical pins/inverses, test enrollment, bounded screens, exact resume, profiling and CI policy remain. This rework adds source-bound corrected controls and independent result reviews. | Both-reference feature-off identity, Rust/native/focused tests, complete performance admission, actual enabled resumes and all 144 fresh held cases pass. Held arithmetic and retained raw worlds are independently checked. Final reviewed-head/main CI remains required; earlier successes do not automatically cover a new head. |

## Correctness and causal interpretation

The attribution finding is verified end to end: native driver 255 becomes X1
`other`; legacy `_move` can rehome without opening a classified spell; public
health turns that classified share into additional susceptibility. Correct
T−1 dating alone did not make the motive-dependent term a physical housing
measurement. The [independent contracts](../audits/connected-world/rework-independent-contract-review-2026-11-07.md)
and [actual source review](../audits/connected-world/rework-core-independent-review-2026-11-07.md)
record the correction and adversarial evidence.

X1 still has one Phase 10 writer and guarded T−1 `read_frame`, bound `OwnRow`
and `separation` consumers. Existing motive-classified home/spell meanings are
preserved. New arrivals count observed living stable IDs at their final
residence independently of motive, with a twenty-turn coverage clock. Gaps,
caps, resets, death, household changes, return and slot reuse do not justify
fabricated displacement or a missing-to-zero ratio. Configured density-only
neutral factors have an explicit current date; residence/water facts remain T−1.

All simulation behavior remains opt-in. **A6 rules 2 and public-health
`legacy_displacement` remain the established defaults**, including old saved
state semantics. Corrected use explicitly selects rules 3 and `density_only`.
Rules 3 also prevents A6 record-only/shuffled controls from erasing or
redirecting D3 inputs. D3-only configuration still does not install the A6
dispatcher. No default promotion follows from correctness review.

The [historical CW6 recheck](../audits/connected-world/rework-cw6-evaluation-audit-2026-11-07.md)
reaffirms all sixty 120-turn rows and the adverse FULL−A6R observations: food
shortfall and recorded epidemic deaths increased in all twelve worlds. That
old contrast jointly changes personal channels, D3 inputs and classification/
crowding feedback; it is not a pure personal-experience effect. The pooled
unknown-driver shares remain 85.07% template and 98.29% procedural, not proof
of reduced physical movement or disease exposure. No old result was tuned away.

Fresh CWR1 retains twelve arms, all-world enrollment, twelve fresh matched
worlds, 120 turns, the fixed two-core-hour ceiling and preregistered controls.
The reviewed [freeze](../audits/connected-world/rework-pre-held-freeze-review-2026-11-07.md)
follows 24 successful official timing/schema cases: 553.2 seconds simulation
plus extraction, projecting 1.383 core-hours with the fixed 1.5 margin. Protocol
SHA256 is `51b8a336…`. All **144/144** cases complete without failure in
0.92911 budget-counted core-hours. Independent arithmetic checks all rows and
six rendered primaries; independent raw readback covers 24 retained first-world
cases / 2,880 snapshots. Seeds 4101–4106 and 4201–4206 are recorded as used,
complete, in one standard lead mark-run. The cohort-content hash is unchanged.

The [closed rework report](connected-world-rework-report.md) retains all twelve
world-level primary differences, uncertainty, activation, rates, nulls and harms.
AD−RD increases mean regional shortfall by 812.431 / 2081.886 and recorded
epidemic deaths by 30.167 / 69.333 (template / procedural). Food is adverse in
11/12 worlds; epidemic deaths rise in nine, fall in two and tie in one. Mean
rates remain adverse, with varying world signs and endogenous populations.
Deleting information also reduces population; the joint food-regime change
can lower regional shortfall while raising observed priced-out subtotals.
Neither is established welfare improvement. Sparse care, template nulls,
incomplete access and capped inputs remain limitations. The inherited generic
activation headings have an explicit erratum; no enrolled world was excluded.
Historical CW6→CWR1 differences cannot isolate one correction across changed
rules, controls and seeds. No efficacy, qualification or promotion follows.

Famine-cause and war-cause deaths remain unrecorded/null, not zero. Endpoint
native disappearance, recorded epidemic deaths and campaign observations are
not proven disjoint components to add together. Regional food availability
shortfall is neither household purchasing access nor a diagnosed famine death.
The existing wallet is not globally conserved cash; modeled sources/sinks,
inferred household groups, unknown costs and finite restitution liabilities
retain their stated limits.

## Verification, performance and remaining costs

The actual rework evidence includes 41 exposure/downstream checks; **1,339 Rust
tests passed**, with two pre-existing manual timing benchmarks ignored; and
70 focused trade plus nine compiled-native lifecycle tests. These are distinct
scopes, not a sum of unique tests. The feature-off comparison reports nine
cases and 399 files with zero differences against each established reference:
original `8abc1acb` and preceding integrated main. The
[baseline equivalence](connected-world-rework/identity/preceding-main-baseline-equivalence.json)
records why `2726bf44` and main `125a6906` share the retained baseline; exact
candidate/source/import records belong with the final verification receipt.

[Enabled exact resume](connected-world-rework-resume/README.md) passes 14 actual
resumed branches plus two checkpoint-writing neutrality comparisons: 202 file
comparisons, zero differences, all eighteen output Arrow identities matching
the pilots. Source/native/input bytes stay fixed. Procedural before-wound/
release checkpoint zero is unavailable; template supplies all four D3
before/after boundaries. Template has no positive care coverage or moving
timber escrow; procedural supplies both. Every declared active category is
covered in the union, without claiming every possible lifecycle transition.

The [complete-window browser evidence](connected-world-rework-viewer-compatibility/complete-window-120.md)
passes **372 browser assertions** and **3,840 prior-frame assertions**. Independent
review corrected an invalid comparison counter from 2,392 to **2,163**
observations that differ under a same-turn lookup, with **3,808** adjacent
next-PH rows checked. The
invalid receipt and failing-old-expression regression remain. No UI/model or
simulation was changed to repair that evidence arithmetic. Legacy/gzip
journeys, optional-field reader checks, pagination and phone containment
regressions remain separate retained checks.

[Final runtime admission](connected-world-rework/performance/README.md) compares
the same five FULL scales against corrected unoptimized source, with fixed
worlds, horizons, native artifact, flags and population trajectories. Their
sum falls **318.28 → 265.89 CPU seconds** (16.5%); 760 non-bundle/Arrow pairs,
complete encoded histories and 36 native/private checkpoint pairs remain
exact. Seventy-two actual same-source checkpoint reads support the latter.
The large measured gains track removed scans and exact Fraction overhead;
small mixed single-run changes are inconclusive. First-candidate regressions,
null pilot results and the incomplete diagnostic profile remain recorded.
Final FULL/OFF CPU is still 1.82–4.31×; raw bundle ratios remain 2.37–4.12×.
RSS changes are small/mixed and no general memory gain is claimed.

[Viewer formatting](connected-world-rework-viewer/README.md) cuts long-history
cold-panel medians about 74–78% while complete rows, strings, source pointers,
reading states and queries remain equal. Loading/selection/heap outcomes are
mixed; phone viewport measurements are not handset hardware qualification.
[Optional archives](connected-world-rework-storage/README.md) reduce the saved
payload representation by 75–84.5% with exact-byte verification and retained
originals. Decoded RSS is effectively unchanged, keeping both copies increases total disk,
and gzip browser loads are slower in the measured medians. No event, identity,
missing value, world size or requested mechanism was removed for these gains.

Ports, unimplemented owned wares, limited constructed-story breadth,
uncalibrated care/proxy assumptions and incomplete cause/person observations
remain explicit. The full 200-seed and procedural qualification gates and default
promotion remain restricted and unrun. No paid narration, purchase, deployment
or credential/sharing change is part of this execution. This artifact accounts
for scope and closed held evidence. Exact reviewed-head/main CI closure remains
a separate gate rather than an inference from a board row.
