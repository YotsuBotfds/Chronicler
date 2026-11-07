# Audit A6 and the displacement contract: adaptive livelihood decisions; home, location, attachment and displacement

Design-audit lane for Program A6 of the connected-world program and for the lead-owned
displacement contract shared by C2, D3 and A6. Written 2026-11-07. Read-only.

- **Sources read.**
  - `/home/user/Chronicler` at `main` `bac45cb5` (PR #90). `git status` was clean before and after.
  - The A4 branch `origin/claude/cw-a4-titled-trade` at `d5ccd4d6`, fetched and read with
    `git show` (copies of six files in `audit-a6/a4src/`, outside the repository).
  - The C2 lane's uncommitted work in `/home/user/wt/c2-care` (base `bac45cb5`, branch
    `claude/cw-c2-care`, not pushed): `labour_reservations.py`, `epidemic_care.py` and
    `docs/integration/epidemic-care.md` were read in place and not modified.
  - Nothing was edited, staged, switched, committed or built in any checkout.
- **Binding inputs.**
  - The program brief (A6, and the amendment's shared contracts).
  - Plan sections 1–2, 5 and 6 (`docs/superpowers/roadmaps/connected-world-program.md`).
  - AUDIT-A1-A2 §3.3 (`money.py` as the payment seam); AUDIT-A4 §5 (carriers, the `trade`
    reservation).
  - AUDIT-C §4.3, §6.2, §6.3 and §8 (crowding, the C1b gate, C2 carers, one labour
    reservation).
  - AUDIT-D §6, §7.5 and §9 (home, location and attachment; D3 options).
- **What was run.**
  - `scripts/refactor_preflight.py --json` on 58 candidate files, read only (`preflight.json`,
    `preflight2.json`, `preflight-summary.txt`, `preflight2-summary.txt`).
  - Seven short in-process probe runs (9–21 s each) on development worlds template 7 and
    procedural 13, using `~/.venvs/native-a3/bin/python` with `PYTHONPATH=/home/user/Chronicler/src`.
    That extension has main's C1b methods and no A4 methods. Method and commands are in the
    appendix; outputs are in `audit-a6/runs/`.
  - No tests, builds, installs, held seeds or long runs.

Labels: **[code]** read in source (file:line); **[doc]** project documentation; **[probe]**
measured by this lane on one development world, exploratory and not evidence for any screen;
**[inferred]** reasoned, not run; **[unverified]** stated, not checked.

All paths are relative to `/home/user/Chronicler` unless marked `A4:` (the A4 branch) or `C2:`
(the C2 lane worktree).

---

## 0. Answers in brief

1. **People do not choose their own livelihoods from their own experience today** [code]. Three
   per-person native choices exist: migrate, switch occupation and plan a merchant trip.
   - **Migration** scores each neighbour from the tick's current, world-wide region statistics:
     mean satisfaction, food sufficiency, room and peer wealth (`behavior.rs:229-412`,
     `:555-781`).
   - **Occupation switching** reads only regional supply against a target occupation ratio
     (`behavior.rs:479-502`). It never reads earnings.
   - **Merchant trips** are the one place with an anti-omniscience rule: trade packets decide
     which markets a merchant knows (`merchant.rs:1036-1110`).

   Every Python livelihood choice is a **planner's assignment in a fixed order**, never the
   person's choice: workshop, repair, granary, woodcutting and care crews, learners,
   apprentices and A4 carriers. The order is priority lists, then lowest skill or ascending
   stable id (§1).
2. **Failed attempts are recorded but nobody learns from them** [code + probe].
   - A C1b refusal is "refused, not diverted", and "a refused agent decides afresh next tick"
     (`migration_closure.rs:16-26`).
   - On procedural 13 with closure on, 1,504 refusals fell on 656 people; 379 were refused on
     more than one turn and 224 again on the very next turn (one person 10 times) [probe].
   - L7 fare refusals, A4 carrier releases, PL1 drops, L5 and RS1 exits and L6a arrears are all
     recorded per person, and no decision reads them (§3).
3. **Time.** A native migration is decided and applied in the same tick, with no journey
   (`migration_closure.rs:24-26`), and is followed by a 5-turn cooldown (`tick.rs:467`, `:1399`).
   Only merchants (hops), PL1 expeditions (outbound, cutting, return), A4 shipments (one edge a
   turn), L5 cohorts and RS1 apprenticeships take time.
4. **Experienced outcomes that are per person, dated and checkpointed already exist**, but
   scattered and bounded (§4):
   - RS4's diaspora ledger (`remittances_state.py:65-78`);
   - RS1 apprenticeship and qualification records;
   - RS3 veteran records;
   - L6a owed wages by agent (`workshop_payroll_state.py:60-63`);
   - A4 shipments;
   - retail claims;
   - C1b's refused ids, one tick deep (`quarantine_rules.py:515-520`).

   Natively, the pool persists location, birth region, a 5-turn displacement counter, an
   8-slot memory ring and 4 information packets (`pool.rs:1875-1885`). It persists no home, no
   enlistment, no work history and no per-person income.
5. **Native memory cost.** Any new persisted pool field changes the schema fingerprint. Every
   earlier exact checkpoint is then refused, even with `--resume-allow-mismatch`
   (`persist.rs:466-473`), and `pool.rs` carries 8 enforced witness layers. The memory ring has
   reserved type codes but no region field, and writing to it would shift every agent's memory
   satisfaction score. Packets would spread socially and be evicted. **Recommendation: keep the
   A6 memory in Python state and give the native decision a transient per-tick input** (the C1b
   and L7 precedent, `pool.rs:1886-1889`). This needs no schema change.
6. **Paid work against farm work would barely activate today** [probe]:
   - In 675 of 677 PL3 crew person-turns on two worlds, the wage exceeded the ordinary income
     withheld (the other 2 were not observed). The median net gain was +0.48 and +1.60
     wealth units.
   - Workshop payroll (A3 `market`) owed no wages at the end of any Phase 10 on template 7.

   A crew-participation decision would mostly be inert in paid modes.
7. **Proposed A6-1: weight migration destinations by experienced failures, and record crew
   experience only** (§7):
   - **Switch.** `--adaptive-livelihoods` (default off), modes `adapt | record_only | shuffled`,
     `--adaptive-livelihoods-rules 1`, hybrid only.
   - **Authority.** The native migration decision stays the only path. Python holds a dated,
     checkpointed per-person memory: border and fare refusals (exact per person through a small
     native receipt) and destinations left within 10 turns.
   - **Native input.** Before each tick, Python installs bounded per-agent, per-destination
     penalties as a transient input. No new random draws are made; the four Gumbel draws per
     agent are unchanged.
   - **Native build.** One build, batched with D3's native work.
   - **Pinned files.** `tick.rs`, `pool.rs`, `ffi/mod.rs` and `lib.rs` are pinned; `behavior.rs`
     is not.
8. **"Displaced" today means three different things, none of which fits C2 or D3** [code + probe]:
   - native `displacement_turns > 0`, meaning "moved in the last 5 turns" (23–34% of the
     living);
   - `origin_region`, the birth region, never updated (59–73% live away from it);
   - the bridge's `displacement_by_region` share, used by narration only.

   Correction to AUDIT-C §4.3: that share **is** inside exact checkpoints, because the pickled
   bridge keeps it (`agent_bridge.py:3181-3189`). It is undated and absent from legacy state, and
   its meaning is wrong for C2 and D3.
9. **Hybrid worlds churn heavily** [probe]:
   - 53–75% of applied moves are driven by flight terms (memories of famine, battle, conquest or
     persecution; persecution; the safety need).
   - A driver-based displacement ledger marks 48–60% of the living as displaced, and one anchored
     to a famine or war event at home marks 29–52%.
   - Anchored to a war event at home: 0.06–0.9%.

   The contract must carry the cause, so that C2 (physical crowding), D3 (war) and A6 (one's own
   spell) can each select their own subset.
10. **Proposed contract** (§11): a lead-owned, Python-only, record-only `--residence-ledger`.
    - **What it holds.** Per person: home, residence and campaign attachment. Per displacement
      spell: origin, start, cause group, home-region anchor event and closure (`returned`,
      `resettled`, `died` and others).
    - **Writer and dating.** One writer, in the livelihoods Phase 10 hook after
      `reconcile_rosters`, stamped `source_turn = T`. Consumers read T's frame at T+1.
11. **Labour reservation.** The C2 lane already wrote the shared query,
    `labour_reservations.booked()` (`C2:src/chronicler/labour_reservations.py:56-81`). A4
    appended the native `trade` category (`A4:workshop_work.rs`, `RESERVATION_CATEGORIES[4]`).
    - **Gap.** C2's hard-coded category tuple reads A4 carriers as `registry_other`.
    - **Proposal.** Adopt `booked()` as the one rule. Derive the category names from the native
      list, publish the claim order, and have D3's recruitment call it behind its switch (§12).
12. **Screen** (§8):
    - **Arms.** `record_only`, `adapt` and `shuffled`, with C1b closure and L7 fares on in every
      arm.
    - **Primaries.** Repeat refusals, quick departures and displaced person-turns, plus a fixed
      harm panel.
    - **Cohort.** CW6 stays reserved for the S5 integrated evaluation. This lane proposes a fresh
      cohort for the lead: template 3301–3306 and procedural 3401–3406, both free in
      `scripts/seed_registry.json` today.

---

# Part 1 — A6 adaptive livelihood decisions

## 1. Where a livelihood is chosen today [code]

| # | Decision | Authority | Person or region | What it reads | Time | Failed attempts | Record of the outcome (checkpointed?) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | **Migrate** (where to) | native `evaluate_region_decisions_observer` (`behavior.rs:934-1225`), target in `best_migration_target_observed` (`:240-412`) | individual, every tick, each agent not on a merchant trip (`:955-958`) and not in its 5-turn cooldown (`:968-978`) | neighbours' **current** mean satisfaction, food sufficiency, room and capacity (`:126-135`, `:330-334`); river bonus; voluntary pulls (frontier, wage gap from peers' mean wealth, chain to bonded emigrants, urban, learning; `migration_drivers.rs:1-60`, `:230-330`); **dated** threat and religious packets (`:361-381`); memories (famine, battle, conquest, persecution, prosperity, death of kin; `memory.rs:270-324`); needs; household wealth (`:1063-1076`); community anchor | none: decided and applied the same tick (`tick.rs:464-467`), then 5-turn cooldown (`:467`, `:1399`) | household cancellation (spouse rebelling, catastrophe; `household.rs:352-470`); C1b refusal (`migration_closure.rs`); L7 fare short (`relocation.rs:1-33`); liquid reserve gate. **No memory of any of them** | `AgentEvent` type 2 with its driver (not persisted natively); a native diagnostic; `life_events` bit; a `Migration` memory with no destination (`tick.rs:916-925`); RS4 diaspora ledger (opt-in, Python, checkpointed) |
| 2 | **Switch occupation** | native `switch_utility` (`behavior.rs:479-502`), applied at `tick.rs:863-889` | individual | the region's occupation supply against `target_occupation_ratio` (terrain, soil, water, food sufficiency, civ demand shifts; `behavior.rs:648-670`); ambition; a prosperity-memory penalty; the need for purpose | instant; skill floored at 0.3 and promotion progress reset (`tick.rs:866-871`) | none | `AgentEvent` type 3; `life_events` bit |
| 3 | **Native merchant trip** | `merchant.rs` planner (`:1552-1565`), `evaluate_route_packet_aware_with_tally` (`:1060-1110`) | individual | trade packets (dated `source_turn`, hop count, decaying intensity) decide which markets are known; known markets are scored at **current** prices; with no packet the planner falls back to every reachable market (bootstrap) | loading (T), departure (T+1), one hop a tick | cancel, replan, unwind (`RETURNED`), sea raid (AUDIT-A4 §1.2) | optional transaction receipts; trip statistics; packets |
| 4 | **A4 titled trade** (branch) | `A4:titled_trade.py` `_dispatch` (Phase 10, `:696-740`) | individual carriers, chosen in ascending id among eligible resident merchants (`:17-21`, `:720-723`) | owners' surplus and local retail prices; destinations within `MAX_HOPS` at **current** prices ("omniscient, as the native bootstrap", `:63-66`) | one edge a turn; carrier reserved under `trade` every turn | `returned` (conquest, closure, route lost), `released` (carrier migrated, switched occupation, enlisted, went on a trip, other work: `RELEASE_REASONS`, `A4:titled_trade_state.py:59`), escheat on death | `Shipment` by stable id, `TradeRecord` (checkpointed, bounded) |
| 5 | **Workshop crew** (L1, payroll L6a, A3) | native `plan_crews_with_priority` (`workshop_work.rs:175-254`), called at `workshops.py:410-414` | assignment by site | eligibility only: adult urban farmer of the settlement, not on a trip, not enlisted, not booked; priority list (qualified, then veterans, `workshops.py:263-277`), then ascending id | per-turn reservation | firm insolvency cuts hours, crew cap, closure; owed wages (arrears) | firm receipts; `OwedWage{agent_id, amount, since_turn}` (`workshop_payroll_state.py:60-63`, checkpointed) |
| 6 | **RS2 workshop repair and PL3 granary crews** | `recovery_crews.py` (header `:8-66`; exclusions `:238-251`) | assignment | eligibility and RS3 or RS2 priority, then ascending id | per turn | `no_labor`; wage residual at the ceiling; `unpaid` mode | `CrewReceipt.members` with wage and income withheld (last turn only, `recovery_crews_state.py:53-125`) |
| 7 | **PL1 woodcutting expedition** | `timber_supply.py` (`:34-45`) | assignment (veterans first, then ascending id) | eligibility | outbound one hop a turn, `CUT_TURNS`, return | dated drops (died, moved, enlisted, trip, other work); recall; unpaid return-leg turns | expedition records (checkpointed) |
| 8 | **C2 carers** (lane) | `C2:epidemic_care.py:374-447` | assignment, ascending id | `labour_reservations.booked()`, envelope, treasury | per turn | limits `envelope`, `treasury`, `labour` | `CareReceipt` (lane) |
| 9 | **L5 learner** (training) | `learning_cohorts.py:30-49` | assignment: lowest skill first, then id; cohorts are finite | eligibility | cohort duration; attendance each turn | exits `died`, `migrated`, `occupation_changed`, `absent` | cohort records (checkpointed) |
| 10 | **RS1 apprentice** (training) | `apprenticeship.py:44-57` | assignment (veterans first, then ascending id) | eligibility | `COMPLETION_TURNS` attended turns | interruptions and dated endings (`dropout`, `migrated`, `occupation_changed`, `site_closed`, …; `:66-80`) | `Apprenticeship`, `Qualification`, `ServiceRecord` per agent, with `income_forgone` and `stipends` (`apprenticeship_state.py:141-205`, checkpointed) |
| 11 | **Retail enrollment and purchases** | boundary `household_retail.py:9-19`; native provisioning | **regional**, sticky (`market`, `paid_work`, `all`, `schedule`); purchases per household | `paid_work` reads crew and firm history | from the region's opening | priced out, offer short | per-id money rows in the frame (taken once) and a sample bounded at 24 (`provisioning.rs:560-573`, `household_retail_state.py:100`); claims per owner (checkpointed) |
| 12 | **L7 fare gate** | `relocation.rs:1-33` | household gate on native moves | adult movers' liquid wealth | — | `short` (blocked), `assisted` | `HouseholdMove` (from, to, members, reason, `is_return`; bounded 64; `relocation_costs_state.py:50-72`); next-turn `ServiceReceipt` |
| 13 | **C1b closure gate** | `migration_closure.rs` | gate on native moves | closed polity pairs | — | refused (both directions) | rows (origin, destination, driver, persons) and refused ids; Python keeps only `refused_last_tick` (`quarantine_rules.py:515-520`) |
| 14 | **RS3 veteran priority** | `veteran_reintegration.py:1-75` | ordering for planners | release records | `ELIGIBLE_TURNS = 20` | `waiting`, `migrated`, `control_lost` | `VeteranRecord` (checkpointed) |
| 15 | **Army recruitment** | `war/armies.py:120-160` | civ-level draft of individuals | soldiers first, then farmer levies of the polity, by distance; excludes rosters, named characters and registry holders | until release | — | roster `(id, region)` |
| 16 | **Farm work** | none: every farmer farms where they live | — | — | — | — | under retail, title is proportional to food work net of crew time (`household_retail.py:1091-1103`) |

**Consequence.** "Paid work against farm work" and "training" are not decisions anybody makes:
a planner fills seats in id order. Migration is the only native individual livelihood choice
that already exists, has a failure stream and has dated information.

## 2. Omniscient against dated information [code]

- **Omniscient.**
  - Migration's main score uses the destination's current mean satisfaction and food
    sufficiency (`behavior.rs:332`).
  - The wage pull uses the destination's current peer mean wealth (`migration_drivers.rs`
    `PullInputs`).
  - Both are read on the turn of the decision.
