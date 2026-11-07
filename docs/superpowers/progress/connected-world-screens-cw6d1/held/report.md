# CW6D1 held evaluation — bounded, no qualification

Frozen source `808726b8c886306229d3e08d76fdee9e6f580dde`; Python 3.13.5; extension SHA-256 `f2fb24f13c386c3965e485330499b9aa435f61a43e8fc02023f950fbf9664256`. The preregistration SHA-256 is `425f25c71015f483efb599c01b0f60aa6569793735bd41b9b15b58f96f8309a7`. Source/extractor/registry identities and timestamps are retained in [source.txt](source.txt), original per-world outcomes in [metrics.jsonl](metrics.jsonl), and reservation identity in [held-run.json](held-run.json).

All 60 runs completed without simulation/extraction failures or missing primary outcomes. Simulation plus extraction used 1,066 seconds (0.296 core-hours) against the frozen 0.75 core-hour ceiling; elapsed wall time was 1,068.7 seconds. Schema pilot 20/20 and timing pilot 10/10 completed before held use. No defaults, qualification gates or paid narration were run.

## Activation precedes effects

| Mechanism | Template 3701–3706 | Procedural 3801–3806 |
| --- | --- | --- |
| Relief service, RS | 0/6 | 2/6: 3801, 3805 |
| Guild mutual claims, GM | 0/6 | 6/6 |

Relief activation requires at least ten relief civilization-turns and a purchase. League activation requires at least twenty turns with members and a paid claim. Cost-only controls cannot satisfy the purchase/claim component; each comparison selects worlds using its service arm, as frozen in the preregistration. All non-activated worlds remain retained. The means compare each arm on its own relief/member turns, so they include changed enrollment and cannot isolate a fixed-cohort effect.

## Primary outcomes

Both template mechanisms have insufficient activation. Procedural relief has only two activated worlds; following the preregistration, no stratum primary mean, sign count or sign-flip summary is reported. Individual observations are retained: 3801 had zero RS−RC short person-turn-rate difference and zero RS−R0 commons membership-rate difference; 3805 had −0.440126 short person-turns per relief-region-turn and +5.441442 commons members per 1,000 recorded relief-realm residents. These two observations do not establish relief efficacy. The denominator is recorded aggregate residents, not native adult person-turns.

For procedural guild claims, mean member civic purse GM−GD was **−0.164888**, range **[−1.617, +0.2036]**, with five positive worlds and one negative. The descriptive exact sign-flip count was **64/64** assignments at least as extreme; this is not a significance test or a benefit finding. Civic purses are rounded to 0.1 in snapshots.

| Procedural seed | Member civic purse GM−GD |
| --- | ---: |
| 3801 | +0.08276900 |
| 3802 | +0.20364706 |
| 3803 | +0.13722467 |
| 3804 | +0.01684866 |
| 3805 | -1.61705658 |
| 3806 | +0.18723810 |

## Mechanism and cost observations

Across all twelve service worlds, relief made six purchases of 2.454 food units and credited 2.869 wealth units to actual owners. Funds received 97 treasury units and returned 23; 1,211 upkeep units were sunk outside the fund as designed. Purchases used existing stock and keyed actual payments. The upper delivery total on activated worlds was 4.908 rations; this is an upper bound, not measured individual consumption.

Across all twelve guild mutual worlds, 571 claims paid 41.622 units from 250.884 units of dues; 159.703 units were returned and zero unclaimed units were recorded. The dues-only arm paid no claims and collected 217.237 units of dues, with 146.502 returned. The arms can diverge in membership and lifespan, so their dues totals are not an equal-enrollment comparison.

**Invalidated historical lower-delivery estimates:** frozen source estimated a lower bound after a short commons pool and zero total cap overflow. Independent review established that the native food ledger exposes net transport, which cannot prove prior relief stayed through gross exports. Original held metrics and bundles remain unchanged. Every historical `delivered_lower`/`lower_unknown` value is unverified; none is efficacy evidence. The corrected candidate emits `delivered_at_least: null`, preserves only the valid upper bound, and suppresses historical positive lower estimates in the viewer and region aggregates with a reason. Its extractor separates the historical estimate from established delivery. No preregistered primary uses this estimate; the correction changes observation only, with provisioning, money, needs and decisions unchanged.

## Harm panel

The table retains per-world GM−GD differences across activated procedural worlds. Relief has fewer than three activated worlds; its raw per-world harm observations remain in the original metrics rather than being summarized as a supported effect. Template effects remain unavailable through non-activation.

| Recorded harm | 3801 | 3802 | 3803 | 3804 | 3805 | 3806 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Final population | +0 | +0 | +0 | +1 | +16 | +0 |
| Final all-realm treasury | +0 | +0 | +0 | -463 | +633 | +0 |
| Run food shortfall | +0 | +0 | +0 | +1134.46 | +281.674 | +0 |
| Priced-out person-turns | +0 | +0 | +0 | -3 | -103 | +0 |
| Priced-out child-turns | +0 | +0 | +0 | +7 | -34 | +0 |
| Epidemic authority deaths | +0 | +0 | +0 | -84 | -25 | +0 |
| Migration events | +0 | +0 | +0 | +498 | -119 | +0 |
| Final mean living-realm wealth Gini | +0 | +0 | +0 | -0.0426227 | -0.0975328 | +0 |

Adverse outcomes include lower average member purse, higher food shortfall on 3804/3805, and mixed treasury and migration changes. The screen supports mechanism/closure evaluation with low relief reach, not default promotion.

Famine and war deaths are explicitly unavailable to this historical slice extractor, not zero. Forest stock was not enabled. Exact owner wealth, guild wall help, separate commons rising/secession effects, claim city-history tuples, and per-reason reform/league event effects were not measured in this compact extractor. Runtime claim matching and fund closure were tested; no omitted measure is inferred from those checks. War deaths must use the later reviewed casualty authority, avoiding the known default-path natural-death attribution issue.

## Reproduction

At frozen `808726b8`, with a verified native environment for that source and the retained authoritative registry reservation:

```sh
PYTHONPATH=src PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 /path/to/native/python scripts/cw_d1_screen.py run output/cw6d1-pilot --screen CW6D1 --cohort pilot --jobs 1
PYTHONPATH=src PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 /path/to/native/python scripts/cw_d1_screen.py run output/cw6d1-held --screen CW6D1 --cohort held --pilot output/cw6d1-pilot/metrics.jsonl --jobs 1
```

The recorded held cohorts are now used. These are reproduction commands, not authorization to consume any fresh held cohort or rerun qualification. For inspection without simulation, read the retained metrics directly; the generic raw report prints summaries below the frozen activation minimum and must not override this evaluation.
