# Connected World A–E coverage: final integration draft

**DRAFT — implementation coverage and remaining gates, not a completion claim.**
Independent evidence owner, 2026-11-07. Actual integrated source inspected at
`d60907284e7c53c19c3a40c6300351c5545a6e93`, with later uncommitted D3 corrections
identified explicitly below. This updates the disposition of the original
[recovery matrix](connected-world-coverage.md); it does not rewrite that dated
reconstruction, historical pins, screen failures or original held outcomes.
The [program and amendment](../roadmaps/connected-world-program.md) remain the
scope. An audit's proposed first slice does not complete its follow-ons, and an
unimplemented audit proposal is not silently counted as implemented.

## Source and landing status

The original reference remains `8abc1acb`, not the development base. Initial main
`e3bce686` already contained #83–#93. Recovered B3 was integrated through #94 at
`4cabac21`; recovered D1a/b through #95 at `f76436ae`, whose tree equals reviewed
`11467a46`. Their source and retained evidence are real recovery, unlike D4:
no original D4 branch or worktree was accessible in the bounded search. D4 was
reconstructed from durable contracts; this establishes neither recovery nor
loss of another container's unpublished work.

The remaining code below is in the integrated #96 candidate, not established
as merged by this audit. The lead's continuation records #94 main CI green,
#95 exact-head CI green and its main CI awaiting verification at this checkpoint.
This source audit does not substitute a fresh GitHub CI observation. Final
reviewed-head green Tests, authorized PR merge and verified main CI remain gates.

## Coverage matrix

“Implemented” describes actual source, not universal benefit, native efficacy,
qualification or a passing final merge gate. All new behavior remains opt-in.

