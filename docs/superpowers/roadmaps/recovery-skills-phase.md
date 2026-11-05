# Recovery, skills and resilient local economies — phase plan

Owner instruction (2026-11-05): review and merge the livelihoods stack (#73, #74), then
build the next phase end to end. That means working simulation systems, viewer
integration, meaningful evaluation and a clean handoff on `main`. Every new switch is
off by default. Merging this code does not qualify it scientifically. The 200-seed and
procedural qualification gates are not run without the owner's approval. Bounded
screens, including procedural worlds, are in scope.

The goal is one connected loop:

- people learn useful skills through real work;
- communities maintain and rebuild productive assets;
- people affected by war or migration can contribute to the recovery.

Each package reuses the existing work registry, workshops, payroll, learning,
households, relocation and local budgets.

## 1. Audit facts the design rests on

The audits were read-only, on PR #74 head `456492e6`, with the native extension
`70587268…`.

- **Skills.**
  - Occupation skill rises +0.05 every turn in a person's current trade, whether or
    not they do any work, and nothing makes it decay. A farmer reaches 1.0 by age 18.
  - Farmer skill feeds only the purpose need and named-character promotion
    (`pool.rs` aggregate match arm `_ => {}`). Income, farm labour, craft conversion,
    teaching and workshop crews read no skill.
  - L5 completion adds +0.25 to a number that is already near its cap.
  - Conclusion: apprenticeship needs its own **qualification record** by stable id, and
    the qualification must gate a real activity.
- **Workshops (L1).**
  - Condition wears only while a site is unfunded.
  - Below 0.5 condition, a 20-coin lump with no labour and no materials resets
    condition to 1.0 (`workshops.py` `_bill`/`_settle`). This is the "free legacy
    restoration" that a repair project must replace, so the site is not repaired twice.
- **Granaries (grain storage).**
  - Condition wears 0.01 per tick, and a 4-work batch adds +0.10, capped at 1.0.
  - Condition drives usable capacity and spoilage.
  - Under `maintain`, timber is the binding limit in 85–92% of region-turns. Batches
    lose a third or more of their effect at the 1.0 cap. Rounding coins per region
    overcharges 14–25%. A zero-capacity asset still asks for work.
  - Reaching condition 0 by turn 100–160 is wear plus starved maintenance, not a bug.
  - Storage labour is an anonymous farmer-equivalent drawn from regional farm labour,
    not identified people.
- **War.**
  - War never damages granary or workshop condition. It seizes grain, captures and
    sacks cities, requisitions food under occupation, destroys some infrastructure
    (scorched earth, temples) and kills people.
  - Rosters hold native stable ids.
  - People leave an army alive through `release_soldiers` (desertion or scattering,
    ids kept in a local set, no event) or `disband` (at-home demobilisation; the event
    has a count and no ids). That is 82% of veterans in procedural worlds.
  - A war's identity is `(war_key, start_turn)`.
  - In 100 turns, template worlds had 0–21 soldiers and procedural worlds had 39–155
    veterans.
- **Migration and links.**
  - Stable ids come from a monotonic counter, and slots are reused.
  - Marriage and Kin bonds survive migration (sentiment decays while the pair are
    apart) and are removed at death.
  - The last region a migrant left exists only in non-checkpointed events.
  - Natural pool: 8–32 settled migrants with a bond of 20 or more in the region they
    left, and over 99% of them hold at least 1 unit of wealth. 55–70% of moves are
    famine moves, so remittances need a settled/non-return filter.
  - No person-to-person transfer exists except inheritance.
- **Clearing.**
  - Native `ecology.rs:770` is authoritative whenever an extension exists (agent
    modes and the off-mode EcologySimulator). Python `ecology.py:827` is the
    no-extension fallback, and a parity oracle exists.
  - Clearing is a flat 0.02 cover loss whenever population exceeds half of carrying
    capacity. Regrowth is blocked while it is over.
  - Wildfire, cooling, volcanoes and succession are separate cover changes.
  - Protection freezes cover; it cannot restore it.

## 2. Packages

Every package is a livelihoods switch (`--<name>`, module `chronicler.<name>`,
appended to `LIVELIHOODS_SWITCHES`) with a cost-retaining or record-only control mode.
Every one requires `--agents hybrid` except RS5.

| Id | Switch (modes; first = default when on) | Mechanism | Requires |
| --- | --- | --- | --- |
| RS0 | — | Shared groundwork; owned by the lead (section 4) | — |
| RS1 | `--apprenticeship` (`train`, `no_qualification`) | Named mentors and apprentices at operating workshop sites; a workshop qualification by stable id; qualified upkeep on site wear | `--workshops` in `operate` |
| RS2 | `--repair-projects` (`repair`, `cost_only`) | Paid repair projects for workshops and granaries from real condition and damage, with labour, timber, coins and an L9 envelope; war damage from real events | `--workshops` (operate) or `--grain-storage` |
| RS3 | `--veteran-reintegration` (`priority`, `record_only`) | Veterans captured from real roster release and disband events by stable id; priority access to crew, apprenticeship and repair openings | at least one of `--workshops`, `--apprenticeship`, `--repair-projects` |
| RS4 | `--remittances` (`send`, `record_only`) | A diaspora ledger from applied migrations; bounded remittances along Marriage/Kin bonds, with a courier fee and exactly-once receipts | `--agents hybrid` |
| RS5 | `--clearing-protection` (`enforced`, `cost_only`) | A controller-funded protection column applied at the clearing decision point, in both native and Python ecology | none (works in all ecology paths) |
| RS6 | — | Viewer panels; Batch Lab and live new-world feature options, with dependencies; browser checks | RS1–RS5 schemas |
| RS7 | — | Constructed and natural examples; preregistered held screens; handoff | all |

### RS1 apprenticeship and skill continuity

- **Workshop qualification.** A record by stable id: `{id, earned_turn, site,
  settlement, region, via: service|apprenticeship}`.
  - It is held for life and travels with the person.
  - It is not occupation skill and does not change `pool.skills`.
  - Service mentors: a crew member reaches `SERVICE_TURNS` crew-turns at any site.
    This gives the first mentors with no external grant.
- **What the qualification enables (the real activity).**
  - With `--apprenticeship` on (both modes), an operating funded site wears
    `OPERATING_WEAR` per turn.
  - Qualified crew members present that turn perform upkeep. They spend
    `UPKEEP_SHARE` of their crew time (so less crew craft work is allocated) and offset
    up to that much wear.
  - A site with no qualified person present wears down. Below `OPERATE_CONDITION` it
    cannot operate until it is repaired: by RS2 when that is on, otherwise by the
    existing L1 lump.
  - Effect is bounded: upkeep never exceeds wear, condition stays in [0, 1], and the
    craft ceiling still replaces the old one. The `no_qualification` control has the
    same wear, attendance and costs and grants no new qualifications.
- **Mentors and apprentices.**
  - A mentor is a qualified crew member present that turn and teaches up to
    `PER_MENTOR` apprentices; each site takes at most `PER_SITE`.
  - Apprentices are living adults resident in the site's settlement and region. They
    are not on a trip, not on an army roster, not already holding work, not already
    qualified, and are adult urban farmers like the crew pool. Veterans come first
    (RS3), then ascending id.
  - Apprentices hold the new registry category `apprentice` for
    `APPRENTICE_FRACTION`. Their ordinary income loses that share through the
    paid-work seam (`extend_paid_work`).
  - With `--workshop-payroll`, the firm pays a stipend from firm cash under the
    purpose `apprentice_stipend`, exactly once. Without payroll the time is unpaid
    and the cost is the forgone income.
  - The mentor's teaching share comes out of their crew work, so it is not paid twice.
- **Attendance and endings.**
  - A turn counts only if the apprentice and a mentor are both present and the
    reservation succeeded.
  - Missing turns are interruptions. More than `MAX_GAP` in a row is a dropout.
  - Completion after `COMPLETION_TURNS` attended turns grants the qualification in
    `train` mode only.
  - Endings are recorded with their reason: death, departure or migration, occupation
    change, site closure, conquest, remobilisation.
- **Continuity.**
  - Per site and turn, record how many qualified people are present (the community's
    teaching capacity).
  - Separately record qualified people alive anywhere (retained by people).
  - A dated `teaching_lost` event fires when a site's last qualified person leaves,
    while graduates elsewhere keep their record.

### RS2 maintenance, reconstruction and repair projects

The asset set is bounded: workshop sites (L1) and granaries (grain storage).

- **Projects.**
  - A project opens when an asset is below `OPEN_BELOW` and its controller can be
    billed.
  - Its scope is the actual deficit `1 - condition`, in work units: no work is planned
    beyond the cap, and partial work credits pro rata.
  - Each project has a cause: `wear` for ordinary maintenance, or `war` for
    reconstruction from a damage record.
- **Inputs.**
  - Labour is named workers reserved in the registry (category `repair`, with
    `repair_wage` through `extend_paid_work` plus a `transfer_wealth` wage).
  - Workshop repair needs a qualified person (RS1) on the repair crew. Without one it
    proceeds at `UNQUALIFIED_RATE`.
  - Timber from the region's stock (L3 when on, otherwise the regional pool, as storage
    does). Coins from the controller's treasury.
  - With `--local-budgets`, all three come within a new `repairs` envelope.
  - Coins are charged once per civilisation per turn, with no per-region rounding
    overcharge.
