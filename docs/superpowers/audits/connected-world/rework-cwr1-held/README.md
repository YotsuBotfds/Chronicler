# CWR1 bounded held screen: complete evidence

**PASS: 144/144 simulations, 12 matched worlds, 120 turns each.** There were
no failures, duplicate/missing cases or source/native/protocol changes.
The [closure receipt](closure-receipt.json), [complete metrics](metrics.jsonl),
[source record](source.txt) and [raw report](report.md) retain the actual
result. Read that report with its
[heading erratum](report-heading-erratum.md): all six enrolled worlds per
stratum are included, including zero-activation cases. The inherited generic
captions do not describe CWR1 selection; the original report bytes remain
unchanged.

Simulation took 2,934.7 seconds and extraction 410.1 seconds: 3,344.8 seconds,
**0.929111 core-hours**, below the unchanged two-hour cap. The fresh runner
subprocess used 3,352.514769 seconds of descendant user-plus-system CPU and
3,357.920780 seconds of wall time. Peak 1,184,040 KiB is a lifetime maximum of
one waited-for child or descendant, not simultaneous process-tree memory.
The scope is explicit in [resource measurement](resource-measurement.json).

The [independent stdlib checker receipt](independent-arithmetic.json) passed
all 144 rows and six rendered primary rows. Raw readback of the predeclared first world of each stratum independently
passed all 24 retained cases and 2,880 snapshots. The input-history limit is
explicit: 2,096 complete signed component merges were reconstructed, while
784 capped merge-turns remain unverified. Implementation/native receipt
review is distinct from a complete retrospective per-input trace audit.

## Results and interpretation

These are **within-CWR1 AD minus RD** world-level mean differences. AD enables
all personal A6 channels; RD records personal A6 without applying its choices.
Both keep rules 3, active D3 input ownership and corrected `density_only`
public-health settings. Raw effects and preregistered rates both remain visible.

| Stratum (six worlds each) | Regional availability shortfall | Recorded epidemic deaths | Shortfall per 1,000 native person-turns | Epidemic deaths per 1,000 native person-turns | Native person-turns |
| --- | ---: | ---: | ---: | ---: | ---: |
| Template | +812.431218 | +30.166667 | +19.870740 | +0.947684 | +2,282.333333 |
| Procedural | +2,081.886493 | +69.333333 | +15.343481 | +0.302042 | +10,072.333333 |

Food shortfall increased in six template and five procedural worlds; recorded
epidemic deaths increased in four template worlds (one decrease, one zero)
and five procedural worlds (one decrease). Harmful average directions
persist in this bounded corrected model, but not in every world. This is
not proof that an adverse outcome is a software defect. Full per-world values,
ranges, sign counts, exact descriptive sign flips and fixed-seed paired-world
bootstrap intervals are retained in the reports and independent audit. Six
worlds per stratum are a small sample, not qualification.

The prespecified epidemic interaction `(AL−RL)−(AD−RD)` averages −18.333333
template and −43.166667 procedural. It measures sensitivity to the legacy
motive-classified multiplier within this model; it does not identify a
physical housing/crowding mechanism. Component-deletion, health-cost and
joint title/allocation regime contrasts remain marginal, contextual effects,
not an additive decomposition or attribution of individual native choices.

Do not attribute old CW6-to-new CWR1 differences to a single fix. The source,
rules, D3 control ownership, crowding recipe and seeds differ. Historical CW6
arithmetic and its control limitations remain preserved separately; controlled
claims here use only the preregistered within-CWR1 comparisons.

Important limits accompany the contrasts:

- Lower raw IX shortfall accompanies lower native person-turns and endpoint
  civilization population; it is not an unconditional welfare benefit.
- `no_relief` is a joint harvest-title/L2 free-pool allocation intervention,
  not removal of all free food or a pure price effect. Observed priced-out
  person-turns increase in every world in both A/R regime comparisons even
  when mean regional availability shortfall falls.
