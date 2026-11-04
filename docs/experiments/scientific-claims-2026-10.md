# Scientific claims: prospective pilot contract

Written before implementation outcome runs or parameter tuning, on integration
`8f180a03`. This default-off pilot is narrower than a general science system.
The parameters below are illustrative design choices, not fitted estimates.

**Prospective control amendment, 2026-10-28:** mechanical acceptance fixtures
were run for the original zero-weight uninformative arm. Before any world
qualification, review identified that it duplicated withholding rather than
testing an evidence process with no information about treatment benefit. The
uninformative arm below is therefore amended to use comparator-centered sham
observations with ordinary posterior updates. The original preregistration
remains in commit `0da8094a`; no parameter is being fitted to world outcomes.
The new measurement-only null check is frozen before its first run: seeds
1000 through 1999 inclusive, fixed retained physical inputs, one observation
per claim/seed. Its mechanical criteria are absolute difference in sham
support frequency <= 0.08 and informative irrigation-minus-masonry support
frequency >= 0.25. These are implementation checks, not an inferential power
or world-benefit claim; nonidentical realized sham beliefs are expected.

**Prospective calendar correction, 2026-10-28:** independent controlled
fixtures starting in all four seasons found that an absolute turn-modulo-six
effort schedule never overlaps summer or winter claims. Before world
qualification, anchor the same six-turn interval to the persisted cohort
`started_turn`. Keep context matching, costs and effort allowance unchanged.
This corrects calendar exposure; it is not parameter fitting to outcomes.

## Question and causal edges

Does paid, locally transmitted evidence reallocate a fixed paid adoption
effort toward techniques whose claimed *contextual grain benefit* is supported
by the existing physical production evaluator? Canonical recipes remain
physically useful for their canonical purposes: a masonry claim about grain
can fail without making masonry itself invalid.

The chain is treasury-funded controlled trial -> noisy dated observation ->
institutional receipt -> bounded local confidence -> allocation of paid
adoption effort -> ordinary practice growth -> ordinary technique physics.
No confidence or validity flag may enter a yield formula. No trial output is
added to world goods, and no world is forked inside a turn.

## Frozen first slice

Only living academies participate. One world-long pilot cohort registers at
most 20 seat IDs; the first qualifying academy proposes exactly two claims:
irrigation and masonry, each claiming at least 2% more grain from a fixed
four-worker grain plot at recipe practice 1 versus 0 over one worker-turn.
Both recipes must already be locally practised. Maximum state ceilings are
20 claims and 40 trials, but this slice uses two originals and at most one
different-academy replication per original. Fallen seat IDs are not recycled.

The context is grain, a fixed equal crew, soil and water quarter-bands,
season and climate phase. Transfer/application requires matching all of
these fields, a grain slot, and a sedentary region. Evidence is not treated
as universal outside its context. This tests the yield effect, not the
separate arable-capacity benefit of farming techniques.

### Physical evaluator

Use the current region's read-only harvest calculation:
`ecology.compute_resource_yields(..., worker_count=0, deplete_reserves=False)`.
A lightweight world view overrides only that region's recipe practice in a
small temporary TechniqueState. Other local practice, physical region fields,
climate, tuning and ecology are unchanged. Convert the first grain slot with
`ecology.goods_per_worker`; evaluate a grain-only controlled plot through
`economy.compute_allocated_production` at a fixed four-worker crew and no
food-demand reallocation. These are existing physical functions, not outputs
sampled from a label saying a claim is true.

The evaluator must leave complete world serialization and all existing RNG
states unchanged, including reserves. Its control/treatment outputs and a
compact input signature are retained as diagnostics, never stock movements.
Trial costs pay for the experimental service, as academy upkeep does; this
pilot does not claim to allocate real agents or harvest real test plots.

### Trials and dependence

A trial costs 2 whole treasury units, paid only if its current patron's exact
projected treasury keeps a 20-unit floor. Costs are `keep` mutations and are
never refunded. Measurement completes one turn later. A seat that falls or
loses eligibility before completion yields a retained cancelled record.
Null, failed and negative trials remain in the cohort; no retry replaces an
unfavorable result. Unfunded requests do not produce observations.

Observed control and treatment add independent namespaced measurement errors
with standard deviation 3% of physical control output. There is no hidden
truth-bit draw. Zero-output tests have no evidential weight. Comparator-
centered sham observations use the ordinary evidence rules described below.
The measured relative difference is compared with the
claim's 2% threshold. The physical outputs themselves do not update belief.

