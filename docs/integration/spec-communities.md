# Communities as M53 oracle 1 specifies them (2026-10)

Branch `feat/spec-communities` from `main` `ac74e5a` (PR #62, community
anchoring). Validation only: the simulation, its outputs and the in-run
community summary of the validation sidecar are unchanged.

PR #62 found that the community oracle's members are about nine in ten
living agents (`community-anchoring.md` section 1), so the cohort oracle,
which compares members with non-members, cannot discriminate. This branch
adds community oracle method 2, the communities as M53 oracle 1's text
defines them with the spec's acceptance criteria, and cohort method 6,
which takes those communities as its member cohort.

**Results:** _pending (section 5)._

## 1. What method 1 does and what the spec says

The M53 spec (`docs/superpowers/specs/2026-03-21-m53-depth-tuning-validation-design.md`,
section 6.2, oracle 1):

> Deterministic label propagation community detection on the graph+memory
> sidecar. Run on each sampled snapshot (every 10 turns). Edge weights:
> friend + co-religionist + kin edges weighted by sentiment. Filter detected
> communities to those where >=80% of members share at least one memory
> `(event_type, turn, valence_sign)` tuple.
>
> Kin-only exclusion: qualifying communities must contain at least one
> non-kin positive-valence edge.
>
> Acceptance: qualifying communities appear in >=15/20 oracle-subset seeds
> (75%); mean community count per seed at steady state (turns 100-500):
> 3-15; community size distribution: median 5-12 agents, no single
> community >5% of regional population.

| | method 1 (`detect_communities`, `run_community_oracle`) | spec |
| --- | --- | --- |
| edges | every bond (rivals and grudges included) | friend, co-religionist, kin |
| weights | none (each edge counts 1) | sentiment |
| regions | edges join any two agents | (implied by the regional criterion) |
| kin-only exclusion | `bond_type != 0`; in the native enum 0 is the mentor and kin is 5 | a non-kin positive-valence edge |
| shared memory | 80% of members share a key (event type, memory turn // 5) with another member; no valence | 80% of members share a tuple (event type, turn, valence sign) |
| acceptance | a community of 5+ at some snapshot from turn 100 in 75% of seeds | that, 3-15 communities a seed, median size 5-12, none above 5% of its region |

Method 1 stays as it is: the in-run community summary
(`validation_community_summary.json`, `agent_bridge`) is built with it, so
changing it would change the sidecar's bytes, and community method 2 keeps
its result as a component.

## 2. Design

### 2.1 Detection (`chronicler/validation_communities.py`)

Read from the spec's text before any probe was run:

* **Edges**: bonds of type friend, co-religionist or kin with positive
  sentiment, between two living agents of the same region at the snapshot.
  The living agents and their regions are the needs sidecar's rows of that
  turn (one per living agent). A pair's weight is the sum of the sentiments
  of the bond slots that join it (a symmetric bond has a slot on each
  side). The region constraint is not in the edge clause of the spec but in
  its regional criterion: a community is a regional group, and with edges
  inside one region every community lies in one region.
* **Bond codes** come from `chronicler.ffi_constants.BOND_TYPES`, a mirror
  of `relationships.rs::BondType` (mentor 0, rival 1, marriage 2, exile
  bond 3, co-religionist 4, kin 5, friend 6, grudge 7). The native extension
  exports no constants, so the mirror is checked twice:
  `tests/test_spec_communities.py` parses the Rust enum and
  `is_positive_valence`; `tests/test_spec_communities_native.py` (with the
  extension) finds the kin code by its native behaviour: the one bond type
  that is both protected from eviction and refused by a symmetric upsert
  (marriage is protected and symmetric, the mentor bond asymmetric).
  `validation_ablation`'s bond constants now read the mirror (same values).
* **Label propagation**, as method 1: labels start as agent ids; at most 20
  sweeps over agents in ascending id order, each taking the label with the
  largest summed weight among its neighbours, ties to the smaller label.
* **Kept** when the group has at least 5 members, when one of its edges
  joins two members by a friend or co-religionist bond (the kin-only
  exclusion: a group joined by kin alone is a family clump), and when one
  memory tuple (event type, memory turn, valence sign), matched exactly, is
  held by at least 80% of its members. "Share at least one memory tuple" is
  read as one memory the group has in common; method 1 and PR #62's
  informational variant (`validation_ablation.detect_spec_communities`)
  read it pairwise (each member shares a 5-turn bucket with some other
  member) and without the valence sign.

### 2.2 Acceptance criteria (the spec component)

Over every steady-state snapshot (turns >= 100 with graph and needs
sidecars; a run shorter than that uses all of them, as method 1 does):

| Criterion | Measured as |
| --- | --- |
| `seed_fraction` | seeds with a community at some snapshot, at least 75% of the analyzed seeds |
| `community_count` | the mean over seeds of each seed's mean count per snapshot, within 3-15 |
| `median_size` | the median size of every community found (all snapshots of all seeds), within 5-12 |
| `region_share` | no community above 5% of its region's population |

**Region share.** A community's share is its size over the living agents
of its region at the same snapshot (the needs sidecar's rows; in hybrid
worlds the agents are the population). Every community lies in one region
(edges join agents of one region), so the region is unambiguous. The
criterion is applied to every community of every steady-state snapshot of
every seed: "no single community" admits none above 5%. This is also the
ratio method 1's in-run summary records (`max_cluster_fraction`: members
in the community's main region over that region's living agents), and the
5% bound its summary-only path tests. The component reports the largest
and median shares, the communities above the bound, the median population
of the regions that hold a community, and how many communities lie in
regions of at least 100 living agents, the smallest region in which a
community of five can stay within 5%.