- **No double payment.**
  - With RS2 on, the L1 lump repair is disabled. RS2 owns repair of workshops, and of
    granaries in regions with an open project, where the region's ordinary `maintain`
    request is suspended for that turn.
  - A project's delivered work is the only thing that moves condition.
  - Failed ticks charge nothing.
  - Cost-only mode reserves, pays and uses timber identically but does not change
    condition.
- **War damage.** Recorded only at existing real events, with the cause
  `(war_key, start_turn)`. No new combat generator.
  - When a region is conquered (`apply_region_conquest`) or its city sacked: granary
    and workshop condition minus `WAR_DAMAGE`.
  - When a granary is seized: granary condition minus `WAR_DAMAGE`.
  - The tuning key `repair_projects.war_damage` (default 1, 0 disables) is the screen
    ablation.
- **Consumers.** No new consumer.
  - Granary: usable capacity and spoilage.
  - Workshop: the L1 `OPERATE_CONDITION` gate and RS1 wear.

### RS3 veteran reintegration

- **Capture.**
  - Recorded at `release_soldiers` (the `leaving` ids, cause desertion or scattered),
    at `disband` before the roster is cleared (cause demobilised or destroyed), and at
    the two silent roster removals in `war/runtime.py`.
  - Each record holds `{id, civ, army_id, war: (war_key, start_turn), cause, turn,
    region}`.
  - Captured only while the switch is on. A non-exact roster redraft invalidates open
    records.
