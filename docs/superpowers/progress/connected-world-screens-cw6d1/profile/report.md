# D1 bounded declared-scale profile

All fourteen paired runs completed (return code zero). Source `808726b8c886306229d3e08d76fdee9e6f580dde`, Python 3.13.5, extension SHA-256 `f2fb24f13c386c3965e485330499b9aa435f61a43e8fc02023f950fbf9664256`. Opt-in common flags were hybrid agents, food allocation, household retail with `all` boundaries and grain reserves; treatment added reform services and guild leagues. [metrics.json](metrics.json) retains process CPU, elapsed time, child peak RSS, every output file size, checkpoint read/write durations and bytes. This is a bounded profile, not qualification or a timing equivalence claim.

| Case | Turns | CPU ratio on/off | Bundle bytes ratio | State bytes ratio | Peak RSS delta MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| Template 5 (8×4) | 200 | 0.958 | 1.032 | 1.054 | +18.97 |
| Template 23 (8×4) | 200 | 0.924 | 1.071 | 1.115 | +12.71 |
| Procedural 19 (32×10) | 200 | 1.114 | 1.073 | 1.074 | +22.93 |
| Procedural 31 (32×10) | 200 | 0.959 | 1.023 | 1.027 | -3.60 |
| Scaled target 18,800 (12×4, seed 42) | 30 | 1.003 | 1.010 | 1.010 | -2.70 |
| Scaled target 43,700 (12×4, seed 7) | 20 | 0.975 | 1.005 | 1.002 | +0.91 |
| Procedural 42 (48×10) | 150 | 1.031 | 1.024 | 1.035 | +3.37 |

The maximum CPU increase was 11.4%, maximum bundle increase 7.3%, and maximum peak RSS increase 22.93 MiB. No proposed review threshold (>25% CPU, >2× bundle/checkpoint size, or +500 MiB RSS) was exceeded. Off/on elapsed times were affected by concurrent authorized lanes; process CPU is reported separately. Small timing decreases are measurement variation, not an optimization claim.

Four 200-turn cases wrote and read checkpoints at 50, 100, 150 and 199; scaled cases wrote/read at 29/19, and 48-region at 149. All reads succeeded. Profiling measures read/write overhead, while lifecycle tests separately establish exact resumed-output identity. Validation sidecars were explicitly enabled for scaled 18,800 and 48-region cases and their real bytes are included in file maps. Cases named scaled22k/scaled52k in the raw artifact are historical directory labels; actual requested initial regional population targets were **18,800/43,700**, not 22k/52k. Native initialization and subsequent population dynamics determine actual agent counts; targets are not a claim of constant native population.

Reproduce with a native interpreter verified against the intended checkout:

```sh
PYTHONPATH=src PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 /path/to/native/python docs/superpowers/progress/connected-world-screens-cw6d1/profile/run_scale_profile.py --output-dir output/cw6d1-profile
```

The retained harness uses the existing CLI and wraps checkpoint read/write timings. It rescales generated carrying capacities and regional populations for the two declared population targets before normal native initialization; this is explicitly a profiling construction. It makes no paid narration calls. Gross-export lower-bound correction in the final candidate changes only observation and was tested separately; this profile retains its original frozen identity.
