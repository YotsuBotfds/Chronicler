# Connected World A–E coverage and recovery audit

This is the historical initial inventory. The [final matrix](connected-world-final-coverage.md) and [final report](connected-world-final-report.md) supersede its remaining-work and reservation statuses; recovery facts and historical source identities below remain unchanged.

Read-only reconstruction on 2026-11-07. This is a scope/evidence inventory, not a
completion declaration. Source inspected: fetched `origin/main`
`e3bce686df1fe2e73a4ee7378c36f2e2647826bb`. The plan of record is
[connected-world-program.md](../roadmaps/connected-world-program.md); the detailed
contracts are the [contract audits](../audits/connected-world/). The original
request and amendment are preserved there as the scope and execution rules; an
audit's proposed implementation is distinguished below from merged behavior.

## Recovery and GitHub facts

- The accessible original checkout `/workspace/Chronicler` was clean at main
  `e3bce686`; it had one worktree and no local D4 branch. The remote branches
  `claude/cw-b3-infrastructure` (`83abd6668e5db22f24e86ab986567a673f78455b`)
  and `claude/cw-d1-institutions` (`e12ba7ec596a57811a3d188102f66a9d083abf18`)
  were fetched and are recoverable source, including their committed tests and
  evidence. `claude/cw-d4-requisition` was absent from fetched remote refs.
  Searches of accessible `/workspace` and `/tmp` found no original D4 checkout.
  These observations establish no recovery of uncommitted D4 work and do not
  establish that another container's work was lost.
- PRs #83–#93 are merged; no PR was open at reconstruction. PR #93's actual
  head was `e39673c00fd08b5f85c1627611b8e018a8defa89`, merged at
  `e3bce686` on `2026-11-07T08:10:42Z`. `6619ceac` is an earlier reviewed X1
  documentation head, not the final PR head.
- Main push Tests run `42354356085` tested exact SHA `e3bce686` and passed all
  nine jobs: no-Rust, bounded offline, current-source wheel, native shards 0/1,
  native execution, native aggregate, Rust, and Viewer. No Actions run existed
  on either recovered B3 or D1 exact head. Their historical local checks are
  not exact-head GitHub CI.
- The stale board's X1-awaiting-PR and D4-active labels are not completion
  evidence. `8abc1acb` remains the original feature-off reference, never the
  current development base.

## Scope matrix

“Remaining” includes implementation, integration, or evidence that the inspected
source does not establish. Historical evidence remains attached to its actual
tested source; it does not automatically qualify a later integrated tree.

