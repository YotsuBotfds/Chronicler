# CWR development schema check, 2026-11-07

The corrected extractor passed all 13 source-bound, eight-turn development
cases: twelve CWR1 arms on shared timing template seed 5, then AD on shared
timing procedural seed 19. This is a schema/control check, **not** the official
120-turn timing pilot, held evidence or either restricted qualification gate.
No held seed was spent. Maintained defaults remain unchanged; the cases use
explicit rules-3 and public-health crowding flags.

The clean source was `09403c15070ddab4977ae8b2e65c336238468447`, imported from
`/workspace/cwr-corrected-v2/src`; the fresh release extension was
`b1d3ea5ac858681960b2cb880c534164905501f6ab4f6f3c94f7c9b5f66196cd`.
The harness checked the source, tracked-file cleanliness, native hash,
catalog and full live registry before starting, and source/native identity
again afterward. It used one sequential simulation job with Rayon, OpenBLAS,
OMP and MKL threads set to one. All raw bundles, Arrow sidecars, exact child
commands and stdout/stderr remain under
`/workspace/evidence/cwr-evaluation/dev-schema-094-v2/`.

The 13 cases took 19.86 seconds of measured wall time, 20.24 seconds of
user-plus-system CPU and 176,632 KiB peak child RSS. These short-run costs
are not extrapolated to the held budget: the full 24-case, 120-turn pilot
remains a separate gate on the final optimized source.

## Failed check preserved and corrected

The first source-bound check at `8de171fd` passed ten template arms, then
correctly stopped when the screen's own `free_given == 0` assertion rejected
RNR. That assertion reflected an incorrect draft interpretation. The actual
native mode-1 contract in `chronicler-agents/src/provisioning.rs` retains
L2's allocation of the existing free pool and removes the retail means test;
its existing Rust regression explicitly distributes positive free food.
Python installs `(commons_consumed + public_release) / ration` in every
active retail mode. `no_relief` also changes the harvest title fraction from
0.9 to 1. It is a joint ownership/allocation intervention, not elimination
of all free food or a pure price control.

The preserved RNR run contains **368.853005 free rations**, zero retail
priority-household turns and zero food through the retail-priority branch.
The corrected extractor records all three observations separately and
requires native mode 1 and the inactive retail-priority branch. It does not
infer zero free food from zero retail-priority activity. Its reread of all
eleven original raw runs passes; the original failed metric rows and failed
receipt remain untouched at `dev-schema-8de-v1/`.

Independent review also demonstrated that missing `native_count` plus a
missing retail observation previously became zero access deficit and zero
unknown coverage. Missing public-grain observations similarly became zero
release. Both now fail explicitly. Negative, fractional and Boolean native
counts also fail. The required count is not equated to the later population
snapshot because deaths between phases can make them legitimately differ.

Seven new regression cases failed the old extractor and passed after the
correction; all **48 focused tests passed**. The actual three-file correction
was independently reviewed against the native implementation, contracts,
diff and tests before integration. No simulation physics was changed to
satisfy the draft or to improve an outcome.

## Reproduction and retained receipts

[The harness](rework-development-schema/run-development-schema.py) always
runs these thirteen shared timing-world cases and labels their rows
`dev_schema`. They cannot be supplied as an official budget pilot. Example,
from the clean frozen checkout with the verified native environment:

```sh
PYTHONPATH=src RAYON_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /workspace/cwr-native/bin/python \
  /path/to/run-development-schema.py \
  --checkout /workspace/cwr-corrected-v2 \
  --expected-source 09403c15070ddab4977ae8b2e65c336238468447 \
  --expected-native-sha b1d3ea5ac858681960b2cb880c534164905501f6ab4f6f3c94f7c9b5f66196cd \
  --out /new/output/directory
```

Compact [passed](rework-development-schema/passed-receipt.json) and
[failed](rework-development-schema/failed-receipt.json) receipts, the
[source identity](rework-development-schema/source.txt) and
[corrected reread](rework-development-schema/failed-run-corrected-readback.json)
are retained beside this audit. The held registry reservation remains
unused pending the full timing/schema pilot, frozen protocol and budget
decision. No fresh effect estimate is made here.
