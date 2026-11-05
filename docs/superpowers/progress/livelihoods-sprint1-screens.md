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
