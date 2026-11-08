## 29 Roadmap versus reality and evaluation results
**Map**
- Roadmaps read: Phase 7 (M48–M61b, `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`), Phase 8 governance (M63–M67), Phase 8–9 horizon (M68–M73, brainstorm), connected-world A–E, system-expansion (Oct), productive recovery, recovery-skills, livelihoods sprints 1–2, and the rework and final reports.
- Code: `src/chronicler/` is 151k lines of top-level Python. `main.py` `_build_parser()` exposes 236 long options, 68 of them `BooleanOptionalAction` switches (counted by importing the parser).
- Default-on for new worlds: 16 modules set `DEFAULT_ENABLED_FOR_NEW_WORLDS = True`, including `governance_runtime.py:87`, `epidemiology.py`, `contact_ledger.py`, `cities.py`, `diplomacy.py`, `finance.py`, `guilds.py`, `maritime.py`, `nomads.py`, `techniques.py`, `experimental/fisheries.py`. `--campaigns` is also default on (`main.py:2152-2155`).
- Default-off: the whole connected-world, livelihoods, recovery-skills and productive-recovery set. `feature_catalog.py` docstring: "Nothing here is on by default." Also off: `health_care.py:14`, `harvest_forecasts.py:20`, `ritual_gatherings.py:27`, `scientific_claims.py:21`, `scholarship.py:69`, `grain_reserves.py:97`, `refugee_routing.py:15`.
- Config layer: 59 `*_state.py` files, 57 with a matching module.

**(a) Roadmap delta**

| Planned item | Status | Evidence |
|---|---|---|
| M48 memory, Mule promotions | built | `chronicler-agents/src/memory.rs`; `agent_bridge.py:96-98` |
| M49 needs, M50 relationships | built | `needs.rs`, `relationships.rs` |
| M51 multi-generational memory | unverified | only ancestry/home-bond hooks in `migration_drivers.rs:33` |
| M52 artifacts | built (Python only) | `src/chronicler/artifacts.py` |
| M54 Rust ecology/economy/politics | built | `ecology.rs`, `economy.rs`, `politics.rs` |
| M55a spatial substrate | built | `chronicler-agents/src/spatial.rs` |
| M55b spatial asabiya | missing | `simulation.py:753-758` applies a civ-wide delta to every region; no per-region term |
| Morton/NUMA sort (amendment thread 3) | partial, profiling only | `spatial.rs:1363-1368` computes the Morton order and discards it; NUMA has 0 hits |
| M56 settlements/urban | built | `settlements.py`; `settlement_ids` used at `conversion_tick.rs:95`, `movements.rs:366` |
| M57a marriage | built | `formation.rs` (`marriages_formed`, `MARRIAGE_CADENCE`) |
| M57b households/inheritance | partial | `household.rs`; spouse pairs `residence_ledger.py:794-806`; inheritance unverified |
| M58 merchants/trade | built | `merchant.rs`, `contact_ledger.py` |
| M59a information packets | built (Rust) | `knowledge.rs` |
| M59b perception-coupled behaviour | unverified | not searched beyond names |
| M60 campaigns/battles/occupation | built, default on | `campaign_logistics.py`, `war/` |
| M61a scale harness | built | `scale.rs` |
| M61b 500K–1M validation and calibration | missing | `phase-6-progress.md:3911` "CALIBRATE M61b" constants; largest measured native peak 53,138 agents (`connected-world-final-report.md`, V11); 200-seed sweep unrun |
| Phase 7.5 viewer / bundle v2 | built | `viewer/src/lib/bundleV2.ts` |
| M63a/b institutions, weight cap | built, default on | `institutions.py`, `governance_runtime.py`. Per-system ceilings not built: one 1.5× governance bucket (`governance_runtime.py:16`); global 2.5× still clamps (`docs/governance/runtime-integration.md:175`) |
| M64 commons and exploitation | missing | `governance_measurements.py:902-908`: "no M64 commons kernel exists". `commons_rules.py` is a livelihoods rule, not M64 |
| M65a/b elite, EMP, PSI, secular cycle | built, default on | `elite_metrics.py`; `governance_runtime.py:1271-1352` |
| M66a/b legitimacy, ambitions | built, default on | `governance_capital.py`, `ruler_ambitions.py` |
| M67 governance tuning gate | missing (blocked) | `docs/governance/m67-readiness.md`: "M67 acceptance is not qualified, and M67 remains blocked" |
| M68 traits/memome | built-but-default-off, demo only | `memome_experiment.py:1-10` "Detached M68a demonstration" |
| M69 prestige goods, patronage, product space | missing | no code hits for gift-debt, patronage or product space |
| M70 revolution cascades | missing | no threshold-cascade code; revolts only via PSI (`governance_runtime.py:250`) |
| M71 information asymmetry | partial | `intelligence.py` (M24 layer); beliefs/decay/deception absent |
| M72 culture tuning | missing | none |
| M73 Phase 8–9 viewer | partial | PSI references in `viewer/src/lib/systems.ts`; not checked further |
| Connected-world A–E | built, default-off, bounded screens only | `connected-world-final-report.md`; ports have no consumer; owned cross-border wares unimplemented |
| System-expansion 1, 2, 3, 5, 6 (impairment, warnings, gatherings, payroll, claims) | built-but-default-off | `health_care.py:1`, `harvest_forecasts.py`, `ritual_gatherings.py`, `workshop_payroll.py`, `scientific_claims.py` |
| System-expansion 4 prime movers, fodder | missing | 0 hits |
| System-expansion 7 grain measures | partial | `grain_*.py`; interoperability unverified |
| System-expansion 8 contingent loss cover | missing | only a disclaimer, `transaction_receipts.py:3` |
| System-expansion 9 domesticates | missing (audit only) | `expansion_audit.py`; 0 Rust hits |
| Recovery-skills RS1–RS5 | built-but-default-off | `apprenticeship.py`, `repair_projects.py`, `veteran_reintegration.py`, `remittances.py`, `clearing_protection.py` |
| Livelihoods L1–L9 | built-but-default-off | `workshops.py`, `food_allocation.py`, `timber_stock.py`, `grain_convoys.py`, `workshop_payroll.py`, `commons_rules.py`, `local_budgets.py`, `learning_cohorts.py`, `relocation_costs.py` |
| Productive recovery PL1–PL6 | built-but-default-off | `timber_supply.py`, `household_retail.py`, `apprenticeship.py` |