- **Already dated and local.**
  - Threat and religious packets: `source_turn`, hops, decay; at most 0.20 and 0.10 of score
    (`behavior.rs:52-58`).
  - Memories with turns and decay.
  - Chain bonds: where bonded emigrants live now.
- **Precedents to reuse.**
  - **Merchants: packets decide which markets are known.** There is no oracle fallback once
    packets exist, but a known market is scored at its current price (`merchant.rs:1096-1110`).
  - **Settlers: an empty destination is judged by home's satisfaction and food**, because
    nothing is known about it (`behavior.rs:138-152`, `:327-333`).
- **A4 declares its destination prices omniscient** (`A4:titled_trade.py:63-66`).
- **Python planners read no experience at all.**

## 3. Time and failed attempts: recorded, and whether the next decision sees them

| Failure | Where recorded | Seen by the person's next decision? |
| --- | --- | --- |
| C1b border refusal | native receipt: aggregated rows (origin, destination, driver, persons) and refused ids (`migration_closure.rs:53-61`); Python keeps only `refused_last_tick` and a "new refusals" count | **no**. The decision is unconstrained and repeats (`migration_closure.rs:16-23`). Probe: 1,504 refusals, 656 people, 379 refused more than once, 224 refused again the next turn [probe] |
| L7 fare short | `HouseholdMove.reason="short"` (bounded 64) | no |
| Household cancellation (rebellion, catastrophe) | counters | no |
| A4 carrier released, cargo returned | shipment outcome and log | no: carriers keep deciding natively because they are not on a native trip (`behavior.rs:955-958` covers native trips only) |
| PL1 member dropped, expedition recalled, unpaid turns | expedition records | no |
| L5 exit, RS1 interruption or ending | dated per person | no |
| L6a owed wage, write-off | `OwedWage` by agent | no |
| Wage refused at the ceiling | money flows (last turn, bounded 512, `money.py:73`), package receipts | no |
| Moved, then left again within a few turns | RS4 ledger (`onward`, `return`) | no. Probe: 1,818 onward moves and 512 returns for 1,114 departures on template 7 [probe] |

