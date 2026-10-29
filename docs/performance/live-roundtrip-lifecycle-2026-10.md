# Draft live round-trip lifecycle repair — 2026-10-29

Status: inactive draft; tests and timing remain unrun during the
forkserver quiet window. Base source is
c76efe8552b4c6c288ebb1f813e2c0a58e5957b1. This changes only integration-test
control flow and fixture cleanup, with no production simulation or live-server
behavior changes.

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

## Validation boundary

No tests, worlds, builds or benchmark ran for this draft during the quiet
window. Focused set/fork/cleanup tests and then the complete live integration
file must pass after the lead releases that window. Native and no-native
checks remain separate; new results must retain exact source/runtime identity.

These real socket/thread tests belong to the integration lane, outside the
bounded offline guard. Production horizons, physics, RNG, output writers and
checkpoint contracts are unchanged. Any wall-time improvement must be observed
after the stronger completion and cleanup assertions pass.
