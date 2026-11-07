# B3 recovered integration verification — 2026-11-07

Reviewed source: `be524a60a3a94a64c9572f1befd3769583773c62`, recovered from
`83abd6668e5db22f24e86ab986567a673f78455b`, integrated against main
`e3bce686df1fe2e73a4ee7378c36f2e2647826bb`. Historical CW3/CW3b results and
the CW3 disk-full failure are preserved. No new held cohort was consumed.

Independent source review by the D1 lane approved the final service-identity
guard and regression. The provisional cwb3 exact inverse follows cwx1; historical
layers are unchanged.

- Focused offline 530 passed, historical witness suite 299 passed plus61subtests.
- Final infrastructure contracts72passed; native5passed24.24s, including exact
  resume in open work, flood-damaged work and a live timber expedition.
- Complete bounded offline oracle:72chunks,7618passed69skipped0failed,446.1s
  on CPython3.13.16; every chunk retained its110second limit. CPython3.13.5
  first failed the unchanged main argparse golden in validation-tooling; no
  golden was modified. uv0.12.23 did not publish3.13.17;3.13.16 passed the
  exact failing golden before the complete rerun.
- Viewer full suite1666passed2skipped4timeouts in2modules under native-build
  contention; the2failedmodules reran25/25passed without changed timeouts.
  Lint and production build passed.
- Production Chromium journeys loaded the natural native procedural31,32x10,
  60turn bundle at1440x900 and390x844, sought Home/PageUp/ArrowRight/End,
  checked dated infrastructure tables and clicked a region. Both passed with
  zero page errors, NaN/undefined or horizontal page overflow. Screenshots
  and report retained outside git.

Native artifact reused read-only after checking Rust sources equal main:
`f2fb24f13c386c3965e485330499b9aa435f61a43e8fc02023f950fbf9664256`.
Each run used `PYTHONPATH=/workspace/cw-b3/src`, `PYTHONHASHSEED=0`,
`RAYON_NUM_THREADS=1`, and the verified native interpreter. Observed resource
quota:4CPUcores (`cpu.max=400000 100000`),16GiB RAM.

## Declared-scale profile

Each row is off/on on the same development/pilot world and B3 base
`--agents hybrid --grain-reserves --grain-storage --repair-projects`, with
`--infrastructure-condition` only on. Screen worlds run200turns with exact
checkpoints50/100/150/199; stress worlds use the penultimate turn. The wrapper
times checkpoint writes and reads, validates restored turn, and records process
CPU, wall, peak RSS, bundle/state/output bytes and artifact identity. Wall
ratios reflect shared resource contention; processCPU is the stronger measure.

| World | CPU ratio | Wall ratio | Bundle ratio | Last checkpoint ratio | RSS delta MiB |
|---|---:|---:|---:|---:|---:|
| t5 | 0.984 | 0.713 | 1.119 | 1.620 | 30.1 |
| t23 | 1.185 | 1.246 | 1.289 | 1.827 | 30.1 |
| p19 | 1.081 | 0.925 | 1.177 | 1.202 | 90.0 |
| p31 | 1.146 | 1.068 | 1.115 | 1.168 | 92.9 |
| scaled22k_s42 | 0.984 | 1.013 | 1.027 | 1.003 | 1.7 |
| scaled52k_s7 | 0.991 | 0.740 | 1.012 | 1.001 | -1.3 |
| p48_s42 | 1.077 | 1.009 | 1.121 | 1.148 | 84.1 |

No proposed threshold was exceeded:25%CPU,2xbundle/checkpoint,500MiB extra
RSS. All14runs exited0. The profile did not enable validation sidecars, so
metrics-row bytes are unmeasured; integrated V11 must include them. Profile
results are bounded engineering evidence, not 200seed or procedural qualification.

Reproduction commands:

```sh
PYTHONPATH=src /workspace/cw-b3-offline/bin/python scripts/run_python_oracle_checks.py --output-dir /workspace/scratch/b3-oracle-31316
PYTHONPATH=src PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 /workspace/cw-d1-native/bin/python -m pytest -q -p no:cacheprovider tests/test_infrastructure_condition_native.py
npm test -- --maxWorkers=1
npm run lint
npm run build
```

Compact retained receipts: `/workspace/scratch/b3-oracle-31316`,
`/workspace/scratch/b3-native.log`, `/workspace/scratch/b3-browser/report.json`,
`/workspace/evidence/b3/profile/summary.json`; profile wrapper and exact CLI
arguments alongside it. These workspace paths are recovery locations, not
claims of publicly uploaded raw evidence. Root separately verifies9case
feature-off identity against8abc1acb and precedingmain, exact-head Tests,
and post-merge main CI.

Unrun here: live server pause/save/fork browser journeys, paid named crews
(a separate follow-on), metrics-row profiling, full200seed/procedural
qualification. Ports remain explicitly deferred because no maritime service
consumer exists. Anonymous unpaid labor and the public-works sink are the
B3 candidate contract; they do not imply named paid workers.
