# Validated live round-trip lifecycle repair — 2026-10-29

Status: validated test-only change, integrated into review source `1c5728b7`.
Focused validation tested exact isolated source
`0fa6a607ab5120b8676172092bf4250c26290580`, based on
`c76efe8552b4c6c288ebb1f813e2c0a58e5957b1`. It changes integration-test
control flow and fixture cleanup; production simulation and live-server bytes
remain unchanged. The earlier timing quiet window ended before these checks.

## Observed waits and source explanation

The historical d028 CI duration report attributed about 20.325 seconds to each
of test_set_round_trip and test_fork_round_trip in both native and no-Rust lanes.
Those are historical test attributions, not fresh measurements or a simulator
speed comparison. The integration test source is unchanged between d028 and c76
(Git blob e1dab407c4337e30744a562302dce267cd998599).

Both tests request ten turns with a pause every three. At the first pause they
perform their operation, check its response and send continue. Their guards
also cover the continue command, so subsequent pauses receive no response.
At turn six the simulation waits for a command while the test waits up to
ten seconds for another server message. Timeout was swallowed, allowing a
test to pass after checking the first response without completing its horizon.

The fixture then sets quit_event and stops the WebSocket server, but does not
wake the simulation's pause queue. make_live_pause without checkpoints blocks
in command_queue.get; quit_check is evaluated between turns. The fixture's
ten-second thread join can therefore expire with a live daemon worker.
This source path explains two configured ten-second waits; no measured phase
breakdown is claimed.

## Repair

The set/fork operation still happens once with every original acknowledgement
and saved-file assertion retained. Every pause now receives continue, and each
test requires the completed message with the original ten-turn horizon.
The existing receive and acknowledgement timeouts are unchanged; a receive
timeout fails instead of silently passing.

Fixture shutdown signals both the between-turn quit event and the paused
command queue, joins the owned simulation thread using the existing ten-second
bound, then stops and joins the owned WebSocket server thread. An unjoined
worker now fails explicitly. Successful shutdown is idempotent.

A new real-connection regression deliberately leaves the worker paused at turn
three, closes its client, invokes fixture shutdown, and requires both owned
threads to terminate and the quit run's result to exist. This exercises cleanup
instead of replacing it with a sleep or removing assertions.

## Completed validation

Three focused set/fork/paused-cleanup cases passed. A 68-case native-installed
selection passed the complete live integration file, `test_live.py`,
`test_live_checkpoints.py`, `test_live_checkpoints_native.py` and
`test_batch_websocket.py`, including hybrid/off native checkpoint cases.

A corrected external observer then passed the entire 18-case live integration
file in both explicit contexts:

| Context | Passed | pytest seconds | Set/fork horizon | Paused cleanup |
| --- | ---: | ---: | --- | --- |
| Python 3.13.5 with verified compiled extension | 18 | 13.29 | ten turns each | stopped at three; both owned threads joined |
| Python 3.13.5 with native package absent | 18 | 11.12 | ten turns each | stopped at three; both owned threads joined |

The native context reused compiled submodule SHA-256
`fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317`
from the source-compatible crate tree
`a4703ef4e9a21b5dbb194d318536a46e6ca8b71c`. Actual compiled origins, three
exported classes and checkpoint schemas were checked. This focused validation
performed no native build. The no-Rust context verified the package absent.
Both used CPU 3, one-thread numerical/Rayon/Python caps and hash seed zero.

Every launched simulation terminated and its owned server joined; no new
Python threads remained. The single-client rejection case deliberately starts
no simulation. Corrected-observer set/fork call times were 0.637/0.526 seconds
with native and 0.417/0.476 without native, with unchanged receive/acknowledgement
deadlines. Teardown no longer waits for an unwoken pause queue. These are
observations of stronger tests completing ten turns, not controlled timings
against the historical cases that stalled at six turns or a simulator speedup.

The first 68-case pytest selection passed in 37.32 seconds, but its outer
observer exited one after misclassifying the intentionally never-started
single-client worker as unjoined. That nonzero outer result and original log
remain retained. The corrected observer distinguishes never-started workers
and passed both full live files. An earlier external-wrapper syntax rejection
also remains recorded and occurred before pytest. Neither issue changed
project source or the successful pytest results.

External evidence `0fa6a607-validation-20261029-001` retains commands, actual
completed-turn/thread rows, identities and raw outputs. Its validation receipt
SHA-256 is
`4d474424b04e563a685e25a7d94efb9c958ab5f2023d586ff30facc191f1732c`.
Subsequent consolidated source `1c5728b7` passed the complete native/no-Rust
suite and all six CI jobs; see the
[exact CI record](../integration/recovered-review-ci-2026-10-29.md).

These real socket/thread tests belong to the integration lane, outside the
bounded offline guard. Production horizons, physics, RNG, output writers and
checkpoint contracts are unchanged. No controlled workload-speed claim is
made from the historical attribution or these targeted checks.
