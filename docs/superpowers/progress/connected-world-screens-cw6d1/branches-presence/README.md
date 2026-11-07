# D1c local presence verification

Final isolated source `8fec1a4b` is committed lead integration `ae6ffab4`
plus independently reviewed presence correction `c0e63bf9`. It changes no
native files. The verified compiled extension is SHA-256
`59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`.
[Source identity](source.json) and [import identity](branches-final-native-identity.txt)
record the actual checkout and interpreter.

The Phase 10 writer now excludes a roster member deployed outside native
residence from local branch groups and dues. Current public army attachment
is the person's own knowledge. A roster member whose army is in that residence
can participate off duty, without a work claim. This uses no X1 frame, moves
no person, and changes no native membership or residence authority. The regression
checks actual excluded payment, same-residence eligibility, return with the same
branch identity, and unchanged native membership/residence.

[Thirteen unit tests](branches-presence-tests.log) passed on the isolated
correction. [All fifteen unit/native tests](branches-final-native.log) passed
on the committed integrated source in 2.43 seconds, including real named dues,
record-only native world/history identity and exact checkpoint restoration with
funded T−1 permission due next tick. Only initial home/foreign memberships in
the exact-resume mechanism case are constructed; transfers, native ticks and
restore are real. No fresh held seeds are consumed by these tests.

[Six natural development runs](metrics.json) over 80 turns use template 23
and procedural 13 with `funded`, `cost_only` and `record_only`, without constructed
memberships. All returned zero. Template funded branches recorded 63 funded
rows, 364 member-turns and 2.680 units of real named dues; cost-only recorded
164 member-turns/0.180 units, record-only 164/zero. Procedural funded branches
recorded 24 funded rows, 232 member-turns/0.750 units; cost-only 171/0.360 units,
record-only 171/zero. These metrics match the earlier native-residence-only
development source; the focused regression specifically establishes deployed
member exclusion. Different enrollment and branch lifespan prevent treating
these totals as an equal-enrollment causal effect. This is mechanism evidence,
not held efficacy or qualification.

Reproduce with the reviewed native environment for this source:

```sh
PYTHONPATH=src PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 /path/to/native/python -m pytest -q tests/test_movement_branches.py tests/test_movement_branches_native.py
PYTHONPATH=src PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 /path/to/native/python -c 'from chronicler.main import main; main()' --seed 23 --turns 80 --agents hybrid --simulate-only --movement-branches --output output/branches/chronicle.md --state output/branches/state.json
```

For the other modes add `--movement-branches-mode cost_only` or `record_only`.
Procedural development uses `--seed 13 --worldgen procedural --regions 32 --civs 10`.
When collecting a test file from another worktree, explicitly set pytest's
`-o pythonpath=/absolute/intended/checkout/src`; its own configuration can otherwise
override the shell's verified import path.

The production browser follow-up must identify the final banner registration
and natural bundle. An initial journey passed value checks but visual inspection
found the parent falsely saying it read no package above a valid branch panel;
this is a viewer catalog defect, not absence of branch records. No earlier limited
pass is substituted for the corrected browser check.

The separate [observed native count artifact](../profile/observed-native-counts.json)
adds measured scale context to the frozen D1a/b profile: strict compatible source,
extension and thread settings restored its original checkpoints without override.
The 18,800 target case had 24,112 living native agents at checkpoint 29 and
24,205 at sidecar turn 30. The 43,700 target case had 44,123 at checkpoint 19.
Historical directory labels `scaled22k`/`scaled52k` are not fixed population claims.
No simulation, held rerun or qualification was required to inspect those artifacts.