## 4. Experienced opportunities and costs: what exists per person

| Datum | Where | Per person | Dated | Checkpointed | Bounded |
| --- | --- | --- | --- | --- | --- |
| Current region, birth region, 5-turn cooldown | `pool.regions`, `origin_regions`, `displacement_turns` (`pool.rs:88-101`) | yes | cooldown only | native exact state | — |
| Memory ring (type, source civ, turn, intensity, decay) | `pool.rs:121-129`; types 12, 13 and 15 reserved (`memory.rs:13-31`) | yes | yes | native | 8 slots, eviction |
| Information packets (type, source region, source turn, intensity, hops, source civ) | `pool.rs:164-171`; types 5–7 free (3-bit type, `knowledge.rs:12-22`, `:55-63`) | yes | yes | native | 4 slots, eviction |
| Skills per occupation | `pool.skills` | yes | no | native | — |
| Wealth (the one balance) | `pool.wealth` | yes | no income history | native | — |
| Diaspora entry (origin, departure, destination, arrival, moves) | `remittances_state.py:65-78` (opt-in RS4) | yes | yes | Python | 2,048 open |
| C1b refused ids | `quarantine_rules.py:515-520` | yes, no destination | one tick | Python | — |
| L7 moves and tracked origins | `relocation_costs_state.py:50-72`, `:126-130` | household | one turn | Python | 64 and 256 |
| Crew wage and income withheld | `CrewMember` (`recovery_crews_state.py:53-70`) | yes | last turn | Python frame | rows |
| Owed wages | `OwedWage` | yes | `since_turn` | Python | per firm |
| Apprenticeship and qualification (attended, interruptions, income forgone, stipends, endings) | `apprenticeship_state.py:141-205` | yes | yes | Python | — |
| Veteran record (cause, release turn, residence, war) | RS3 state | yes | yes | Python | bounded |
| Shipment (holder, carrier, outcome, release reason) | `A4:titled_trade_state.py` | yes | yes | Python | bounded |
| Retail claim; priced out | claims per owner; priced out in a sample of 24 | claims yes, priced out no | — | Python | yes |
| Per-person money of a settled turn | `money.py` flows | yes | last settled turn | Python | 512 |

**What A6 would need that does not exist:** a per-person, dated, checkpointed record of the
destination a refused move aimed at; an "arrived at, left at" history beyond RS4 (which is opt-in
and closes on return); and, for crews, a multi-turn history of net pay per kind of work.

## 5. Native structures that could carry a memory, and the cost [code + inferred]

| Option | Carries | Schema cost | Side effects |
| --- | --- | --- | --- |
| Memory ring, reserved type 12 ("refused by polity", source civ = the refusing polity) | polity-level refusal, dated, decaying | none (arrays already persisted) | evicts another memory from 8 slots; changes `compute_memory_satisfaction_score` (sum of intensities, `memory.rs:328-338`) and so every decision; passes as a legacy memory to children; **no region field** |
| Packet type 5 ("destination experience") | region, turn, intensity | none | packets propagate along bonds (`knowledge.rs:794`) and compete for 4 slots by retention priority; a low-priority type is evicted when slots fill (as `MovementNews` is), so memory would be unreliable; a higher-priority type would evict threat or trade news |
| New persisted pool field | anything | the schema fingerprint changes (`persist.rs:16-24`); every older exact checkpoint is refused even with `--resume-allow-mismatch` (`:466-473`); `pool.rs` has 8 enforced layers | none on behaviour |
| **Transient per-tick input** (C1b, L7, paid-work precedent; `pool.rs:1886-1889`) | whatever Python installs that turn | **none** ("transient fields change neither payload nor schema", `persist.rs:22-24`, `:355-361`) | none; Python owns the memory |

**Recommendation:** Python memory plus a transient native input.

## 6. Probe findings (development worlds; exploratory)

Configurations are listed in the appendix: A = template 7, 200 turns, PL3 crews, RS4 and retail
`all`; B = procedural 13, 120 turns, the same plus C1b closure of trade and migration; C = plain
hybrid plus RS4; D = template 7, workshops, payroll and A3 `market`.

| Measure | template 7 | procedural 13 |
| --- | --- | --- |
| Moved in the last 5 turns (`displacement_turn > 0`), mean share of the living | 0.34 (A) | 0.23 (B) |
| Living away from their birth region | 0.73 (A) | 0.59 (B) |
| Applied moves: flight / voluntary / hunger / other | 2,600 / 264 / 240 / 340 (A) | 2,668 / 1,393 / 361 / 568 (B) |
| RS4 departures / onward moves / returns | 1,114 / 1,818 / 512 (A) | 2,028 / 2,261 / 701 (B) |
| C1b refusals; distinct people; people refused on more than one turn; refused again the next turn; most refusals of one person | — | 1,504; 656; 379; 224; 10 (B) |
| PL3 crew person-turns with wage > income withheld | 166 of 167 (1 not observed), median +0.48 (A) | 509 of 510 (1 not observed), median +1.60 (B) |
| A3/L6a owed wages at the end of Phase 10 | 0 of 408 open firm-turns (D) | — |
| Enlisted person-turns; with the army away from the roster's home region | 0 (no armies) (A) | 609; 423 (69%) (B) |
| Native migrations by agents on an army roster | — | 30 (17 flight-driven) (B) |
| Married pairs living apart (mean of 10-turn samples); with a partner on a merchant trip | 3.8 of 64; ~60% (A) | 27.6 of 219; ~46% (B) |

---

## 7. Proposed first slice A6-1

### 7.1 Scope and why

**The decision: where to migrate.** A6-1 weights migration destinations by the person's own
dated failures.

- It is the only existing individual livelihood choice.
- It has the strongest natural failure streams: repeated C1b refusals, L7 fare refusals, and
  heavy churn of quick onward moves and returns.
- It links directly to the displacement contract.

