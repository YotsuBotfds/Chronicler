# Systems expansion after the October integration

**Status:** experimental implementation in progress, 2026-10-28. The standing
below separates implemented slices from proposals and qualification debt.
Experiments remain default off; no default promotion follows from this roadmap.
This complements the Phase 7–9 roadmaps and the
[deferred backlog](../../integration/deferred-backlog-2026-10.md), rather than
renumbering their milestones.

The useful next step is to make time, ownership and information constrain
existing decisions. An injured farmer needs care that costs somebody work;
a workshop needs a customer before it can pay wages; a warning needs to arrive
before somebody spends money preparing. These mechanisms can create longer
causal histories without adding independent event generators.

## Input and source standing

The user supplied **Kimi's “Chronicler: Unplanned Simulation Systems Ideation”**
(`Chronicler Simulation Systems Ideation.md`, SHA-256
`90c5ea7e1d2d107af3d9d96edf7106305d659635a526d7766b212e5b5b53e5d5`).
It labels its review 2026-10-29 and targets main `cb9fe70c`. This roadmap was
prepared on 2026-10-28 against integration `bcdd21f3`. The supplied review's
branch counts and exhaustive-history novelty claims were not independently
reproduced here. Five parallel, bounded source/planning audits checked the
actual integration seams of its nine candidates.

All nine are retained below, with narrower causal definitions and explicit
dependencies. The integration already contains PR #68 debt-holder history,
public granary history, scholarship recovery, capacity-aware refugees and
read-only historical forensics; those are not proposed as new work here.
The [dev-lead handoff](../../integration/dev-lead-2026-10-28.md) records what
was built and tested in the first checkpoint. Subsequent work is recorded in
the [expansion development record](../../integration/expansion-development-2026-10-28.md).

## Current implementation standing

| Candidate | Implemented experimental slice | Remaining boundary |
| --- | --- | --- |
| Impairment and care | Stable-ID farmer injuries, next-turn fractional work loss, costly household care and recovery; integer people and food demand remain separate from work. | Fixed-cohort recovery, natural-world balance and large-world cost qualification; no disease or battle injury model. |
| Delayed warnings | Past-observation harvest reports, delayed contact transmission, paid granary preparation, outcomes and withheld/shuffled controls. | Matched policy comparisons and prospective skill baselines. A discovered negative target increment was corrected; the affected old study remains recorded as a failure. |
| Recurring gatherings | Bounded local attendance, real food/fund costs, dated actual-arrival contact and bond attempts; cost-only/contact/bond controls. | Wider-world effects and network outcomes. A bond attempt is not a formed bond; selected arrivals are not invented pilgrimages. |
| Scientific claims | Paid contextual academy trials, delayed evidence, dependence accounting and evidence-driven paid technique effort; default off. | Natural-world informative/withheld/transmission/sham studies. Accounting groups are not certified independent experimental units. |
| Metrology and loss cover | Bounded native cargo observations, voyage continuity and loss IDs, plus independent public-granary stock/payment receipts. Incomplete capture, virtual cargo, foreign treasury credits and domestic producer sinks are distinct. | Private cash, cargo title, general private settlement and loss ownership. The recorders alone cannot fund private inspection fees or insurance. |
| Water power and firms | Source-audited design and labor/cash dependencies. | No production implementation; avoid adding output before labor and income reconcile. |
| Domesticates | Source-audited draft-animal proposal. | No new cohort implementation; reconcile ownership, creation, fodder and pastoral accounting first. |

The first four slices have development runs and historical inspectors.
The study harness forks one exact checkpoint per seed and records controls,
source and native identities. Its unchanged continuations matched six of six
parent final states in the initial 24-run development set. This checks fork
integrity, not efficacy. The read-only expansion audit found the warning-target
defect rather than treating all generated observations as valid.

Performance work is separate: reader-owned validation turn indexes preserve
reports and accelerate repeated turn filtering, but the measured full report
did not show a reliable overall improvement. The lean ablation output path is
implemented with exact retained-file/oracle checks. Five whole-orchestrator
pairs gave a noisy 1.146x median paired ratio (range 0.986–2.115x); final
precleanup artifact footprint fell 44.6–48.6%. These workload-specific results
do not establish simulation-tick or universal speedups. Oracle thresholds,
horizons and the offline 110-second chunk limit are unchanged.

## Decisions before adding state