- **Reintegration.**
  - Eligible veterans are alive, adult, released within `ELIGIBLE_TURNS`, not
    re-enlisted, and in a region whose controller is the civilisation they served.
  - In `priority` mode they come first, among candidates who are otherwise eligible,
    for workshop crew openings (native planner `priority_ids`), apprenticeship seats
    (RS1) and repair crews (RS2).
  - Nothing is guaranteed: with no opening there is no placement. No people, money or
    skill is created.
  - `record_only` captures and tracks without priority.
- **Outcomes.** Each is dated: `placed:{crew|apprentice|repair}`, `waiting`,
  `remobilised`, `died`, `migrated`, `control_lost`, `expired`.

### RS4 migration, knowledge and household support

- **Diaspora ledger.**
  - Built from applied migration events (native event type 2, including L7 moves) as
    `{id, origin, departure_turn, destination}`.
  - Bounded and checkpointed.
  - A move back to the origin closes the entry as a return. Each origin records its
    loss and each destination its gain, separately.
  - Knowledge flow: the ledger notes migrants who hold an RS1 qualification (skill
    leaving origin, arriving at destination).
- **Remittances.**
  - **Sender:** alive adult, settled (displacement 0, at least `SETTLED_TURNS` since
    arrival), not on a trip, outside the origin.
  - **Recipient:** one Marriage or Kin bond with sentiment of at least 20, alive, in
    the origin, not on a trip. Spouse first, then highest sentiment, then lowest id.
  - **Amount:** at most `SHARE` of wealth above a `RESERVE`, capped at `CAP` per turn.
    A `FEE` share goes to a disclosed courier sink.
  - **Native op:** one pairwise operation (purpose `remittance`). It validates both
    ids before any change and applies debit, fee, credit and ceiling refund under one
    key. Absent or dead parties move nothing. Residuals are refunded.
  - **Receipts:** exactly once, through a Python `last_settled_turn` per sender on
    resume.
  - **Placement and exclusions:** runs after the agent tick, after L7 fares.
    Inheritance stays separate. Remittances never touch food allocation and never
    create income.

### RS5 funded protection of forest cover from clearing

- **Column.** An optional region-batch column `clearing_protection` p in [0, 1] (absent
  = 0).
  - It is a transient RegionState field, reset when absent.
  - Applied in both `ecology.rs` and `ecology.py` at the clearing decision as
    `cover -= clearing × (1 − p)`.
  - Cooling, wildfire, volcanoes and succession are untouched.
- **Ledger.** A native receipt `cover_not_cleared` goes into the timber/extraction
  ledger when L3 is on, and the package's own ledger otherwise.