**Findings**
1. [high] sim-depth/docs: Governance (M63–M66, PSI) is default on for every new world, but its gate M67 is blocked and unqualified. The default-on system has no calibration evidence. `governance_runtime.py:87`; `m67-readiness.md`.
2. [high] bug: Four default-path decisions read causal provenance, against the stated contract. These are `cities._lord_change`, `diplomacy._aid_convoys`, `epidemiology._reports` and `nomads._herds`. Natural deaths are booked as army casualties (about 17% of soldier deaths). Merchant income is paid to the current region, not the origin. `connected-world-program.md:410-422`; `docs/integration/causal-provenance.md`.
3. [high] Adverse: connected-world full configuration (CWR1 fresh, 144 runs, held) raised regional food shortfall in 11 of 12 worlds and recorded epidemic deaths in 9. Historical CW6 was adverse in 12 of 12 on both measures (+1110 and +1255 food; +22 and +151 deaths). Personal person-turns also rose. `connected-world-rework-report.md:73-100, 180-190`.
4. [high] Null/harm: CW4 quarantine (trade closure) was null on both primaries. Harms: forgone route income, merchant unwinds, and food shortfall after relief rising in 10 of 12 worlds. `connected-world-program.md:370-380`. Implication: quarantine as modelled is not a lever.
5. [med] Trade-off: CW5c care lowered the epidemic death rate in 6 of 6 template worlds. It raised food shortfall in 5 of 6, from more survivors. Care and food need one welfare metric, not separate primaries.
6. [med] Wages (CW1): at fixed enrollment, wages raised household money credited in every activated world. Wider enrollment lowered it, mainly through replaced farm income (59% template, 86% procedural). The priced-out effect was null. Implication: the wage is not the lever; substitution is.
7. [med] Floor-means food relief worsened the poorer half's shortfall in 12/12 worlds. Targeted relief reversed it in 12/12. `phase-6-progress.md:112` (livelihoods sprint 1 screen). Implication: universal floors are the wrong instrument.
8. [med] Livelihoods bind on teaching seats and inputs, not wages. Learners rarely complete. Workshops add only 5–12% crafts. Budgets cut workshop output in 12/12 worlds for little relief. Commons rules cut extraction in 5/6 worlds, but clearing stays 10–20× harvest.
9. [med] Recovery-skills: veteran priority is null. Apprenticeship completions are 3.3 and 0.8 per world. Remittance fees are 163–204 against 926–1161 credited. `recovery-skills-phase.md:345-380`.
10. [med] Watershed protection (CW3): upstream clearing protection did not change downstream water or food. Its cost alone raised downstream shortfall in 6 of 6 worlds. Cost and benefit were not held equal.
11. [med] Attribution defect (fixed by opt-in): unknown displacement reason became a 1.25 susceptibility multiplier. Unknown was thereby treated as risk. Explicit `density_only` removes it. `connected-world-rework-report.md:35-50`.
12. [med] Health: procedural raw deaths were +2.8 against cost-only care. Arrivals were +20.8 against shuffled reports. `connected-world-final-report.md`.

