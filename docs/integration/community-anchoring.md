# Community anchoring and the procedural needs-ablation design (2026-10)

Branch `feat/community-anchoring` from `main` `b1c9274` (PR #61, ablation
oracles). PR #61 left two open decisions (`ablation-oracles.md` section 8):
the kin roots anchor community members' migration by about 1%, where the
M53 spec claims 15-30%; and the procedural material pairing of the needs
ablation measured +6.7% [-5.3%, +18.7%] on a cohort of 3.6 agents a fork.
This branch adds a spec-faithful community anchoring term behind a switch
that is off by default (A), redesigns the forks of procedural worlds for
power and reruns the needs ablation (B).

**Results:**

* **Community anchoring** (`--community-anchoring`, off by default) is the
  term M53 describes: positive bonds to people of the same region with whom
  the agent shares a memory, at least one of them non-kin, lower the odds
  of acting on a reason to move. Switched off, output is byte-identical to
  `main`. Switched on, migration falls 5-7%, every required oracle passes
  in both full gates, and the anchor scales with an agent's ties.
* **It does not reproduce M53's 15-30%.** At the strength calibrated from
  the spec's band, the oracle's community members migrate 9.1% (template)
  and 5.9% (procedural) less over the 20-turn window, about what
  non-members show. The oracle's members are about nine in ten agents
  (section 1). Agents with four ties migrate 10-13% less, not the predicted
  22%: a reason to move persists, so a held mover moves later. Matching
  the M53 number takes about twice the anchor and cuts all migration by
  16% (section 7). The switch stays off, the claim is recorded as not
  reproduced, and the cohort oracle's causal components stay reported only
  (section 10).
* **Fork design 2** forks procedural worlds every 20 turns from turn 100,
  which restores the needs ablation's power with the real exposure. The
  procedural material pairing now passes: 1.119 [1.093, 1.145], where PR
  #61 measured 1.067 [0.947, 1.187]. Needs method 8 and cohort method 5
  score design-2 arms; design-1 arms keep methods 7 and 4.

## 1. What M53 means by anchoring

The M53 spec (`docs/superpowers/specs/2026-03-21-m53-depth-tuning-validation-design.md`,
section 6.2):

* **Oracle 1** defines a community: "groups of 5+ agents with mutual bonds
  and shared memories", found by label propagation over "friend +
  co-religionist + kin edges weighted by sentiment", kept when at least 80%
  of members share a memory `(event_type, turn, valence_sign)`, and with a
  **kin-only exclusion**: "Pure dynastic/family clumps do not count".
  Acceptance: 3-15 communities a seed, median size 5-12, none above 5% of
  its region.
* **Oracle 4** compares the members of those communities with matched
  non-members (same civ, region, occupation, similar satisfaction):
  "community members show 15-30% less migration (social anchoring) OR
  20-40% higher rebellion co-participation (collective action)". Its
  failure investigation: "bond effects on utility too weak -> check
  relationship utility modifiers"; "memory -> utility pipeline
  disconnected".

So anchoring is meant to be **community-specific**: membership of a group
held together by mutual bonds that include non-kin ties and by shared
experience, acting on migration through the decision utility. It is not
generic kin: the spec excludes family clumps from what counts as a
community, and the household already moves together (`household.rs`).
The model's only anchor so far is the relationship part of a migrant's
roots (`ROOTS_MARRIED` 0.02 plus 0.02 per unit of home bonds, at most 0.06),
which acts only on the voluntary pulls and anchors non-members as much as
members (`ablation-oracles.md` section 3.3): kin and household roots, not
community.

**What the oracle measures instead.** Two defects of the community
detection make the cohort oracle's "members" nearly everyone (probes of
`main`, template seeds 42-61 x 222 turns and procedural 32 x 10 seeds
42-51, turns 100 and 200):

| | template | procedural |
| --- | ---: | ---: |
| communities per snapshot (median) | 2 | 10 |
| community size: median / p90 / max | 15 / 147 / 258 | 11 / 137 / 350 |
| communities above 5% of their main region | 100% | 99% |
| regions a community spans (median) | 3 | 4 |
| members' share of living agents (median) | 96% | 89% |

* `detect_communities` propagates labels over **every** edge, rivals and
  grudges included, unweighted, across regions (the spec names friend,
  co-religionist and kin edges weighted by sentiment).
* Its kin-only exclusion tests `bond_type != 0`, from a docstring that
  numbers kin 0; in the native enum 0 is **mentor** and kin is 5
  (`relationships.rs`), so a pure kin clump passes.
* `run_community_oracle` checks only that a seed has a community of 5+; the
  spec's size and count criteria are not checked.

Detected as oracle 1's text specifies (friend, co-religionist and kin edges,
positive, weighted by sentiment, within a region; the kin code corrected),
communities look like the spec's: 7 per snapshot in template worlds and 14
in procedural ones, median size 6 and 5, p90 9 and 8, holding 23% and 15%
of agents (`validation_ablation.detect_spec_communities`, informational).
Members of those communities migrate exactly as much as everyone else on
`main` (1.060 against 1.062 moves per agent over 20 turns, template; 1.226
against 1.216, procedural).