- **Who pays.**
  - The controller adopts protection for at most `MAX_REGIONS` forested regions under
    clearing pressure.
  - It pays `WARDEN_COST` per protected region-turn in which clearing was actually
    active, planned against the projected treasury and charged after the tick as
    `keep`. Unpaid enforcement lowers p.
  - With `--local-budgets`, protection sits within a `wardens` envelope that it shares
    with L8.
- **Stated trade-off.** Protection forgoes the forest→plains succession bonus (+20
  carrying capacity). The `cost_only` control adopts and pays identically and applies
  no cap.

## 3. Dependencies and ownership

```
RS0 (lead: registry categories, transfer purposes, extend_paid_work,
     crew priority_ids, switch registry, stub APIs, workshops seams)
  ├─ RS1 apprenticeship ── qualified_ids(world, region) ──┐
  ├─ RS3 veterans ───────── priority_ids(world, region) ──┼─> RS2 repair projects
  │                                                       │   (workshop + granary,
  │                                                       │    war damage, L9 envelope)
  ├─ RS4 remittances (own native op)                      │
  ├─ RS5 clearing protection (own native column + parity) │
  └─ RS6 options/viewer (server + UI; panels after schemas) <── all
RS7 evidence <── all integrated
```

| Lane | Owns (may edit) | Reads (must not edit) | Native build |
| --- | --- | --- | --- |
| Lead / integration | RS0 seams, `simulation.py`, `ffi/mod.rs` shared hooks, `livelihoods*.py`, `batch_manifest.py`, `transport_contract.json`, `tuning.py`, witness layers, test enrollment and manifests, board, ledgers | — | shared RS0 extension |
| RS1 skills | `apprenticeship*.py`, the RS1 parts of `workshops.py` (via the RS0 seams), tests | payroll, registry | uses RS0 |
| RS2 repair | `repair_projects*.py`, the RS2 parts of `grain_storage.py`, war-damage hooks at the four existing call sites, the L9 `repairs` envelope | RS1/RS3 APIs | uses RS0 |
| RS3 veterans | `veteran_reintegration*.py`, capture hooks in `war/armies.py` and `war/runtime.py` | — | uses RS0 |
| RS4 remittances | `remittances*.py`, the native op in `wealth_transfer.rs`, its FFI method | — | own |
| RS5 clearing | `clearing_protection*.py`, `ecology.rs`, `ecology.py`, `ffi/ecology_sim.rs`, region-batch column parsing, parity tests | — | own |
| RS6 options/viewer | `viewer/` panels and readers, `live.py` start/batch validation and forwarding, `SetupLobby`, `BatchPanel` | snapshot schemas | none |

Lanes edit a shared file only through the seam RS0 provides. Where a lane must touch a
lead-owned file (`ffi/mod.rs`, `simulation.py`), it keeps the edit minimal and lists it
in its handoff; the lead integrates it and records the witness layer.

## 4. RS0 groundwork (lead)

- **Native.**
  - Append `apprentice` and `repair` to `RESERVATION_CATEGORIES`.
  - Append `apprentice_stipend`, `repair_wage` and `remittance` to the transfer
    `PURPOSES`.
  - `extend_paid_work(turn, rows)`: merges rows into the turn's pending paid-work
    install or creates it. It refuses an id that already has a pending share, and
    refuses any share above that id's reservations, so each person still has at most
    one paid share per turn.
  - `plan_workshop_crews(..., priority_ids=None)`: listed ids come first among the
    eligible, the rest in ascending id. The default leaves the order unchanged.
- **Python.**
  - The five switches, with modes, help text, prerequisites, state containers, CLI
    forwarding and manifest keys.
  - Stub modules that implement the package protocol inertly, plus the cross-lane API
    stubs `apprenticeship.qualified_ids`, `veteran_reintegration.priority_ids` and
    `note_outcome`, and `repair_projects.legacy_workshop_repair_allowed`.
  - In `workshops.py`, guarded seams for before-crew reservation, crew priority ids,
    operating wear and the legacy repair gate.
- **When off.** Every addition is unused while its switch is off. Feature-off identity
  is checked against `main` with its own extension.

## 5. Obligations for every package

- Tests that fail on wrong behaviour, with real-native cases where native code runs.
- Adversarial lifecycle cases: death, migration, return, remobilisation, controller
  change, site closure, slot reuse.
- Money and material closure per turn, with no double spend and no double-paid time.
- Failed-tick rollback, duplicate receipts, and exact checkpoint/resume inside live
  projects, cohorts and ledgers.
- Correct enrollment (offline chunks with headroom, or the native shard manifest).
- Viewer readers that are strict, where missing data is unknown rather than zero.
- An integration page in `docs/integration/` for each package.
- Feature-off identity checked against the correct baseline with the correct extensions.