### 2.3 Community method 2

`run_community_oracle` (method 2 by default): method 1's whole result is
the legacy component (its fields stay at the top level, as cohort method 4
keeps method 3's) and the spec component is `spec`. Which decides is
`validation_gate.COMMUNITY_SPEC_REQUIRED` (off: method 1 decides; section
6). The gate lists the component that does not decide under informational
non-PASS (`community_spec`), and the community row of the gate summary
says which decides. `run_community_oracle(..., method_version=1)`
re-scores method 1 exactly; `community_method_2_result` (pure) re-scores
saved components under either rule, and `community_method_1_result`
recovers method 1's result from a method 2 result. The comparator reports
community 1 -> 2 under "Oracle method changes" (`rebaseline_required`).

### 2.4 Cohort method 6

Cohort method 5 with method 2's communities as the members of every
component (`run_cohort_oracle`, the default; design-2 arms):

* **observational**: method 3's estimator, matching (same civ affinity,
  region and occupation, satisfaction within 0.10), window, censoring and
  criteria, on method 2's communities, over every snapshot whose window
  fits the run (as method 3). It adds `community_method_version` 2 and
  `matching`: members, matched members, match rate and mean satisfaction
  gap over every evaluated snapshot and over the chosen ones; each seed's
  record adds its chosen snapshot's members.
* **kin roots** (and the placebo when it runs): method 2's members at the
  fork; `community_method_version` 2.