| Original scope | Actual implementation / authority | Evidence and remaining disposition |
| --- | --- | --- |
| A1 package accounting | `wealth_accounting.py`, `money.py`: opening/closing balance, typed uncapped transfers, treasury carry closures and all new payer registrations. One native wealth balance remains spendable. | Original A1/CW1 retained. Corrected treasury sign reviewed; care exclusion removed only after wage/withholding integration. `f81bc0af` restores historical declaration prefixes and registers restitution. Final source guard/offline/native/CI still required. |
| A1-2 native sources/sinks | `wealth_observation.rs`, `tick.rs`, `wealth_transfer.rs`: actual f32 stage changes for gross/applied income, each withholding, decay, ceiling/floor, births, estates/inheritance and transfers; rounding separately declared. Observer arms before payers and drains after all Phase 10 payers. | Independent native source approval; 774 Rust tests. Strict `1e-8` closure passed A1-only 22k/52k stress with births/deaths/migration and exact resumes. Final all-payer profile/resume remains pending. Wealth is not globally conserved cash; model Soldier wages, merchant tax and tithe remain explicit modeled sources. |
| A2 wages versus enrollment | Retail schedule replay and household-group cohorts distinguish wages from expanded enrollment and replaced farm income. Rules 2 cuts cap-doomed grain before reserve procurement. | Preserve CW1: fixed enrollment wages raised household credits; priced-out-rate effect null. Aggregate credit decline came from enrollment/farm-income replacement. CW6 fixes the enrollment rule at `all`; that is not a promise of identical treated populations. |
| A3 firms and demand | `workshop_economics.py`, payroll and native owned-output columns: paid inputs, real household purchases, one ruler capital contribution, inventory/cash/arrears, idle closure and no duplicate commons output. | CW2 null/adverse evidence retained. Actual individual payroll receipts now feed A6. No fictional market rescue or permanent employment guarantee; foreign owned-wares carriage remains the audit proposal listed separately below. |
| A4-1 titled food | `titled_trade.py`: stable shipments/holders, direct owner payments, actual title, income withholding, reserved carrier, bounded capacity and one terminal outcome; quarantine/maritime route graph. | CW5 mixed result and pretreatment exclusions retained. Cargo location is separate from native carrier residence. Non-pilot commons trade and its modeled merchant income remain declared. |
| A4-2 custody | `war_requisition.py` and titled-trade hooks seize actual hostile local custody, convert food only to capped actual army rations, record destruction and acquisition-value restitution claims. | Independent D4 review and unit/native service tests. Distant destination conquest returns cargo rather than inventing local capture; cession/death/release/reset paths keep explicit outcomes. Final natural custody/restitution transition resumes and integrated screen remain gates. |
| A4-3 timber | `timber_orders.py`: measured repair gaps, net outstanding domestic/in-transit orders, dated prices, real carrier purchase from origin treasury, finite destination escrow, graph/capacity/sea loss, delivery into existing PL1 store and exact refunds/loss/seizure. A6 applies the holder's own market/return memory to timber too. | Unary payment aliases were invalid on the first integrated pilot; failure retained before held use. Corrected at `506498df`, with actual native dispatch/delivery test `8e116c71`. **Open at d609:** L9 proposal used timber quantity as commons food relief; B3's measured repair-work/patrician-stake fix is in review. Final active freeze/profile/held must include that correction. |
| A4-W owned wares | The A4 audit proposes merchant purchase from firms and resale to households after A3-2. Actual candidate implements owned food and timber, not this mechanism. | Explicit scope disposition required from lead: roadmap §5.7 commits food-first and later timber but does not adopt this separate audit proposal. Do not count native commons wares or A3 local household sales as owned cross-border wares. |
| A5 lifecycle and RL1–RL7 | Retail rules 2 follows every conquest/siege/occupation event, distinguishes duplicates, preserves stable owner/heir/escheat/remote-title semantics, records cohorts and PL3 withholding split; D4 adds real custody without a competing title store. | Historical natural war/native resume evidence retained. Latest title/labor correction uses final economy factors, civilian census, full care/guard plans and actual IC work. Six direct FFI plus actual 16-turn FULL care and urban/rural tests passed; all-source lifecycle gates remain pending. Controllerless confiscation and terminal commons deposits remain explicit boundaries. |
| A6 migration experience | `adaptive_livelihoods.py` and native inputs: dated own refusal/quick-departure penalties, signed capped D3 scores, actual closure/fare receipt, no new RNG or Python movement authority. | Native gate/date/rollback/record-only identity regressions pass. Bounded memory/sample drops are explicit. Scores are inputs, not completed moves or proof of motive. Final fresh integrated effects/harms and active-transition restores pending. |
| A6 work/training | Real consumers exist in workshop crew plans, academy learner recruitment, new apprenticeship offers, repair, granary, woodcutting, IC, care and guard planners. Actual wages, matched own withholding and actual training progress feed subsequent personal choices. | This exceeds recording crew experience alone. Unknown title opportunity costs and mixed unassignable work shares stay null and cannot trigger monetary refusal. New training needs two prior failed-progress observations without progress; current commitments continue. Under all-region retail many monetary utilities may remain unknown: report activation, not presumed adaptation. |
| A6 information/trade | Native own-residence history, living ties formed before T and dated decayed packets define known destinations; unknown foreign state is replaced by a home-observed prior. Food/timber carriers use own usable trade packets and dated closed-shipment failures. | Actual native foreign-truth perturbation and refusal tests; signed score/source masks recorded. Unsupported legacy raw decision/driver-budget observers are refused while adaptation acts. `shuffled` is a migration-score placement control, not an equal-exposure control for every work/trade choice. |
| B1/B2 water | Procedural drainage graph, conserved storage account, record-only and replacing flow model; existing environment draws retained while superseded flood effect is suppressed. | Original CW3 disk-full failure and five-world primary analysis remain intact; deterministic supplementary completion is separately labeled. Primaries null; not evidence that protection universally helps. Templates still refuse watershed because no elevation authority exists. |
| B3 condition/repair | Recovered infrastructure sibling records service-gate irrigation/roads; wear/flood/war damage, stable asset/work IDs, shared RS2/PL1 resources and distinct L9 works proposal. Named crews, actual wages/refusals and material sink replace anonymous labor only in the opted-in named path. | #94 integration and historical CW3b retained; new named-crew and finite-envelope fixes independently reviewed. `cfcaa5ea` funds roads within L9 using repair worker-turn stakes, not fictional nutrition. Paid crew/lifecycle/browser development evidence exists; whole-program source/profile/CI gates pending. |
| B3 ports | No maritime consumer reads a port service level. | Explicit dependency deferral in original plan; no cosmetic port repair effect is claimed. Roads grant service-gated range, not an unimplemented transport discount. |
| B4 cover/wood/water | `harvest_cover.py`: settled L3 standing stock bounds unsupported canopy loss; shared canopy for multiple timber slots; original ecology regrowth/lag retained; record-only control. | Focused/constructed native restore/identity evidence is mechanism evidence. Existing downstream flow reads changed cover naturally. Natural integrated activation and held downstream outcomes pending, not inferred from canopy arithmetic. |
| B5 connected environment | Basin arrows, dated cross-polity controls, linked regional context, asset/work/person histories and explicit failed/stalled works; no aggregate harm assigned to an upstream person. | Viewer readers and dated adapters exist. Earlier panel-only and missing-sidecar profile limitations remain historical. Final integrated desktop/phone, old bundles, natural failed-work examples and complete profile remain gates. |
| C1 protection costs | Targeted closure replaces multiplier/flat loss for opted-in channels; native migration gate; public-health named paid guards with dated capacity replace anonymous enforcement. | CW4 null and CW4b mixed/food-harm results preserved. Contacts remain decaying stock; relief exemption and unrestricted soldier/pilgrim channels explicit. Paid staffing capacity is not inferred from unpaid work. |
| C2 supplies/sanitation | `public_health.py`: actual grain consumed at prior prices, foreign purchase versus internal allocation, one L9 value/cash envelope and purpose-specific prepaid wage carries. Prior actual irrigation service is the sanitation proxy. | Independent funding/source review. Actual pilot corrected channel-list/date schema and nullable paid worker income; unknown deductions are counted separately from observed subtotal. Final schema/timing/held checks pending. Irrigation is water management, not an invented sewer system; opportunity food/labor costs remain harms. |
| C2 displacement/crowding | One registered T−1 X1 aggregate read computes displaced/resident share and regional susceptibility multiplier. No narration bridge share or same-turn/future frame is consumed. | Implemented, but A6 unknown-cause measurement loss also lowers this exposure proxy; see causal limitation below. A lower proxy is not evidence that actual crowding or forced displacement decreased. |
| C3 mortality separation | Regional epidemic fractions/deaths, individual health-care injury episodes, ordinary native mortality and campaign casualties retain their distinct authorities. | Tests retain one epidemic death authority and no individual diagnosis from regional fractions. D3 wounds use existing episodes; health work impairment retains that system's occupational eligibility. |
| C4 informed choices | Dated source reports, delivery/expiry, own observed mortality experience, explicit expected-loss/cost comparison and shuffled report placement; current wage/supply/enforcement costs visible. | Mechanism/source tests and strict health screen implemented; actual validated pilot, frozen fresh cohort and report pending. Goods contact is a labeled cost proxy because food-import origins are unrecorded. Soldier/pilgrim routes are not counted as preventable benefit. |
| D1a relief | Real owner food purchases through finite relief funds replace synthetic material-need relief credit; refunds and no-label cost control. | #95, 60/60 held runs, fresh 3701/3801 cohort. Relief reached only 0/6 template and 2/6 procedural worlds; primary summaries suppressed. Historical positive lower-delivery estimate withdrawn because net transport cannot prove survival through gross exports; valid upper bound retained. No individual beneficiary is invented. |
| D1b leagues | Dated actual merchant-delivery links, stable league/guild/city identities, real dues and finite loss-matched civic claims, with dues-only control. | #95 held: procedural 6/6 activation; mean member-purse difference negative, five positive worlds/one large negative; harms mixed, no efficacy/default claim. Native/browser/profile receipts retained; not final union evidence. |
| D1c abroad branches | Named local adults pay actual host dues; stable branch identity; strictly T−1 funded permission can alter existing native recruitment/lapse; current public hostility/closure rechecked. Deployed-away roster members excluded without moving residence. | Independent source review, 15 unit/native tests, real fee and exact restore with permission due, six natural development runs. No transported home news or grievance stack; payer enrollment diverges across modes, so totals are not equal-cohort efficacy. Final union/held/browser still pending. |
| D2 attribution | Transfer/mint/destruction/restriction, actor/victim/cause observers retained. B3 adds accepted war damage in separate condition units, without duplicating wear/flood/events. | Existing source guard and default-defect registry remain. Seven provenance-consuming decision sites, merchant origin/current-region income mismatch, stale legacy agent mode and natural deaths booked as army casualties are not silently corrected on default paths. |
| D3 separation/injury | Campaign-selected deterministic 30% combat survivors receive existing injury episodes after health settlement; attrition not converted. Native migration remains sole mover; army attachment never becomes residence. Active opt-in suppression covers the old whole-polity Soldier war multiplier, including unrostered Soldiers. | Native/unit source reviewed; record-only preserves mortality path. Prior kin separation, dated local threat and exact war-instance peace notices feed movement. Natural activation/active lifecycle resumes and integrated effects pending. **New composition bug found at d609:** unknown A6 moves rehome X1 and erase the return target. Lead's uncommitted fix remembers legitimately known dated home, merges witnessed wars and keeps unavailable late-release home unknown; final exact-source/guard review pending. |
| D4 army supply/restoration | Army.rations is the carried store. Actual initial/refill/forage withdrawal, capped requisition/destruction, custody and treasury-funded restitution close; frozen Phase 2 service census aligns food/farm/title/income exclusions with meals. Later recruits start next turn; releases retain this turn's meal. Existing RS2/B3 own reconstruction. | Independent reviews found/fixed double meals, commons/owned-store double subtraction and pool rebinding. Compiled fed-0/1, civilian production/health denominator, urban/rural and actual care/title tests pass. Soldier wages remain modeled, personal restitution lapses at death, and archive caps are explicit. Final active supply/restitution/repair transition restore and fresh screen pending. |
| E linked histories | Strict package adapters join named people, inferred household groups, stable firms, shipments/orders, armies/claims, branches/leagues, works/assets and regions with source pointers/dates; navigation from chain, region and search. Seven reading states distinguish off, unknown, malformed, not sampled, truncated, recorded none and recorded observations. | Source/reader/navigation tests and production journeys exist. Household keys are inferred current groupings, not permanent lineages. Numeric person IDs are segmented across recorded non-exact continuation/pool reset. Regional joins are labeled context, not individual allocation or causation. Final whole-viewer/browser/old-bundle gates pending. |
| E stories/provenance | Exact saved-record citations, nested source dates and reviewed person namespace guards; strict production-reader receipt bound to bundle bytes before example finder accepts facts. Mechanically composed first-match adaptation/failure/mixed observations; explicit constructed-world metadata/banner. | Mixed C2 capacity/tick dates and identity namespaces independently corrected. Final natural examples must retain source/build/commands/turns, exact pointer and validation receipt; absent categories remain null. A finding labeled adaptation is an observation, not an efficacy claim. No paid narrator. |
| E whole-program evidence | Catalog/compatibility, append-only/inverse/witness and test enrollment, isolated source/native identities, bounded schema-validating screens and active-event resume planner implemented. | Latest tested feature-off source `43f02cca` matches both 8abc and true preceding 11467: 9 cases/399 files/0 differences each. It does not certify later source automatically. Final full offline/native/Rust/viewer/browser, active union exact resume, complete V11 profile, held evaluation, independently reviewed final PR and both CI observations remain pending. |