1. **Work is separate from population.** Preserve integer living people and
   occupation counts. Define fractional productive time after impairment,
   care, military service and employment. Food demand still follows people.
   Apply each deduction once at the production and corresponding income
   boundary. A shared work-time contract precedes health, firms and draft work.
2. **Every payment has an owner and receiver.** Existing finance borrowers
   index civilization treasuries. A firm ID cannot be put into that field.
   Establish typed wallets and realized transaction receipts before general
   private borrowing, insurance or standards fees. Start firms debt free.
3. **Domain identities survive observation.** A voyage, policy, injury,
   claim or experiment needs stable identity and exactly-once consumption
   across resume. Event IDs identify emitted observations; they do not replace
   the underlying contract or trial identity.
4. **Information has a dated visibility boundary.** Forecasts predict hazards,
   scientific evidence concerns contextual effects, and standards are
   conventions. They do not share a universal truth score. Narration,
   historiography and forensic reports remain observational readers.
5. **Define the clock per mechanism.** Biographical age treats a turn as a
   year; resources use a twelve-turn seasonal cycle; SEIRS has four internal
   substeps. Specify durations and observation windows in simulation turns.
   An injury lasting multiple turns cannot be described as a few weeks.
6. **Budget state before choosing its home.** Default-off output identity
   does not guarantee old exact-checkpoint compatibility. Adding native
   persistent fields changes the native schema fingerprint. Choose an
   explicit migration policy or optional authoritative checkpoint state with
   rebuildable native caches. Never persist agent slot indices.

## Sequence and boundaries

| Track | First deliverable | Dependency / decision |
| --- | --- | --- |
| A: work and households | Temporary farmer impairment and spouse care | Define work-time and checkpoint contracts first; preferred next production experiment |
| A: information and food | Delayed harvest warnings that change paid granary procurement | Freeze observation, timing and scoring rules; river-flood warnings wait for hydrology |
| A: coordinated culture | One costly recurring harvest gathering | Can proceed independently with bounded attendance and existing contact semantics |
| B: production | One work-constrained watermill; then one debt-free workshop | Reconcile current craft/labor/income accounting before either adds output |
| B: evidence | Institutional claim/testing pilot | Specify observable trials, independent evidence and paid effort before world runs |
| C: transactional institutions | Grain standards and narrow port loss cover | Per-good cash receipts; immutable voyage/loss ownership for insurance |
| C: biological capital | Settled draft-animal cohorts | Reconcile pastoral herd creation, ownership and work/fodder accounting |

Tracks can be designed in parallel. Production writers to the same work or
cash boundary need one integration owner and a frozen contract; adding agents
does not remove that dependency. Complete one causal slice and its controls
before composing its feedback loops with the next.

## 1. Temporary impairment and household care

**New edge:** realized work → nonfatal injury → less productive time → costly
spouse care → recovery. Existing SEIRS and campaign death ownership stay
authoritative. The first slice excludes disease, battle injury, chronic
disability, hospitals, fertility and direct mortality changes.

Begin with adult farmers who actually worked and survived existing death
resolution. Exclude enlisted IDs. Resolve new episodes after deaths and apply
their work effect from the following turn. At the economy boundary a present,
eligible spouse can allocate bounded care. The caregiver cannot simultaneously
provide full care, farm work and military service. Apply lost time once to
productive labor and associated income; preserve consumption by living people.
Recovery and assignment cleanup handle death, absence, migration and slot reuse.

Use sparse episodes keyed by stable agent IDs and existing ID lookup machinery;
derive work availability during existing occupation/counting passes. A sparse
map followed by a lookup for every agent is still a dense runtime cost. Avoid
linear slot searches for every episode. Do not create another household registry.

**Acceptance:** productive time + impairment + care cannot exceed availability;
an injected fixed injury cohort recovers more slowly without care while care
still costs work. Resume inside an episode, after a move and after caregiver
death must match uninterrupted execution. Censor recovery at death instead of
reporting only survivors. Pre-register impaired person-turns, care expenditure,
recovery and labor loss; hunger or mortality changes are downstream outcomes.

**Seams:** [native occupation counting](../../../chronicler-agents/src/ffi/mod.rs),
[economy](../../../chronicler-agents/src/economy.rs),
[households](../../../chronicler-agents/src/household.rs),
[campaign armies](../../../src/chronicler/war/armies.py),
[epidemiology](../../../src/chronicler/epidemiology.py),
[native persistence](../../../chronicler-agents/src/persist.rs).

