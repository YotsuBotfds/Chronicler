# Livelihoods sprint 1: preregistered screens (L11)

Written 2026-11-05, before any held-cohort run was inspected. These are
bounded screens of a default-off experimental source, not powered scientific
validation. The 200-seed and procedural qualification gates remain out of
scope and unrun. The independent units are worlds (seeds), not agents or
turns.

## Fixed source and budget

- Source: the combined integration branch at the commit recorded with the
  results, with the native extension built from that same commit (SHA-256
  recorded).
- Budget, frozen in the plan's section 6: 1.5 core-hours in total, at most
  3 concurrent processes, ≤ 4 GiB transient disk. Raw outputs are deleted
  after metric extraction; the example worlds are kept outside the repo.
- Development cohort, used for debugging and inspected freely: template
  seeds 1–3.
- Held cohort, frozen now: template (8 regions, 4 civs) seeds 101–106 and
  procedural (32 regions, 10 civs) seeds 201–206. Hybrid agents, 200 turns,
  every arm on the common base `--grain-reserves --public-grain-shipments`,
  so one off arm serves every comparison. If the budget runs out, the
  unfinished strata are reported as incomplete; they are not dropped
  silently.

## Arms

| Arm | Flags added to the base |
| --- | --- |
| off | none |
| L1 operate | `--workshops` |
| L1 cost-only (ablation: costs and asset kept, no work replacement) | `--workshops --workshop-mode cost_only` |
| L2 floor_means | `--food-allocation` |
| L2 targeted_relief | `--food-allocation --food-allocation-regime targeted_relief` |
| L3 timber stock | `--timber-stock` |
| L3 ablation (accounting kept, no cap) | `--timber-stock` plus tuning `livelihoods.timber.enforce_cap: 0` |
| L4 convoys | `--grain-convoys` |
| I1 work × food allocation | `--workshops --food-allocation` |
| I2 timber use × workshop demand | `--workshops --timber-stock` |
| I3 convoy disruption × relief release | `--grain-convoys --food-allocation --food-allocation-regime targeted_relief` |
| all in sprint | all four switches, defaults |

The L2 `equal` regime is an identity control. It has already been shown to
reproduce the off trajectory snapshot for snapshot (native test), so it is
not rerun as a screen arm.

## Outcomes (per world, compared with the same world's off arm)

- **Activation funnel** for each package: eligible opportunities, attempted
  decisions, committed resources, delivery, consumer action. Examples: sites
  selected → funded operating site-turns → crew work realized → craft output
  in site regions; scarce region-turns → people allocated → shortfall by
  household-means half; timber slots → turns the cap bound → extraction
  withheld; convoys dispatched → delivered, captured, lost or returned.
- **Primary outcomes.**
  - L1: craft output in site regions, and treasury spent as a public cost.
  - L2: shortfall person-rations for the poorer half versus the richer half.
  - L3: closing timber stock and extraction relative to the ablation arm.
  - L4: grain delivered versus lost or captured.
- **Shared outcomes:** final total population and total treasury, plus the
  mean of each per-world paired difference with its range across worlds.
- **Adverse outcomes, always reported:**
  - L1: idle and unfunded site-turns, and craft output lost to zero ceilings
    during construction.
  - L2: worse shortfall for the poorer half.
  - L3: no change at all (null activation).
  - L4: wasted escort, and cargo lost after payment.
- **Stopping rules.** Every arm runs once per held world; nothing is tuned
  after held outcomes are inspected. A run that raises is recorded as
  failed, with its error, and not rerun silently.

## Results (held cohort, run 2026-11-05)

Artifacts in the repository: per-world metrics
(`livelihoods-sprint1-screens/metrics.jsonl`, one row per arm and world), the generated summary
(`livelihoods-sprint1-screens/report.md`) and source identity (`livelihoods-sprint1-screens/source.txt`).
Rerun or re-summarize with `scripts/livelihoods_screens.py`. Raw bundles are not committed;
they can be reproduced from the fixed seeds.

- **Source and environment.** Source `7674aa965fbda59cb797aff7d1b061ecd64412e9`. The native extension
  (SHA-256 `f820ff2f28583a9c76e96e1bae494ce0d022dc8fc1c5f2259dfe41741e33a637`) was built from the
  same native source. Template 8 regions × 4 civs, seeds 101–106; procedural 32 × 10, seeds
  201–206. 200 turns, hybrid, base flags `--grain-reserves --public-grain-shipments`.
- **Execution.** 144 runs (12 arms × 12 worlds), 0 failed, 699 s wall at 3 concurrent
  processes, 0.53 core-hours. Peak RSS was 499 MiB per run, and the kept example worlds take
  396 MB (not committed).
- **Budget.** Together with the development pilots, about 0.6 of the frozen 1.5 core-hours
  was used. No stratum was dropped.

These are screens. Worlds are the units, and there are six per stratum, so the precision is
low. No parameter was tuned after these results were seen.

### Activation and primary outcomes

