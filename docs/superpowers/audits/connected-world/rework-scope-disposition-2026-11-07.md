# Connected World scope disposition for the correctness rework

This read-only reconciliation compares the [program and owner amendment](../../roadmaps/connected-world-program.md),
the contract audits, [final coverage](../../progress/connected-world-final-coverage.md),
[final report](../../progress/connected-world-final-report.md), and the current
[rework contracts](rework-independent-contract-review-2026-11-07.md).
Historical main is `2726bf449d0e4d581a72034000ee0861a58ee439`. Current source
inspection used the clean integrated worktree at
`8de171fda59a2051075d61183bf58dea5d011450`. This is a scope and interpretation
check, not approval of subsequent source, execution evidence, qualification or CI.
No simulation, native build, held seed, heavy test or external write was used.

The adopted implementation is substantially broader than the initial recovered
B3/D1 lanes. Calling its adopted mechanisms integrated does not mean every
original aspiration, audit proposal or possible causal measurement exists.
The focused rework should repair demonstrated correctness and control defects,
retain adverse results, and measure practical costs. This inspection found no
additional runtime merge blocker beyond the defects and verification gates
already assigned to that rework. It does identify the claim boundaries below.

## Original scope and present disposition

| Scope | Inspected implementation and trust boundary |
| --- | --- |
| A1/A2 money and wages | `wealth_accounting._frame` itemizes native stage changes, typed payers and rounding against the existing spendable balance. It does not establish globally conserved cash. CW1's fixed-enrollment wage result and null priced-out effect remain separate from CW6's joint adaptive contrast. Endpoint birth/death observations have the limits below. |
| A3 firms and demand | `workshop_economics.py` pays for local inputs, sells to local households and records firm cash/inventory. Native owned-output exclusion prevents duplicate commons output. Neither local sales nor ordinary commons merchant traffic implements owned cross-border wares. |
| A4/A5 food, timber and lifecycle | `titled_trade.py`, `timber_orders.py` and `war_requisition.py` provide actual food/timber custody, escrow, terminal outcomes, capped army food transfer and funded restitution. Cargo location remains distinct from native residence. Timber procurement cannot create timber or justify an unsupported budget benefit. Liabilities are not spendable balances. |
| A4-W owned cross-border wares | Audit A4 lists this as a recommended follow-on, including carrier-to-firm purchase and household-to-holder resale. Adopted roadmap §5.7 commits to food and timber, and the integrated implementation does not provide A4-W. Final coverage calls it unadopted; preserve the explicit **unimplemented** designation. It is not a technical deferral caused by a missing port consumer, and this rework does not newly implement or evaluate it. |
| A6 and D3 adaptive choices/human consequences | Actual native movement remains authoritative. Rules 3 separates personal A6 controls from D3 movement inputs in `adaptive_livelihoods._before_agent_tick_v3`; rules 1/2 retain historical behavior. D3-only operation still does not install the A6 dispatcher. War attachment, residence, remembered home, wounds and releases remain different observations. Explicit corrected flags and matched controls are essential to any new causal interpretation. |
| B1/B2/B4 water and cover | Procedural drainage and conserved water accounts, actual standing timber and ecology-owned cover/regrowth are integrated. Template geography still lacks an elevation authority for watershed mode. The old joint timber/cover contrast cannot identify either isolated effect. No new climate calibration follows from source correctness. |
| B3/B5 condition, paid works and environment history | Irrigation/roads, named opted-in crews, wages, material costs, finite budgets and stable asset/work histories exist. Roads have service-gated range; no transport discount is implied. `infrastructure_condition.KINDS` excludes ports. `maritime._own_port` uses controlled/unoccupied coastal geography rather than infrastructure service, so port condition lacks a consumer. Ports remain the roadmap's explicit **technical dependency deferral**. |
| C1–C4 protection/care/information | Actual staffing, wages, food supplies, dated reports, costs and existing epidemic mortality authority remain. Irrigation service is an explicit water-management/sanitation proxy, not a modeled sewer or household occupancy system. The common care coefficient is uncalibrated and may be generous for some pathogens. No additional housing-contact authority was found that would justify motive-dependent exposure. |
| D1 institutions | Actual funded relief, leagues and dated paid branch permissions are integrated. Sparse relief activation and withdrawn historical delivery lower bounds remain; source completion does not imply efficacy or equal-enrollment effects. |
| D2/D4 war attribution and resources | Actual army rations and custody/restitution use existing authorities. Battle losses, wounded survivors, roster disappearance, native deaths and epidemic deaths are distinct quantities. Severe ration shortfall remains a modeled adverse outcome; no food is to be minted to improve it. Default-path provenance consumers, merchant origin/current-region income mismatch and natural deaths booked as army casualties remain recorded default defects. |
| E histories, examples and provenance | Strict saved-record pointers, stable joins, reading states and real browser journeys exist. Regional context is not an individual causal observation; inferred households are not permanent lineages. The natural finder reports missing example categories honestly. The constructed artifact has the narrower scope below. |