* **community anchor**: `members` / `non_members` are method 2's; method
  1's members are reported as `method_1_members` / `method_1_non_members`
  (method 5's cohort); the tie cohorts are unchanged.

Which component decides is method 5's rule: the observational one unless
causal oracles are required (`--require-causal-oracles` stays off).
`run_cohort_oracle(..., method_version=5)` re-scores method 5 exactly
(method 1's communities, PR #62's `spec_members`); arms of design 1 are
still scored by method 4. The comparator reports cohort 5 -> 6.

## 3. Pre-registration

Written before any gate of this branch ran, after the detection and
criteria of section 2 were fixed and tested, from probes of `main`
`ac74e5a` (fresh release extension, SHA-256 `8497d374...`, the bytes of PR
#62's builds) on seeds outside the gates' ranges: template seeds 1000-1019
x 500 turns and procedural 32 x 10 seeds 1000-1019 x 300 turns, the full
gates' world and turns. The validator of this branch scored them; on both
batches its re-scores of community method 1 and cohort method 5, and every
other oracle, equal `main`'s validator's results.

### 3.1 What the probes show

| Probe of `main` | template (20 x 500) | procedural (20 x 300) |
| --- | ---: | ---: |
| steady-state snapshots / communities | 820 / 2,395 | 420 / 2,357 |
| seeds with a community | 20 of 20 | 20 of 20 |
| communities a seed per snapshot: mean (seed sd) | **2.92** (0.76) | 5.61 (1.18) |
| seeds whose own mean is within 3-15 | 8 of 20 | 20 of 20 |
| size: median / p90 / max | 5 / 7 / 37 | 5 / 7 / 26 |
| share of its region: median / max | 0.135 / 1.0 | 0.152 / 0.905 |
| communities above 5% of their region | **100%** | **100%** |
| median living agents of a region with a community | 43 | 37 |
| communities in regions of 100+ agents | 0 | 0 |
| members' share of living agents (median): method 1 / method 2 | 96.7% / 8.9% | 88.7% / 5.8% |
| members matched to a control (cohort method 3's matching): method 1 / method 2 | 7.7% / 67.1% | 9.5% / 57.4% |
| shared memory of a community (famine, migration, persecution, kin death) | 55%, 26%, 13%, 5% | 42%, 39%, 14%, 4% |
| kin share of a community's edges (median) | 0.67 | 0.73 |
| migrations per agent over 20 turns: method 2 members / non-members | 1.31 / 1.09 | 1.29 / 1.24 |

* **No community stays within 5% of its region, in either world.** A
  community of five exceeds 5% of any region with fewer than 100 living
  agents; the regions holding communities have a median of 43 (template)
  and 37 (procedural) and none reached 100. The criterion was written for
  worlds of tens of thousands of agents (the spec's sidecar budget is sized
  for 50K); the gate worlds hold hundreds.
* Method 2's communities are a tenth of the agents (method 1's nine in
  ten), so a member can be matched with a non-member: two thirds of
  members find a control, against one in thirteen.
* Members of method 2's communities migrate more than non-members on
  `main`, not 15-30% less. Their shared memories are mostly famine and
  migration: many are groups of kin and friends who suffered or moved
  together.

### 3.2 Predictions for the gates

Gates: template full (200 x 500) and procedural full (100 x 300) of this
branch with the default configuration, against `main`'s full reports with
`--require-strict-regression`; one template full gate with
`--community-anchoring` (arms `needs`, `kin_roots`, `community_anchor`)
against PR #62's flag-on report of the same configuration. Ranges are the
probe's estimate with a 95% prediction interval for a gate of 200 (100)
seeds where one applies.

1. **Simulation unchanged.** The 9-case turn-speed matrix, `main` against
   this branch: 399 files, 0 differences. Every comparison: every metric
   delta 0, NO REGRESSION, PASS (strict), with community 1 -> 2 and cohort
   5 -> 6 (and nothing else) under "Oracle method changes"
   (`rebaseline_required`). Needs method 8 and every oracle other than
   community and cohort equal `main`'s results.
2. **Community method 2 on `main`'s simulation fails its acceptance
   criteria**, so it is not made to decide (the decision rule of this
   branch): method 1 decides and passes, as on `main`; the spec component
   is reported.
   * region share: FAIL in both worlds; at least 99% of communities above
     5% of their region.
   * template: mean count 2.92 [2.55, 3.29] against the 3-15 band: more
     likely to fail than to pass; procedural 5.61 [5.00, 6.22]: PASS.
   * median size 5 (5-6): PASS in both; seeds with a community: at least
     95%: PASS in both.
   * members' share of living agents (median): template 7-11%,
     procedural 5-7%.
3. **Cohort method 6.** Observational component PASS in both worlds (it
   passes 20 of 20 probe seeds; method 3's estimator is non-discriminating);
   match rate 0.60-0.72 (template) and 0.50-0.65 (procedural). Kin roots on
   method 2's members: rate ratio 0.97-1.00, FAIL against the pre-registered
   0.85 (as for method 1's members: 0.988 template, 0.992 procedural).
4. **The community anchor on method 2's members** (template flag-on gate).
   The flag-on batch is PR #62's (same simulation, seeds and arms), so its
   other cohorts reproduce PR #62's exactly: method 1's members 0.909
   [0.901, 0.917] (130,400 agent-forks), four ties 0.873, one to three
   0.898, no tie 0.926. Prior: the stronger-anchor probe of PR #62 at the
   calibrated anchor (40 seeds, one fork) gave its spec members 0.969 +-
   0.072 against spec non-members 0.930 +- 0.037, and its full gate 0.912
   against 0.906, no separation. Method 2's members hold more counted ties
   (mean 2.16 against 1.31; four ties 27% against 10%); weighting the full
   gate's tie-group ratios by the probe members' moves gives 0.898 for
   members and 0.908 for non-members.
   * Members 0.90 (0.88-0.93), about 14,000 agent-forks, 95% interval about
     +-0.02; non-members 0.91 (0.89-0.92).
   * The pre-registered M53 claim (RR <= 0.85, upper bound below 1) FAILS on
     method 2's members.
   * Members are not separated from non-members: the difference is below
     0.03 and the 95% intervals overlap.

Nothing in sections 2 or 6 may change after a gate's result; a failed
prediction is reported as such.

## 4. Gates

_Pending._

## 5. Results

_Pending._

## 6. Decisions

_Pending._
