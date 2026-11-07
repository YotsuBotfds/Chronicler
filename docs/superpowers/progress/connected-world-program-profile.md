# Connected World whole-program declared-scale profile

All fourteen serial development cases completed on immutable runtime
`eaa4a5d3e1cb5c958b5e32719601c28986c9f6ac`, with no source/import/native guard,
strict wealth closure, checkpoint restoration or full-arm extractor failure.
This is V11 profiling and bounded development evidence, not either restricted
qualification gate and not evidence for promoting a default.

The new behavior and records have a substantial cost. Across these seven
single-run pairs, FULL CPU was **1.81–6.90×**, bundles **2.13–3.94×**, and peak
RSS rose **60–1,010 MiB**. The lead accepted these measured costs for the
opt-in experimental program, conditional on no resource exhaustion, closure or
source guard failure. This acceptance is not a performance win, fixed-work
optimization, throughput guarantee or performance qualification. Population,
behavior and record volume differ between arms, so the ratios describe the
cost of the actual enabled program rather than isolated implementation cost.

## Source, environment and measurements

The clean private checkout was `/workspace/cw-final-profile-v3`; every child
verified its frozen Python/Rust input digest before and after simulation, its
actual imported Python path and the release extension hash. The interpreter
was `/workspace/cw-evidence-native/bin/python`, CPython 3.13.5. The imported
extension SHA-256 was
`59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`.
Its reviewed native source fingerprint is
`38b21020673a028ce6bcd76e19fb3e0c01eed5893b89f1ce6ff6eda6cf8925a2`;
the source/artifact build receipt is also retained with CW6 native-build
evidence. No new native build was needed for these profiles.

The approved profiling tool's SHA-256 is
`1c21d7db60cfe9d9a3d60f4ed06fe2ff0117762aed51cdd26dee71b7d7d0d410`.
An exact copy is retained beside the records. Independent source review
approved tool commits `19003814`, `ded9da61` and `c4c1b5bf` before this run;
runtime review and integrated test gates are separate. Each case used a fresh
process, `RAYON_NUM_THREADS=1`, `PYTHONHASHSEED=0`, no narration, and actual
native simulator counts without a simulator proxy.

The host reported five visible/affinity CPUs but a cgroup quota of four CPUs
and 16 GiB memory. The lead scheduled the one profiler process alongside at
most three other one-job checks. The machine receipt's earlier scheduling
note mentions two pilots; later checks also occupied the fourth CPU slot.
CPU/process time and shared-host wall time are both recorded, not conflated.
No offline chunk limit was raised. Run RSS is captured before checkpoint
reads; maximum process RSS including those reads is recorded separately.

OFF retains the productive-recovery prerequisite chain, health care and
all-region retail enrollment, but removes the Connected World effects and
records, selects retail rules 1 and legacy quarantine. FULL uses the exact
integrated-screen FULL flags, including strict A1, rules-2 personal information,
named infrastructure crews and funded institutional branches; procedural FULL
also uses watershed flow. This OFF is the cost control for this program, not
the no-switch default scenario. Final default-path byte identity is a separate
matrix. Each plan retains the complete executable CLI, including duplicate
options whose final value is what the parser uses.

## Actual scale and cost

The table uses actual initialized agents and the largest post-turn live native
count. Historical case names do not establish population. In particular, the
historical `scaled52k` configuration starts at 43,700; FULL reaches 53,138
during the twenty-turn run. The separately authorized extra initial-52,000 pair
was conditional on neither historical arm reaching 52,000; that condition did
not occur. The historical `scaled22k` configuration starts at 18,801.