## 2. Design

### 2.1 The term (`chronicler-agents/src/community.rs`)

* **Community ties** of an agent: positive-valence bonds (mentor, exile
  bond, co-religionist, kin, friend; marriage excepted, since the spouse
  moves with the household) of sentiment at least 20 (the migration
  drivers' `BOND_MIN_SENTIMENT`) to a living agent of its own region with
  whom it shares a memory: the same event type with both memory turns in
  one 5-turn bucket, the key oracle 1 compares. A merchant away on a trade
  trip still counts.
* **Kin-only exclusion**: the ties count only when one is non-kin; an agent
  held by kin alone keeps its kin roots and household as before.
* **Anchor** = `COMMUNITY_ANCHOR` x counted ties / 4, the ties counted up
  to `COMMUNITY_FULL_TIES` 4 (with the agent, a group of five, oracle 1's
  smallest community).
* **Where it acts** (`behavior.rs`, `evaluate_region_decisions_with`): the
  anchor is subtracted from the migrate utility of an agent whose migrate
  gate is open (a positive utility toward a better region), after the
  household damper. It lowers the odds of moving against every other
  action by `exp(-anchor / T)` at the decision temperature T = 0.3 and
  never closes the gate: a reason to move stays one. Rebellion, occupation
  switches and staying are untouched (the anchor is not a stay bonus, which
  would also damp rebellion, the spec's other community effect).
* It draws no number: the decision keeps its four Gumbel draws per agent,
  so an anchored and an unanchored run share their random numbers up to the
  first changed decision. A Rust test checks that the anchor only ever
  turns a move into another choice, and that agents who did not move decide
  exactly as before.
* Cost: one pass over at most 8 bonds with at most 8 x 8 memory
  comparisons each, only for agents with the gate open and only with the
  switch on.

### 2.2 The switch

| Layer | What |
| --- | --- |
| World | `WorldState.community_anchoring`: `True` on, `None` off (dormant: omitted from every output, `tests/test_serialization_dormant_fields.py`); `chronicler.community_anchoring` (`DEFAULT_ENABLED_FOR_NEW_WORLDS = False`) |
| CLI | `--community-anchoring` / `--no-community-anchoring`; an explicit `--community-anchoring` with `--agents off` is refused; a saved setting is kept on resume |
| Live | new live worlds follow the default (off) |
| Native | `AgentSimulator.set_community_anchoring(enabled, full_anchor=None)`, getter `community_anchoring`; `TickOptions.community_anchoring` (`scale::CommunityAnchoring { enabled, full_anchor }`, `persist_struct!`; the checkpoint layout fingerprint changes, as for any new native field). The bridge sends it only when the world has it on: a plain run makes the native calls it always made |
| Tuning | `agents.community_full_anchor` overrides the full anchor (utility units) |
| Batch manifest | `community_anchoring` is a simulation argument (a report with it is another configuration) |
| Checkpoints | `feature_flags` records it; an exact resume adopts it and refuses `--no-community-anchoring` against a saved `True` |
| Gate runner | `--community-anchoring` is forwarded to every agent-mode run (not to the aggregate determinism run, whose manifest then records `None`); with it the default arms add `community_anchor` |
| Ablation | `--decision-ablation community_anchor` (`scale::ABLATE_COMMUNITY_ANCHOR`) switches the anchor off from the start turn; it is refused on a world without the switch |
| Diagnostics | `get_migration_driver_stats()["community_ties_k"]`: agents with the gate open by counted ties (zeros with the switch off); `get_community_ties()` lists every agent's ties as the decision counts them |

### 2.3 The validator's mirror

`validation_ablation.community_ties` recomputes the ties from a turn's
sidecars (relationships, memory signatures, the needs snapshot's regions).
A native test runs a 60-turn hybrid world with the switch on and checks that
the final pool's native ties (`get_community_ties`) equal the mirror computed
from the final sidecar snapshot, agent for agent.

## 3. Calibration and pre-registration

Written before any run with the switch on (the full text is kept with the
run reports, `preregistration.md`, and reproduced here).

**Target, from the spec's range.** An agent fully embedded in a community
of five (four counted ties) should make 22.5% fewer moves over the oracle's
20-turn window: the midpoint of 15-30%.

**From the decision model, not the oracle.** For an agent with the gate
open at move probability P, an odds ratio x lowers the per-turn hazard to
x / (1 - P + P x); P = 0.2 lies between a barely positive migrate utility
(0.13 against stay 0.58 at T = 0.3) and 0.3. The 20-turn count then moves
through the 5-turn settling lock, c = h / (1 + 5h), at the measured hazard
(0.053 moves per agent-turn, h = 0.072 per eligible turn). 22.5% fewer moves
needs x = 0.67: **`COMMUNITY_ANCHOR` = -0.3 ln 0.67 = 0.120143**. Fewer ties
scale the log-odds linearly. No agent is anchored beyond the band: a full
member makes about 22% fewer moves (25% as P -> 0).

**Predicted effects** (direct effect only, the exposure probes' plain moves
as weights):

| Cohort at the fork | template | procedural |
| --- | ---: | ---: |
| oracle community members (method 4's cohort) | 0.93 | 0.95 |
| oracle non-members | 0.92 | 0.95 |
| four counted ties | 0.77 | 0.78 |
| one to three counted ties | 0.88 | 0.90 |
| no counted tie | 1.00 | 1.00 |
| members of communities as oracle 1 specifies them | 0.90 | 0.91 |
| all agents | 0.93 | 0.95 |

The exposure: 45-53% of agents hold no counted tie, 11% (template) and 6%
(procedural) hold four; the oracle's members and non-members hold about the
same ties (template mean 1.62 against 1.44; a non-kin tie in 55% and 49%).

**Causal test** (arm `community_anchor`, forked exactly as the gate's
other arms, cohorts fixed from the plain run's turn-T sidecars, rate ratio
plain / ablated, seed-clustered one-sided 95% bound):

1. The pre-registered claim of cohort method 4 on the oracle's members: RR
   <= 0.85 and upper bound < 1. **Predicted to fail** (0.93, 0.95).
2. Mechanism (a candidate restated claim): agents with four counted ties:
   RR between 0.70 and 0.85, upper bound < 1. Predicted to pass (0.77-0.78).
3. Specificity: agents without a counted tie: 95% interval within
   0.97-1.03. Predicted to pass.
4. Dose: RR(four ties) < RR(one to three) < RR(none).

Broader effects are reported against `main`'s full-gate reports
(exploratory: another configuration), with the predicted fall of migration
per agent-turn of 5-7%. The constants were not changed after any measured
outcome.

## 4. The causal test with the switch on

Full gates with `--community-anchoring` (frozen tree `e67c083`, extension
`8497d374...`): template 200 seeds x 500 turns, forks at 100-400 (800 per
arm); procedural 32 x 10, 100 x 300, forks every 20 turns from 100 (900 per
arm); arms `needs`, `kin_roots` and `community_anchor`. Migration of the
cohort over the 20 turns after a fork, plain arm (anchor on) over the
`community_anchor` arm (anchor off from tick T+1); 95% interval;
(agent-forks; informative seeds):

| Cohort at the fork | predicted (template / procedural) | template | procedural |
| --- | ---: | ---: | ---: |
| **oracle community members** (method 4's cohort; criterion RR <= 0.85, bound < 1) | 0.93 / 0.95 | 0.909 [0.901, 0.917] (130,400; 200) **FAIL** | 0.941 [0.937, 0.945] (417,781; 100) **FAIL** |
| oracle non-members | 0.92 / 0.95 | 0.895 [0.874, 0.917] (20,446) | 0.938 [0.927, 0.948] (70,065) |
| four counted ties (restated criterion 0.70-0.85, bound < 1) | 0.77 / 0.78 | 0.873 [0.856, 0.891] (18,830) **FAIL** | 0.899 [0.888, 0.911] (29,309) **FAIL** |
| one to three counted ties | 0.88 / 0.90 | 0.898 [0.889, 0.907] (69,204) | 0.931 [0.926, 0.936] (210,944) |
| no counted tie (criterion: interval within 0.97-1.03) | 1.00 / 1.00 | 0.926 [0.917, 0.936] (62,812) **FAIL** | 0.952 [0.948, 0.957] (247,593) **FAIL** |
| dose: four < one to three < none | holds | holds | holds |
| members of communities as oracle 1 specifies them | 0.90 / 0.91 | 0.912 [0.898, 0.925] (37,927) | 0.932 [0.923, 0.941] (71,053) |
| spec non-members | | 0.906 [0.898, 0.914] | 0.942 [0.938, 0.946] |
| members' rebellion (reported) | 1.00 | 1.013 [0.993, 1.032] | 1.008 [0.997, 1.019] |

Agents with four ties, by part of the window (plain / ablated moves):
first ablated turn 0.763 (template) and 0.798 (procedural), turns 1-5
0.820 and 0.875, turns 6-20 0.897 and 0.910.

* **The pre-registered claim fails, as predicted.** The anchor lowers the
  oracle members' migration by 9.1% (template) and 5.9% (procedural),
  against the 15% minimum. The oracle's members are 86-89% of the agents
  and hold about the ties the non-members hold, so the anchor moves both
  alike (non-members 10.5% and 6.2%): with this cohort, a community anchor
  cannot be told from a general one.
* **The anchor is weaker over the window than calibrated.** For agents
  with four ties it gives about a fifth fewer moves on the first ablated
  turn (0.763 and 0.798), near the per-decision target, but 10-13% fewer
  over the 20 turns (0.873 and 0.899). A held mover keeps its reason to move
  and leaves later; an unanchored mover who left is settled for five turns.
  The calibration counted the settling lock but not this deferral of a
  persistent reason, so it predicted 0.77-0.78 where the window shows
  0.87-0.90: the 20-turn effect is about half the per-decision one. The
  restated criterion (0.70-0.85) fails on the minimum effect in both
  worlds.
* **It also reaches agents without ties** (0.926 template, 0.952
  procedural; the specificity criterion fails): household followers move
  with an anchored lead (four in ten migration units on `main` are
  followers), ties form during the window, and the regions an anchored
  mover does not enter are less crowded for others.
* **Dose holds** in both worlds: four ties < one to three < none. The
  effect is largest where the ties are, as the mechanism says.
* **It does not follow oracle 1's communities.** Members of communities as
  the spec defines them are anchored slightly more than non-members in
  procedural worlds (0.932 against 0.942) and not at all in template ones
  (0.912 against 0.906). About a third of those members have no counted
  tie of their own (section 3).
* **Rebellion** barely moves (members 1.013 template, 1.008 procedural),
  as designed: the anchor acts only on the migrate utility. The one
  exception is template agents with four ties, whose rebellion rises 3.7%
  [1.0%, 6.4%]: an agent held at home rebels there instead.

## 5. What else moves, and the gates

### 5.1 Paired by seed

The same seeds with the switch off and on. Procedural: the two full gates'
plain batches, 100 seeds x 300 turns. Template: seeds 42-91 of the
flag-on gate against a flag-off batch of the same seeds, 50 x 500. Rates
are per agent-turn over the whole run (agent-turns from every turn's civ
populations). The paired column is the mean +- standard error of the
per-seed log ratio of rates, or of the difference:

| Per seed | procedural off -> on | paired | template off -> on | paired |
| --- | --- | ---: | --- | ---: |
| migration | 0.0753 -> 0.0715 | **-5.3% +- 0.9%** | 0.0637 -> 0.0596 | **-6.8% +- 1.8%** |
| rebellion | 0.0385 -> 0.0374 | -3.3% +- 8.8% | 0.0339 -> 0.0367 | -8.1% +- 23.2% |
| occupation switches | 0.0381 -> 0.0374 | -1.9% +- 0.7% | 0.0476 -> 0.0456 | -4.1% +- 1.7% |
| deaths | 0.01856 -> 0.01831 | -1.2% +- 0.6% | 0.01663 -> 0.01645 | -1.1% +- 0.7% |
| births | 0.01879 -> 0.01857 | -1.1% +- 0.5% | 0.01648 -> 0.01630 | -0.9% +- 0.6% |
| loyalty flips | 0.00653 -> 0.00664 | +1.1% +- 2.4% | 0.00224 -> 0.00209 | -8.2% +- 7.6% |
| final population | 541 -> 545 | +4.8 +- 11.4 | 186.5 -> 185.9 | -0.6 +- 5.2 |
| populated regions (end) | 19.64 -> 19.55 | -0.09 +- 0.33 | 5.06 -> 5.20 | +0.14 +- 0.13 |
| regional concentration (HHI of population shares, end) | 0.0728 -> 0.0723 | -0.0004 +- 0.0013 | 0.2595 -> 0.2444 | **-0.0152 +- 0.0070** |
| largest region's share | 0.114 -> 0.114 | +0.0004 +- 0.0025 | 0.336 -> 0.323 | -0.013 +- 0.008 |
| people in regions above capacity | 4.2% -> 3.4% | -0.8 +- 1.0 points | 5.1% -> 2.9% | -2.2 +- 1.5 points |

* Migration falls 5.3% and 6.8%, inside the predicted 5-7%.
* Occupation switches fall with it (1.9% and 4.1%): fewer arrivals take up
  a new trade. Deaths and births fall about 1%, and the population does
  not change.
* Template worlds end less concentrated: the HHI falls 0.015, about two
  standard errors. The largest region's share and the share of people
  above capacity fall too, within the noise. With the anchor, fewer people
  follow the pull into the most crowded regions. Procedural worlds have
  20 populated regions, not 5, and show no change.
* Rebellion and loyalty flips have no detectable change. Template
  rebellion comes in bursts: its rate ratio (1.08) and its paired log ratio
  (-8%) disagree in sign, and both are inside the noise.

### 5.2 Full gates with the switch on, against `main`

Exploratory comparisons (another configuration: `community_anchoring`
None against True), against `main`'s full-gate reports of PR #61, which
were re-scored:

| Full gate | `main` (PR #61) | switch on |
| --- | --- | --- |
| template: gate | PASS (strict), NO REGRESSION | PASS (strict), NO REGRESSION |
| template: migration per agent-turn (floor 0.05) | 0.0634 | 0.0586 |
| template: satisfaction mean | 0.6212 | 0.6209 |
| template: needs ablation | PASS (method 7) | PASS (method 8; design 2 keeps template forks every 100 turns): every pairing passes, safety 1.173 [1.027, 1.319] |
| template: kin roots, members | 0.988 FAIL | 0.992 FAIL |
| procedural: gate | PASS (strict), NO REGRESSION | PASS (strict), NO REGRESSION |
| procedural: migration per agent-turn | 0.0755 | 0.0717 |
| procedural: satisfaction mean | 0.5667 | 0.5708 |
| procedural: needs ablation | FAIL (material, design 1) | PASS (method 8, design 2): material 1.128 [1.108, 1.149], safety 1.101 [1.005, 1.196] |
| procedural: kin roots, members | 0.996 FAIL | 0.991 FAIL |

Every required oracle passes with the switch on, in both worlds. The
informational rows are the two cohort ablations (kin roots and the
community anchor). The template migration rate's distance to its strict
floor narrows from 0.0134 to 0.0086.

## 6. The procedural material pairing: fork design 2

### 6.1 Real exposure

Per pairing, from the procedural and template full gates of PR #61
(`ablation-oracles.md` section 3.1; design 1): q is the share of forks with
a cohort (from the seeds with one over their forks, forks taken as
independent), size the mean cohort of a fork that has one, h the ablated
arm's events per agent-turn, SE the realized seed-clustered standard error.

| Pairing | template: q, size, h, SE | procedural: q, size, h, SE | synthetic model of PR #61, procedural (q, size) |
| --- | --- | --- | --- |
| autonomy -> rebellion | 0.16, 44, 0.087, 0.071 | 0.51, 67, 0.076, 0.078 | 0.61, 44 |
| social -> migration | 1.00, 3.9, 0.057, 0.022 | 1.00, 42, 0.060, 0.016 | 1.00, 50 |
| purpose -> switch | 1.00, 33, 0.047, 0.014 | 1.00, 70, 0.035, 0.022 | 1.00, 66 |
| material -> migration | 0.53, 34, 0.051, 0.017 | **0.40, 9.0**, 0.065, **0.060** | 0.72, 28 |
| safety -> migration | 0.03, 19, 0.045, 0.094 | **0.15, 8.2**, 0.050, **0.100** | 0.28, 11 |

The procedural material cohort is 3.6 agents a fork on average (720
agent-forks over 200 forks, 63 informative seeds), a fifth of the model's.
`scripts/synth_ablation_oracles.py` now carries these measured exposures
(`template_gate`, `procedural_gate`) and the candidate designs; with them it
still underestimates the realized SE of the sparse pairings (procedural:
material 0.040 against 0.060, safety 0.078 against 0.100, autonomy 0.034
against 0.078: regional waves and frailty spread wider than modelled). The
power below therefore takes each pairing's **realized** SE and scales it
by the model's SE ratio between designs, with the normal approximation of
the pre-registered criterion, P(RR >= 1.10 and RR - t SE > 1) at Student t
on the informative seeds (`calibrated_power.py` with the run reports).

### 6.2 Power and the choice of design

| Procedural full, 100 seeds | material +15% / +20% | safety +15% / +20% | autonomy +20% | needs component +20% |
| --- | ---: | ---: | ---: | ---: |
| every 100 turns, 2 forks (design 1) | 0.80 / 0.95 | 0.42 / 0.61 | 0.81 | **0.47** |
| every 50 turns, 4 forks | 0.88 / 0.99 | 0.65 / 0.86 | 0.96 | 0.82 |
| 200 seeds, 2 forks | 0.88 / 0.99 | 0.66 / 0.87 | 0.96 | 0.83 |
| **every 20 turns, 9 forks (design 2)** | **0.96 / 1.00** | **0.86 / 0.98** | **1.00** | **0.98** |

* With its real exposure the procedural needs component had about half the
  power PR #61's pre-registration stated (0.47 at +20%, not 0.97-0.99): the
  material pairing itself had 0.95 at +20% but only 0.80 at +15%, and the
  binding pairing was safety (0.61).
* Forks every 20 turns from turn 100 (100, 120, ..., 260) tile the turns
  101-280 with disjoint windows: every agent-turn of the steady state is in
  exactly one window, the most exposure forks can give without overlap. It
  is the smallest spacing that restores the stated component power (0.98 at
  +20%); every 50 turns gives 0.82. More seeds would cost a plain run of 300
  turns each (twice the batch for 200 seeds) where a fork costs 22 turns.
* Cost: 900 forks per arm instead of 200 (checkpoints 4.5 GB at the peak,
  removed per seed once forked).
* **Template worlds keep design 1** (every 100 turns, 800 forks per arm).
  Their realized power at +20% is lower than stated too: safety 0.66,
  autonomy 0.88, component 0.58 (safety's cohort is at 3% of forks). Raising
  it the same way would need forks every 20 turns, 19 a seed (3,800 a
  arm); this branch reports it and leaves it (section 10).

### 6.3 The procedural full gate with design 2

`main`'s simulation (switch off, so the plain batch is `main`'s: every
metric delta against `main`'s report is 0), 100 seeds x 300 turns, forks
at 100, 120, ..., 260, arms `needs`, `kin_roots` and `placebo` (900 forks
each), frozen tree `e67c083`, extension SHA-256 `8497d374...`:

| Pairing | design 1 (PR #61: forks 100, 200) | **design 2 (9 forks a seed)** | placebo, design 2 |
| --- | ---: | ---: | ---: |
| autonomy -> rebellion | 1.468 [1.312, 1.624] (6,786; 76) | 1.440 [1.324, 1.556] (31,021; 85) PASS | 0.988 [0.975, 1.002] |
| social -> migration | 1.165 [1.133, 1.196] (8,303; 100) | 1.167 [1.148, 1.187] (35,982; 100) PASS | 0.999 [0.989, 1.010] |
| purpose -> switch | 1.259 [1.215, 1.302] (13,978; 100) | 1.280 [1.259, 1.301] (59,305; 100) PASS | 0.999 [0.982, 1.015] |
| **material -> migration** | **1.067 [0.947, 1.187] (720; 63) FAIL** | **1.119 [1.093, 1.145] (13,631; 100) PASS**, lower bound 1.097 | 0.991 [0.973, 1.009] |
| safety -> migration | 1.211 [1.004, 1.418] (240; 22) | 1.132 [1.049, 1.215] (1,026; 61) PASS | 0.954 [0.865, 1.042] |
| spiritual -> migration (reported) | 1.219 [1.194, 1.244] | 1.222 [1.202, 1.242] | 0.998 [0.992, 1.003] |
| needs ablation component | FAIL (material) | **PASS** | FAIL in every pairing, as it must |

(agent-forks in the cohort; informative seeds.) The gate: PASS (strict),
NO REGRESSION against `main`'s report, every metric delta 0, needs 7 -> 8
and cohort 4 -> 5 under "Oracle method changes" (`rebaseline_required`).

* **Material passes.** With the terms, agents below the material threshold
  migrate 11.9% more [9.3%, 14.5%]; the one-sided bound (1.097) clears no
  effect, the estimate clears the +10% minimum. The realized SE is 0.013,
  better than the 0.028 the power calculation expected: the cohort is 19
  times design 1's, not 4.5 times.
* **Why design 1 saw so few.** Re-scored on design 2's forks at 100 and 200
  only, the arms reproduce PR #61's estimates exactly (material 1.0672
  [0.9471, 1.1873], 1,001 / 938 moves, 720 agent-forks; every pairing
  equal). Material shortage comes in waves: the cohort is 403 and 317 at
  turns 100 and 200 but 3,534 at 140 and 4,747 at 220 (per fork turn
  1,044, 3,534, 858, 1,119, 317, 4,747, 412, 1,197 from 120 on), and the
  effect at the two old fork turns was 1.16 and 0.97. Two fixed fork turns
  sampled two quiet moments of a wave-driven exposure; nine forks sample the
  waves.
* **The term behaves as specified.** The effect grows with the depth of the
  deficit (the push is 0.5 x (0.30 - material)): 1.097 for material 0.20-0.30
  (half the cohort, push below 0.05), 1.121 for 0.10-0.20, 1.181 below 0.10.
  The cohort's moves are mostly famine-memory moves (48% of the plain arm's
  largest terms; material need itself 8.5%): the need adds to a push already
  there, so its relative effect is moderate. Agents in no deficit move 3.6%
  more with the terms (spillover), a third of the pairing's effect.
* **Placebo.** Every pairing sits at 1 with nine forks a seed (largest
  departure safety 0.954, interval across 1); no pairing passes. The
  seed-clustered bound stays calibrated with the denser forks.
* **Safety** (1.132 [1.049, 1.215], 61 informative seeds against 22) and
  the other pairings are measured more tightly; autonomy and spiritual are
  as before.
* **Kin roots** (cohort component, design 2): members' migration 0.992
  [0.989, 0.996] (407,516 agent-forks), FAIL as before; placebo 0.997.
* Cost: plain batch 1,045 s (with nine checkpoints a seed), arms 4,094 s
  for three arms (2,700 forks, 3.3 s at turn 100 to 5.3 s at turn 260, mean
  4.3 s), validation 637 s; 1 h 36 min in all. The two default arms take
  about 45 minutes (four times design 1's 9 minutes).

## 7. A stronger anchor (exploratory, not adopted)

This probe was run after the gates, so it asks a separate question: what
would meeting M53's number cost? Setup: template seeds 42-81 x 200 turns,
one fork at turn 100, the `community_anchor` arm, and the full anchor set
by `agents.community_full_anchor`. Ratios are plain / ablated migration
over the 20-turn window, +- the 95% half-width. Migration is per
agent-turn over the run, against the same seeds with the switch off
(0.0638). Cohorts per fork: members 6,314; non-members 1,114; four ties
983; no tie 3,019; spec members 1,789.

| Full anchor | migration | members | non-members | four ties | one to three | no tie | spec members | spec non-members |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.120 (calibrated) | 0.0607 (-4.9%) | 0.944 +- 0.037 | 0.902 +- 0.078 | 0.976 +- 0.072 | 0.931 +- 0.043 | 0.941 +- 0.038 | 0.969 +- 0.072 | 0.930 +- 0.037 |
| 0.24 | 0.0537 (-15.8%) | 0.811 +- 0.037 | 0.866 +- 0.113 | 0.739 +- 0.078 | 0.799 +- 0.042 | 0.857 +- 0.054 | 0.734 +- 0.055 | 0.848 +- 0.042 |
| 0.36 | 0.0498 (-21.9%) | 0.753 +- 0.041 | 0.739 +- 0.090 | 0.672 +- 0.063 | 0.705 +- 0.049 | 0.818 +- 0.052 | 0.659 +- 0.065 | 0.784 +- 0.039 |
| 0.60 | 0.0424 (-33.5%) | 0.651 +- 0.038 | 0.517 +- 0.061 | 0.447 +- 0.068 | 0.606 +- 0.036 | 0.718 +- 0.045 | 0.601 +- 0.058 | 0.646 +- 0.036 |

* At the calibrated anchor, the probe agrees with the full gate within its
  much wider intervals (one fork, 40 seeds).
* **Reaching the M53 number takes about twice the anchor.** At 0.24, the
  members' ratio is 0.81 and agents with four ties are at 0.74, inside the
  15-30% band. The cost: migration falls 16% over the whole run, and agents
  with no tie are held back almost as much (0.86). Members are still not
  separated from non-members (0.81 against 0.87, overlapping intervals).
  At 0.36 the run's migration rate (0.0498) is below the template gate's
  strict floor of 0.05. That floor is measured on 500-turn runs; these are
  200 turns.
* **Oracle 1's communities do separate at strength:** spec members 0.73
  against 0.85 at 0.24, 0.66 against 0.78 at 0.36. A stronger anchor does
  act on communities as the spec defines them. The oracle's own member
  cohort is too broad to show it.
* No anchor strength gives a consistent change in rebellion.

## 8. Versions and re-scoring

* **Fork design** (`chronicler.ablation_arms`, `ABLATION_DESIGN` 2; the
  manifest's `schema_version` is its design and design 2 also records
  `design`): design 1 forks every 100 turns from turn 100 in every world;
  design 2 forks every 20 turns from turn 100 in procedural worlds
  (`fork_every`; read from the plain manifest's `simulation.worldgen`) and
  every 100 in template worlds. `load_ablation_arms` checks each manifest
  against its own design's fork turns for the batch's turns and world, and
  records `design` in the report's `ablation_arms` from design 2 on (design
  1 summaries keep their bytes).
* **Needs method 8** (`NEEDS_ORACLE_METHOD_VERSION`): method 7 on design-2
  arms (the components also carry `fork_design`); estimator, cohorts,
  window, minimum effect and criteria unchanged. **Cohort method 5**:
  method 4 on design-2 arms plus `community_ablation`, the community
  anchor's component (`NOT_RUN` without the arm; reported, never deciding,
  in either causal mode).
* **Re-scoring**: `run_oracles` picks the methods from the arms' design
  (`validation_io.ablation_methods`): design-1 arms are scored by needs
  method 7 and cohort method 4, exactly as on `main` (their components keep
  their fields: no `fork_design`, no community component; the tests check
  it); a batch without arms by methods 8 and 5 (`NOT_RUN` components). A
  method refuses arms of the other design (`run_needs_oracle(...,
  method_version=7)` re-scores design-1 arms). `needs_method_7_result` and
  `cohort_method_4_result` still re-score saved components.
* **Comparator**: method 7 -> 8 and 4 -> 5 are reported under "Oracle
  method changes" with `rebaseline_required`, never as new or resolved
  failures (`tests/test_validation_ablation.py`).
* **Gate**: the community component is listed under causal evidence as
  `cohort_community` ("decides": false) and, when it does not pass, among
  the informational rows (`cohort_community_ablation`); nothing it says
  changes a verdict.

## 9. Identity, resume and tests

Builds: fresh release extensions (`maturin develop --release --locked`,
`CARGO_TARGET_DIR` and the virtual environments outside the checkout),
the compiled submodule and its three simulator classes checked before any
run: `main` `b1c9274` (SHA-256 `6f5c5d6a...`, the same bytes as PR #61's
merged build) and this branch at `e67c083` (`8497d374...`), the tree every
gate and identity run used (a `git archive` export). The commits after it
change no simulation code (a tuning-key registration, tests, documents).

* **Switch off, byte-identical to `main`**: `scripts/turn_speed_identity.py`,
  the 9-case matrix (hybrid seeds 42, 7 and 1234, off-mode 42 and 7,
  procedural 48 regions hybrid and off, scaled 22k and 52k agents), `main`'s
  tree and extension against the branch's: **399 files, 0 differences**.
  Hybrid batches with validation sidecars, `main` against the branch:
  template seeds 42-51 x 200 turns **1,110 files**, procedural 32 x 10
  seeds 42-44 x 200 **351 files, 0 differences**. The procedural full
  gate's plain batch (design 2's checkpoints at nine turns) reproduces
  `main`'s report: every metric delta 0.
* **Exact resume with the switch on** (`scripts/checkpoint_identity.py`,
  resumed at every turn): hybrid seed 42 x 60 turns (59 resume points,
  1,780 files), procedural 32 x 8 seed 11 x 40 (39, 1,176), and seed 7 with
  scholarship and the `community_anchor` ablation from turn 20 x 60 (59,
  1,780): **0 differences**; each straight run with checkpoints equals the
  plain one.
* **Native**: the switch and its checkpoint state; the validator's ties
  equal the native ties agent for agent on a 60-turn run; an anchored run
  differs from the plain one, and its `community_anchor` arm from turn 0
  decides exactly as the plain run (the anchor draws nothing); a zero full
  anchor (tuning override) equals the plain run; an anchored run resumes
  exactly (`tests/test_community_anchoring_native.py`). Rust: the anchor
  only turns moves into other choices and draws the same numbers, off and
  ablated equal the plain decision, ties need a shared memory, a home
  region, a positive bond and a non-kin tie (`community.rs`,
  `behavior.rs` `ablation_tests`, `scale.rs`).
* **Tests** (final tree, after the last commit that changes code): `cargo test --locked`
  1,070 passed, 0 failed (36 targets); not-slow 6,756 passed, 3 skipped,
  0 failed; `python scripts/run_python_oracle_checks.py` PASS (13 chunks,
  2,735 passed, 59 skipped, 0 failed). New:
  `tests/test_community_anchoring.py`, `tests/test_community_anchoring_native.py`,
  the Rust tests above; updated: the ablation and validation tests for
  methods 8 and 5 and fork design 2 (both designs loaded and scored, each
  method refusing the other design's arms, the comparator's method
  changes), the dormant-field list, the migration budget's keys.

## 10. Decisions

### 10.1 Community anchoring

* **The switch stays off by default and experimental.** It is not
  promoted at any strength, and the calibrated full anchor (0.120143)
  remains its default.
* **The term does what it says, but weakly over the window.** It holds
  movers back in proportion to their ties (dose holds in both worlds) and
  draws no numbers. Switched on, migration falls 5-7% and every gate
  passes. The pre-registered mechanism criterion failed, though: agents
  with four ties are at 0.87 and 0.90, against 0.70-0.85. So did the
  specificity criterion: agents with no tie are at 0.93 and 0.95, against
  0.97-1.03.
* **The stronger anchor is not adopted** (section 7). Meeting M53's
  member-level 15% takes about twice the anchor. That cuts all migration by
  about 16% and holds back agents without ties almost as much, and it
  still does not separate the oracle's members from its non-members.
  Tuning to the oracle's number would buy a pass, not a mechanism.
* **M53 oracle 4's anchoring claim is recorded as not reproduced.** The
  claim is that community members migrate 15-30% less. Neither term meets
  it: the kin roots give 0.99, and the community anchor gives 0.91
  (template) and 0.94 (procedural) at its calibrated strength. The cohort
  oracle's causal components (kin roots, community anchor) stay reported
  and never decide, and `--require-causal-oracles` stays off. Cohort method
  3's observational verdict is unchanged: PASS, non-discriminating.
* **The restated claim was pre-registered and is not adopted.** It
  required a 15-30% reduction for agents with four counted ties, an upper
  bound below 1, no-tie agents within 0.97-1.03 and dose ordering. It
  failed on the minimum effect in both worlds, and on specificity. Dose
  held.

### 10.2 Fork design 2

* **Adopted.** Procedural full gates now fork every 20 turns from turn 100
  (needs method 8, cohort method 5); template full gates keep every 100.
  With the real exposure, the procedural needs component passes: material
  1.119 [1.093, 1.145] on `main`'s simulation and 1.128 with the switch on.
  The placebo arm stays at 1 throughout.
* **Cost:** the two default arms take about 45 minutes in a procedural full
  gate, against 9 before.
* **Template power is reported, not raised:** safety 0.66 and the needs
  component 0.58 at +20%. Raising them would need 19 forks a seed. Both
  template full gates passed every pairing anyway (safety 1.230 on `main`,
  1.173 with the switch on).

### 10.3 Follow-ups

* **Community detection as oracle 1 specifies it, as a new community oracle
  method.** That means friend, co-religionist and kin edges weighted by
  sentiment, within a region, the kin code corrected, and the spec's size
  and count criteria. The cohort oracle would then compare those
  communities. `validation_ablation.detect_spec_communities` already
  computes them (informational). With that cohort the anchoring question
  can be asked again: a stronger anchor does separate spec members from
  non-members (section 7).
* **The calibration model should count the deferral of a persistent reason
  to move.** Over the 20-turn window the effect is about half the
  per-decision one.
