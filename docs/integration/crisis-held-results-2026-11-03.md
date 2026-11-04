# Modest held crisis results — 2026-11-03

All **12 declared trajectories / six matched pairs / 240 completed turns** ran
at clean source `4ae065994c6c3f6a9988fb7f343f1fe6357c4d0d`. The
[declaration](crisis-held-evaluation-2026-11-03.md) was committed at `245a57aa`
before execution and remains frozen, including its historical pre-run status.
No seeds, endowments, metrics or signs were changed after observing results.
These are held seeds within constructed development families, not independent
scientific validation or an endorsement of either policy.

Every pair had equal normalized opening world, native bytes, Python RNG and
NumPy RNG, with only the declared policy field removed from world comparison.
Every trajectory retained an exact opening checkpoint, 20 dated full-main
snapshots, normal viewer bundle, final state and final checkpoint. All 1,440
native and 480 public food-balance rows passed their tolerances. Maximum native
residual/tolerance was `0.006329`; maximum absolute public residual was
`8.882e-16`. Seven pure metric/identity/clock regressions pass. Native execution
used a fresh source build verified by the release lane; no native import was
needed by those seven tests.

## Observed outcomes

The following are **care enabled minus disabled**. Work and progress are summed
across the actual recorded native service receipts; later path differences do
not isolate one instantaneous care effect.

| Seed | Care worker-turns | Recovery progress | Final weighted sufficiency difference | Mean-turn weighted sufficiency difference | Deficit-region-turn difference |
| --- | ---: | ---: | ---: | ---: | ---: |
| 202 | +32.8000 | +102 | -0.001297 | +0.008915 | 0 |
| 303 | +31.6000 | +129 | +0.001099 | -0.000279 | 0 |
| 404 | +44.0000 | +123 | +0.000128 | -0.000006 | 0 |

Care was actually delivered, with 164/158/220 recipient-turns respectively.
Neither arm shows a two-consecutive-observation regional recovery after a
recorded deficit. Positive-demand region coverage is `6/8` throughout seeds202
and303; seed404 changes between `4/8` and `5/8`. Zero-demand native regions are
unweighted, not filled with an invented food value. Every turn still has a
known weighted mean. Both arms have 120/120/96 known deficit-region-turns.
The sign of the final and mean food difference varies; no general food benefit
or harm follows from this small case set.

The following are **shuffled reports minus normal reports**. Brier is the mean
over four uniquely identified resolved reports per trajectory, with zero
unscored reports; cumulative snapshot outcomes are deduplicated.

| Seed | Procurement coins | Public spoilage | Final weighted sufficiency difference | Mean-turn weighted sufficiency difference | Deficit-region-turn difference | Mean Brier difference |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 202 | -2 | -11.3953 | +0.061284 | +0.012524 | -2 | +0.240989 |
| 303 | +4 | -5.0686 | +0.095053 | -0.000293 | 0 | -0.078075 |
| 404 | 0 | -19.3766 | -0.033906 | +0.006713 | -2 | +0.200029 |

All four forecast regions have positive-demand coverage at every turn.
Normal/shuffle total procurement coins are 51/49, 81/85 and61/61 respectively.
Region0 first has sustained sufficiency after a deficit at source2 in both
arms for every seed. Seed202 shuffle also records region1 recovery at18;
other regions have no observed post-deficit sustained recovery. The improving
means coexist with regional shortfalls/declines in every trajectory; the full
per-turn/per-region summaries retain all such transitions. A worse report score
does not consistently imply worse food, higher cost or greater spoilage here.
Sufficiency remains stock/demand, not measured meals or household access.

## Reproduction and identities

From this checkout, with CPython3.13+ and a freshly built matching extension,
choose a new external output directory. This command made the first evaluation:

```sh
PYTHONPATH=src:. PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  /workspace/scratch/chronicler-release-env/bin/python \
  scripts/crisis_held_evaluation.py \
  /workspace/scratch/crisis-held-evaluation-first-20261103 --simulate-only
```

The interpreter path is environment-specific. The runner makes no API calls,
keeps partial/failed arms and returns nonzero for an incomplete/invalid pair.
A final integrated-source replay is a qualification replay of these now-observed
seeds; it is not a new holdout. No 200-seed scientific gate was run here and no
defaults changed. Generated worlds/checkpoints/logs stay outside Git.

- Declaration SHA-256: `454c33b05cdd342ad6ea1a712fe863258274b38b02fa1412c64743947a6a84c6`.
- First `evaluation.json` SHA-256: `3f21466e4cdbe31e45fecd0f3780c37e1fa1d09edb8ba020765e0995edd7b1c0`.
- Native SHA-256: `d15cb4c3f7e71778ce9127688486aba85a01459c344dcbb3dfd8e3331e824b8d`.
- Rust tree: `543df3bb74804c71cf16046a7cac8f43ea9bfe45`.
- Source tree: the exact clean commit above; `source_dirty=false` in manifest.

The manifest binds each opening witness and bundle hash. All first-run bundle
SHA-256 values are retained here so missing local artifacts remain explicit:

| Family / seed / arm | Bundle SHA-256 |
| --- | --- |
| care / 202 / off | `b183f0ac542620d8f26060e345e02029c7f83190b147781c27276fc6fb5f1a9e` |
| care / 202 / on | `5c17d777060fddec9106e039f3af67fef61270e7ce195b20a16e519a16e3f5f2` |
| care / 303 / off | `3b8506b94fab1437bc29cafff00d7df467e1587c4c3355ffe802849452cb2a00` |
| care / 303 / on | `72846abb15c83712d3cca203a864d2fd87af644824eb77e485e0309e86fe4424` |
| care / 404 / off | `18cb039a32d8891d76d6d62c2fe36368a3f97793c02495d04f99de05b0bd8148` |
| care / 404 / on | `7b353b74f295fbe70272aa3ec51c267371833df968091ee54847dbfa5ffa3e7b` |
| forecast / 202 / normal | `d4527fec628beff9e90b2265609a11babd56d05a81cf690ea18fd161bcaab1af` |
| forecast / 202 / shuffle | `68ab5a2a101501fc2048612110cd3dd6341364c576453caf4bcd9fb65d72e481` |
| forecast / 303 / normal | `e45d9a4e48668d4ba367aa3c0fa28f9b92e724597e050077872dcdecf9872c26` |
| forecast / 303 / shuffle | `50af4c8eb4cf255c9cf02279b191c18b37e1180a556c8fd78e4e5d7a69cdf9d0` |
| forecast / 404 / normal | `22d2d970dcb2b70c7d4953c86c51773e0fe8f041c9b7d95801124d8b43aaa9ac` |
| forecast / 404 / shuffle | `4837d4bed76c36d5b95166d686c0cca7ddcc1bd9e7f30ebf76b29c1b25bc5cc0` |