## A6 unknown cause is a model-input limitation too

The honest native correction does not label new experience/information effects
as old news, religion or foreign-truth drivers. Affected applied migrations use
cause 255; all-migration events and their untruncated sidecar remain observable.
X1 classifies 255 as `other`. A person with no open spell is immediately rehomed
by such a move; no new flight/hunger displacement spell opens. Existing open
spells continue across onward moves according to the unchanged X1 contract.

This can lower recorded flight/hunger moves, opened spells, displaced person-
turns and displacement anchors even when real war-related movement did not fall.
`public_health.environment_factors` then consumes T−1 recorded
`displaced / residents`, sets `crowding_factor = 1 + 0.25 × share`, and supplies
that factor to the epidemic model. Thus the classification change can also
reduce modeled crowding exposure and indirectly change disease/C4 outcomes;
it is **not merely a missing viewer cause**. FULL−A6R combines behavioral,
information and this proxy effect. Report unknown cause share, total migrations,
X1 counts and exposure factors together; do not interpret fewer recorded spells
or lower deaths as proof that actual displacement/crowding fell. Retaining the
measurement harm does not authorize changing X1's one-writer definitions.

The discovered D3 return-home interaction is separate and technically fixable:
a person can remember a prior known home without changing X1's canonical home.
That correction must pass its own dated-access/closed-loop tests and be included
in the next active runtime freeze. Unknown prior home cannot be reconstructed
from an army's location or another person's record.