- Retail `all` fixes a qualifying-controlled-region eligibility recipe, not
  an identical realized enrollment set. All procedural AD complete access
  totals are unknown; observed retail subtotals do not measure every person's
  access. Missing populated-region coverage and unrecorded famine/war causes
  remain null, never favorable zeros.
- Template food-shortfall and epidemic-death differences for work-deletion
  and public-health cost contrasts are zero.
  That is not absence of paid work, wages, services or configured mechanisms:
  one template AD world has two adaptive offer declines, paid work/care wages
  are nonzero, and water service is present. Template delivered epidemic-care
  coverage and patient food are zero; care efficacy is not established there.

Root recorded the started cohort **once**, after closure and independent
144-case arithmetic PASS, at commit `d3eae00c`. Both registry entries now read
`run`, complete with 144 rows; cohort-content SHA256 remains `62ce5aa8…`.
The [mark-run proposal](mark-run-proposal.json) is the historical unexecuted
proposal from this lane, not a command to run again. The lead's registry
receipt is `docs/superpowers/progress/connected-world-rework/held/registry-record.json`.

Metrics SHA256:
`6c56e3ffa725848c69aecf6f2edfcdf81adb18e5c5f038562e2c9d3c73ace9e0`.
Raw report SHA256:
`e5d64f1658265a64ed100d158d650d29eed1f0247d77ea980599c3a145eaf2c3`.
Closure receipt SHA256:
`244ac65f49b01a718ff251a13fe93cddc493e9e9f22adb901fb1466e918383eb`.

## Preserved start and recovery boundary

The preregistered screen started **2026-11-07T22:41:33Z** at immutable source
`b45c1e99572d4d6a60fb01fbd75cb7688aa54e93`, with protocol SHA256
`51b8a336969f48b4beb6f5b3e543062eda71822b98513b337ceb2d010e6efe7a`
and receipt identity
`98c7bb2accb18b04e68f0585780ba58f85f03ece77c987d82ff67ceb7d9370a8`.
The reviewed source is production/scripts-equivalent to runtime `8792be88`.
The native artifact is `b1d3ea5…`, with the same 57-file `f55df55…` input
receipt and separately verified native crate pyproject.

This start is **not a result or completion receipt**. It records twelve fresh
worlds, all twelve arms, 120 turns each: 144 planned cases. Template seeds
4101–4106 and procedural seeds 4201–4206 were registered before the source-
bound pilot. The full matching 24-case pilot passed with a 1.383-core-hour
projection after its fixed 1.5 margin, below the unchanged two-hour cap.
No default was promoted and neither restricted qualification gate is run.

The [start record](start.json), [source snapshot](source-start.txt), actual
[launch arguments](launch.json) and independently reviewed
[wrapper](run-bounded-held.py) preserve the live execution boundary. The
generic runner owns its normal start ledger and budget enforcement. The
wrapper adds source/native/protocol and matrix checks, scoped CPU/wall/RSS
measurements, and captures report stdout directly as Markdown. It does not
edit or mark the seed registry.

All raw output and live metrics are under
`/workspace/evidence/cwr-evaluation/held-cwr1-b45c1e99-v1/`.
The frozen checkout is `/workspace/cwr-held-runtime`; its local generic ledger
is `output/held-runs/ledger.jsonl`. The integration owner is the sole registry
writer. From this start the reservation is potentially spent, including if
the process is interrupted. Preserve failures, nulls and unrun cases; do not
replace seeds, tune the model or increase the cap after starting.

For recovery, inspect the existing output and ledger, check the same
source/native/protocol identities, and resume that recorded run through the
unchanged generic runner if it is recoverable. Do not launch a new output
directory for the same cohort. If the environment is unavailable, the
integration owner must record the limitation and treat the started cohort
conservatively; this receipt does not promise automatic restart.

The paragraphs in this section preserve the original start boundary. They
are historical recovery instructions, not an instruction to restart a completed
cohort. Results and the once-only registry disposition are recorded above.