## Attribution correction and causal evidence

The historical path is independently verified in the
[contract audit](rework-independent-contract-review-2026-11-07.md): native
unknown driver 255 becomes X1 `other`; `_move` can rehome instead of opening a
known-motive spell; `public_health.environment_factors` converts the classified
share into extra susceptibility. Respecting T−1 does not make that extra term
a physical occupancy measurement.

The corrected explicit `density_only` choice neutralizes that additional term
while retaining epidemiology's existing density terms. X1 keeps its historical
home/spell interpretation and observes reason-independent recent residence
arrivals separately. Recent arrival is a dated physical observation, not a
forced-displacement label or another exposure coefficient. The twenty-turn
coverage clock, caps, gaps, old checkpoints, deaths and stable-ID reuse must
remain visible; incomplete recent-arrival shares are null. New-enable defaults
remain legacy, so reports and reproducible commands must name rules 3 and
`density_only` explicitly. This preserves the owner's no-promotion boundary.

The [historical CW6 recheck](rework-cw6-evaluation-audit-2026-11-07.md) reaffirms
FULL−A6R food shortfall and recorded epidemic deaths increased in all twelve
120-turn worlds. Old A6R also suppressed D3 scores; the old contrast therefore
cannot identify a pure personal-experience effect. Correcting those contracts
does not establish that the adverse outcomes disappear or were all defects.
Fresh preregistered matched comparisons must retain world-level harms, nulls,
activation, cost-retaining controls and unchanged horizon/seed identities.
Historical held worlds are evidence, not a tuning set or fresh cohort.

## Observation limits that must survive the handoff

`wealth_accounting._frame` computes `world.births` as closing stable IDs absent
from the opening and `world.deaths` as opening IDs absent from the closing.
Those are exact endpoint-set observations under stated pool continuity, not a
complete biological birth/death event register or a cause partition. The
separately observed native `birth_endowment` component in `tick.rs` records the
actual wealth effect of successful spawning. Do not divide that aggregate
wealth by a presumed endowment to invent an independent birth count, or treat
an endpoint count as age-, parent- or cause-specific evidence. No defect in
the existing balance-closure calculation was established by this distinction.

`screen_runner.HARM_PANEL` deliberately supplies no extractor for
`deaths_famine` or `deaths_war`: they remain unrecorded/null. The native death
sidecar and A1 endpoint disappearance count do not partition causes; D3's
battle loss observations are not a complete all-war-deaths register. Regional
food availability shortfall is neither household purchasing access nor a
diagnosed famine death. Epidemic cumulative deaths retain their own authority
and must not be added to native deaths as though those were proven disjoint.
The rework screen's observed retail-access subtotal remains null as a complete
world-access measure when populated region-turns lack provisioning records.
These limits reduce the causal questions supported by the data; replacing
nulls with zeros or new diagnoses would reduce trust.

The [constructed history example](../../progress/connected-world-e-history/constructed/README.md)
is a reversible redaction of three individual-observation fields in an
unchanged natural run. Its preserved wage, unknown opportunity cost, exact
edit disclosure and production banner demonstrate visibility/provenance.
It is not a separately simulated alternate story, a policy counterfactual,
an independent outcome sample, or the broader per-slice constructed story
suite proposed in audit E §9.2. Editing a natural bundle is an allowed
constructed-fixture method in that proposal; it cannot establish the missing
simulation or natural activation. Keep both statements explicit.

## Completion gates and remaining limits

Correctness source approval, fresh bounded causal evidence, before/after
profiles at the same declared scales, feature-off identity against original
`8abc1acb` and preceding main `2726bf44`, enabled exact resume, native/Rust/Python
and viewer/browser checks, reviewed-head CI and verified main CI remain
separate gates. Historical successes do not automatically pass a new diff.
The full 200-seed/procedural qualification gates and default promotion remain
restricted and unrun; no source-only review can relax them.

Viewer indexing improvements must preserve complete records and all reading
states. The optional gzip archive reduces only the saved transport/storage
representation: the source remains, total local disk grows when both are kept,
and decoded history/RSS is not reduced. The rejected encoder shortcut remains
a measured null, not a speed claim. No cost improvement justifies silently
dropping events, narrowing the world or disabling requested mechanisms.

Unimplemented wares, deferred ports, incomplete story-suite breadth,
uncalibrated coefficients, bounded individual observation and unavailable
cause-specific deaths remain limitations. This focused review found no reason
to invent a new feature program to close them before completing the defined
correctness, causal and performance gates. Their honest disposition is part
of completion; it is not evidence that they were implemented or qualified.