## 2. Fallible harvest warnings and preparedness

**New edge:** observations → delayed probabilistic report → paid preparation
→ changed shortage losses. Early famine warning already appears in the M34
plan; novelty lies in fallibility, delivery and costly action beyond the
granaries' existing response to realized harvest variance.

Kimi's upstream flood example is blocked: current disasters use regional
hazard draws, and rivers do not carry discharge/head or a precursor that
causes the later flood. Reading a future disaster hash would expose simulator
truth. Start with current/past harvest and seasonal observations instead.
Freeze the publication phase, horizon, noise and recipient eligibility before
qualification. A report temporarily changes a bounded granary stock target;
existing procurement pays treasury, respects routes/surplus and bears spoilage.
No direct food creation or mortality modifier.

Use one observer per region, bounded observation windows, at most one active
report per recipient-region and a dated delivery/expiry queue over existing
contact edges. Observation noise uses a new namespaced stream without advancing
existing RNG. Target O(regions + active contact edges), with sparse publication;
this is an unmeasured design budget.

**Acceptance:** compare existing granaries, reports withheld, normal delayed
reports and within-seasonal-cycle shuffled reports. Register a seed-clustered shortage
window without selecting only treatment-induced famines. Verify identical
climate-shock vectors across arms, delivery before purchases and purchases
before shortage. Score prediction against the hazard separately from damage
altered by preparation. Report calibration against seasonal climatology,
false-alarm spending and spoilage. An omniscient immediate-warning arm is only
an explicitly labelled diagnostic.

**Seams:** [climate](../../../src/chronicler/climate.py),
[granaries](../../../src/chronicler/grain_reserves.py),
[contact ledger](../../../src/chronicler/contact_ledger.py),
[M34 warning plan](../specs/2026-03-16-m34-resources-seasons-design.md).

## 3. Recurring gatherings with real attendance

**New edge:** calendar obligation → expenditure/attendance or cancellation →
contact and bounded relationships. A Harvest Festival already exists as
cultural-renaissance flavor; another generic legitimacy bonus adds little.

Begin with one regional harvest observance. Charge real host food/funds;
cancel under shortage or occupation. Select at most 32 present attendees by
stable ID and create/refresh at most eight eligible bonds. Count actual
cross-region attendance through capped pilgrimage contact, including its
existing pandemic-import consequence. Persist schedule identity and last
outcome so conquest cannot reset the calendar into a second occurrence.
Use a deliberate calendar cadence under the existing seasonal abstraction.

**Acceptance:** cost-only, no-contact and no-bond ablations isolate the effects;
cancellation incurs neither expenditure nor gathering exposure. Bucket agent
rows by region once on ceremony turns. Routine attendance gets compact counters;
reserve narration for first occurrence, cancellation and meaningful change.
Do not appropriate reserved native memory codes 12–13 or 15; the initial pilot
can archive events without adding agent-memory semantics.

**Seams:** [resource seasons](../../../src/chronicler/resources.py),
[contact](../../../src/chronicler/contact_ledger.py),
[relationships](../../../chronicler-agents/src/ffi/mod.rs),
[reserved memories](../../../chronicler-agents/src/memory.rs).

## 4. Usable work and prime movers

**New edge:** intermittent usable work limits a concrete production step.
Steam power is already a technique; useful work should not be another whole-
economy multiplier. Legacy `Resource.FUEL` maps from `ResourceType.EXOTIC`,
which the current goods economy treats as food. It is not a spendable coal good.
Timber extraction also has unresolved forest-cover accounting. Defer biomass,
coal and new energy goods until those contracts are explicit.

Pilot one watermill per selected eligible city under a hard global cap.
Persist condition, paid upkeep and work capacity. With no river discharge/head,
label its seasonal reliability proxy dimensionless rather than calibrated
hydropower. Work constrains one selected craft step, alongside existing raw
inputs and labor; replace or relax that constraint once.

**Acceptance:** idled, unfunded or unreliable equipment supplies no work;
inputs, labor and delivered work all bound output; upkeep is charged once.
Ablate reliability, upkeep and conversion efficiency separately. Reject the
slice if it behaves like an equivalent generic technique bonus. Target
O(regions + capped mills), with no extra agent scan.

**Seams:** [resource mapping](../../../src/chronicler/resources.py),
[goods and craft production](../../../src/chronicler/economy.py),
[technique registry](../../../src/chronicler/techniques_state.py),
[production-ledger debt](../../integration/production-ledger.md).

