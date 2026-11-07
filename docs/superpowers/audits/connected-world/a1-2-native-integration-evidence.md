# A1-2 and connected native integration evidence

Development evidence, 2026-11-07. This is not a held screen or qualification.
All new behavior remains opt-in. This record does not replace integrated
whole-program evidence, exact-head CI or final source review.

## Source, artifact and review

Source commits in the isolated `codex/cw-evidence` lane:
`7009187c` (wealth stages, D4 service, D3 mortality and A6 input),
`10dde332` (D1c dated branch input), `e5ca097f` (strict A1/new payment readers),
`7aed96dd` (A6 personal information), `2dcb2ce2` (signed treasury fix),
`9e001701` (honest adaptive attribution), `38488ff6` (A1 lifecycle resume).
The lead cherry-picked these into the integrated source with different hashes.

Independent actual-source review by the B3 owner found and blocked two issues:
A6 scores were counted as news/religion, and the new generic wealth reader
used the wrong sign for treasury debit units. Both were corrected and
independently approved, including the final `9e001701` diff. The original
native source batch was reviewed against actual implementation and tests.

Final native source digest (all `src/**/*.rs`, Cargo.toml, Cargo.lock and
build.rs; sorted relative paths, NUL, bytes, NUL, SHA-256):
`38b21020673a028ce6bcd76e19fb3e0c01eed5893b89f1ce6ff6eda6cf8925a2`.
The isolated and integrated native sources matched before scale execution.

CPython 3.13.5 release extension:
`/workspace/cw-evidence-native/lib/python3.13/site-packages/chronicler_agents/chronicler_agents.cpython-313-x86_64-linux-gnu.so`,
SHA-256 `59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`.
Native checkpoint layouts remain agent `v1:dcf0c34097c88451`, ecology
`v1:4ab7f8c199b5e5f8`, politics `v1:b1a710f3450f5015`.

## Checks

- Full Rust library suite: **774 passed**. Includes copied f32 stage closure
  and unchanged checkpoint bytes; enlisted stable identity/food fraction and
  slot reuse; one-turn dated branch service; native personal knowledge and
  expiry; foreign-truth perturbation of unknown destinations; adaptive-only
  target changes with no news/religion attribution; record-only decision,
  RNG and migration-driver identity; workshop declines without army relabeling.
- Wealth accounting Python suite: **30 passed**. Includes strict failure on
  an unobserved balance writer and uncapped signed treasury/carry closure.
- Real extension contract suite: **7 passed in 4.94 seconds**. Includes seed 7,
  35 turns with births/deaths/migration and exact native wealth closure;
  malformed/pending/stale input failures before mutation; mutual legacy
  observer refusal; and exact resumes at turns 14 and 28. Every output after
  either resume equals the straight run (only wall-clock timestamp normalized).
  Pending observers are absent from checkpoint restore.

Representative commands (use the intended environment and source path):

```sh
PYO3_PYTHON=/workspace/cw-evidence-native/bin/python LIBRARY_PATH=/workspace/cw-native-libs cargo test --locked --lib --manifest-path chronicler-agents/Cargo.toml
PYTHONPATH=src /workspace/shared/chronicler-venv/bin/python -m pytest -q tests/test_wealth_accounting.py
PYTHONPATH=src /workspace/cw-evidence-native/bin/python -m pytest -q tests/test_connected_world_native_contracts.py
```

The local linker needed an unversioned symlink in `/workspace/cw-native-libs`
to the installed `libpython3.13.so.1.0`. Earlier failed test invocations due to
missing libpython and stale unknown-purpose test values were diagnosed before
the final full pass. No production workaround or checkpoint-layout change was
introduced.

## Declared-scale A1 tolerance stress

The official `turn_speed_identity._SCALED_RUNNER` scales initial population
and carrying capacity. The labels do not mean the raw 12-region CLI starts
with that many agents. A raw unscaled seed-7 warmup was retained separately
and is excluded below. The declared targets are 43,700 and 18,800 people.

