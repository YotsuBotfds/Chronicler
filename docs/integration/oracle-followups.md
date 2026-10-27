# Oracle follow-ups (2026-10)

Branch `fix/oracle-followups` from `main` `3c3775d` (PR #55, needs oracle
method 5), fast-forwarded to `6da8fe5` (PR #56, narration provenance:
narration only, no oracle input changes) before any commit. Validation
tooling only: the cohort oracle, the needs oracle, the cohort re-score script
and tests. No simulation code changed; every gate batch below is `main`'s
simulation.

PR #55 (`procedural-drift.md` section 5) left three questions:

| Question | Finding | Decision |
| --- | --- | --- |
| 1. Do deaths bias the cohort oracle? | Yes, its effect sizes: in a world where membership changes nothing and members die more, method 2 reads members migrating less (d +0.221) and rebelling less (+0.188); with the observed mortality contrast, +0.032. But the oracle passes every synthetic world, deaths or not, with no effect or a reversed one: its verdict cannot fail (section 1.4) | **Cohort method 3**: each member against its matched control while both live. Effect bias removed (within 0.010 of zero); verdicts unchanged |
| 2. Does age confound the needs pairs? | Partly, and the signal sits in large age gaps: pairs within 5 years of age carry little of method 5's concordance. Re-matched within 5 years, the template full gate reads +0.106 pooled / +0.027 binding (unmatched +0.166 / +0.191), the procedural full gate +0.036 / -0.040 (+0.091 / +0.134). A synthetic age confound passes method 5 in 90% of batches and a 5-year age match in none, but the match keeps 8-11% of the informative pairs, detects a real effect in 2-25% of batches and fails both full gates' seed fraction (93 of 200, 47 of 100) | **Not adopted**: it costs too much power; numbers documented (section 2). The needs verdict stays method 5's |
| 3. Is there a spiritual pairing? | Spiritual need drives migration (a push below 0.30) and sect recruitment; conversion does not read it. Migration is in the agent event stream, sect membership is not | **Needs method 6**: method 5's verdict plus the spiritual -> migration pairing reported beside it, never deciding. Its pairs are mostly cross-faith (section 3) |

New method versions: `COHORT_ORACLE_METHOD_VERSION = 3`,
`NEEDS_ORACLE_METHOD_VERSION = 6`. `run_cohort_oracle(..., method_version=2)`
and `run_needs_oracle(..., method_version=5)` re-score the old methods
exactly, verified on every new batch below; the comparator reports 2 against
3 and 5 against 6 as method changes (`rebaseline_required`). No threshold
changed.

## Method

Linux, Python 3.13.17, `PYTHONHASHSEED=0`, hybrid. One venv
(`uv sync --frozen`) with a release extension built fresh from `main`'s tree
(`maturin develop --release --locked`, its own `CARGO_TARGET_DIR`; compiled
module and `AgentSimulator`, `EcologySimulator`, `PoliticsSimulator`
checked): SHA-256 `99c1e1d5...e12f`, the same bytes as the method 5 gates'
extension. This branch changes no Rust.

**Exploration batches.** The template and procedural subset cohorts (seeds
42-61, 200 turns; procedural 32 regions, 10 civs) were run on `main`'s tree
with an observation-only probe that records, at every needs snapshot, each
agent's age, belief, movement and household fields from the native agent
snapshot (`get_snapshot`, the batch the bridge itself reads at that point).
It only reads: seed 42 x 40 turns with and without it gives identical files,
and both subset gate batches below equal their probe batches in all 2,000
hashed sidecar inputs each and every bundle (without `generated_at`). The probe and
analysis scripts are kept with the run reports, not in the repository.

**Retained sets.** The procedural-drift pair tables (every method 5 pair of
the procedural full gate cohort, 100 x 300, and of the template full gate's
first 80 seeds, both agents' ages from that branch's probe; `main`'s
simulation) and the needs-followups full gate's sidecars (`full-head`, 200 x
500, the `d44cf4f` simulation: needs and agent events only).

## 1. The cohort oracle and deaths

### 1.1 What it compares

