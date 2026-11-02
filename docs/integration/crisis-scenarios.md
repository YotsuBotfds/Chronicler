# Crisis development cases — admissions and limits

These are constructed development cases, not held-out evaluations or evidence of
general realism. Seed42 was already used in development. No seed search, paid
narration, threshold changes to obtain a preferred result or default promotion
is part of this slice. Source and receipts identify each actual producer.

| Case | What actually ran | Admission / result | Remaining boundary |
| --- | --- | --- | --- |
| A transport | Finite grain2000/300/0, model people400/20/400 and a three-region chain; the real hybrid planner must reserve and depart grain0→2 before comparing eight further turns. The intervention closes region2's incident routes for two economy phases. | The original cargo arrives in the baseline and returns under disruption; a new delivery arrives after reopening. Snapshot4 destination native sufficiency is1.1755 versus0.4516 in the browser pair. Original paused state/native bytes/RNG stay unchanged. | Constructed geography/inventories; regional closure, not arbitrary individual edge deletion. Sufficiency is not household meals. |
| B work and care | Eight turns with actual native occupational injuries, existing spouse care off/on, identical initial pool/RNG. Explicit low yields0.05, soil/water0.2, empty grain, injury rate0.25 and recovery work10. | At the first matched care boundary, source2/region5, care uses0.4 worker-turns for two recipients. Recovery progress7 versus5; production0.09320 versus0.09544, both below demand11.5. | Constructed production stress, not a demonstrated crop effect from an injected drought or infectious illness. Later divergent paths do not isolate an instantaneous marginal effect. |
| C receiving region | Four turns with existing native household migration and liquid gate1. A separately declared development variant reduces region2's initial yield to0.25 of its generated value. | Two real1→2 migration events at source2 have dominant diagnostic term`famine_memory`; one matches a two-person household sample. Next native count32→35, demand16→17.5, sufficiency0.701→0.657. Ledger balances and post-arrival exact continuation pass. | Diagnostic contribution is not sole cause or forced eviction. Net growth also includes other demographic changes. Receiving service demand/enrollment is not demonstrated. |
| D institutional loss | Existing paid academy teaching followed by a constructed hostile transfer. The unchanged 20-turn case loses13.321908 held crafts once and never re-founds. A separate explicit restoration arm acts at paused source13. | Restoration pays the existing30-coin fee, creates a distinct seat with fall provenance; later buys actual crafts and delivers native teaching. Exact continuation covers the fee, paid holdings and delivered work. | Deliberate restoration bypasses the spontaneous lottery; no construction labor/material model. The API requires an attested pause boundary and still needs app/coordinator integration. |
| E distribution | Analysis of **every** recorded A/B/C turn, with hashes checked against A's actual bundles. Demand-weighted known native sufficiency, regional deficits and two-consecutive-snapshot recovery are declared before extraction. | A's mean rises1.1723→1.2858 while region2 remains below1 and worsens. B and C have no sustained recovery; all qualifying and neutral transitions, coverage and changing weights are retained. | Regional differences, not household access/meal inequality. A changing demand-weighted mean is not a pure fixed-population welfare change. |

Negative evidence remains part of the suite. C's original abundant receiver did
not satisfy the constrained-stock admission; a briefly requested0.05-yield
variant did not produce target2 arrivals. Neither was silently replaced in its
receipt. D's natural founding cooldown ends before the eight eligible
source12–19 draws, but none meets the3% threshold. An initial restoration attempt
at paused source12 failed culture28: the later same-turn culture37 was not yet
available. The successful deliberate arm uses a separately declared source13
boundary, with no changed seed, draw or resource endowment.

## Reproduce the usable transport journey

Use Python3.13+, `PYTHONHASHSEED=0` and a real compiled extension built from this
checkout's Rust tree/ABI. The helper never builds or installs a runtime. Select a
fresh external directory; existing output and symlinks are refused.

```sh
env PYTHONPATH="$PWD/src:$PWD" PYTHONHASHSEED=0 \
  RAYON_NUM_THREADS=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  "$NATIVE_PYTHON" scripts/crisis_transport_example.py \
  /absolute/fresh/crisis-transport --simulate-only
```

The helper writes ordinary viewable bundles, the common exact checkpoint, both
final checkpoints, a durable pair manifest, observations and`WALKTHROUGH.txt`.
The walkthrough contains the exact command to open the original loaded-cargo
checkpoint paused in the existing live viewer. Start the production viewer with
`cd viewer && npm ci && npm run build && npm run preview` (or use the existing
installed dependencies). Open the private link printed by the live command;
keep its token out of screenshots, notes, exports and backups.

Inspect the destination in Trade → Food. In Bounded what-if choose regional
transport disruption, region2, duration2, horizon8. Review the readable region
and effective window **before** running. Compare the resulting runs through the
existing comparison, inspecting regional food, recorded cargo return and later
delivery. Nearby events do not prove a further causal relationship. The original
stays paused. Exact continuation refuses an incompatible Python/native producer;
older viewable bundles remain usable with missing observations unknown.

Other focused executable cases are`scripts/crisis_labor_example.py` and
`scripts/crisis_migration_example.py`; their output is diagnostic JSON and exact
checkpoints, not a promise that those files themselves are viewer bundles.
`scripts/crisis_distribution_summary.py` analyzes the declared A/B/C evidence
layout; it does not launch simulations. D's bounded cases are in
`tests/test_crisis_institution_recovery_native.py` and`tests/test_lab_academy.py`.
These Python/native checks do not stand in for browser verification.

## Qualification state

M7 remains partially covered: completed outputs and bounded admissions exist,
but receiving services, complete common-point alternatives for every case and
held evaluation remain unfinished. M8's actual transport browser journey passes
at desktop/390px with recorded pre-relief food comparison; academy restoration
is not yet a UI control. Delayed report
harm/food outcomes remain M6's explicit unmet acceptance. Full scientific gates
and default-policy promotion remain unrun.

Local evidence:`/workspace/shared/chronicler-crisis/m7-suite`, with original
failed admissions retained. Source/evidence publication is tracked separately
in the active roadmap; a local output path alone is not an off-machine backup.
