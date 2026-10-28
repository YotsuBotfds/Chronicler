# Python qualification supervisor — preregistration

Registered before implementation/tests on a separate branch from frozen source
`d051d7c06b1a490841d148b8906bde22f2f5d0f0`. This is a development-tool follow-up;
it does not change that source's active qualification, existing gate recovery,
simulation code, experiment defaults, or source/native environments.

## Fixed scope and acceptance

The tool runs one full Python pytest lane against an explicitly named clean,
immutable source checkout and interpreter. Its only native choices are an exact
compiled extension SHA-256 or verified absence of the extension. It is not a
shell executor, gate runner, partial-test aggregator, or native build/install
tool. A passing Python suite does not qualify Rust tests, scientific balance,
new mechanisms, performance, rendering, or another operating system.

The child invocation is fixed: full pytest, quiet output, the chosen source's
`src` and the checkout root on the import path, no pytest cache, an external temporary directory and
JUnit output. There are no extra-command, test-selection or pytest-argument
passthroughs. Inherited pytest argument/plugin overrides and configured addopts
are cleared; the frozen checkout's test paths and conftest still apply. Native
execution preloads the actual compiled submodule and checks the three exported
simulator classes; absence is checked without accepting a fake replacement.

Every run requires a new output directory outside the source checkout. The
request records the fixed protocol, source SHA, interpreter path and runner
bytes. Before and after pytest, capture/check source HEAD, clean status,
tracked-file hashes, interpreter/version/platform, dependency versions, native
file/hash and thread environment. Use one-thread numerical/native settings and
`PYTHONHASHSEED=0`; do not print inherited credentials or the full environment.
Tracked symlinks and submodules are rejected: a clean link name does not freeze
its target bytes, including links checked out as text on Windows.

Only the following earns a passing terminal receipt: child exit zero, a valid
JUnit report with executed test cases, no failures/errors and unchanged required source/runtime
identities. Nonzero test exits, missing/malformed JUnit, changed identities,
launch errors, and interrupted work remain distinct failed/unknown evidence.
Logs, JUnit and atomic live/terminal receipts remain in the external destination.
File writes flush and replace atomically. Do not overwrite another run.
Status rechecks pass/outcome/exit consistency, both required artifact hashes and
actual JUnit cases/counts before returning a verified passing receipt.
Pytest 9 counts successful subtests in its JUnit `tests` header without writing
additional testcase elements. Such an excess is accepted only when the final
pytest summary independently matches every serialized passed/skipped case and
the exact successful-subtest excess. Failed, unsupported or mismatched subtest
accounting remains an error. Receipts report parent cases and successful
subtests separately, retaining the declared JUnit total.

## Detachment and process boundaries

Foreground execution uses portable Python. Detached launch is Linux-only in
this version: it uses a new session, redirected input/output, a copied immutable
runner and a PID/boot/creation identity. Status must verify that identity before
claiming a worker is alive; unsupported liveness inspection reports unknown.
Shell-exit survival is tested separately from machine-loss behavior. No machine
restart, container teardown, or disconnected-host survival is promised.

The full pytest process is one atomic job, preserving interactions between
tests. Cooperative pause requests during pytest are pending until its exit.
Pause acknowledgement occurs only before launching pytest or after that child
has exited, with a live verified supervisor and no active pytest child. No
signal pauses a running test. Resume clears the request; status distinguishes
requested transitions from worker acknowledgement. Pause intervals are recorded
and are not performance evidence.

An absent worker with no terminal receipt is interrupted, never passing. A
subsequent attempt starts the full lane in a new directory. There is no automatic
acceptance of partial tests, seed outputs, or a previous lane's progress.

## Verification registered before execution

After the reserved quiet benchmark finishes, run focused tests covering:

- mandatory source/interpreter/native choice, fixed command and environment;
- fresh external destination and atomic status/terminal receipts;
- exact compiled module identity, native absence and mismatches;
- source/runtime changes and nonzero pytest exit handling;
- JUnit missing, malformed and failure cases;
- verified live/dead/reused process identities;
- pause pending during a child, acknowledgement only at a boundary, resume;
- a real tiny committed source checkout under the selected interpreter, with
  actual pytest/JUnit output, and detached/boundary checks where supported.