## Explicit boundaries versus unfinished work

Established technical/model boundaries: ports have no service consumer;
watersheds require saved procedural elevation; wealth is not globally conserved
cash; native and Python cargo positions are distinct; individual epidemic status
is unobserved; public costs and sanitation are declared proxies; household keys
are inferred; sample absence is unknown; non-exact pool replacement ends identity
continuity. Restitution liability is not spendable wealth, nor an inherited estate
claim; archive/memory bounds remain visible.

The roadmap explicitly records tax/tithe debtor changes, decay-versus-food double
payment policy and broader relief for later policy decisions. No toll or extra
transport discount is invented. A4-W is an unimplemented audit proposal requiring
lead scope disposition. The pending L9 timber unit correction, D3 remembered-home
composition fix, final execution evidence and PR/CI gates are **unfinished work**,
not technical deferrals. Full 200-seed/procedural qualification, default promotion,
paid narration, deployment, purchases, credentials and sharing changes remain
outside authorization. This draft supplies no reason to stop independent lanes.

## Post-d609 closures and final evidence in progress

At the next immutable runtime freeze,
`eaa4a5d3e1cb5c958b5e32719601c28986c9f6ac`, the two functional blockers above
are corrected rather than deferred:

- `b1603c56` stores the legitimately observed personal home/date, keeps the
  first known anchor and union of witnessed war instances, and matches return
  against that memory after X1 rehomes unknown-cause moves. A late denied
  OwnRow read preserves unknown. Exact call-site registrations permit only
  the reviewed dated consumer and saved-bundle metadata reader; live-state
  and unregistered decision reads remain denied. Independent source approval
  examined the closed-loop and guard regressions; the earlier guard failure
  is retained, not called a pass.