| Package | Template worlds 101–106 | Procedural worlds 201–206 |
| --- | --- | --- |
| L1 operate | 6/6 worlds operate. Per world: 440 operating site-turns, 24 building, 2 idle. Crew work allocated 432.8, realized 129.8. Site-region craft output 259.6, against 232.6 under cost-only. Treasury paid 1752. | 6/6 operate. Per world: 488 operating site-turns, 37 building, 87 idle (unfunded). Work 496.8 allocated, 182.4 realized. Craft output 364.9 against 346.3. Paid 2316. |
| L1 cost-only (ablation) | Builds and pays (1814 per world), but no work replaces the ceiling. Craft output 232.6. | Paid 2316. Craft output 346.3. |
| L2 floor_means | 536 scarce region-turns per world. Mean shortfall: poorer half 0.476, richer half 0.375 (poorer worse in 6/6 worlds); children 0.462. | 1982 per world. Poorer 0.433, richer 0.328 (6/6); children 0.416. |
| L2 targeted_relief | Relief reaching targeted households: 259 rations per world. Poorer 0.408, richer 0.441 (poorer better in 6/6 worlds). | 324 rations per world. Poorer 0.356, richer 0.380 (6/6). |
| L3 timber stock | The cap binds in 4/6 worlds (8.5 slot-turns per world). Extraction 246.8 per world, against 254.7 in the ablation (−3%). Cover loss is 2118 per world, about 8.6× extraction. | Binds in 6/6 worlds (30 slot-turns). Extraction 1430 against 1493 (−4%). Cover loss 19,407 (13.6×). |
| L3 ablation (accounting, no cap) | Overdraft 6.8 per world. Trajectory identical to off. | Overdraft 27.4 per world. Identical to off. |
| L4 convoys | 247 eligible deficits; 236 under one coin; 17 without budget. 24 dispatched, 24 arrived, 245 grain delivered. 0 captured, lost or escorted. | 965 eligible; 720 under one coin; 263 without budget. 39 dispatched, 37 arrived, 342 grain. 0 captured, lost or escorted. |

### Interactions

- **I1, work × food allocation.** The shortfall gap under floor_means persists:
  template 0.470 vs 0.370, procedural 0.440 vs 0.338. Workshops operate as in L1.
- **I2, timber × workshop.** With the timber cap, workshop site-region craft output is
  240.8 against 259.6 in the template worlds (−7%) and 348.3 against 364.9 in the procedural
  worlds (−5%). Realized crew work is also lower. Timber is the binding input of the
  workshop, as the L1 development run suggested.
- **I3, convoy × targeted relief.** Relief reaches targeted households at the L2 rate
  (239 and 297 rations per world). Convoy deliveries are unchanged (25 and 40 arrivals).
- **All in sprint.** Every package activates, and the shortfall gap matches floor_means.
  One convoy was lost (procedural).

### Paired totals against off

Final population and treasury differences (mean, with range across worlds):

| Arm | Template population | Template treasury | Procedural population | Procedural treasury |
| --- | --- | --- | --- | --- |
| L1 operate | +4.5 [−39, +63] | +175 [−1105, +1976] | −10.5 [−173, +172] | −207 [−1341, +1338] |
| L2 floor_means | −0.7 [−31, +30] | +455 [−795, +1899] | +29.7 [−86, +147] | +268 [−2154, +3852] |
| L2 targeted | +1.2 [−39, +58] | +317 [−536, +2080] | +32.0 [−41, +148] | +488 [−785, +1850] |
| L3 timber | −3.8 [−18, 0] | +217 [−201, +1505] | −31.0 [−125, +18] | −535 [−3290, +920] |
| L4 convoys | +0.8 [−15, +30] | +158 [−340, +1333] | −19.5 [−229, +138] | +89 [−1935, +1755] |
| All | −14.8 [−61, +16] | −293 [−1384, +545] | −9.7 [−200, +176] | +34 [−2130, +1653] |

Every range includes zero. These screens support no claim about aggregate population or treasury
effects; the divergent trajectories are total model effects, not isolated causes.

### Adverse outcomes and limits

- **L1.** Crew ceilings mostly exceed the region's raw inputs, so realized work is a third of
  allocated. Construction turns zero the region's crafting. Procedural payers leave sites idle
  for about 87 site-turns per world.
- **L2.** The default floor_means rule worsens the poorer half's shortfall in every world.
  This is the mechanism's intended distributional consequence, not a welfare improvement.
- **L3.** Cover loss from clearing, cooling, wildfire and succession, not harvest, dominates
  the timber stock. A commons rule acting only on extraction (L8) would have little leverage
  without addressing clearing.
- **L4.** Capture, loss, return and escort occur naturally almost never (one loss). The risk
  mechanics are shown by the offline tests and constructed runs. Activation is limited by the
  existing reserve purchase rules: a whole-coin payment floor and the surplus rule.

### Review corrections (2026-11-05)

- The L4 cost-retaining risk ablation was not run in these screens. The held worlds had
  0 captures, 1 loss and 0 escorts, so they say nothing about the risk edge. That edge is
  shown by constructed offline tests. The ablation key `livelihoods.convoys.threat_scale`
  is added in the review follow-up.
- L3 Python/native parity: not applicable. Only Python owns the stock, the native economy
  applies the cap column, and the Python oracle economy is not used on the hybrid path.
- The L1 downstream effect on learning and repair supplies was not measured here. It moves
  to the sprint-2 screens, which run workshops with academy services.
- Enabled exact-resume evidence:
  `scripts/checkpoint_identity.py run OUT --case hybrid_s42 --ks 10,17,19,21,30,45,59 --jobs 2
  --cli-arg=--grain-reserves --cli-arg=--public-grain-shipments --cli-arg=--workshops
  --cli-arg=--food-allocation --cli-arg=--timber-stock --cli-arg=--grain-convoys`,
  native extension f820ff2f…, source 7674aa9: PASS at all 7 resume points.