## 6. Evidence plan (RS7)

- **Development examples.** Each package gets one constructed example (labelled
  constructed) and one natural activation found in an ordinary seed (labelled
  natural), both reproducible by command. They show success (a site kept operating by
  its graduates, a granary rebuilt after a sack, a veteran placed, remittances
  received) and failure (teaching lost, a repair starved of timber, veterans waiting
  without openings, remittances ended by bond decay or death).
- **Held screens.** Before running anything, freeze the source, arms, controls,
  outcomes and seeds in a preregistration. Seeds are fresh: template 501–506,
  procedural 32×10 601–606.
  - A timing pilot sets the aggregate compute budget.
  - The extractor is validated against the expected schemas; a missing outcome fails
    visibly.
  - Cost-retaining controls: `no_qualification`, `cost_only`, `record_only`.
  - Interactions: apprenticeship × repair, veterans × apprenticeship, repair ×
    local budgets, clearing × commons.
  - Results are reported by world and by stratum, including nulls and adverse effects.
  - Nothing is tuned on held worlds.

## 7. Explicit gaps

- General household food retail (L6b) stays open; nothing here claims it.
- No new combat event generator.
- Infrastructure repair (only an `active` flag exists today) is outside the bounded
  asset set.
- The 200-seed and procedural qualification gates are not run.

## 8. Status and handoff (2026-11-05)

Every package below is integrated on `claude/recovery-skills`. Each switch is off by
default and none is promoted. Merging does not qualify the code scientifically.

| Package | Switch (modes) | Lane commit | Integration page |
| --- | --- | --- | --- |
| RS0 groundwork | none | lead | this plan, section 4 |
| RS1 apprenticeship | `--apprenticeship` (`train`, `no_qualification`) | `7b0b2e5c` | `docs/integration/apprenticeship.md` |
| RS2 repair projects | `--repair-projects` (`repair`, `cost_only`) | `e7d72f76` | `docs/integration/repair-projects.md` |
| RS3 veterans | `--veteran-reintegration` (`priority`, `record_only`) | `6a5801e2` | `docs/integration/veteran-reintegration.md` |
| RS4 remittances | `--remittances` (`send`, `record_only`) | `c7730cc9` | `docs/integration/remittances.md` |
| RS5 clearing protection | `--clearing-protection` (`enforced`, `cost_only`) | `e0cb49e6` | `docs/integration/clearing-protection.md` |
| RS6 feature options | none (Batch Lab, live setup) | `e3de7f3b` | `docs/integration/feature-options.md` |
| RS7 evidence | none | lead | `docs/superpowers/progress/recovery-skills-screens.md` |

**Independent review.** Three reviewers worked from the code, not from the lanes'
reports:
- A: RS1 and RS3.
- B: RS4 and RS5.
- C: RS2.

There were no blockers. Every confirmed defect was fixed with a regression test that
fails on the previous code; the list is in the board's `review_fixes`
(`docs/superpowers/progress/recovery-skills.json`). Two of the defects matter beyond
this phase:
- Phase 10 read wealth from before the livelihoods after-hooks had run. This was
  already on `main` and affected L6a and L7.
- The #74 feature-off identity evidence had compared the same Python tree twice. The
  correct rerun passes, and the tool now refuses that mistake.

**Verification of the final source.**
- The bounded offline lane passes.
- Native suites: 130 passed, 1 skipped.
- Feature-off `turn_speed_identity` against `main` `9f950cb4`: 9 cases, 399 files, 0
  differences.
- All-switch `checkpoint_identity` `hybrid_s42_long`, every livelihoods and
  recovery-skills switch on: PASS at 19 resume points.
- Viewer: 139 test files and 1,346 tests, lint and build. The browser QA
  (`viewer/scripts/qa-recovery-skills.mjs`) passed 470 checks at desktop and phone.

**Held screens.** 228 runs, 0 failed, 0.86 core-hours
(`docs/superpowers/progress/recovery-skills-screens.md`, Results):
- RS2 granary condition: +0.030 (t) and +0.079 (p) against cost_only.
- RS5 forest cover: +0.025 and +0.057 against cost_only.
- RS4: 926 and 1,161 wealth units credited per world, with 163 and 204 in fees.
- RS1 completions are rare (3.3 and 0.8 per world), and its operating wear costs 10–14
  lump repairs per world.
- RS3 priority is a null.

**Out of scope, unchanged:**
- household food retail (L6b);
- infrastructure repair;
- any new combat generator;
- calibration of the declared constants;
- default promotion;
- the 200-seed and procedural qualification gates.