Per seed the oracle takes the best eligible snapshot (`_cohort_candidate_priority`).
At a snapshot it detects communities (bonds and shared memories), finds for
each member the first non-member of its civ, region and occupation with
satisfaction within 0.10, and compares the members' and controls' counts of
migrations and of rebellions over turns t+1 .. t+20 (method 2): Cohen's d,
control minus member. A seed counts when migration is lower among members or
rebellion higher, and its larger |d| of the two exceeds 0.10; PASS takes 60%
of seeds and a median above 0.10.

Method 2 counts each agent over its own lifetime in the window. An agent that
dies early has fewer turns to act, so if members die more than controls the
members read as migrating and rebelling less.

### 1.2 Deaths on real batches

The subset exploration batches and the template full gate batch (`main`'s
simulation), every eligible snapshot, the members and controls as the oracle
chooses them:

| Measure (rows: agents at a snapshot) | Template subset | Procedural subset | Template full (200 x 500) |
| --- | --- | --- | --- |
| snapshots with communities | 341 of 360 | 342 of 360 | 9,393 of 9,600 |
| communities per snapshot, median; members per community, mean | 3; 37 | 14; 30 | 3; 39 |
| member rows with a matched control | 23% | 24% | 23% |
| died in the window: all members / controls | 32.3% / 27.1% | 34.0% / 30.9% | 31.0% / 28.0% |
| died in the window, matched pairs: member / control | 27.5% / 27.1% | 30.6% / 30.9% | 28.4% / 28.0% |
| member age, median (probe); control | 38; 32 | 34; 27 | (no probe) |
| migrations per window: matched members / unmatched members / controls | 1.153 / 1.122 / 1.149 | 1.322 / 1.301 / 1.318 | 1.066 / 1.085 / 1.065 |
| rebellions per window: matched members / unmatched members / controls | 0.732 / 0.949 / 0.680 | 0.570 / 0.792 / 0.523 | 0.500 / 0.666 / 0.469 |

Members die more than their controls (they are older), mostly the 77% of
members who have no matched control: method 2 counts them against the other
members' controls. Matched pairs die alike. Pooled over every snapshot,
matched members and their controls migrate at the same rate.

### 1.3 Synthetic worlds

`synth_cohort.py`: 20 replicated batches of 20 seeds x 200 turns per world,
sized like the template subset's snapshots (about 190 living agents, 85%
members, communities of about 40, cells of 24), event rates as measured
(1.15 migrations and 0.7 rebellions per agent and window), deaths replaced
by newborns. Membership changes nothing unless stated. The verdict is the
oracle's; d is the per-snapshot effect at every eligible snapshot (no
selection; control minus member, so positive is "members do less";
seed-clustered standard errors in brackets):

| World | Method 2 PASS | Method 3 PASS | Migration d, method 2 | Migration d, method 3 | Rebellion d, method 2 | Rebellion d, method 3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| no effect, equal mortality (1.6% a turn) | 100% | 100% | -0.007 (0.005) | -0.001 (0.006) | +0.001 (0.005) | -0.005 (0.006) |
| no effect, observed mortality (members 1.95%, others 1.57%) | 100% | 100% | **+0.032** (0.005) | -0.005 (0.006) | **+0.022** (0.004) | -0.003 (0.006) |
| no effect, members die more (3.0% / 0.5%) | 100% | 100% | **+0.221** (0.004) | -0.002 (0.004) | **+0.188** (0.004) | +0.010 (0.004) |
| no effect, others die more (0.5% / 3.0%) | 100% | 100% | **-0.210** (0.009) | -0.004 (0.014) | **-0.160** (0.009) | +0.009 (0.014) |
| members migrate x0.7, equal mortality | 100% | 100% | +0.339 (0.005) | +0.297 (0.006) | -0.008 (0.005) | +0.003 (0.006) |
| members migrate x0.7, others die more | 100% | 100% | **+0.114** (0.010) | +0.324 (0.015) | **-0.184** (0.008) | +0.006 (0.014) |
| reversed (members migrate x1.3, rebel x0.7), equal mortality | 100% | 100% | -0.266 (0.004) | -0.251 (0.006) | +0.258 (0.005) | +0.244 (0.006) |
| reversed, members die more | 100% | 100% | **-0.038** (0.004) | -0.248 (0.004) | **+0.438** (0.004) | +0.232 (0.004) |