## 5. Employers with customers and payroll

**New edge:** customer demand → receipts → payroll pressure/layoffs → worker
wealth. Cities already convert regional raw inputs to wares and reduce urban
farm labor; agents already receive occupation income. Employment must replace
the selected production/labor/income share rather than pay wages on top of it.

Pilot a debt-free guild-funded workshop, at most one per selected city and
eight employees. Give it working cash, inventory and payroll; one budgeted
municipal procurement order supplies an actual paying customer. Bankruptcy
closes the employer without an automatic state rescue. General retail cash
clearing, private succession and borrowing are later work. Finance's borrower
field and servicing currently index civilization treasuries, so accepting a
firm ID there would corrupt ownership.

**Acceptance:** reconcile opening cash + receipts − purchases − wages −
distributions = closing cash, and inventory/labor separately. Preserve unpaid
transfer residuals at agent wealth ceilings. Test death, migration, conquest,
arrears, layoffs and failure. A demand shock must pressure payroll through
receipts; no-payroll and no-layoff controls isolate that chain. Reuse one resident
index, then O(workshops × employee cap); avoid a full pool scan per employer.

**Seams:** [city production](../../../src/chronicler/cities.py),
[economy](../../../src/chronicler/economy.py),
[finance borrower contract](../../../src/chronicler/finance.py),
[guild purses](../../../src/chronicler/guilds.py).

## 6. Claims, tests and replication

**New edge:** paid trial → noisy evidence → local confidence → adoption effort
→ ordinary technique effects. Canonical techniques remain physically effective
recipes. A random validity bit on irrigation would break that separation.

Represent a proposition as `(recipe, context, metric, intervention, comparator,
threshold, horizon)`. Start with a contextual grain-benefit claim about an
existing technique and a spurious grain-benefit claim about masonry. Specify
a local physical evaluator and paid trial effort; drawing results directly
from a hidden validity label would establish only a toy inference system.

Proposed pilot caps: 20 seats, 20 active claims and 40 tests per cohort, with
one independent replication per original trial and bounded delivery. These are
unmeasured limits. Begin in controlled eligible fixtures. Confidence belongs
to receiving seats, with dated evidence receipts and dependence/source IDs.
Use institutional contact topology initially. Packet intensity is salience,
not confidence; do not overload the four native packet slots or add dense
per-agent belief columns. Do not fork whole worlds inside a simulation turn.

**Acceptance:** fixed physical inputs give identical yields regardless of
confidence; fixed received evidence gives identical decisions until another
observation arrives. Forwarding one result cannot create independent evidence.
Retain negative tests, cancellations and spending. Information-withheld,
transmission-disabled and uninformative-test controls distinguish evidence
from scholarship spending/contact advantages. Measure adoption allocation,
targeted benefit, testing cost and false rejection on held-out seed cohorts.
Twenty connected seats do not constitute twenty independent experimental units.

**Seams:** [techniques](../../../src/chronicler/techniques.py),
[scholarship](../../../src/chronicler/scholarship.py),
[native knowledge](../../../chronicler-agents/src/knowledge.rs),
[observational provenance](../../../src/chronicler/provenance.py).

## 7. Grain measures and interoperability

**New edge:** incompatible local conventions require a paid service, while
trade exposure makes compatibility valuable. Internal goods/cash units remain
canonical. Route transport cost currently applies to every good, so it cannot
represent grain-specific inspection fees.

Start with two grain measures and one standard per participating region/city.
An incompatible grain transaction pays an explicit conversion/inspection fee
from merchant to a named guild/city receiver through a per-good realized
receipt. Adoption has a one-time cost and uses sparse trade/contact exposure.
Fraud and perceived quantities are later mechanisms; incompatibility itself
must not create or destroy grain.

**Acceptance:** non-grain cargo never pays this fee; compatible grain avoids it;
all quantities and cash reconcile. Ablate mismatch fees, adoption costs and
network-dependent adoption separately. O(regions) state and O(1) compatibility
checks per transaction; no agent standard column in the first slice.

**Seams:** [Python route cost](../../../src/chronicler/economy.py),
[native route graph](../../../chronicler-agents/src/merchant.rs),
[guild purses](../../../src/chronicler/guilds.py).

## 8. Narrow contingent loss cover