Each record stores its immutable trial ID, source-data signature, protocol,
parent trial, context/environment block and dependence group. Different IDs
or seats alone do not establish independence. Trials in the same climate
cluster/year/protocol block contribute at most one unit of evidence to a
claim. Repeated source-data IDs are counted once, including copied evidence
given an alias ID. Distinct dependent observations average within their one
unit; this can correct a conclusion without inflating sample size. An
independent replication waits at least 12 turns and needs another academy
with matching claim context. It is planned irrespective of the first result.

### Local delivery and confidence

Only directly adjacent academy regions form institutional links. Proposals
and evidence move one hop per turn, at most three hops, with a six-turn
delivery lifetime from publication. They are copied records, not native
agent packets or replications. Receipt and queue deduplication is exactly
once by record/recipient. Falling academies cannot receive or relay.

Confidence is a Beta(1,1) posterior mean over the seat's *received*
informative evidence, with the dependence caps above. It has no time drift
and reads no unreceived result or physical diagnostic. Conditional on fixed
context, received records and budget, allocation does not change until new
evidence arrives.

Every sixth turn relative to cohort `started_turn`, each applicable
participating academy may pay one treasury
unit for adoption effort, regardless of its confidence. Its fixed effort is
split between applicable locally known recipes in proportion to confidence.
The combined extra adoption-rate allowance is at most 0.01 per region. The
ordinary technique kernel still applies prerequisites, suitability caps,
population shortfall and disruption; confidence cannot invent a recipe or
override any gate. No candidate receives a direct yield bonus.

## Controls and accounting

Persist controls on ScientificClaimsState:

* `withhold_information`: proposals, trial planning and trial/effort payments
  continue, but outcomes do not enter policy receipts. This is the spending-
  matched information control in fixed eligible fixtures.
* `transmission_enabled=False`: local observation remains; no institutional
  messages travel. This isolates geographic spread, with its trial spending
  reported separately because fewer replication protocols can arrive.
* `uninformative_tests`: preserve paid trial scheduling and physical
  diagnostics. Both observed readings are centered on the physical
  comparator, with the same independent measurement-noise rule. The ordinary
  informative/support/posterior rules still apply; realized confidence can
  change or differ across claims, but these observations cannot reliably
  distinguish the true treatment benefits. Paid effort still occurs.

Information is not allowed to decide which unfavorable trials disappear or
whether a planned replication is funded. Endogenous treasury/eligibility
changes can alter later spending in world runs; report those differences
instead of calling such trajectories perfectly spending-matched.

State bounds include at most 400 proposal receipts, 800 evidence receipts,
1,200 pending messages and 40 most-recent effort allocations. Paid adoption
totals and trial records account for costs; no dense agent belief columns or
unbounded per-turn institutional histories are added. Failed, cancelled,
expired and withheld work must remain visible in counters/records.

## Prospective acceptance

1. Flag off: full output identity, no new random draws or code-path calls.
2. Same physical inputs: exact evaluator outputs regardless of confidence or
   controls; evaluator preserves complete serialized world and existing RNG.
3. Noiseless controlled fixtures: irrigation's canonical grain effect exceeds
   2%; masonry changes no grain. Zero production is uninformative.
4. Proposals/results cannot reach unconnected institutions or arrive before
   their dates. Context-mismatched evidence cannot steer local adoption.
5. Copying one record cannot become a replication; duplicate source data or
   dependent environmental blocks cannot create extra evidential weight.
6. Trials and effort debit exactly their recorded costs, once, including
   cancellations, accumulator paths and saved/resumed runs.
7. Withheld/sham controls keep spending and scheduling equal in fixed eligible
   fixtures. Withheld evidence cannot alter allocation; sham evidence has no
   reliable treatment discrimination on the frozen measurement-only seed
   cohort, without forced equal beliefs. Local-only fixtures retain local
   confidence and remove remote information effects.
8. Technique physics, prerequisites, caps and ordinary growth remain the
   authority; no grain is created by an experiment or receipt.
9. Hold received observations and eligibility fixed while changing hidden
   physical yield coefficients. Confidence and paid allocation stay unchanged
   until an actual new observation arrives.

Later confirmatory world cohorts must be preregistered separately after this
mechanical pilot is stable: seed, scenario eligibility, horizon, exposure,
independence blocks, allocations, targeted grain benefit, experiment costs,
false rejection/acceptance and paired ablations. Twenty connected academies
are not twenty independent experimental units. No population balance,
scientific qualification, default promotion or latency claim follows from
the controlled fixtures alone.
