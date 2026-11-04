# Frozen modest crisis evaluation — 2026-11-03

This declaration is committed **before** executing any evaluation trajectory.
It evaluates new seeds inside two previously constructed development families;
it is not independent scientific validation of the model, representative
history, household welfare, or a default-policy recommendation.

## Fixed design

- Base: `63581a9a1a1297396ce2227ac2683aeefd5ad8a3`.
- Seeds: **202, 303, 404**, selected before observing these runs. They are absent
  from the existing crisis scripts/tests/docs searched at declaration time.
  They are held out from this crisis development program; no claim is made that
  nobody has used these integers elsewhere in the repository's history.
- Horizon: **20 completed turns**, full `main.execute_run`, hybrid native runtime,
  narration disabled. Preserve ordinary bundles, exact opening checkpoints,
  complete histories, source/build identities, and final states externally.
- Family **care**: eight generated regions/four civilizations, all grain stocks
  empty, grain slots `[0,255,255]`, synchronized base/effective yields
  `[0.05,0,0]`, soil/water `0.2`, injury rate `0.25`, recovery work `10`.
  Existing spouse care disabled versus enabled; all other initial inputs match.
- Family **forecast**: four regions/two civilizations, each civilization owns
  consecutive pairs with a capital at its first region, each region population
  `60` and capacity `100`, initial treasury `45` per civilization, complete
  adjacency, region0 no food yield/stock, regions1–3 grain base/effective yield
  `1.8`, soil/water `1`, finite grain/salt `150` each. Public reserves start
  empty, public storage capacity `100`/condition `1` per region. Existing normal
  reports versus shuffled reports; all other initial inputs match.
- Twelve trajectories total. Within each seed/family pair, normalize only the
  declared policy field and require equal initial world, native bytes, Python
  RNG and NumPy RNG witnesses. No replacement seeds, tuning, rerunning with
  changed endowments, post-hoc positive admission, or filtering neutral/reversed
  outcomes. Failed runs remain recorded and distinguish failure from no effect.

## Predeclared measures

Extract every recorded turn and region, retaining missing observations as
unknown. Use the existing `crisis_distribution_summary.summarize` convention:
positive-native-demand weighted sufficiency, explicit region/demand coverage,
regional deficits, two-consecutive-observation recovery after a deficit, and
mean-improvement transitions with regional shortfall/decline. Sufficiency is a
Phase-2 stock/demand signal, not measured meals or personal food access.

Report each arm and each intervention-minus-control difference for the final
weighted sufficiency, mean of available turn-level weighted sufficiencies,
observed deficit-region-turns, actual care worker-turns/recipients/recovery
progress, public procurement coins and spoilage, and forecast resolved/unscored
counts and Brier scores. Deduplicate dated forecast outcomes by report identity;
never sum cumulative snapshots repeatedly. Check native and public balances
against their own recorded tolerances. Report coverage alongside outcomes.
Changing populations, institutions and economic paths limit causal attribution
of later component differences; these are matched policy trajectories.

## Execution status

Declaration frozen; execution not yet started. Results will be appended after
running the unchanged declared design. Generated artifacts and private logs
remain outside Git.