**Crew experience is recorded, not decided** (record-only in A6-1). The probe shows paid crews
almost never lose money against forgone income, so a crew-participation rule would be inert in
paid modes. A6-1 records, for each named crew member, what a participation rule would have
concluded, which measures activation for A6-2 without changing any crew. Each crew turn's net is
the wage received, minus the income withheld, minus the retail title forgone, with unpaid turns,
owed wages and ceiling residuals noted.

### 7.2 Switch, modes, rules

- **Switch.** `--adaptive-livelihoods` / `--no-adaptive-livelihoods`, a livelihoods package
  (`adaptive_livelihoods.py` and `_state.py`, new). It is appended to `LIVELIHOODS_SWITCHES`
  after `residence_ledger` and before `attribution_records` and `wealth_accounting`, so the
  observers stay last. Today's order is at `livelihoods_state.py:54-62`; C2 inserts
  `epidemic_care` before D2.
- **Modes** (`--adaptive-livelihoods-mode`):
  - `adapt` (default): installs the penalties.
  - `record_only`: the no-adaptation control. It keeps the same memory and computes and records
    the same rows, but installs nothing, so every output except its own record equals the switch
    off. This needs a test.
  - `shuffled`: the signal-destruction control. It installs the same rows with the same
    magnitudes, but each row's destination is replaced by another of the agent's admissible
    neighbours, chosen by `stable_hash_int("a6_shuffle", turn, agent_id, region)`. The number of
    agents affected and the total penalty are kept; the link between experience and destination
    is destroyed. An agent with a single neighbour is unshuffled, and is counted.
- **Rules.** `--adaptive-livelihoods-rules 1`. A saved state keeps its version and mode; a
  change on resume is refused.
- **Catalog.** `REQUIREMENTS["adaptive_livelihoods"] = (_HYBRID, _feature("residence_ledger"))`.
- **Refused combinations:** with an active `--decision-ablation` (a validation experiment would
  confound it) and with the opt-in decision observer, unless A6 exposes its own term to the
  observer (§7.10).

### 7.3 Authority (no duplicate decision path)

- The native migrate decision stays the only decision. A6 adds one term to the destination score
  inside `best_migration_target_observed`, after the religious bias and before the "became best"
  comparison (`behavior.rs:372-392`), and includes it in `adj_score`, as the threat penalty is
  included. The opportunity term therefore sees it too.
- No Python diversion and no second target choice.
- C1b keeps the refusal authority; L7 and the liquid reserve keep the fare authority. A6 never
  blocks or forces a move.

### 7.4 Dated information it may read (local, delayed, experienced)

Rows installed at turn T are built only from memory entries dated T−1 or earlier.

1. **`refused`.** The person's own decided move from region o to region d was refused at T−1,
   by C1b or by an L7 fare short.
   - This must be exact per person. The C1b receipt aggregates persons by route
     (`migration_closure.rs:57-61`), so A6 adds its own native receipt row
     (`id, from, to, gate`) for every consolidated move a gate removed. These are diffed in
     `tick.rs` after the gates (`:811-829`).
   - L7 already has per-household rows; using A6's receipt for both keeps one source.
2. **`left_soon`.** The person arrived at d at turn t1 and left d at t2 (onward or a return),
   with t2 − t1 ≤ `QUICK_LEAVE_TURNS` (10). This is read from the residence ledger's arrival and
   departure turns (§11); A6 keeps no second ledger.