**(b) Design implications.** Adverse results recur in food shortfall and epidemic deaths. Null results show that interventions act through substitution (farm income, household money), not their intended channel. Next designs should measure household access and welfare, not regional availability. Each subsystem's cost must be paired with its benefit under equal cost.

**(c) Grand features never landed.** M55b spatial asabiya (frontier overextension); M61b 500K–1M scale; M64 commons exploitation and the elite-commons amplifier; M67 gate; M69 prestige goods and patronage; M70 revolution cascades (the M59a channel is already built); M71 beliefs and deception; M72 culture tuning; NUMA; ports as a service; domesticates and pastoral herds; prime movers and fodder; contingent loss cover and private cargo title; procedural scenarios and continuous terrain (deferred).

**(d) Next-lead priorities, in order**
1. Qualify or default-off governance (PSI, M67). It is on by default with no gate. Owner decision needed.
2. Fix the four default-path provenance reads and the army-casualty booking. Correctness precedes depth.
3. Add household welfare and access measures before any new subsystem. The food-versus-care trade-off cannot be judged without them.
4. Close core depth gaps cheaply: M55b spatial asabiya (amendments rate it highest payoff), M64 commons, and M70 on the existing M59a channel.
5. Consolidate (section e) before adding, so evaluated behaviour is kept and held identities stay valid.
6. Scale: real M61b validation beyond 53k agents. Either make the Morton order real or delete the discarded sort.
7. Breadth last: ports, domesticates, insurance and prime movers should wait until a held primary is positive.

**(e) Consolidation candidates** — see the table below.

**Simulation depth**
- Give M55b a per-region asabiya term from the existing four-line arithmetic; this gives overextension and frontier vigour.
- Make the Morton order (`spatial.rs:1363`) feed an iteration and measure it, or drop it.
- Add household access and welfare outcomes to the connected-world primaries, using `food_allocation.py` rations.
- Implement M70 on `knowledge.rs` packets (the roadmap already requires one diffusion channel).

**Confidence** Verified by grep, file reads and an import of `_build_parser()` (236 options, 68 switches, 16 default-on modules). Inferred from roadmap text where marked `unverified`. No tests, builds or simulations were run.

**Streamlining candidates**

| Candidate (path or symbol) | Action (delete / merge into X / extract / rewrite) | Lines saved (approx) | Breaks or blocks (tests, pins, CLI flags, saved-bundle compat) | Risk (low/med/high) |
|---|---|---|---|---|
| `chronicler-agents/src/spatial.rs:1363-1368` discarded Morton sort, plus `scale.rs:57`, `ffi/mod.rs:1146`, `sort.rs` Morton helper | rewrite (make the order used) or delete | ~60 | `tests/test_rust_turn_speed.py` uses `profile_spatial_sort`; FFI `set_spatial_sort_profiling`; M61b evidence | med |
| 57 `*_state.py` / module pairs | merge the small pairs | unverified | Checkpoints and saved bundles load state modules; breaks compatibility without a shim | high |
| Upkeep group: `maintenance_obligation`, `operating_wear`, `infrastructure_condition`, `repair_projects`, `recovery_crews`, `infrastructure_crews` (+ state) | merge into one condition ledger, with repair as an action | ~1–2k of 6.9k | Six CLI switches (`--maintenance-obligation`, `--operating-wear`, `--infrastructure-condition`, `--repair-projects`, `--recovery-crews`); feature catalog requirements; RS2 held evidence | high |
| Care group: `health_care`, `epidemic_care`, `public_health`, `quarantine_rules` (+ state) | merge into one health-response module with channels | unverified | Named switches; CW4/CW5c evaluated arithmetic (uniform 0.3 × coverage); identity runs must be redone | high |
| Teaching group: `learning_cohorts`, `learning_services`, `apprenticeship`, `scholarship` (+ state) | merge `learning_services` into `apprenticeship` (L5 notes "crew-taught apprentices" as the next step) | unverified | `--learning-cohorts`, `--apprenticeship`, `--scholarship` flags; RS1 evidence | med |
| Transfer family: `remittances`, `relocation_costs`, `local_budgets`, `domestic_credit` | extract a shared transfer-with-fee primitive over `wealth_transfer.rs` | unverified | Each has a switch and a native seam; receipts depend on exact transaction shape | med |
| Food/forest family: `timber_stock`, `timber_supply`, `timber_orders`, `harvest_cover`, `clearing_protection`, `commons_rules` | merge into one forest-stock module | unverified | Six switches; timber cap and quota evidence (L1, L8, PL1) | high |

Not a candidate: `MARRIAGE_CADENCE` (`agent.rs:145`) is used by `formation.rs:606`, so it is not dead code.