**New edge:** premiums buy a funded transfer following a specified loss. Cargo
currently leaves regional stock, merchant income is partly a regional profit
proxy, and piracy also charges realms. Existing sea-trade logs lack immutable
voyage and merchant identity. Define insured owner and loss units first.

The first feasible port pool covers a specified existing piracy-related
treasury loss, rather than claiming general cargo-value insurance. Segregate
underwriting reserves from money already offered as loans. Premiums use
observed loss history, never true future raid risk. Claims transfer cash;
seized/destroyed goods remain lost.

**Acceptance:** premiums/claims conserve cash; payments cannot exceed coverage
or reserves; replay/resume cannot pay twice. An insurance-only transfer arm
preserves voyages, raids and lost cargo. Test correlated raids exhausting the
pool. Ablate coverage, pricing and reserve limits separately. Wealth transfers
alone do not establish safer trade; coverage-to-voyage choice needs a later
explicit behavior mechanism. Index voyage identity and process new crossings,
not policy × lifetime voyage history; cap active contracts and compact closures.

**Seams:** [maritime](../../../src/chronicler/maritime.py),
[native sea logs](../../../chronicler-agents/src/merchant.rs),
[finance](../../../src/chronicler/finance.py),
[domestic-credit claims](../../../src/chronicler/domestic_credit.py).

## 9. Domesticates as breeding capital

**New edge:** inherited draft capacity has feeding costs and delayed replacement.
Nomads already have moving, growing and dying herds that supply food. Their
near-empty pastures receive abstract restocking, and settled ownership applies
abstract slaughter/sale decay. Those cannot silently become conserved breeding
capital.

Begin with one settled draft-animal cohort: breeding adults, replacement delay,
one inherited draft trait, paid fodder and explicit animal losses. Decide
whether these are separate animals or transfers from pastoral herds. Count
pasture/feed once, retain traits on transfer, and require both technique
knowledge and actual animals. Existing `ox_plough` practice already raises grain
yield and farmland capacity: explicitly reconcile or replace its draft-related
benefit under the pilot before adding animal work. Farm work is the sole initial use; manure,
transport, meat, disease and requisition follow separately. Apply draft work
at a bounded labor input before the existing farmland curve, without multiplying
farmer count, yield and cargo capacity simultaneously.

**Acceptance:** opening stock + births + imports − deaths − slaughter − exports
= closing stock. Zero breeding stock cannot create replacement animals without
explicit imports. Test
famine, conquest, feeding and ownership transfer; no-breeding and no-draft-work
controls isolate replacement and productivity. State scales with regions/cohorts,
not individual animals.

**Seams:** [nomadic herds](../../../src/chronicler/nomads.py),
[farm production](../../../src/chronicler/economy.py),
[technique prerequisites](../../../src/chronicler/techniques_state.py).

## Qualification and wall-clock contract

Each slice needs a short preregistration: eligible units, outcomes/windows,
intervention timing, deterministic streams, control arms, stop conditions,
sample/power limits and frozen parameters. Start with conservation and boundary
fixtures, then a development cohort, then held-out template/procedural gates.
Retain failed and inconclusive results. Full milestone qualification remains
the documented 200-seed before/after gate; these proposals do not waive it.

Require flag-off output/RNG identity, enabled exact resume at every new state
boundary, consumption/reset checks, stable ordering across threads, source and
native-binary receipts, bounded offline chunks and appropriate native/viewer
checks. State an explicit policy for older checkpoints before changing schema.
Emit compact regional summaries and named-person milestones; copying every
episode, employee, policy or trial into every snapshot grows with entities ×
turns and makes fork qualification expensive.

Use the [simulation workload matrix](../../performance/simulation-scaling-2026-10.md)
for defaults, dense agents, larger geography, long horizons and ensembles.
Measure CPU, elapsed time, peak memory, checkpoint size/time, output bytes and
event volume on quiet, paired runs. Proposed early target for each bounded
pilot: no more than 2% added whole-turn CPU at its declared cap; a miss triggers
profiling or a scope decision, not a hidden reduction in agents or seed counts.
This target and all complexity budgets above are unmeasured acceptance proposals.

For immediate wall-clock investment, prioritize an immutable validation turn
index, lean ablation-fork output, resident/household decision indexes and
history serialization measurements from that performance plan. The
[workflow plan](../../performance/workflow-scaling-2026-10.md) covers identified
native-build reuse, shared CPU budgeting and staged checks. Automatic workers
are already quota-aware in this integration; the other performance experiments
still require measurements and exact equivalence evidence.