Mocked probes test orchestration contracts. A real tiny-child result qualifies
the tool path on its recorded host only. Record all commands, failures, passes,
skips, source/runner identities and platform limits before reporting completion.

## Usage

Run from any checkout containing the tool; the source being qualified is named
explicitly and can be a different immutable worktree:

```sh
python scripts/python_qualification.py run \
  --source /path/to/frozen-checkout --git-sha FULL_SOURCE_SHA \
  --python /path/to/isolated-env/bin/python --native-sha EXTENSION_SHA256 \
  --output /outside/source/qualification-001 --detach

# A separate no-native lane uses its own interpreter and fresh destination.
python scripts/python_qualification.py run \
  --source /path/to/frozen-checkout --git-sha FULL_SOURCE_SHA \
  --python /path/to/no-native-env/bin/python --no-native \
  --output /outside/source/qualification-002 --detach

python scripts/python_qualification.py status --output /outside/source/qualification-001
python scripts/python_qualification.py pause --output /outside/source/qualification-001
python scripts/python_qualification.py resume --output /outside/source/qualification-001
```

Replace the uppercase identity placeholders with complete lowercase hashes.
Omit `--detach` for foreground execution. `--start-paused` permits a deliberate
pre-pytest boundary acknowledgement. A pause requested during pytest stays
pending until that whole child exits; this tool cannot create a quiet interval
halfway through a test suite.

Receipts are `request.json`, `launch.json`, `status.json` and terminal
`result.json`; execution artifacts are `supervisor.log`, `pytest.log` and
`pytest-junit.xml`. `status` reports lost/reused Linux workers as interrupted
and reports unverified liveness as unknown on unsupported hosts. Neither
launch nor progress is a passing result.

## Evidence status

Preregistration commit: `02f46f31`. Focused mocked and actual tiny-child checks
ran after the reserved benchmark window on Linux/x86-64, Python 3.13.5:
**27 passed** in the no-native environment (4.04 s), and **27 passed** with
the actual compiled extension (9.52 s), SHA-256
`fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317`.

Terminal-receipt corruption, a changed external symlink target, source/runtime
changes, missing/malformed/empty JUnit evidence, failed launch, and cooperative
pause/resume have explicit regression cases. Foreground and detached tiny
pytest jobs produce verified one-test passing receipts.

These are tool checks, not full-source, Rust, population, performance, or
cross-platform qualification. Windows/macOS execution and machine-loss
recovery were not run. Existing interrupted suites and recovered scholarship
gate jobs are not reclassified, changed or controlled by this follow-up tool.

The first full-suite launch exposed a launcher-path defect: a copied runner
does not receive the checkout root at `sys.path[0]` as `python -m pytest` does.
That attempt ended at collection with missing checkout-level `tests`/`scripts`
imports and remains a failed execution receipt. The corrected fixed environment
includes both `src` and the checkout root; the actual tiny fixture now imports
both namespaces so this boundary is exercised before another full attempt.

The corrected full-source executions on frozen `d051d7c0` subsequently exited
zero: native/fb20 had 7,348 passed and 6 skipped in 1,049.62 s; no-native had
7,037 passed and 303 skipped in 738.74 s. Each also passed 526 subtests. The
original strict reader rejected pytest 9's JUnit header accounting, so those
original terminal receipts remain `qualification_error`. A later reader-only
adjudication may validate the unchanged hashed logs/XML and recorded stable
before/after identities; it must hash-link the original receipt and both runner
versions, preserve the original result, and state that no tests were rerun.
The initial collection failure remains a failed attempt.

Reader-correction checks passed on the same Linux/Python 3.13.5 host: **36
passed** without native (3.76 s) and **36 passed** with native/fb20 (4.53 s).
The real foreground/detached tiny children each execute two successful subtests.
Regression cases reject missing/mismatched terminal summaries, failed subtests,
duplicate counters, wrong parent counts and trailing output. These checks do
not add cross-platform or scientific qualification.