| Scope | Merged implementation / recovered source | Tested evidence already retained | Remaining work and disposition |
| --- | --- | --- | --- |
| A1 income and wealth accounting | #86 `wealth_accounting.py` observes opening/closing wealth and typed package transfers; one native `wealth` remains spendable | ledger tests and CW1; `native_model` is explicitly a residual | A1-2 must itemize native occupational income, decay, ceiling refusal, births, estates and rounding; integrate care wage/withheld income and later payers. Current A1/C2 exclusion is deliberate until then. Never relabel this as globally conserved cash |
| A2 wages versus enrollment | #86 retail interval replay and household-group cohorts; storage cap cut under retail rules 2 | CW1 108 runs, 0 failures; fixed-enrollment wage raises household money in every activated world; priced-out-rate wage effect null | Preserve this conclusion and the separate enrollment effect; integrated compatibility/resume remains necessary |
| A3 firms and real demand | #88 paid inputs, ruler starting capital, household customers and idle closure; #92 rules 2 prevents owned firm output entering commons a second time | CW2 60 runs; no consistent primary effect; adverse idle closure is disclosed | Source-level invariants and integrated compatibility; timber access is not solved by paid inputs |
| A4-1 owned food cargo | #92 `titled_trade.py` uses stable shipment/carrier identities, purchase transfers, delivered retail title, income withholding | CW5 24 runs; 3 worlds excluded by pre-treatment window; food-shortfall direction differs across strata | Food-first implementation is not timber procurement; current destination-conquest return and carrier-death escheat are provisional A4-1 outcomes |
| A4-2 war custody | Durable A4/D audits; no recovered D4 source | A5 lifecycle tests establish destruction, not rations transfer | D4 must provide cargo seizure/restitution and exactly-once destination/outcome accounting; test death, conquest, cession, migration and resume transitions |
| A4-3 timber orders | No timber order/escrow mechanism in main | A4 audit documents shortage and demand omissions | Implement cross-civ orders, real payer escrow, delivery, refunds and failure outcomes; do not count domestic PL1 expeditions as cross-border purchases |
| A5 owned-stock lifecycle | #86 retail rules 2 hooks every conquest/siege/occupation event; heirs/escheat, remote title and pool reset already exist | RL1–RL3 tests, natural native occupation/siege/cession resume | D4 transfer/restoration integration; timber-store war treatment and controllerless confiscation must remain explicit boundaries unless separately changed |
| A6 adaptive livelihood decisions | X1 #93 supplies record-only dated residence/displacement contract; existing experience records do not alter choices | X1 guard, identity and resume tests; A6 audit only proposes adaptation | Native movement semantics first; dated individual migration failure/cost memory, work/training participation and later information/trade choices require actual decision consumers and evidence. Audit A6-1 is only migration; A6-2 crew filter, A6-3 known destinations/return pull and A6-4 carrier memory are distinct follow-ons |
| B1 watershed account | #84 procedural drainage graph, conserved storage account and record-only mode | conservation, graph, feature-off and record-only evidence | Integrated old-bundle/resume/profile coverage |
| B2 dynamic flow | #90 replaces native hydrology terms/cascade and legacy river flood; recalibrated forcing and dated flood/drought consequences | CW3 30 runs, one disk-full failure retained; five-world primary analysis plus separately labelled deterministic supplementary completion; primary effects null | Preserve failure and differing cost exposure. Full qualification remains restricted |
| B3 condition and repair | Recovered `83abd666`: irrigation/roads service, wear/damage, sibling `infrastructure_works`, timber/budget integration, tests/viewer | CW3b 72 runs, 0 failures; 7 pre-treatment exclusions; service benefits conditional on activation; timber stalls in every world; RS2 competition/treasury harms | Integrate X1 order/witnesses; independent source review and fresh checks. Desktop/phone journeys and declared-scale profile were unrun. Labor is anonymous and unpaid; repair coins are a public-works sink, not wages. Decide/implement original paid labor requirement explicitly |
| B3 ports | No service consumer in maritime | audit establishes absent consumer | Explicit dependency boundary: ports deferred until a maritime service consumer exists; do not invent a cosmetic repair effect |
| B4 forest–timber–water feedback | Main L3 stock follows cover but explicitly never changes it; watershed reads cover | existing forest/water observations | Audit's harvest-gap canopy loss (`harvest-cover`) is unimplemented. Add opt-in cover linkage, no double destruction of standing timber, records/control and downstream evidence |
| B5 connected environmental viewer | Watershed panel merged; recovered B3 asset panel | watershed browser checks on dated sources; B3 component tests | Basin map/arrows, history series, public-works causal/region joins and upstream/downstream civ context are not established by a snapshot panel alone; failed-public-works natural or labelled constructed story needed |
| C1 targeted protection costs | #85 closure replaces multiplier and charges enforcement; #87 adds native migration closure | CW4 both primaries null; CW4b mixed/leaning primary results, food harm in 10/12 worlds | Preserve lagged contact stock and all harms; audit C1.2 named guards replacing flat enforcement cost remains a proposed follow-on and needs an explicit scope disposition |
| C2 epidemic care | #91 L9-funded named carers, labor exclusion, paid wages, T−1 capacity, own epidemic CFR modifier | CW5c 36 runs, 0 failures; template primary reductions, procedural mixed; per-pathogen readings favor care; survivor food harm disclosed | Supplies with real purchase/consumption receipts, B3 sanitation and X1 crowding consumers; A1 integration; costs and mechanisms remain separately observable |
| C3 mortality separation | #91 tests keep regional epidemic fractions, individual injuries and native endemic mortality separate | `test_epidemic_care.py` invariants | Keep these invariants for sanitation/crowding/injury additions; no second disease death authority |
| C4 informed public health | Main still uses C1's trigger; no delivered-report decision mechanism | audit design only | Dated reports, delivery/expiry, experienced disease outcomes and explicit protection cost comparison; signal-destruction control; independent effects/harms evaluation |
| D1a real reform services | Recovered `e12ba7ec`: poor relief buys real food and removes synthetic relief credit | offline/native tests and draft CW6D1 preregistration | Independent review, integrated source, fresh held cohort, exact-head CI and browser evidence; no established completed held screen |
| D1b guild leagues | Same recovered branch: cross-border stable league identities, purse dues and real aid on recorded threats | tests/viewer; no completed held screen established | Same gates, relation to actual merchant/trade links and genuine activation evidence |
| D1c movement branches abroad | No branch mechanism in main or recovered D1 diff | audit 7.4(c) proposes record-only first, native lapse/recruitment later | Must disposition cross-border movement organization separately; leagues alone do not implement branches |
| D2 attribution | #89 observer labels actor/victim, transfer/mint/destruction/restriction, natural soldier deaths and restored-civ identity reuse | source guard and observer tests | New D4/D3 records must retain attribution. Seven provenance-consuming decisions, merchant origin/payment mismatch and natural-death casualty booking are recorded default-path defects; change only behind opt-in/rules path |
| D3 human war consequences | X1 records home/residence/army attachment and displacement; D2 separates death observations | record-only tests | Injury via existing health-care episodes, release/return, separated kin, evacuation and actual labor/food consequences. Resolve enlisted native migration from source before adding soldier motion; fix inexact roster identity only under opt-in path. Crew record panels are not behavior |
| D4 requisition/restoration | No recoverable branch; design contracts in audits | A5 tests only verify taken stock destruction | Reconstruct transfer to capped rations; subtract/replace minted refill without stacking; restitute actual funded reparations by stable owner id; capture cargo exactly once. RS2/B3 own reconstruction rather than a duplicate repair authority |
| E1 evidence tooling | #83 generic screen runner, full seed registry, compatibility matrix, strict RL8 readers | tests and all retained screen receipts | Reconcile branch-only registry entries, schema/extractor validation before held seeds, complete harm extractors rather than hidden zeros |
| E linked histories | Individual/regional panels and recovery-chain joins exist; no `entityHistory` module/view in main | prior package reader tests | Connected person/household/firm/shipment/asset/region timelines; source pointers, source dates, id versus region versus inferred joins; disabled/unknown/malformed/not-sampled/truncated/zero/recorded states; stable navigation |
| E stories and provenance | Existing narration grammar and audit; generic `sN.*` resolution only verifies snapshot existence | historical narration audit tests | Resolve exact program record citations, reject causal claims on regional/inferred joins, no paid narrator; natural adaptation/failure/mixed examples plus explicit constructed-demo metadata/banner |
| E integrated qualification | Green historical CI and per-slice identity/resume evidence | exact initial main run above | Whole-program catalog compatibility, feature-off identity against `8abc1acb` and preceding integrated main, active-transition exact resumes, old bundles/imports, desktop/phone journeys, declared-scale profile, final independent review/PR/CI/main verification. Bounded screens never imply restricted qualification |

