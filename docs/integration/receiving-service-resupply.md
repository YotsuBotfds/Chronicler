# Receiving academy: permission, stock and actual recovery

The prior receiving-service negative case is retained unchanged in
`crisis_receiving_service_admission.py` and its native regression. It has real
food-distress-associated arrivals and a living academy, but no post-arrival
supplies or actual teaching result. It is not a successful recovery.

The generated seed42 five-region/two-realm world explains the failed resupply
attempt. Receiver2 (Verdant Plains) belongs to Ashkari; suppliers0/1 belong to
Kethani. Ashkari's relation to Kethani is neutral, but Kethani's return relation
is suspicious. `economy.build_merchant_route_graph` requires both neutral or
better. Its only initial directed edges are0→1 and1→0. Stock, a quote and a
funded academy cannot create a missing diplomatic route. This is a supported
model constraint, not a native planner defect.

## Separately declared finite development variant

`scripts/crisis_receiving_service_example.py` declares both starting relations
neutral, enables the existing cities/techniques/academy-service mechanics, and
keeps the generated map, people, native occupations and RNG. Initial grain is
100/0/0/0/0 and crafts200/20/8/0/0; receiver owner's treasury is500. The real
first economy phase caps supplier0 crafts at20. Receiver2's base yields are
one quarter of the generated values, as in the previous receiving variant;
the generated effective yield remains explicit in `initial-world.json`.
This is an initial endowment and permission choice, not an estimate of a
negotiated diplomatic action. No dispatches, people or service receipts are
injected, and no seed search or model threshold change was used.

The full coordinator runs three common turns and writes a complete exact
checkpoint and ordinary viewer bundle. Its source2 migrations include actual
1→2 moves whose dominant diagnostic is `famine_memory`, with matching household
eligibility samples below food sufficiency1. The native non-Scholar upper bound
rises29→33; receiver native sufficiency is approximately0.7014. These are
regional potential learners and recorded diagnostic contributions. They are
not enrollment, household food access, or proof of forced eviction.

The same checkpoint starts three alternatives with identical world/native state
before the stated control, and matching Python/NumPy RNG:

| Arm | Only boundary control | Observed bounded result |
| --- | --- | --- |
| open | Keep academy services and routes enabled | Real craft deliveries fund purchases and subsequent native Scholar work. |
| closed | Set the existing receiver trade suspension counter to3; two economy phases are blocked | An unladen craft reservation is cancelled, new deliveries pause, and later real resupply restores actual teaching. This is not a mid-transit cargo return. |
| paused | Pause the existing academy-services switch | No new supply purchases or native teaching requests are made. Legacy unmetered scholarship efficacy returns; this does not disable learning. Missing native delivery receipts remain unknown; a sum over known receipts is not measured zero work. |

The paused arm is an existing compatibility control, not a pure "no institution" counterfactual: `academy_service_fraction` returns1 when the resource-backed feature is disabled. No general learning-effect comparison is claimed.

Actual destinations and phases matter. The planner reserves1→2 crafts at
source1 and departs/arrives at source2; the physical arrival is consumed by the
following source3 economy. The open academy buys0.811300 crafts for one coin
at its actual0.299275 quote, then uses those holdings for0.101412 Scholar-days
at source4. Later the planner reserves0→2 at source4 and departs/arrives at5;
source6 buys0.754921 for one coin at0.349666, then source7 teaches0.094365.
These flows are not an assumed0→2 dispatch inferred from an origin's stocks.

The ordinary craft quote rises at the depleted receiver (source1 about3.20,
supplier1 about0.0222), while suppliers retain physical crafts. The native
planner also considers category priority, reachability, commitments, capacity
and its shadow inbound/outbound tally. These observed economy prices do not
claim to expose its complete marginal route score. All dated market quotes,
closing stocks, actual imports and destinations are preserved in each
`market-trace.json` and bundle's transaction receipts.

The environment phase decrements the counter before each economy: source3
sees2, source4 sees1, and source5 sees0/reopened. Counter3 therefore means two
blocked economy phases in this direct-boundary example, not three. Earlier
private receipts retain their original descriptive label; actual timing and
model inputs are unchanged by this wording correction.

The closure preserves an already queued arrival: it still buys at source3 and
teaches at4. At source7 its held inventory and work request are0, with actual
work unknown, while the open arm delivers0.094365 Scholar-days. New closed-arm
cargo really arrives at source6, enters the source7 economy, supports a paid
0.980574 purchase, and supplies0.122572 actual Scholar-days at8. Admission binds
this arrival→following purchase→following teaching chain and its earlier service
gap. Later paths differ: known delivered work through source15 is about0.457
open versus0.515 closed. This demonstrates bounded disruption and recovery;
it does not show general harm, superior policy, or unchanged migration.

## Reproduction and qualification

Use a freshly built matching native extension and Python3.13+:

```sh
env PYTHONPATH="$PWD/src:$PWD" PYTHONHASHSEED=0 \
  RAYON_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  "$NATIVE_PYTHON" scripts/crisis_receiving_service_example.py \
  /absolute/fresh/receiving-service --simulate-only
```

The helper refuses existing output, retains failed/partial admissions, and
returns nonzero for partial results. It writes `case.json`, source/helper/native
identities, exact common/final checkpoints, three viewable bundles, raw dated
market traces and `WALKTHROUGH.txt`. In the viewer compare `open`/`closed`, select
region2, and inspect Trade/Food and Learning. Snapshot numbers are source+1.
The original three snapshots remain identical in every arm.

The native test executes the complete helper from an explicitly supervised
hashseed0 process, checks the permission gate, same-source witnesses, distress
association, chronological recovery, disabled-service unknowns, artifact
preservation and exact turn8→16 continuation. Replay compares complete history,
world JSON, native bytes, and final Python/NumPy RNG. Every native food balance,
academy material balance and merchant receipt-completeness check must pass.
The original constrained no-stock negative is run alongside it.

This remains a constructed development scenario, with a16-turn horizon and
explicit opportunity/demographic effects. The moderate held evaluation and
broader qualification have separate declarations; this example alone closes
neither scientific qualification nor the complete crisis program.