| World / turns | Initial / peak OFF → FULL | CPU seconds OFF → FULL (ratio) | Run wall seconds OFF → FULL | Peak RSS MiB OFF → FULL | Bundle MiB OFF → FULL (ratio) | State MiB OFF → FULL | Max matched checkpoint ratio |
| --- | --- | --- | --- | --- | --- | --- | --- |
| template_s5 / 200 | 180 / 229 → 249 | 13.32 → 24.12 (1.81×) | 15.28 → 30.73 | 449.9 → 792.3 | 8.79 → 18.69 (2.13×) | 2.04 → 3.19 | 1.99× |
| template_s23 / 200 | 196 / 224 → 299 | 12.30 → 23.12 (1.88×) | 12.40 → 23.37 | 438.3 → 788.8 | 8.47 → 19.73 (2.33×) | 1.92 → 2.97 | 1.94× |
| proc32_s19 / 200 | 502 / 740 → 1,026 | 36.53 → 95.15 (2.60×) | 48.15 → 108.67 | 945.9 → 1941.7 | 26.70 → 68.13 (2.55×) | 6.38 → 9.54 | 1.98× |
| proc32_s31 / 200 | 544 / 795 → 894 | 33.18 → 76.03 (2.29×) | 38.49 → 76.16 | 895.7 → 1906.2 | 22.69 → 68.00 (3.00×) | 6.02 → 9.48 | 2.10× |
| scaled22k_s42 / 30 | 18,801 / 22,952 → 24,571 | 16.33 → 112.70 (6.90×) | 16.36 → 112.77 | 419.3 → 659.0 | 3.00 → 11.85 (3.94×) | 1.87 → 8.20 | 1.32× |
| scaled52k_s7 / 20 | 43,700 / 49,507 → 53,138 | 28.54 → 65.41 (2.29×) | 28.75 → 65.47 | 603.3 → 663.5 | 2.29 → 7.58 (3.31×) | 1.99 → 7.69 | 1.18× |
| proc48_s42 / 150 | 506 / 880 → 1,046 | 24.41 → 52.71 (2.16×) | 24.49 → 52.89 | 808.1 → 1533.5 | 20.62 → 53.03 (2.57×) | 5.18 → 8.31 | 1.98× |

The four screen-world pairs ran **200 turns**; procedural 48 ran **150 turns**;
stress cases ran 30 and 20 turns. These override the integrated held screen's
separate 120-turn horizon. All cases include real Arrow validation sidecars,
including the historical 43,700-agent pair. Seven FULL bundles passed the
strict integrated extractor with zero reported problems. Bounded sample drops,
unknown causes, null personal costs and adverse physical outcomes remain in
the measurements; an extractor pass does not make them zero or establish
effectiveness.

The maximum measured run/process RSS was 1,941.7 MiB, with no OOM. There were
52 actual checkpoint writes and exact same-source reads at the declared
turns, with no mismatches and restored turns checked. The largest observed
write took 3.348 seconds; the largest read took 4.216 seconds. These are
single-run observations under shared-host scheduling, not latency guarantees.
Matched-turn checkpoint size ratios, per-stage write/read times, checkpoint
identity headers, real Arrow rows/bytes/hashes, bundle/state/output bytes,
per-turn CPU/wall/count rows and final physical output maps are retained.

Every pair exceeds the playbook's 25% CPU review threshold and doubles bundle
size. Procedural 31 also doubles a matched checkpoint. Procedural 19/31/48
exceed the additional-500-MiB RSS threshold. The 18,801-agent FULL run is the
largest relative CPU adverse result (6.90×), not a discarded outlier. Different
population trajectories and active mechanisms help explain why scale alone
does not order the ratios; this profile does not isolate their contributions.

## Reproduction and retained records

The canonical tool is `scripts/cw_program_profile.py`. On a clean checkout at
the frozen runtime, with a native environment verified against that source:

```sh
PYTHONPATH=src /workspace/cw-evidence-native/bin/python scripts/cw_program_profile.py run /workspace/evidence/reproduced-program-profile --source-root "$PWD" --expect-commit eaa4a5d3e1cb5c958b5e32719601c28986c9f6ac --native-sha256 59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617 --python /workspace/cw-evidence-native/bin/python --rayon-threads 1
```

The measurement tool was introduced on a separate review branch after the
runtime freeze. Copy the exact retained `profile-runner.py` outside the frozen
checkout if that checkout does not yet contain the canonical tool, then invoke
that path with the same arguments. Do not edit the frozen runtime to install
the tool: its source/import guards are intentional.

The compact directory `connected-world-program-profile/` retains all fourteen
`plan.json` and `profile.json` records, the parent `runs.json` including exit
codes and final file maps, machine metadata, raw-output hashes, this exact
runner and a portable summary helper. Regenerate the summary with:

```sh
python docs/superpowers/progress/connected-world-program-profile/summarize.py
```

The raw runs, actual checkpoints and bundles remain outside the checkout at
`/workspace/evidence/final-program/profile-eaa4a5d3/` (about 1 GiB at completion).
Their availability after container reclamation is not promised; the compact
receipts and reproducible source/commands are committed. No held seed,
qualification run, paid call, deployment, default or credential changed.
