# Resource-backed academy teaching candidate

Enable with `--agents hybrid --cities --scholarship --techniques --academy-services`.
The candidate is off by default. City craft markets provide usable native craft
quotes; an academy can exist without supplies, a quote, staff or successful
service. `--no-academy-services` pauses purchases and teaching while retaining
paid supplies. A saved candidate is dormant with agents off; other active modes
are refused. Exact resume retains the setting and refuses contradictory flags.
Disabling scholarship cannot discard paid or unknown institutional holdings.

This replaces the unintegrated count-based prototype. Living scholars and
potential learners are upper bounds, not available workers or enrollment.
The native runtime selects actual live adult Scholars by stable identity,
excluding travelers and enlisted agents, with at most one work unit per person.
Urban Scholars can teach; the rural-farmer city exclusion is not a teaching rule.
Current illness/care work models farmers, not individual Scholar sickness. No
additional Scholar health state or wages are invented.

## Stocks, work and timing

- Phase10 records actual academy upkeep due, paid and satisfied. Zero due is
  satisfied without a payment. Current native post-trade craft prices are copied
  from the existing calculation as four appended Float32 output columns; Python
  does not reconstruct a native price in different precision. Missing or nonpositive
  quotes cannot fund a new purchase. A usable quote and projected treasury bound
  procurement after actual private loading/departure commitments.
- A purchase removes actual market crafts and charges treasury once into separate
  institution-held supplies. Payment is the existing model's domestic fiscal
  sink, not an invented seller-wealth transfer. Promised capacity is bounded by
  dated native Scholar/non-Scholar counts; they do not establish availability.
- On the following turn, after politics and immediately before the native agent
  tick, applicable prior-patron upkeep and held supplies bound the work request.
  Phase2 count upper bounds are detached before its borrowed batch is released.
  The native wealth phase confirms surviving identities and actual delivered
  work, reducing those Scholars' ordinary income. Requests/reservations are not
  recorded as delivered work. Current farmer care losses are preserved separately.
- One actual Scholar-day serves eight modeled learner-equivalents and consumes
  one already-purchased craft per equivalent. These are explicit candidate units,
  not measured teaching efficacy. Unused supplies remain held. Prior delivered
  service scales only the academy's local technique-adoption increment in the
  next turn's actual technique phase. Research, adjacent diffusion and forgetting
  keep their existing rules. Pausing restores the historical adoption rule.
- Seat index plus region/founder/founding turn/name binds a supply incarnation.
  Peaceful patron change preserves holdings but old-patron upkeep cannot fund new
  teaching. Destruction/replacement records a one-time loss. Duplicate live academy
  hosts are refused before allocation, so seats cannot reuse one regional pool.

The schema1 child `history[n].scholarship.learning_services` records completed
`captured_turn=n`; individual receipts use sourceN/availabilityN+1. Purchases,
held crafts, actual work, consumption and losses remain separate. The dated
material account reconciles opening+purchased−used−lost=closing, disclosing its
residual and1e-6 absolute tolerance. Unknown legacy holdings stay unknown. This
does not claim a complete per-good native craft lifecycle ledger; native aggregate
consumption and transport are distinct from this institutional inventory account.

Native pending work is transient and deliberately absent from its old checkpoint
layout. The Python writer refuses while either Python or native work is pending.
Completed checkpoints retain paid supplies, receipts, policy, native state and RNG.
Cancellation releases an unconsumed reservation; a failed native tick is not
claimed to roll back. Resume the prior completed checkpoint after a failed turn.

## Actual qualification and retained failures

The price-enabled wheel SHA-256 is
`665309da6f8653a525b99eec9f97f8562bca0cd7923f7bf07fd690affea3d7cd`;
its installed compiled bytes match SHA-256
`d15cb4c3f7e71778ce9127688486aba85a01459c344dcbb3dfd8e3331e824b8d`.
Rust tree `543df3bb74804c71cf16046a7cac8f43ea9bfe45`, CPython3.13 ABI.
Earlier no-price wheels are retained, not silently reused.

Nine actual native service checks cover pending/cancel refusal, real income cost,
market-to-held transfer, exact paid-holdings continuation, no-stock failure,
explicit finite restock/recovery, peaceful patron transition, hostile loss once
and the actual technique caller consuming prior delivered service. A half-work
reservation reduces ordinary income by0.098 after existing decay. The scenarios
are fixed-seed constructed controls; restock is a declared exogenous source and
controller transitions are not represented as simulated battles. One hostile
transition destroyed the academy rather than preserving it; that negative
admission result is retained.

The combined focused run passed389 tests, then the additional technique test
passed in the nine-test native selection. Guarded contracts/metadata passed241;
no-native selection passed135 with three legitimate native absences. Source
lineage checks passed440 and61 subtests independently of behavior proof.
Actual disabled old/new pairs with scholarship/techniques enabled retain39
artifacts and24 native states across all four modes; an additional eight-turn
standing-academy hybrid pair retains eight artifacts/eight native states, full
decisions/world/RNG, without stripping observations.

Viewer1,131 tests passed before the final focused keyboard adjustment; six final
focused checks, lint/build and production desktop/390px checks pass. Real receipts
showed56 crafts purchased for one coin, then six actual Scholar-days using48
previously held crafts. Newly bought crafts are not added to that consumption.
The history keeps decimal values together and supports keyboard horizontal
scroll. A real newly generated older-source standing academy loads without
fabricated service values. Initial borrowed-snapshot lifetime, missing native
price, capture-clock and keyboard failures remain in the evidence folder.

## Run and inspect

With matching source/native build and locked dependencies:

```bash
PYTHONHASHSEED=0 python -m chronicler.main --seed 42 --turns 8 \
  --agents hybrid --cities --scholarship --techniques --academy-services \
  --simulate-only --checkpoint-every 2 --output output/academy/chronicle.md \
  --state output/academy/state.json
cd viewer
npm run dev
```

Load `chronicle_bundle.json`, open Learning, select a seat and inspect its dated
service history. An ordinary generated world may have no standing academy.
The constructed working example and checkpoints are under
`/workspace/shared/chronicler-crisis/m5-integration/example`; its generator and
manifest explicitly record the pre-existing academy and finite initial supplies.
Broader combined CI, held crisis scenarios, distributional recovery, scientific
qualification and default promotion are separate gates in the active roadmap.