Deaths bias method 2 by as much as a real effect: differential mortality
alone gives |d| of 0.16-0.22, halves a true migration effect (+0.34 ->
+0.11), invents a rebellion effect (-0.18) and hides a reversed migration
effect (-0.27 -> -0.04). Method 3 reads every null within 0.010 of zero and
every effect as with equal mortality.

### 1.4 The oracle cannot fail

Every world above passes under both methods, including the reversed one
(members migrate more and rebel less, 95-98% of seeds counted). Three rules
compound: the best of 18 eligible snapshots per seed, the expected direction
in either behaviour, and the effect size taken from the larger of the two
behaviours, which need not be the one in the expected direction. With a few
matched controls per snapshot (13 on the template subset) a noise d of
0.3-0.5 clears 0.10 at some snapshot of almost every seed. Deaths cannot
raise a pass rate that is already 100%; method 3 removes their bias from the
measured effects, which is what it can do. The verdict needs a redesign
(open, section 5): for example method 2 of the needs oracle's approach,
every snapshot's matched pairs pooled per behaviour with a pre-stated
direction and a seed-clustered bound.

### 1.5 Method 3

`COHORT_ORACLE_METHOD_VERSION = 3` keeps method 2's communities, matching,
window (t+1 .. t+20), snapshot choice, criteria and thresholds, and compares
each member with its matched control over the turns both were alive: the
pair's window ends at the first death of either (that turn's events count,
as in needs method 5; a dead agent has no later events). A member without a
matched control has no partner to share its turns with and is left out
(method 2 counted it against the other members' controls). Deaths come from
`agent_events.arrow` (`run["deaths"]`, `_load_agent_deaths`); a run without
them is scored as uncensored matched pairs. Results add `comparison:
"matched_pairs"` and `outcome_censoring: "first_death_in_pair"`, and per seed
the chosen snapshot's `pairs` and `censored_pairs`.
`run_cohort_oracle(runs, method_version=2)` re-scores method 2 exactly
(method 2 results keep their bytes); `scripts/rescore_cohort_oracle.py` now
scores methods 1, 2 and 3.

On real batches the verdicts do not move: every seed of all four gates
counts under both methods (section 4). Method 3's effects are noisier, since
it uses fewer agents: a median of 3 matched pairs at a template seed's
chosen snapshot (subset and full) and 6 at a procedural full seed's, and 40-49%
of those pairs are cut short by a death. On the template full gate its median
effect is 2.0: with three pairs whose counts do not vary within a group,
`_cohen_d` returns the raw difference of means. That degenerate effect size
is another face of section 1.4, not of the censoring.

## 2. Age in the needs pairs

### 2.1 How much of method 5's concordance goes with age

Age enters behaviour directly: no healthy-world migration driver below 20
(`migration_drivers::MOBILITY_MIN_AGE`), roots of 0.006 a year past 35
(`ROOTS_PER_YEAR`), social restoration scaled by age / 40 (`needs.rs`),
mortality steps at 20 and 60. The needs sidecar carries no age; the
procedural-drift pair tables do (the probe's ages for both agents of every
method 5 pair). Net concordance (seed-clustered lower bound) of the pooled
and binding pairs by the pair's age gap, high-need agent's age minus the
low-need agent's:

| Method 5 pairs | Procedural full, pooled | Procedural, binding | Template (80 x 500), pooled | Template, binding |
| --- | --- | --- | --- | --- |
| all | +0.091 (+0.066), 4,781 | +0.134 (+0.098), 1,984 | +0.169 (+0.131), 3,144 | +0.164 (+0.116), 1,620 |
| high-need agent older | +0.100 (65% of pairs) | +0.121 (55%) | +0.212 (68%) | +0.215 (52%) |
| high-need agent younger | +0.081 | +0.160 | +0.079 | +0.114 |
| age gap within 5 years | +0.077 (+0.003), 542 | -0.012 (-0.130), 247 | +0.004 (-0.113), 251 | -0.103 (-0.240), 107 |
| within 10 years | +0.067 (+0.014), 995 | +0.002 (-0.085), 429 | +0.024 (-0.056), 506 | -0.043 (-0.151), 230 |
| within 20 years | +0.039 (-0.003), 1,840 | +0.041 (-0.022), 797 | +0.097 (+0.040), 994 | +0.037 (-0.042), 484 |
| gap 21-40 years (high older) | +0.137 | +0.130 | +0.251 | +0.290 |
| gap over 40 years (high older) | +0.132 | +0.256 | +0.236 | +0.305 |
| gap over 40 years (high younger) | +0.077 | +0.247 | +0.120 | +0.186 |

The higher-need agent is older in 65-68% of informative pooled pairs. A
linear fit of the pair's sign on its age gap attributes +0.006 of +0.091
(procedural) and +0.026 of +0.169 (template) to the direction of the gap:
little. But the concordance is not spread over the pairs: pairs whose ages
are close carry almost none of it, and pairs a generation or more apart
carry most of it, whichever agent is older. That pattern is not a one-way
age effect; it says the association the oracle reads lives in pairs that
differ by much more than their need.

Matching instead of selecting (candidate method 6: pairs matched as method 5
plus ages within a tolerance; age from the agent's birth event, so the
founders placed at world creation, whose age the event stream does not
record, are not paired), on the retained 200 x 500 template set:

| `full-head` (200 x 500) | Pooled net (lb), seeds of 200 (120 needed), informative | Binding net (lb), informative | Full gate |
| --- | --- | --- | --- |
| method 5 | +0.170 (+0.150), 168, 8,127 | +0.197 (+0.170), 4,175 | PASS |
| founders left out, no age limit | +0.184 (+0.163), 160, 6,976 | +0.205 (+0.175), 3,627 | PASS |
| ages within 40 years | +0.156 (+0.132), 149, 4,754 | +0.188 (+0.153), 2,400 | PASS |
| within 20 years | +0.097 (+0.064), 120, 2,487 | +0.144 (+0.097), 1,196 | PASS (at the seed fraction) |
| within 10 years | +0.058 (+0.013), 100, 1,319 | +0.113 (+0.049), 613 | FAIL (seed fraction) |
| within 5 years | +0.036 (-0.026), 84, 716 | +0.097 (+0.007), 339 | FAIL (bound, seed fraction) |
| same life stage (0-19, 20-34, 35-59, 60+) | +0.058 (+0.018), 103, 1,537 | +0.121 (+0.066), 733 | FAIL (seed fraction) |

Leaving the founders out does not lower the concordance; tightening the age
match does. On this older set the pooled pairs lose most of theirs at 5
years and the binding pairs half; on `main`'s template full gate (2.3) it is
the other way round. At 300-700 informative pairs either component sits
within one or two standard errors of zero, and of the other; the seed
fraction fails on both sets.

### 2.2 Synthetic null and positive worlds

`synth_needs_age.py`: 40 replicated batches of 100 seeds per world, needs
snapshots every 10 turns (turns 100-290), 20 cells of 8 agents, ages uniform
0-80 (births recorded), traits uniform 0-0.8 (the oracle's 0.1 tolerance
applies), calibrated to about 26-40 informative pooled pairs per seed (the
real full gates have 40-48). Material need is `0.17 + 0.004 x age` plus noise
(sd 0.08) in the confounded worlds (needs rise with age), 0.33 plus noise
otherwise. A migration hazard per turn of `0.025 x f(age)`, f 0.6 below 20,
1.4 at 20-35, falling 0.025 a year after (roots), times `1 + effect` below
the threshold 0.30 when the need acts. Full-profile verdicts (pass rate of
the 40 batches) and mean net concordance, pooled (binding):

| World | Method 5 | Ages within 5 | within 10 | within 20 | Method 5 net | Within 5 net | Within 20 net | Informative pairs per seed, method 5 / within 5 |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| needs say nothing, no age link | 0% | 0% | 0% | 0% | -0.004 (-0.001) | -0.005 (-0.003) | -0.007 (-0.001) | 26.1 / 3.4 |
| needs say nothing, need rises with age | **90%** | 0% | 0% | 0% | +0.081 (+0.053) | +0.003 (+0.011) | +0.007 (-0.007) | 39.2 / 3.4 |
| need acts (x1.6 below 0.30), no age link | 100% | **25%** | 95% | 100% | +0.226 (+0.289) | +0.226 (+0.304) | +0.236 (+0.303) | 29.2 / 3.9 |
| need acts (x1.6), need rises with age | 100% | **5%** | 62% | 100% | +0.279 (+0.335) | +0.182 (+0.312) | +0.185 (+0.298) | 43.9 / 3.9 |
| need acts weakly (x1.3), need rises with age | 100% | **2%** | 5% | 52% | +0.191 (+0.210) | +0.099 (+0.171) | +0.106 (+0.158) | 41.8 / 3.7 |

An age link of this size makes method 5 pass needs that say nothing in 90%
of batches and inflates a real effect by half or more (+0.279 against
+0.182; weak, +0.191 against +0.099); matching ages removes it (nulls within
0.01 of zero, no false pass). But at a 5-year tolerance a
seed keeps 3-4 informative pairs, the 60% seed fraction cannot be met, and
the oracle detects a real effect in 2-25% of batches. Ten years recover
most of the power where the effect is strong; twenty years recover it in
this world, whose age effects are smooth.

### 2.3 Power on real batches

Candidate method 6 (ages from birth events) on the subset batches and the
fresh full gates (section 4; `main`'s simulation): pooled net (lower bound),
seeds with C > D, informative pairs; binding net (lower bound); the verdict
with full-profile rules.

| Variant | Template subset (20 x 200) | Procedural subset (20 x 200) | Template full (200 x 500) | Procedural full (100 x 300) |
| --- | --- | --- | --- | --- |
| method 5 | +0.196 (+0.082), 14, 336; +0.240 (+0.080); PASS | +0.046 (-0.021), 11, 711; +0.060 (-0.069); FAIL | +0.166 (+0.144), 154, 8,114; +0.191 (+0.164); PASS | +0.091 (+0.066), 72, 4,781; +0.134 (+0.098); PASS |
| founders out, no age limit | +0.282 (+0.140), 17, 209; +0.302 (+0.092); PASS | +0.115 (+0.037), 12, 463; +0.151 (-0.006); FAIL | +0.175 (+0.152), 152, 7,002; +0.192 (+0.164); PASS | +0.089 (+0.061), 66, 3,567; +0.131 (+0.090); PASS |
| within 40 years | +0.263 (+0.084), 14, 160; +0.313 (+0.050); PASS | +0.098 (+0.010), 10, 366; +0.131 (-0.040); FAIL | +0.158 (+0.131), 146, 4,829; +0.157 (+0.122); PASS | +0.081 (+0.045), **58**, 2,658; +0.088 (+0.041); FAIL |
| within 20 years | +0.221 (+0.034), 14, 95; +0.100 (-0.173); FAIL | +0.072 (-0.060), 8, 222; +0.196 (-0.004); FAIL | +0.090 (+0.053), **118**, 2,489; +0.069 (+0.019); FAIL | +0.031 (-0.016), 50, 1,539; +0.024 (-0.046); FAIL |
| within 10 years | +0.120 (-0.138), 8, 50; -0.053 (-0.509); FAIL | +0.016 (-0.095), 9, 124; +0.077 (-0.156); FAIL | +0.084 (+0.037), **101**, 1,308; +0.033 (-0.035); FAIL | +0.029 (-0.029), 49, 873; -0.036 (-0.127); FAIL |
| within 5 years | +0.259 (-0.156), 6, 27; -0.091 (-0.639); FAIL | -0.013 (-0.196), 4, 77; -0.086 (-0.380); FAIL | +0.106 (+0.044), **93**, 680; +0.027 (-0.067); FAIL | +0.036 (-0.041), 47, 506; -0.040 (-0.155); FAIL |
| same life stage | +0.158 (-0.141), 9, 57; +0.200 (-0.169); FAIL | +0.042 (-0.104), 8, 142; +0.051 (-0.185); FAIL | +0.104 (+0.061), **98**, 1,494; +0.034 (-0.032); FAIL | +0.016 (-0.039), 48, 986; -0.037 (-0.135); FAIL |

With the probe's exact ages (founders paired too) the subsets read the same
within a few pairs (template within 5 years: 30 informative pairs, +0.200,
bound -0.194).

### 2.4 Decision

Age matching is not adopted: it costs too much power. The tolerance the
code's age effects call for is about 5 years (it holds a pair's roots
difference to 0.03, a fifth of a full need push of 0.15, and its
social-restoration multiplier difference to 0.125). At 5 years every real
batch with the need terms on fails the full profile: a seed keeps 3-5
informative pairs, so the seed fraction fails structurally (93 of 200 and
47 of 100 seeds against 120 and 60), and one component's bound falls below
zero (binding +0.027 on the template full gate; both components on the
procedural one). In the synthetic worlds the same match detects a real
effect in 2-25% of batches. Only 40 years passes the template full gate, and
nothing passes the procedural one; a 40-year tolerance leaves the gaps that
carry the signal, and choosing a tolerance by which gate it passes would be
tuning.

What the numbers say about method 5 is for the needs oracle's owners to
decide: a synthetic age link of the simulation's size passes it with needs
that say nothing, and on real batches its concordance concentrates in pairs
a generation apart. Its verdict is unchanged here. The age-matching code is
kept with the run reports (it reads ages from birth events, which every
batch has; the founders' ages are not in any sidecar).

## 3. A spiritual pairing

### 3.1 What spiritual need drives

* **Migration.** `needs::compute_need_utility_modifiers`: below
  `SPIRITUAL_THRESHOLD` (0.30) the deficit times `SPIRITUAL_WEIGHT` (0.4) is
  added to the migrate utility, as safety, material and social are, with its
  own driver term (`spiritual_need`, code 13 in `MIGRATION_DRIVER_NAMES`).
* **Sect movements.** `movements::grievance` for creed `CREED_SECT` reads
  the spiritual need (below 0.45, with satisfaction below the grievance
  line, adults only): it recruits sect members.
* **Not conversion.** `conversion_tick` converts by the region's conversion
  rate and the agent's satisfaction; it does not read the need.
* **No pilgrimage or temple attendance** exists as an agent behaviour.
  Temples and sharing the region's majority faith restore the need; they are
  conditions, not choices.

The agent event stream (`agent_events.arrow`) records migrations (with their
driver), rebellions, occupation switches, loyalty flips, births, deaths and
dissolutions. It does not record conversions (each event row carries the
agent's belief, but nothing marks a change) or movement membership. So the
one behaviour that can be paired with the spiritual need from the sidecars is
migration.

### 3.2 Needs method 6

`NEEDS_ORACLE_METHOD_VERSION = 6` keeps method 5's pairs, criteria, pooled
totals, binding component and verdict, and reports `informational_pairings`:
`spiritual` with event type migration, `required: false`, its pairs and its
binding pairs (threshold 0.30, the gap and matching of the other binding
pairs), each with concordant and discordant counts, informative pairs, seeds
with informative pairs, net concordance, its seed-clustered standard error
and one-sided bound; per seed, `informational.spiritual` (`[pairs,
concordant, discordant]` for both). The spiritual pairs are censored at the
pair's first death as the others are, but are not in `censored_pairs`, the
pooled totals or any criterion. `run_needs_oracle(..., method_version=5)`
re-scores method 5 exactly (no informational key).

### 3.3 What it reads

The spiritual pairing on the gate batches (method 6, `main`'s simulation):
concordant / discordant, net (seed-clustered lower bound):

| Batch | Spiritual pairs | Spiritual binding pairs | Method 5 verdict (same batch) |
| --- | --- | --- | --- |
| template subset (20 x 200) | 61 / 46, +0.140 (-0.029) | 25 / 25, 0.000 (-0.332) | PASS |
| procedural subset (20 x 200) | 198 / 143, +0.161 (+0.037) | 119 / 94, +0.117 (-0.032) | FAIL (pre-existing) |
| template full (200 x 500) | 1,891 / 1,696, +0.054 (+0.024), 200 seeds | 829 / 705, +0.081 (+0.038), 191 seeds | PASS |
| procedural full (100 x 300) | 1,333 / 1,087, +0.102 (+0.066), 100 seeds | 815 / 622, +0.134 (+0.088), 100 seeds | PASS |

The procedural full numbers equal the informational spiritual pairing that
`procedural-drift.md` (section 1.4, +0.102) scored with its own script on
the same simulation (its retained counts: 1,333 / 1,087, binding 815 /
622). The pairing has power at full scale (both bounds positive on both
worlds) and not in a subset (template bound -0.029, binding pairs tied).

Within a cell the spiritual need differs mostly by faith: sharing the
region's majority faith restores it, so 77-84% of informative spiritual
pairs and binding pairs (the exploration subsets, faith from the probe) are
two agents of different faiths. The lower-need agent's migrations in
those pairs are driven by famine memory first; persecution and persecution
memory drive 22% (template) and 12% (procedural), the spiritual-need term
itself 5% and 14%. So the pairing reads a minority faith's persecution as
well as the spiritual push, as the material and safety pairings read their
conditions (`needs-calibration.md` section 4). It has not been run against a
build with the need terms zeroed.

Not required for any gate: it has power only at full scale, and what it
measures is not yet separated from persecution. A gate decision comes later.

## 4. Gates, re-scores, tests

### 4.1 Gates

All four gates ran from a frozen copy of the branch at `99bfb7d` (`6da8fe5`
plus the oracle commit; later commits change tests and documents only), in
the venv above (extension `99c1e1d5...e12f`, built from `3c3775d`'s
`chronicler-agents`, identical in `6da8fe5` and the gate tree),
`PYTHONHASHSEED=0`, each in a fresh empty output root, one full gate on the
machine at a time; subsets with `PYTHON_CPU_COUNT=2`, full gates without it
(as the baselines ran):

```
python scripts/m53b_run_validation.py --profile subset --parallel 1 --output-root <fresh>
python scripts/m53b_run_validation.py --profile subset --worldgen procedural --parallel 2 --output-root <fresh>
python scripts/m53b_run_validation.py --profile full --parallel 3 --require-strict-regression \
  --output-root <fresh> --baseline-report <method 5 template full report (procedural-drift section 4)>
python scripts/m53b_run_validation.py --profile full --worldgen procedural --parallel 3 \
  --require-strict-regression --output-root <fresh> \
  --baseline-report <method 5 procedural full report (procedural-drift section 4)>
```

| Gate | Verdict | Comparison | Needs, method 6 (method 5's numbers): pooled (lb), seeds | Binding (lb) | Cohort, method 2 -> 3: seeds, median effect |
| --- | --- | --- | --- | --- | --- |
| template subset, 20 x 200 (126 s) | PASS, exit 0 | against `main`'s report of the batch: NO REGRESSION | +0.196 (+0.082), 14 of 20 (12 required) | +0.240 (+0.080), informational | 20 / 20, 1.249 -> 20 / 20, 1.524 |
| procedural subset, 20 x 200 (220 s) | **FAIL**, exit 2: needs | against `main`'s report of the batch: NO REGRESSION (`main` FAIL / FAIL) | +0.046 (-0.021), 11 of 20 | +0.060 (-0.069), informational | 20 / 20, 0.915 -> 20 / 20, 0.750 |
| template full, 200 x 500 (1,562 s) | PASS strict, exit 0 | against the method 5 baseline: NO REGRESSION, exit 0 | +0.166 (+0.144), 154 of 200 (120 required) | +0.191 (+0.164) | 200 / 200, 1.536 -> 200 / 200, 2.000 |
| procedural full, 100 x 300 (1,758 s) | PASS strict, exit 0 | against the method 5 baseline: NO REGRESSION, exit 0 | +0.091 (+0.066), 72 of 100 (60 required) | +0.134 (+0.098) | 100 / 100, 0.943 -> 100 / 100, 1.000 |

* **The procedural subset's failure is `main`'s.** `main`'s own oracle
  fails the same batch with the same numbers (method 5; method 4 too, +0.093
  (+0.033), 11 of 20: `production-ledger.md` records it since PR #52's
  mine-soil correction, the full gates deciding). It is not required for
  this branch's decision and not caused by it.
* **Both full gates**: the comparison lists two method changes, cohort 2 ->
  3 and needs 5 -> 6 (PASS / PASS each), `rebaseline_required`, no new or
  resolved required failure, no regression reason; the twelve regression
  metric deltas are 0.0. Every other oracle result (arcs, artifacts,
  community, determinism SKIP, era, regression) is JSON-equal to the
  baseline report's. Other oracles PASS as in the baselines (artifacts and
  regression strict).
* A first template full attempt was stopped by a session time limit at 194
  of 200 seeds, before any report; its output root was deleted and the gate
  rerun in a fresh one (the table's run).

### 4.2 Old against new on every batch

Each gate batch was also scored by `main`'s validator (the frozen `3c3775d`
tree: `python -m chronicler.validate --batch-dir <batch> --oracles all
--profile <profile>`), and that report compared with the gate's by this
branch's comparator (`python -m chronicler.validation_compare --profile
<profile> --baseline-report <main's> --current-report <gate's>
--fail-on-regression`). For all four batches:

* NO REGRESSION, exit 0; exactly the two method changes; every other oracle
  result JSON-equal; no other report field differs.
* This branch's `run_needs_oracle(..., method_version=5)` and
  `run_cohort_oracle(..., method_version=2)` equal `main`'s needs and
  cohort results field for field; method 6 without its informational keys
  equals method 5 (pooled totals, binding component, censored counts and
  every per-seed tally); methods 6 and 3 re-scored equal the gate's.
* For the full gates, `main`'s needs and cohort results of the new batches
  also equal the method 5 baseline reports' (the same simulation), so the
  oracle change is the only difference from the baselines.

### 4.3 Tests

* New in `tests/test_validate.py`: cohort method 2 passes on mortality
  alone and method 3 does not (and the mirror image, and no deaths); the
  method 3 window ends at the pair's first death, either agent, that turn
  included (five cases); members without a matched control left out;
  method 2 results keep their bytes; the spiritual pairing reported without
  deciding (a spiritual-only world fails; its counts, bounds, threshold and
  per-seed tallies); a reversed spiritual pairing leaves method 5's verdict,
  totals, censored counts and per-seed tallies unchanged; the spiritual
  threshold mirrors `agent.rs`, `narrative._NEED_THRESHOLDS` and the
  migrate push in `needs.rs`; method 5 has no informational key. Updated:
  the default versions (needs 6, cohort 3) and the version arguments.
  `tests/test_validation_compare.py`: needs 5 against 6 and cohort 2
  against 3 are method changes in both profiles, never new or resolved
  failures; same-method comparisons still count new failures.
* Focused validation suites (`test_validate`, `test_validation_*`,
  `test_batch*`, `test_main`, `test_m53b_run_validation`,
  `test_procedural_gates`, `test_snapshot_pruning`, `test_bundle_codec`,
  `test_audit_batch_d`, `test_m10_integration`, `test_m19_integration`):
  559 passed.
* `python scripts/run_python_oracle_checks.py`: PASS in 93.5 s, 11 chunks,
  2,656 passed, 56 skipped (the largest chunk, `systems-2`, 29.4 s of 110 s).
* `pytest -m "not slow"` (one process, the release extension installed):
  6,647 passed, 3 skipped, 526 subtests, at `99bfb7d`.
* Not run: `cargo test` (no Rust change), `pytest -m slow`, the viewer (no
  viewer change).

## 5. Open

* **The cohort verdict cannot fail** (1.4). Every synthetic world passes,
  the reversed one included, and on the template full gate matched members
  and their controls migrate alike over all snapshots (1.066 against 1.065
  per window). A redesign (every snapshot's matched pairs pooled per
  behaviour, each with its pre-stated direction and a seed-clustered bound,
  as needs method 2 did for the needs oracle) is a gate decision with its own
  null and power checks; not done here. Until then a cohort PASS is not
  evidence that communities anchor behaviour.
* **Method 5's age dependence** (2.4): a decision for the needs oracle's
  owners. Possible next steps: report an age-matched binding component
  beside the verdict; add `age` to the needs sidecar so the founders, whose
  ages no sidecar records, can be paired (at subset scale exact ages read as
  the birth-event ages); or adjust for age instead of matching on it.
* **Spiritual pairing** (3.3): its pairs are mostly cross-faith and part of
  what it reads is persecution; not checked against a build with the need
  terms zeroed. Reported, not required; a gate decision later.
* **The procedural subset 42-61 fails the needs oracle on `main`** (since PR
  #52; 4.1), under methods 4, 5 and 6 alike.
* Not run: `cargo test`, `pytest -m slow`, viewer checks (nothing they cover
  changed).