All four runs used two Rayon threads, exact mode, simulate-only and a
checkpoint every five turns. Only A1 was enabled in the on arms, in strict
mode. The 22k case also wrote the declared validation sidecars. This isolates
the fixed `1e-8` closure tolerance; it is not an all-features performance test.

| Case | Turns | Peak live agents | Strict frames | Max absolute closure | Births / deaths / moved |
| --- | ---: | ---: | ---: | ---: | --- |
| scaled52k_s7 | 20 | 47,731 | 20 | **0.0** | 12,589 / 11,564 / 95,227 |
| scaled22k_s42 | 30 | 23,929 | 30 | **0.0** | 9,843 / 4,715 / 63,638 |

| Case | Arm | Wall seconds | CPU seconds | Peak RSS KiB | Bundle bytes | Checkpoint bytes / raw bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| scaled52k_s7 | off | 15.22 | 11.08 | 345,544 | 681,804 | 5,414,502 / 22,540,966 |
| scaled52k_s7 | strict A1 | 12.68 | 11.84 | 339,280 | 836,597 | 5,455,727 / 22,700,602 |
| scaled22k_s42 | off | 9.95 | 10.60 | 478,788 | 654,846 | 6,089,967 / 21,989,699 |
| scaled22k_s42 | strict A1 | 13.75 | 12.13 | 496,544 | 854,668 | 6,143,926 / 22,197,384 |

These single measurements do not establish a speedup or a precise overhead;
other lane work and cache effects can affect wall time. Both pairs had
identical physical outputs after removing only A1's records/envelope and the
bundle timestamp: 10 files at 52k, 32 at 22k, zero differences. Arrow events,
memories, other state files and sidecars were byte-identical.

22k Arrow validation sidecars, identical off/on:

| File | Rows | Bytes |
| --- | ---: | ---: |
| validation_needs.arrow | 87,202 | 10,466,874 |
| validation_relationships.arrow | 122,831 | 1,843,562 |
| validation_memory_signatures.arrow | 293,653 | 3,524,954 |
| validation_resource_ledger.arrow | 570 | 14,946 |

The profiles used integrated HEAD `6bc0a0908ae24c947c5a7a589a49fbd4c9a67e1d`
with the lead's pending Python wiring. All four checkpoint headers record the
same actual Python package digest
`0627b87169a40feec3b9dab84ad4240d5c3ace0b3db1bd2f11a06b69359de33b` and the
extension above. The later source advance caused the exact checkpoint loader
to refuse timing-only reads with a source-digest mismatch; this refusal was
retained, not bypassed. Checkpoint read/write timing remains for the final
frozen whole-program profile. The independent lifecycle resume test above
used an unchanged source and passed exactly.

Reproduce the stress using the repository runner and an appropriate native
Python (record resource measurements separately):

```sh
RAYON_NUM_THREADS=2 python scripts/turn_speed_identity.py run /tmp/cw-a1-stress --source-root "$PWD" --case scaled52k_s7 --case scaled22k_s42 --cli-arg=--wealth-accounting --cli-arg=--wealth-accounting-mode --cli-arg=strict --cli-arg=--checkpoint-every --cli-arg=5
```

Full local profiles, commands, checkpoint headers, output identities and logs
are under `/workspace/evidence/native-a1/`; compact summary is `summary.json`.

## Limits retained

Native income/decay are still modeled sources/sinks; this adds no second
spendable balance or global cash conservation. Actual transfer rounding and
unexplained closure remain separate from modeled income. The fixed-enrollment
wage finding is unchanged; no claim is made that wages caused the earlier
aggregate decline or improved the null priced-out rate.

A6-affected target evaluation uses the existing unknown migration-driver code
because the legacy budget has no independent A6 term. This can reduce X1
flight/displacement classifications and must remain visible as a limitation
and harm in integrated evidence. Unaffected and record-only movements retain
their previous drivers. Legacy raw decision observation and migration-budget
queries refuse active A6 inputs rather than mislabel them as news/religion.
The A6 frame retains dated personal input/source-mask provenance.