- `3f0d16a7` values timber orders through current measured workshop idle and
  bounded road repair worker-turn stakes. Granary/irrigation inputs are reserved
  first without invented food relief. Region-scoped grants fund dispatch only,
  not promised completed repairs. B3 and D4 independently reviewed the source;
  real needs with no defensible stake can remain unfunded.

Declared-scale profiling is executing serially against that detached source
with verified extension `59f536b8…`, native source `38b21020…`, actual native
counts, validation-sidecar rows/bytes, CPU/RSS, final output maps and strict
same-source checkpoint read/write timings. Screen-scale profile cases remain
**200 turns** and procedural 48×10 remains **150 turns**, independent of CW6's
pre-held amendment to 120 turns. The first four profile runs passed: template
5/23 off/full, four exact checkpoints each and no FULL extractor errors. CPU
ratios 1.81/1.88 and bundle ratios 2.13/2.33 are material costs, not performance
wins. The lead accepts flagged overhead only as opt-in experimental behavior
and records, conditional on no OOM, balance-closure or source-guard failures;
there is no default promotion. Later procedural/stress outcomes are not implied
by those template passes.

This appendendum does not close the remaining final gates or overwrite the
matrix's dated d609 source observations. A new feature-off check on the last
runtime, final whole-program profile/resume/held/browser/CI receipts and the
lead's explicit A4-W proposal disposition must be attached before any completion
statement.

## Lead scope disposition: audit proposals versus adopted program

A4-W cross-border owned wares is not implemented. The adopted roadmap §5.7
commits titled food and A4-3 timber orders; A4-W remains a separate unadopted
audit proposal. This program does not advertise a wares-trade switch or count
A3's local household sales/native commons wares as that feature. Extending
owned wares carriage requires a later explicit market/title contract and its
own evaluated integration. This is a scope disposition, not a claim of a
technical dependency like ports. Tax/tithe debtor policy, decay policy and
default promotion likewise retain the roadmap's explicit later-decision status.
All adopted original A–E rows remain implementation/evidence obligations; the
short next-task field cannot waive those gates.
