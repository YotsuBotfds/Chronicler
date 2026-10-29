# Live narration invocation: test-owned synchronization

This isolated child of qualified `cbf6e368` changes one integration test. It
preserves the empty spy result, all twelve original kwargs assertions, the
five-second failure bound, the WebSocket context and normal fixture teardown.
No production code, dependency, workflow or simulation behavior changes.

`test_narrate_range_passes_great_persons_and_agent_name_map` now sets a
`threading.Event` **after** updating `captured_kwargs`, then explicitly asserts
`await asyncio.to_thread(event.wait, 5.0)`. The wait stays off the event loop.
Previously a receive already in progress could not notice the dictionary
update: the server correctly emits no completion entry for the spy's empty
`[]` result (`live.py:441–442`, `795–799`). No sleep or shorter deadline is used.

Root reviewed the source, fixture and a dedicated loopback observer before
exactly one old process followed by one new process. Both exact singleton
nodes passed; neither was retried. These are observations from this small
qualification, not confidence estimates or a suite-wide speed claim:

| Measurement, seconds | Original cbf test | Event test |
| --- | ---: | ---: |
| Test body | 5.095193 | 1.681849 |
| JUnit setup + call + teardown | 5.569 | 2.245 |
| Whole child process | 7.494207 | 4.724938 |

Each guard remained active with **zero** native imports/loads, generation,
runtime/factory, LLM completion/API, process-launch or denied-network attempts;
no Chronicler native module was loaded. Each child used one CPU (actual affinity
`[0]`), thread caps 1, a 30-second process wall bound, 25 CPU seconds, a 1 GiB
address-space cap and a 1 MiB individual output-file cap. The separate `/tmp`
filesystem retained its 3 GiB floor plus the registered 16 MiB admission reserve.
All eight recorded test/config/runtime source hashes matched before and after.

This is a dedicated **loopback** observer, not the ordinary offline guard.
It maps only the unchanged `localhost` test-server host to numeric `127.0.0.1`,
permits ephemeral loopback binds and connects only to registered server ports,
and permits the async AF_UNIX wakeup pair without Unix bind/connect. Inference
port 1234, other endpoints, DNS and child processes remain denied. Client
construction reads actual processor metadata from `os.uname().machine` without
spawning platform's optional subprocess; no test/client mock is changed.

The unchanged narration path attempts `WorldState.model_validate` on its
bundle-shaped dictionary; model hydration was allowed, while world generation
and simulation entrypoints were denied. This is not a no-model-import claim.
The daemon-server fixture still signals `server.stop()` in `finally`; no added
join or stronger cleanup guarantee is claimed. No whole-file suite, native
lane, full CI, simulation, statistical study or main merge was run here.

External evidence: `/tmp/chronicler-review-evidence/live-narration-test-signal-20261029/`.
The sealed JSON readout is `old-new-qualified-readout.json` (SHA256
`4a31fb93b1e2e4b15857d55418d821364b8505ea096a1b9aebfabcb037850821`). Original logs, JUnits, guards, staged
old/new module bytes, source snapshots, static twelve-assertion proof and root
pre-execution approval are retained. The source branch remains separate and
unpushed pending root integration review.
