# CW6 final integrated bounded held screen

All 60 declared runs pass: five arms × twelve original reserved worlds × 120
turns, zero simulation failures and zero missing/malformed outcomes. The strict
check confirms all 131 outcomes, including three primaries, on every world.
This is bounded evaluation, not either restricted qualification gate; defaults
remain off. The results are mixed and include adverse outcomes.

The immutable held source is `5ec73003837b5149091593ffa411d33dd32e9491`.
Its physics is exactly `eaa4a5d3e1cb5c958b5e32719601c28986c9f6ac`; the six
intervening files are documentation and final-pilot receipts. Native SHA-256:
`59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`.
Frozen preregistration SHA-256:
`f8924582ad5292d27e185fe4eea69241c130b71b25e5471aa05128783640941d`.
The exact frozen bytes, start ledger, source/import/runner/module/registry
identities, complete per-world metrics, report and strict check are retained.
All held worlds enter every comparison; activation never filters enrollment.

Template seeds 781–786 and procedural seeds 881–886 each have all five arms:
FULL, A6R (A6 record_only), D3R (D3 record_only), D4C (requisition cost_only)
and SUP (joint timber-orders-off plus harvest-cover record_only). The timing
pilot was template 5/procedural 19. The 200→120 horizon amendment and pilot
freeze preceded the first held start at 2026-11-07T15:51:57Z. No held outcome
informed source, controls, primary outcomes, extraction or horizon.

The ten-case final pilot took 312.2 seconds, projecting 1,873.2 seconds for held;
with the fixed 1.5 margin, 0.7805 core-hours fit the unchanged 1.0-core-hour cap.
Actual held simulation 1,298.0 seconds plus extraction 169.4 seconds = 1,467.4
seconds (0.40761 core-hours); wall time 1,473.2 seconds. One simulation process
was used, with `RAYON_NUM_THREADS=1`; no timeout or cap was raised.

Paired mean primary differences, FULL minus the named control, each stratum
including all six worlds:

| Primary | Control | Template mean | Procedural mean |
| --- | --- | --- | --- |
| Household balance change/1,000 person-turns | A6R | -3.41826 | -1.03271 |
| Observed native deaths/1,000 person-turns | D3R | -0.410319 | +0.282220 |
| Service asset-turns/region-turn | joint SUP | +0.00445480 | -0.00723957 |

These are differences in whole-world modeled outcomes, not income, welfare,
causal decomposition or globally conserved cash. In particular a negative
balance-growth difference does not establish that paid wages caused credits
to fall. Retail enrollment is fixed to boundary all in every arm. The report
retains per-world ranges, signs, descriptive sign-flip enumeration, all fixed
harms, null mortality-by-cause observations and every secondary outcome.
Generic fixed harms use control minus FULL; explicitly labeled CW6 outcomes
use FULL minus control. The independent manual summary pins the latter.

The adverse fixed harms are material. FULL minus A6R mean cumulative food
shortfall after relief is +1,110.365 template/+1,254.741 procedural food units;
recorded epidemic-authority deaths are +22.167/+151.333. These aggregate
epidemic observations remain separate from individual care episodes and the
whole-world native-death primary. The balance-growth primary is lower on both
strata; procedural D3 death-rate and joint-SUP service contrasts are adverse.
No default promotion or general health/welfare benefit follows from this screen.
Template 786 forest stand is explicitly unavailable (no timber-capacity slot)
in all five arms, and mortality-by-famine/war-cause fields remain unrecorded.

There are material adverse/measurement limits. FULL actual army meals total
312/684 demanded on templates and 1,498/5,465 procedural; physical food removal,
kit credit, destruction and once-per-army consumption nevertheless all close.
FULL created 180 timber orders and delivered 186.668 timber units, with 898.443 measured
maintenance work across twelve worlds; delivery/dispatch does not establish
an isolated repair benefit. Recorded D3 evacuations 624/returns270/wounds109
are mechanism records, not an attribution of every native move or death.
Closing recorded unpaid/unrecorded restitution is zero on all FULL worlds;
that does not invent payment for lapsed dead/missing claimants.

Unknown native migration causes comprise 85.07% of FULL template moves and
98.29% procedural. Bounded A6 row drops are 776 and 205,136; they never replace
untruncated world totals. X1 classification loss also changes C2's T−1 crowding
input `1 + 0.25 × displaced_share`, so A6 contrasts mix information/behavior
with exposure-proxy feedback. Lower classified displacement cannot establish
less physical displacement or a health benefit. D3 movement inputs pass
through A6, so component controls include their configured interactions.
SUP is a joint procurement/canopy contrast. Six worlds per stratum and 120
turns cannot establish universal effects, late lifecycle outcomes or default
promotion. Full restricted 200-seed/procedural qualifications remain unrun.

Independent review re-extracted all ten retained first-world bundles/Arrow
sidecars and reviewed actual source, dates, controls, native component/typed
balance closure/continuity, physical army food, escrow/prior prices and each
primary. The final review receipt records completed 60-row budget/enrollment/
report readback. `registry-return-rows.json` contains only the two completed
CW6 entries; the lead integrates them by id, preserving all historical and
other-lane registry entries.

Actual commands from `/workspace/cw-screen-final`:

```sh
PYTHONPATH=src /workspace/cw-evidence-native/bin/python scripts/cw_integrated_screen.py run /workspace/evidence/cw6/held --screen CW6 --cohort held --jobs 1 --pilot /workspace/evidence/cw6/pilot-final/metrics.jsonl --keep-first
PYTHONPATH=src /workspace/cw-evidence-native/bin/python scripts/cw_integrated_screen.py check --screen CW6 --cohort held --metrics /workspace/evidence/cw6/held/metrics.jsonl
PYTHONPATH=src /workspace/cw-evidence-native/bin/python scripts/cw_integrated_screen.py report /workspace/evidence/cw6/held/metrics.jsonl --screen CW6
PYTHONPATH=src /workspace/cw-evidence-native/bin/python scripts/cw_integrated_screen.py mark-run /workspace/evidence/cw6/held --screen CW6 --registry /workspace/evidence/cw6/held/seed_registry-CW6-run.json
```

The last command changed only an external copy of the lead's registry. Full
retained first-world bundles/Arrow sidecars remain outside the checkout at
`/workspace/evidence/cw6/held/runs/`; exact hashes and sizes are retained here.
Earlier failed/superseded pilots remain separate. Active V6 and canonical V6
byte-for-byte resume evidence are separate neighboring records (80 total
resumed branches, all pass), not additional held scientific worlds.