## Seed reconciliation

Compared every `scripts/seed_registry.json` version on fetched `claude/cw-*`
and `claude/connected-world` refs (20 refs) plus main: 88 distinct historical
entry variants. The only entry ids missing on main are B3's `cw3b-held-t` and
`cw3b-held-p` (3501–3506 and 3601–3606). Both are marked run, complete, 72 rows,
identity `9b5c4f4121c8ac43cff0ad3073d42395b734a31a955ee4060b0fa9195c6b58e9`.
Merge these records without changing their historical source or receipt.

CW5c already used template 3301–3306/procedural 3401–3406. Audit A6's proposed
cohort with those numbers is stale and cannot be held again. CW6 781–786/881–886
and reserve 791–796/891–896 remain reserved; CW3 template 751–756 is never-run
by design, not automatically available for reassignment. CW3 procedural receipt
remains `complete: false` after its recorded disk-full failure.

Candidate fresh D1 cohort: template 3701–3706/procedural 3801–3806. Candidate
later pairs: 3901/4001, 4101/4201, 4301/4401, 4501/4601 and 4701/4801, each
six sequential seeds. These have no collision in the full remote registry union;
they are candidates, not reservations. The lead must reserve them in the live
registry before a run and run the registry/extractor checks. Pilot worlds stay
template 5/procedural 19 and are never held.

## Review and execution contract

V0–V13 remain the per-slice checklist. Review the actual integrated diff against
the specification/tests, preserve historical pins, append only reviewed exact
inverse layers, enroll test modules and retain source/extension identities.
Each PR needs green premerge Tests on its independently reviewed exact head and
verified main CI after merge. Red main freezes feature merges. No direct main
push, protection bypass, default promotion, paid narration, deployment, credential
or sharing changes, or restricted full 200-seed/procedural qualification run.

The declared-scale evidence target in audit E is 200 turns at template 8×4 and
procedural 32×10, feature-off/on on pilots and development worlds, including CPU,
RSS, output and checkpoint sizes/times, then 22k/52k-agent short stress worlds
and procedural 48×10 at 150 turns. Historical screen timings alone do not provide
these measurements. A genuine access failure blocks only the affected action;
it does not turn unimplemented independent scope into a deferral.