Native army service preserves residence, migration and roster attachment. Its
food fraction is the actual army ration; there is no second civilian meal or
farm production. Soldier model income is retained; farmer levy income is
withheld. D3 suppresses the native soldier war mortality multiplier only in
active mode; record-only and default-off mortality are unchanged. Final
integrated D4 service, care/payment, all-features resume, compatibility,
viewer/browser and held evidence remain lead integration gates.

## Integrated enlisted-service diagnostic

After the lead's all-feature pilot exposed a Python/native farm-title mismatch,
independent inspection established that `provisioning::people_by_region` is the
shared L2 and household-retail population authority and already excludes the
frozen service census. An enlisted title holder remains a real owner and may
sell an existing title; service supplies no new title, civilian meal or purchase.
The native economy's food population and farmer count exclude the same stable
ids; rural health loss divides by this civilian farmer count. No additional
native production change was needed.

Six direct compiled-extension regressions were added to
`tests/test_connected_world_native_contracts.py`. Constructed fed-0/fed-1 census
forks verify civilian food demand/consumption, one excluded farmer plus a half
turn of actual health impairment, free-food and retail purchase exclusion,
existing-title sale without own consumption, positive withheld enlisted income,
continued civilian meal/income for an id outside the frozen census, and transient
consumption on success. The fixtures explicitly set linear foraging and positive
farmer yield; they do not claim natural recruiting evidence. The first fixture
iteration used a 16-year-old health worker (native adulthood is 20) and a dormant
first yield slot; its expected-positive checks failed until these fixture
assumptions were corrected. Production source was unchanged.

All 13 tests in the native contract module passed in 4.14 seconds, using the
lane Python source and the unchanged reviewed extension SHA256
`59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`.
These diagnostics do not replace the complete integrated lifecycle/resume or
held evaluation gates.

A later integrated-test setup caught the checkout's pytest `pythonpath = ["src"]`
overriding `PYTHONPATH`. The direct native checks above remained valid, but did
not exercise the lead's newer Python service hooks. Tests against the lead must
pass `-o pythonpath=/workspace/Chronicler/src` as well as the intended environment.
The missing new care helper failed import before any simulation; no held seed
was used. Integrated labor evidence below records the corrected invocation.

The corrected integrated invocation passed all **16 native contract tests in
5.76 seconds** against the lead's actual Python import path, with the unchanged
reviewed extension. In addition to the six direct service cases, this includes:

- A 16-turn, 32-region, ten-civilization procedural development world (seed 7)
  with CW6's FULL flags. It copies the actual final float32 economy input after
  every preparation hook, verifies retail stores exactly those operands, calls
  the real farm/title conservation authority every turn, and requires positive
  natural C2 farm removal. Outcome selection and labor are not mocked.
- Two constructed mixed urban/rural native pools. An actual spatial cell is
  assigned to a rank-2 city through ordinary native settlement assignment, then
  a real farmer in either that cell or the countryside enters the census. Native
  linear-forage output must equal the sum of civilian urban/rural farm shares
  minus an actual quarter-turn named work removal. Both cases passed.

The independent review found and the lead corrected an intermediate retail
factor captured before late C2/guard preparation, and a new-pool rebind that
could change rural health exclusions after preparation. The final factor is
now copied after all preparation hooks. Changed rosters trigger the same native
health preparation again before any livelihood work consumer. IC named work
already settles through RS2's explicit callback before retail; no second
allocation authority or settlement reorder was required. The initially raised
IC-order concern was withdrawn after following that callback in actual source.

Reproduce the integrated tests while this lane's test file is still separate:

```sh
PYTHONPATH=/workspace/Chronicler/src RAYON_NUM_THREADS=2 \
  /workspace/cw-evidence-native/bin/python -m pytest -q \
  -o pythonpath=/workspace/Chronicler/src \
  tests/test_connected_world_native_contracts.py
```

Test source is the lane checkout; production Python is the lead's integrated
checkout with its reviewed labor-boundary edits, not this lane's older Python.
Once integrated into one checkout, its normal `pythonpath = ["src"]` is correct.
These cases do not claim naturally activated named IC repairs or guards, and
remain distinct from the planned whole-program lifecycle/resume and held gates.