3. Nothing about destinations the person has not experienced. **Not read:** D2 attribution
   records and causal provenance (D2's contract, plan §5.9).

### 7.5 The rule (declared, uncalibrated constants)

- **Penalties on destination d for agent i at T:**
  - `refused`: `P_REFUSED × (1 − (T − t)/W_REFUSED)` for `T − t < W_REFUSED`, with
    `P_REFUSED = 0.20` (the threat penalty's maximum) and `W_REFUSED = 10`.
  - `left_soon`: `P_LEFT × (1 − (T − t2)/W_LEFT)`, with `P_LEFT = 0.15` and `W_LEFT = 20`.
- **Polity-level option (lead decision, open question 2).** A C1b refusal is about a border. The
  `refused` penalty may also apply to every neighbour ruled at T by the refusing polity, as the
  person learns "this border is closed". The default proposed is destination-level, which is the
  strict reading of "experienced".
- **Cap.** The sum per (i, d) is capped at `P_CAP = 0.30`, below the hysteresis of 0.18 plus the
  river bonus of 0.1. Penalties only, no bonuses, in A6-1.
- **Bound.** At most `MAX_ROWS` installed rows per turn (e.g. 16,384; overflow is counted and
  the oldest dropped first).

### 7.6 Time and failure

- Memory ages out (`W_*`). Failures are the input; nothing is remembered forever.
- The native travel time is unchanged: one hop with no journey, a declared boundary.
- The 5-turn cooldown stays: displaced agents do not evaluate migration (`behavior.rs:968-978`),
  so a penalty acts on the next evaluation after the cooldown.

### 7.7 Determinism and randomness

- No random draws in `adapt` or `record_only`. Utilities change; the number of draws does not.
  `gumbel_argmax` draws once per option (`behavior.rs:88-107`), on a per-region, per-turn stream
  (`tick.rs:728-733`, `:752-756`).
- `shuffled` uses its own `stable_hash_int` namespace and no global stream.
- Rows are sorted by (agent id, region), and the parallel region evaluation reads them
  immutably.

### 7.8 State and checkpoint

- **Python** (`world.livelihoods.adaptive_livelihoods`, omitted while absent):
  - `schema_version`, `mode`, `rules`, `last_settled_turn`, `last_installed_turn`;
  - memory rows `{id, kind, region, polity, turn}` (bounded `MAX_MEMORY`, oldest evicted and
    counted);
  - the last frame: rows installed, agents affected, refusals and quick departures observed,
    decisions changed by A6 (native diagnostic), crew experience and would-decline counts;
  - counters and a dated log.
- **Native:** transient input and receipt only, so no schema change.
- An exact resume at a turn boundary carries the Python memory. Nothing is pending natively at
  a boundary.

### 7.9 Refusal of unsupported modes

- Outside `--agents hybrid`: refused at start and on resume, with a clean `LivelihoodsRefusal`
  hint (the RL3 precedent).
- A rebuilt native pool, whose ids now name other people: `on_pool_reset` drops the memory,
  dated.
- A turn the package did not observe (switch off, then on): the memory is closed as
  `unobserved_gap`, the RS4 precedent (`remittances.py:208-214`).
- A legacy JSON resume without hybrid: refused.
- A native extension without the A6 methods: refused when the switch is set.
- A change of mode or rules on resume: refused.

### 7.10 Interactions

- **C1b.** A6 reads refusals and never changes closures or the C1b receipt. Under closure, `adapt`
  should cut repeated refusals and may steer refused people to an open neighbour by their own
  later choice. This is consistent with C1b's "refused, not diverted", because the gate still
  never diverts. The harm lines follow C1b's flight and hunger split.
- **A4 carriers.** A carrier who migrates is released (`A4:titled_trade.py:57-59`). A6 does not
  exempt carriers. A change in churn changes releases, so they are a harm-panel line. Native
  trips stay exempt (`behavior.rs:955-958`).
- **A3, RS, PL1 crews and C2 carers.** Native migration already ends those commitments and the
  packages record dated drops. A6 changes no planner. Crew experience is recorded only.
- **Retail `paid_work` boundary.** A6-1 (migration) does not touch enrollment directly. Any A6-2
  crew rule would change which regions ever had a paid crew, and so `paid_work` enrollment (the
  CW1 lesson). Screens with retail must use `market`, `all` or `schedule`.
- **Residence ledger.** Read only; A6 never writes it.
- **Decision observer and ablations.** The observer reports candidate scores
  (`observer.end_candidate`, `behavior.rs:392`). If A6 lands without its own observer field,
  refuse the combination.
- **Health care, L2 and retail.** Unaffected, except through who lives where.

### 7.11 Native and Python split

- **Native** (one build, batched with D3's native work):
  - a new `adaptive_migration.rs`: `AdaptiveMigrationInput { turn, rows: Vec<(u32, u16, f32)> }`,
    install, check and take, and a receipt
    `{ turn, refused: Vec<(u32, u16, u16, u8 gate)>, changed: u32, rows_used: u32 }`;
  - transient `pool.adaptive_migration` and `pool.adaptive_migration_receipt`;
  - `tick.rs`: check the turn, refuse a stale input, take the input after decisions, and diff the
    removed moves into the receipt;
  - `behavior.rs`: a binary-search lookup and the score term, with a "changed by A6" diagnostic
    on the threat diagnostic's pattern (`:354-371`);
  - FFI `set_adaptive_migration`, `cancel_adaptive_migration`, `take_adaptive_migration_receipt`.
- **Python:**
  - the package (memory, rows, modes, receipt intake, record, viewer record);
  - livelihoods hooks: `before_agent_tick` installs, `after_agent_tick` takes the receipt once,
    `rollback_agent_tick` cancels, `phase10` reads the ledger and updates memory;
  - catalog, CLI and manifest entries;
  - the viewer panel (new files, not `viewer/src/types.ts`, which is pinned).

### 7.12 Files A6-1 would touch, with preflight verdicts (read only)

| File | Preflight verdict | Note |
| --- | --- | --- |
| `chronicler-agents/src/behavior.rs` | references only | the score term |
| `chronicler-agents/src/tick.rs` | **enforced**: 9 layers (academy, crisis, household candidates; l2, l5, l6, l7, pl4, cwc1b) | take the input; refusal diff |
| `chronicler-agents/src/pool.rs` | **enforced**: 8 layers | two transient fields |
| `chronicler-agents/src/ffi/mod.rs` | **enforced**: 16 layers (A4 adds cwa4) | three methods |
| `chronicler-agents/src/lib.rs` | **enforced**: 7 layers | `mod adaptive_migration` |
| `chronicler-agents/src/migration_closure.rs`, `relocation.rs` | references only | untouched if A6 diffs in `tick.rs` |
| `src/chronicler/livelihoods.py`, `livelihoods_state.py`, `feature_catalog.py` | references only | — |
| `src/chronicler/batch_manifest.py` | **enforced**: 24 layers | CLI keys (the lead's integrated layer) |
| `tests/test_batch_manifest.py` | **enforced**: 20 (native shard owner, oracle chunk, witness) | — |
| `scripts/run_python_oracle_checks.py`, `scripts/testing/native_shards_manifest.json` | references only | enroll the new tests in a chunk with headroom |
| `src/chronicler/agent_bridge.py` (6), `main.py` (9), `viewer/src/types.ts` (5) | **enforced** | **avoid**: use the livelihoods hooks, the CLI owned by `livelihoods.py` and new viewer files |
| `src/chronicler/quarantine_rules.py`, `remittances.py`, `relocation_costs.py` | references only | read only; agreement tests |

### 7.13 Tests (minimum)

- **Identity.** Switch off is byte-identical to `bac45cb5` and to `8abc1acb`. `record_only` equals
  the switch off except its record.
- **Native unit tests:**
  - an input for another turn is refused;
  - no draws are consumed: the Gumbel stream position is identical with and without rows;
  - a penalty changes only the agent and destination named;
  - the cap is honoured;
  - the input is cleared after the tick;
  - the refusal receipt lists exactly the moves the C1b and L7 gates removed;
  - a follower's restored action is not counted as a refusal of the follower.
- **Python tests:**
  - memory dating: a row built at T reads nothing dated T;
  - expiry;
  - bound and eviction counted;
  - pool reset and gap closures;
  - mode and rules refusal on resume;
  - `shuffled` keeps row count and total magnitude.
- **Exact resume** of an enabled run across turns that carry memory, with C1b refusals on.
- **Multi-turn consumption** of the transient input (AGENTS.md: transient signals cleared before
  return, checked over several turns).

### 7.14 Later A6 slices (not in A6-1)

- **A6-2: crew participation.** A person declines a crew offer of a given kind when its
  remembered net over the last E turns is at most 0 (unpaid turns, owed wages, a ceiling
  residual, forgone title).
  - It is applied as a filter after `booked()` in the Python planners (PL3, PL1, C2), with a
    decline recorded, which is not a booking.
  - Native-planned workshop crews need a `declined` list in `plan_crews_with_priority`
    (`workshop_work.rs`, unpinned; its FFI is pinned).
  - Start it only if A6-1's record shows activation.
- **A6-3: an information gate for migration.** Destinations are known only through the person's
  own past residence, a bonded person living there, or a dated packet from there. Unknown
  destinations are scored as settlers score empty land. Optionally, a dated return pull home for
  the displaced. This is a larger behavioural change.
- **A6-4: trade.** A4 destinations limited to markets the carrier holds trade packets for (the
  M59b rule), and a per-merchant memory of returned shipments. Python only.

## 8. Screen design (A6-1)

- **Cohort.** CW6 (template 781–786, procedural 881–886) stays reserved for S5's integrated
  evaluation. The lead reserves a fresh cohort for this screen. Proposed: template 3301–3306
  (8×4) and procedural 3401–3406 (32×10). Both are free in `scripts/seed_registry.json` at
  `bac45cb5`: neither appears in the used, development or reserved sets printed by
  `scripts/connected_world_screens.py registry` [probe]. Use the 200-turn template and procedural
  sizes, set from the shared timing pilots (template 5, procedural 19).
- **Common flags (every arm).** `--agents hybrid`; epidemics on (default);
  `--quarantine-mode closure --quarantine-channels trade,migration` (so refusals exist);
  `--relocation-costs` (paid); `--residence-ledger`. Retail stays off, to keep the enrollment
  confound out.
- **Arms.** `record_only` (no-adaptation control), `adapt` and `shuffled` (signal destruction).
  Feature-off is checked by identity, not run as an arm.
- **Primaries.** Paired per world against `record_only`; direction counts per stratum.
  - **P1 repeat refusal.** Refusals per distinct refused person, or the share of refused people
    refused again within 3 turns.
  - **P2 quick departure.** The share of applied moves whose mover leaves that destination
    within 10 turns (from the ledger).
  - **P3 displaced person-turns per 1,000 person-turns** (ledger, flight and hunger spells).
- **Fixed harm panel:**
  - population at the end;
  - deaths per 1,000 person-turns;
  - epidemic deaths per 1,000;
  - cross-polity epidemic arrivals;
  - food shortfall after relief;
  - mean satisfaction;
  - rebellions;
  - refused migrants fleeing war, famine or persecution (C1b flight count);
  - L7 households short and fares paid;
  - merchant unwinds;
  - commitments released by migration (A4, PL1, L5, RS1 where on; `n/a` otherwise).
- **Activation, per world.**
  - `record_only` sees at least 20 C1b refusals.
  - `adapt` installs at least 50 rows and changes at least 1 decision (native diagnostic).
  - Worlds that fail activation are reported, and excluded from direction counts per the
    preregistration.
  - `shuffled` must install the same row count as `adapt` on turn 1, after which the
    trajectories diverge.
- **Validation and ceiling.**
  - Validate the extractors (refusals, ledger spells, quick departures) on development worlds
    first.
  - Compute: about 3 arms × 12 worlds × 10–40 s, roughly 0.25 core-hours; ceiling 0.5 from the
    pilot.
  - Record source, native, extractor and schema identities. Report nulls.

---

# Part 2 — the lead-owned displacement contract

## 9. What exists

### 9.1 Native [code]

- **Fields.**
  - `regions` (physical location).
  - `origin_regions`: set at spawn to the spawn region and never updated (`pool.rs:354`). It
    serves as "home" for exile bonds (`formation.rs:302-336`) and chain migration
    (`migration_drivers.rs:327`).
  - `displacement_turns` (u8): set to 5 on every applied move (`tick.rs:467`), decremented each
    tick (`:1398-1399`). It means "recently moved", whatever the reason.
  - Merchant trips: `trip_origin_region` is home during a trip. `pool.regions` follows the
    transit hop (`merchant.rs:1176-1199`), and the merchant returns home at the end of the
    delivery tick (`:1266-1286`).
- **Snapshot.** The snapshot exposes `region`, `origin_region` and `displacement_turn`
  (`ffi/schema.rs:10-38`). It has no trip origin, no enlistment and no home. `trip_agent_ids()`
  lists the travellers (`wealth_transfer.rs:385-390`).
- **No native enlisted flag.** Soldiers never move natively (AUDIT-D §6). Levies keep the Farmer
  occupation, farm and are titled at home.
- **Persistence.** All of the above is persisted in exact native state (`pool.rs:1875-1885`).
  Gates and receipts are transient.

### 9.2 Python [code]

- **The bridge's `displacement_by_region`.** The share of each region's agents with
  `displacement_turn > 0` (`agent_bridge.py:1368-1373`), recomputed after every agent tick
  (`:1710`) and used only by narration (`main.py:1369`, `narrative.py`).
  - Correction to AUDIT-C §4.3: it is pickled with the bridge in exact checkpoints, because
    `__getstate__` removes only `_CHECKPOINT_DERIVED` (`agent_bridge.py:3181-3189`).
  - It is not in the world state or bundle, is undated, and is cleared when the bridge resets
    (`:3159`).
  - Its meaning (moved in the last 5 turns) is not displacement.
- **Named characters only:** `_origin_regions` and `_departure_turns` for `exile_return` after 30
  turns away (`agent_bridge.py:1277-1278`, `:2385-2420`).
- **RS4 diaspora ledger** (opt-in): one entry per mover by stable id, with origin and departure,
  destination and arrival, and moves. A return or a death closes it. Bounded at 2,048. It is the
  only checkpointed "who left where" record (`remittances.py:1-24`, `:186-260`).
- **L7.** Household moves (`is_return`) and the origins of tracked arrivals for one turn.
- **C1b.** Refused ids, one tick deep.
- **RS3.** Veteran records: release cause, turn, residence, served civ, war.
- **Health care.** Episodes carry `origin_region`, and active episodes follow the patient's
  location (`docs/integration/health-care.md:43-63`).
- **Aggregate refugees.** Famine and overflow refugees exist only when agents do not own the
  population. In hybrid the Rust pool owns it, and Python-side refugee flows are not made
  (`ecology.py:341-345`). In hybrid, a refugee is a native migrant.

### 9.3 Army attachment: home, location, campaign [code + probe]

- **Roster.** The roster entry `(id, region)` holds the native region, refreshed after the tick
  by `reconcile_rosters` (`war/armies.py:406-445`). `Army.region` is the campaign location and
  `Army.home_region` the staging region.
- **Away on campaign.** On procedural 13, 69% of enlisted person-turns had the army in a
  different region from the roster's home [probe].
- **Enlisted agents still migrate natively.** 30 native migrations by agents on a roster in 120
  turns, 17 of them flight-driven [probe]. `reconcile_rosters` silently moves their roster
  region (`armies.py:430`). Nothing native prevents it, because there is no enlisted flag.
- **Recruitment exclusions.** Recruitment excludes rosters, named characters and registry holders
  (`armies.py:135-141`). It does not exclude this turn's health-care patients or caregivers:
  health rows are not in `work_reservations()` (`ffi/mod.rs:409-412`) [inferred].

### 9.4 Family and household links [code + probe]

- **No stored household entities.** Households are derived from marriage bonds and parent ids
  (`household.rs:1-4`).
- **Who follows a migrating lead.** A co-located spouse follows unless on a merchant trip
  (`household.rs:369-380`). An enlisted spouse can follow, since there is no native flag.
- **Separation today.** Separated married pairs are 6% (template 7) and 13% (procedural 13) of
  live pairs, about half because one partner is on a trip [probe].
- **War separation is invisible.** Enlisted spouses stay co-resident natively (37 married
  person-samples with an enlisted spouse, 1 apart) [probe].

### 9.5 Persisted against transient

| Item | Exact checkpoint | Legacy JSON | Dated |
| --- | --- | --- | --- |
| native region, birth region, cooldown, trips | yes (native) | rebuilt | cooldown only |
| bridge displaced share | yes (pickled bridge) | no | no |
| RS4 ledger | yes | yes (world) | yes |
| C1b refused ids | yes | yes | one tick |
| rosters | yes | yes (stale ids possible after a non-exact rebind, AUDIT-D §6) | — |
| migration events with driver | per turn in `world.agent_events_raw` | — | turn |

## 10. How many are "displaced" under each candidate definition [probe]

Configuration C (plain hybrid plus RS4). Means are over the last three quarters of the turns.

| Definition | template 7 | procedural 13 |
| --- | --- | --- |
| native cooldown (`displacement_turn > 0`) | 0.292 | 0.283 |
| away from the birth region | 0.698 | 0.682 |
| spell opened by a flight- or hunger-driven move from home; closes on return, after 20 turns at one residence, or on death | 0.598 | 0.482 |
| the same, flight only | 0.535 | 0.397 |
| the same, and home had a famine or war event in the 5 turns before departure | 0.517 | 0.289 |
| the same, war event only (controller change, occupation, conquest) | **0.0006** | **0.0089** |

- **Spells.** Opened 1,064 / 1,918. Closed by return 389 / 577, resettlement 182 / 346 and death
  429 / 562.
- **Median lengths.** Return 10 turns; resettlement 20 (the threshold); death 13–14.

## 11. Proposed contract

### 11.1 Definitions

- **Residence** `res(i, T)`: the native region after T's agent tick. A merchant on a native trip
  keeps the residence last recorded, since the ledger sees no migration event for a trip. A4
  carriers and PL1 crews do not move natively.
- **Location** `loc(i, T)` (physical): equal to residence, except a native merchant in transit
  (the snapshot region) and an agent on an army roster (`Army.region`). This is record only in
  v1.
- **Attachment** `att(i, T)`: `(army_id, army region)` from the rosters after
  `reconcile_rosters` at T, else none.
- **Home** `home(i)`, dated `home_since`:
  - set to the residence at first observation, and to the birth region for newborns;
  - changes only when a voluntary or unclassified move is applied (a migrant re-homes at once);
  - or when an open spell resettles after `REHOME_TURNS` (20) at one residence;
  - never on enlistment.
- **Displacement spell.** Opened when an applied move leaves home and its driver is in C1b's
  `FLIGHT_DRIVERS` or `HUNGER_DRIVERS` (`quarantine_rules.py:106-113`). A follower carries the
  lead's driver (`behavior.rs:830-838`).
  - Fields: `start`, `origin = home`, `cause ∈ {flight, hunger}`, plus `evacuated` and other
    appended causes later (D3d). `anchor ∈ {war, famine, persecution, none}` is the dated
    home-region event in the `ANCHOR_TURNS` (5) before departure. `moves` counts the moves.
  - **Displaced** = an open spell.
- **Closures:** `returned` (residence equals home after a move), `resettled` (home becomes the
  residence), `died`, `pool_reset`, `unobserved_gap`. **Returned** = a spell closed with
  `returned`.
- **Separated** (D3 consumer, computed by the ledger when asked): a married partner or a
  dependent child's parent alive with a different residence or location, with the cause `trip`,
  `attached`, `displaced` or `migrated`.

### 11.2 Where it is computed: one writer

- **Package.** Python, lead-owned: `residence_ledger.py` and `_state.py` behind
  `--residence-ledger`. It is record-only and changes nothing it observes, on the D2 and A1
  observer pattern.
- **Position.** It is inserted before `adaptive_livelihoods`, `attribution_records` and
  `wealth_accounting`.
- **Inputs, read in the livelihoods `phase10` hook of T**, which runs after `reconcile_rosters`
  (`simulation.py:2399-2402`):
  - T's applied migration events with drivers (`world.agent_events_raw`, the RS4 read,
    `remittances.py:154-164`);
  - the post-tick snapshot and `trip_agent_ids()`;
  - rosters;
  - region state for anchors: controller change against its own previous reading,
    `occupied_by`, `last_conquered_turn == T`, a new `famine_cooldown`, persecution flags.
- **No native change.** Only `apply_migrations` relocates ordinary agents
  (`relocation.rs:24-25`).
- **Late dissolutions.** Army dissolutions at end-of-turn sync are seen at T+1.

### 11.3 Dated persistence; consumers at T+1

- **The frame.** Each frame is stamped `source_turn = T` and holds:
  - open spells, by residence region and by origin;
  - arrivals and departures this turn, by cause and anchor;
  - returns, resettlements and deaths;
  - attached people with the army away from their home region;
  - separations, on demand.
- **State.** Bounded rows by stable id (home, home since, residence since, the last move, open
  spell), checkpointed, and omitted while off.
- **Who reads what, when:**
  - C2 at Phase 1 of T+1 (the epidemic tick) reads the T frame, as C2's capacity is dated
    (`C2:docs/integration/epidemic-care.md:34-44`).
  - D3 at Phase 5 or Phase 10 of T+1.
  - A6 at `before_agent_tick` of T+1.
- **Resume.** An exact resume at the boundary restores it. A legacy resume rebuilds nothing:
  history before the first observation is unknown, not zero (`observed_from` turn).

### 11.4 Readers and what each may read

| Reader | What | Why it is allowed |
| --- | --- | --- |
| C2 crowding | per-region open spells (residence) and this turn's arrivals, dated T | a physical effect on susceptibility, not a decision. Lead to decide stock against flow: the stock is high everywhere (§10) |
| D3 | spells with `anchor == war`, attachment, separation, returns; RS3 releases for the enlisted | its own events (evacuation, release, return) arrive as native moves or RS3 records, never as ledger writes |
| A6 | the person's own row: arrival and departure turns, spell | one's own experience |
| C4 and other ruler decisions | aggregated counts dated T only | dated reports, no per-person truth |
| viewer, narration | records | no causal invention |

D2 records and causal provenance stay unreadable by decisions.

### 11.5 Relation to existing records

- **RS4 keeps its own diaspora ledger.** Its outputs are untouched. A test checks that RS4's
  `origin` and closures agree with the ledger's home and returns when both are on (the
  `booked()` and `recovery_crews._excluded` precedent).
- **The bridge share stays narration-only.** No consumer may switch to it.
- **The native cooldown and birth region stay as they are** on the default path.

## 12. The one labour reservation rule

### 12.1 What exists [code]

- **The native registry** (`workshop_work.rs:56-116`) refuses anyone already holding registry
  work, positive rural health work loss or an unconsumed teaching plan. The reservation is all
  or none, one per person per turn, and cleared after the tick (`pool.rs:199-201`).
  - Categories on main: `workshop`, `learning`, `apprentice`, `repair`.
  - A4 appends `trade` (4), with `trade_holders` and the static FFI
    `work_reservation_categories` (`A4:workshop_work.rs`, `A4:ffi/mod.rs`).
- **The C2 lane's `labour_reservations.booked(world, sim, turn)`**
  (`C2:src/chronicler/labour_reservations.py:56-81`). It is read-only and gives the first reason
  in a fixed order: health patient, health caregiver, `registry_<category>` or
  `registry_other`, trip, enlisted, RS1 mentor.
  - It is equal to `recovery_crews._excluded`, which PL3 keeps, and a test checks the agreement.
  - C2 carers are reserved under `repair` (`C2:epidemic_care.py:85-87`, `:447`).
- **A4 does not call `booked()`** [code]:
  - Carriers are reserved in `reserve_first`, and a refused reservation releases the carrier
    (`other_work`).
  - Dispatch eligibility in Phase 10 excludes trips, rosters and own shipments.
  - In Phase 10 the registry and the health rows are already empty.
- **Recruitment** (Phase 5) excludes registry holders only.

### 12.2 The rule (proposed)

1. **One work commitment per person per turn.** It is enforced by the native registry, with health
   rows counted after `prepare_health_care`.
2. **Every Python planner that names people calls `booked()` before naming anyone.**
   - The categories come from `sim.work_reservation_categories()` (A4's method), with a fallback
     to the tuple for older builds, so `trade` is named.
   - Reasons are strings, append-only, and never persisted as indices. C2 stores none; it uses
     the set.
3. **Claims are served in phase order; no later consumer displaces an earlier one.** Each
   refusal is recorded by the consumer.

   | Order | Claims |
   | --- | --- |
   | 1 | health care (patients and spouse or kin caregivers; D3's wounded soldiers through combat episodes appended in Phase 10 of the previous turn, AUDIT-D §6) |
   | 2 | `reserve_first`: multi-turn holdings (PL1 crews, A4 carriers) |
   | 3 | `prepare_phase2` in `LIVELIHOODS_SWITCHES` order (L1 and A3 crews, RS1, RS2, PL3, …, C2 carers) |
   | 4 | campaigns: recruitment, which should call `booked()` behind D3's switch; the default path is unchanged |
   | 5 | `before_agent_tick` (L5 learners) |
   | 6 | the teaching plan |

4. **Validity window.** `booked()` is meaningful between `prepare_health_care` and the agent tick.
   A Phase 10 planner (A4 dispatch, a D3 episode append) books at the next turn's `reserve_first`
   or prepare, where the registry enforces the rule.
5. **The displaced are ordinary residents where they live.** The attached are excluded
   everywhere, as today. **An A6 decline is not a booking.**

### 12.3 Reconciliation items

- **(a)** When C2 and A4 both merge, `REGISTRY_CATEGORIES` must include `trade`, or be read from
  the native list. Otherwise carriers show as `registry_other`: still excluded, but mislabelled.
- **(b)** C2 carers under `repair` cannot be told apart from RS2 or PL3 crews in the registry.
  Either accept attribution through C2's receipts, or append a `care` category in the next native
  batch. That is needed only if D3 caregivers must be visible in the registry, and they are not:
  they are health-care rows.
- **(c)** Recruitment's missing health exclusion is a D3 item, behind D3's switch.
- **(d)** `labour_reservations.py` becomes lead-owned at integration. The C2 lane's file is the
  starting point.

---

## 13. Decisions proposed for the lead

1. **A6-1 decision scope:** migration destination weighting from the person's dated failures
   (C1b and L7 refusals, quick departures); crew experience recorded only. A6-2 (crews), A6-3
   (information gate, return pull) and A6-4 (A4 trade packets) come later.
2. **Memory in Python state and a transient native input.** No persisted native field and no
   schema change.
3. **Switch:** `--adaptive-livelihoods`, modes `adapt|record_only|shuffled`, rules 1, hybrid
   only. It requires `--residence-ledger`. It is refused with decision ablations, and with the
   decision observer unless A6 exposes its own term.
4. **Native receipt:** an exact refused-move row per person (`id, from, to, gate`), diffed in
   `tick.rs`. C1b's receipt and FFI are not changed.
5. **One native build** for A6-1 together with D3's native parts. The lead writes the witness
   layers for `tick.rs`, `pool.rs`, `ffi/mod.rs`, `lib.rs` and `batch_manifest.py`.
6. **The displacement contract** is `--residence-ledger`: lead-owned, Python-only, record-only,
   written in the livelihoods `phase10` hook after `reconcile_rosters`, and stamped
   `source_turn = T`.
7. **Displaced** = an open spell opened by a flight- or hunger-driven move from home, with
   `cause` and `anchor`. Consumers filter: C2 takes every spell, D3 takes `anchor == war`, A6
   takes the person's own. Declared constants: `REHOME_TURNS = 20`, `ANCHOR_TURNS = 5`.
8. **Labour:** adopt C2's `booked()` as the shared query, with the category names from native
   and the published claim order. Recruitment adopts it behind D3's switch.
9. **Correct AUDIT-C §4.3** in the plan: the bridge's displaced share is in exact checkpoints, but
   it is undated and has the wrong meaning. No consumer may use it.
10. **A6-1 screen cohort:** template 3301–3306 and procedural 3401–3406, reserved in the registry
    before any run. CW6 stays for the S5 integrated evaluation.

## 14. Open questions (lead or owner)

1. Does a voluntary migrant re-home at once (as proposed), or after settling? This changes D3's
   meaning of "return".
2. A C1b refusal penalty: destination-level only (strictly experienced), or every neighbour of
   the refusing polity ("the border is closed")?
3. Should L7 fare refusals count as destination failures? The cause is money, not the place.
4. **A native commitment exemption.** Should people holding multi-turn Python commitments
   (A4 carriers, PL1 crews, RS1 and L5) be exempt from native migration and switching, as native
   trips are (`behavior.rs:955-958`)? It would change A4 and PL1 outputs, so it needs a rules
   version. It is an A6 or D3 question.
5. **Enlisted agents migrate natively** (30 in 120 turns [probe]). Should attachment block native
   migration (D3, needs a native input), or should the ledger record it as desertion-like
   movement?
6. **C2 crowding:** use the stock of open spells (high everywhere: 29–60%) or this turn's
   arrivals?
7. **The baseline churn:** 53–75% of moves are flight-driven, and people are refused up to 10
   times in a row. Record it for the owner as a possible calibration question on the default
   migration model? This lane recommends recording it, not changing it.
8. Is family separation computed every turn by the ledger (a relationship read each turn), or
   only when D3 is on?

## 15. Pins (preflight, read only; `audit-a6/preflight-summary.txt`, `preflight2-summary.txt`)

| File | Enforced pins | Layers |
| --- | --- | --- |
| `chronicler-agents/src/tick.rs` | 9 | academy, crisis, household candidates; l2, l5, l6, l7, pl4, cwc1b |
| `chronicler-agents/src/pool.rs` | 8 | academy; l2, l5, l6, l7, pl4, s1r, cwc1b |
| `chronicler-agents/src/ffi/mod.rs` | 16 | academy, crisis, food accounting, household; l1a, l2, l5, l6, l7, pl1, pl4, rs0, rs4, rs5, s1r, cwc1b (+ cwa4 on A4) |
| `chronicler-agents/src/lib.rs` | 7 | academy; cwc1b, l1a, l2, l5, l6, l7 |
| `chronicler-agents/src/ffi/schema.rs` | 3 | academy, crisis, food accounting (not needed: no snapshot column added) |
| `chronicler-agents/src/household.rs` | 1 | household candidate (not needed) |
| `src/chronicler/batch_manifest.py` | 24 | every livelihoods layer through cws1 and cwd2 (+ cwa4, cwc2) |
| `tests/test_batch_manifest.py` | 20 | including the native shard owner and oracle chunk |
| `src/chronicler/agent_bridge.py` | 6 | avoid |
| `src/chronicler/main.py` | 9 | avoid |
| `src/chronicler/simulation.py` | 11 | avoid: the livelihoods hooks already exist |
| `src/chronicler/models.py` | 4 | avoid |
| `src/chronicler/run_checkpoint.py` | 4 | avoid |
| `src/chronicler/ecology.py` | 1 (rs5) | avoid |
| `viewer/src/types.ts` | 5 | avoid: new viewer files |
| `src/chronicler/health_care.py`, `health_care_state.py` | digest (`tests/test_health_care_policy.py:1023-1024`) | D3 episode appends must not edit them |
| `behavior.rs`, `migration_drivers.rs`, `memory.rs`, `knowledge.rs`, `relocation.rs`, `migration_closure.rs`, `workshop_work.rs`, `persist.rs`, `agent.rs`, `formation.rs`, `demographics.rs`, `decision_delivery.rs` | none (references) | — |
| `livelihoods.py`, `livelihoods_state.py`, `feature_catalog.py`, `remittances*.py`, `relocation_costs.py`, `quarantine_rules.py`, `household_retail.py`, `recovery_crews.py`, `timber_supply.py`, `workshops.py`, `workshop_payroll.py`, `workshop_economics.py`, `apprenticeship.py`, `veteran_reintegration.py`, `money.py`, `wealth_accounting.py`, `war/armies.py`, `war/occupation.py`, `war/runtime.py`, `action_engine.py`, `attribution_records.py`, `learning_cohorts.py`, `cities.py`, `epidemiology.py`, `narrative.py`, `decision_delivery.py` | none (references) | — |
| `scripts/run_python_oracle_checks.py`, `scripts/testing/native_shards_manifest.json` | none (references; the manifest pins test paths) | enroll the new tests |

## 16. Turn-order rows to add (for the plan's section 6)

| Turn T step | Change | Owner |
| --- | --- | --- |
| Phase 1: epidemic tick | C2's crowding option reads the `residence_ledger` frame dated T−1 | C (contract: lead) |
| Phase 2: `prepare_health_care` → `reserve_first` (PL1, A4) → `prepare_phase2` in switch order | every new Python planner calls `booked()` first; claim order as in §12.2 | lead |
| Phase 5: campaigns, recruitment | D3: recruitment calls `booked()` behind its switch | D |
| `before_agent_tick` (T) | A6 installs the transient adjustment rows built from memory dated T−1 or earlier | A6 |
| Agent tick (T): decisions | the native destination score reads A6's rows; then household consolidation, the C1b gate, the liquid and L7 gates; A6's receipt diffs the refused moves and counts the changed decisions | native hook (lead) |
| `after_agent_tick` (T) | A6 takes its receipt once; refusals go to memory; `rollback_agent_tick` cancels a pending input | A6 |
| Post-tick | `finish_health_care` → snapshot → `reconcile_rosters` (unchanged) | — |
| Phase 10, livelihoods `phase10`, before A6, D2 and A1 | `residence_ledger` update from T's moves, snapshot, trips, rosters and region events; frame `source_turn = T` | lead |
| Phase 10, after the ledger | A6 reads quick departures from the ledger; crew experience recorded from T's receipts | A6 |
| Phase 10 (D3, later) | combat episodes appended after `finish_health_care` (AUDIT-D §6) | D |
| End-of-turn sync | late army dissolutions; the ledger sees them at T+1 | — |

## 17. Issues found

1. **C1b refusals repeat without learning.** People were refused up to 10 times, and 224 times
   again on the very next turn, on one world [probe]. This is the documented design ("decides
   afresh", `migration_closure.rs:20-23`). Classified as a missing capability that A6 addresses.
2. **Enlisted agents migrate natively and their roster region follows silently**
   (`armies.py:430`) [probe]. Classified as a missing capability for D3. Not a casualty defect.
3. **Recruitment can draft a health-care patient or caregiver of the same turn**: the registry
   rows that recruitment reads omit health rows [inferred, not reproduced]. This applies only
   with `--health-care` and campaigns. A D3 item.
4. **The AUDIT-C §4.3 statement on the bridge share's checkpointing is inaccurate** [code]. It is
   in exact checkpoints.
5. **Known displacement measures are unsuitable** [probe]: the cooldown (23–34%) and the birth
   region (59–73%).
6. **A6 interaction with C2's category tuple** once A4 merges (§12.3a). This is labelling only.
7. **A4 carriers keep deciding natively.** Releases on migration are by design
   (`A4:titled_trade.py:57-59`). Recorded so the harm panels count them.

## 18. Not verified here

- No A6 or ledger code exists. All effect sizes are inferred.
- The probe ledger is a stand-in, not the proposal's exact implementation:
  - The war anchor approximates with `occupied_by`, `last_conquered_turn` and controller change,
    read at `after_agent_tick`.
  - Merchants in transit were not held at their trip origin.
  - Home at first observation used the region at turn 1.
- Crew net excluded the forgone retail title. Under retail it lowers the net, and was not
  measured.
- That recruitment double-books health rows was not reproduced.
- That the bridge share survives an exact resume was read from the code, not run.
- Activation on held cohorts, the timing pilots and procedural worlds other than 13 were not run.
  Template 7 is famine-heavy (population falling to 107 by turn 200).
- The A4 branch was read at `d5ccd4d6` while its review was running; its final state may differ.
  The C2 files are uncommitted lane work.

## Appendix: probe method

All runs were from `/home/user/Chronicler` with
`env PYTHONPATH=/home/user/Chronicler/src PYTHONHASHSEED=0 RAYON_NUM_THREADS=2 CHRONICLER_QUIET=1 ~/.venvs/native-a3/bin/python <probe> <out> -- <args>`.
Each probe wraps one package hook in-process, after the original returns, and only reads state.
Nothing is written to the repository.

- `probe_a6.py` wraps `remittances.after_agent_tick` (snapshot, migrations with drivers, RS4,
  rosters, C1b refused ids, marriage bonds every 10 turns) and `recovery_crews.phase10` (member
  wage and income withheld).
  - A: `--seed 7 --turns 200 --agents hybrid --simulate-only --grain-reserves --grain-storage --repair-projects --recovery-crews --remittances --food-allocation --household-retail --household-retail-boundary all`
    (11 s).
  - B: the same with `--seed 13 --turns 120 --worldgen procedural --regions 32 --civs 10 --quarantine-mode closure --quarantine-channels trade,migration`
    (17 s; rerun with an enlisted-migration counter, 21 s, identical totals).
- `probe_disp.py` runs the candidate ledger of §10 beside the simulation.
  - C: `--seed 7 --turns 200` and `--seed 13 --turns 120 --worldgen procedural --regions 32 --civs 10`,
    each with `--agents hybrid --simulate-only --remittances` (10–12 s each; three iterations
    adding the anchor variants).
- `probe_arrears.py` wraps `workshop_payroll.phase10` (open firms, insolvency, `OwedWage` rows).
  - D: `--seed 7 --turns 200 --agents hybrid --simulate-only --cities --workshops --workshop-payroll --workshop-economics`
    (9 s).
- Summaries: `summarize_a6.py`, and the summary JSON in `runs/disp/*.json`.
- Seed check: `python scripts/connected_world_screens.py registry`, plus a scan of
  `scripts/seed_registry.json` for template 3301–3306 and procedural 3401–3406.
