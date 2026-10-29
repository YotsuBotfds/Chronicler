# Care source witnesses after optional artifact-budget composition

The first CI run for budget composition `b95281a3` is preserved as a failed
integration attempt: run `40966535032`, attempt 1. The bounded offline lane
stopped in the existing care codec source-witness contract after 42 passing
parents and 61 successful subreports in its health-care-policy chunk. It first
reported the old `agent_bridge.py` digest; a static audit also found the old
`main.py` digest in the same ten-member literal map. The budget115 module was
later in the chunk and had not been reached. No same-source retry is claimed.

This source-only child deliberately rebinds exactly those two literal hashes:

| Reviewed source | Previous witness | Composed witness |
| --- | --- | --- |
| `src/chronicler/agent_bridge.py` | `6665e4620a4f9f249c52788d9dd97a92d37d1d32aa47cca3e040d9938cc3039e` | `0ad61ddadf43e1a52b55559a9708e4a5d7b90350f7a6979c192534a9d3f32e18` |
| `src/chronicler/main.py` | `bb40d2188e28bf1c6d3dfaebaf1e2e0b16483dc67c35ab842711c46c95a41861` | `0e62573977eab538606ad3be0025e371206067b347917816fb199318016c05ec` |

Review covered the complete qualified65-to-budget composition diff in both
files. The bridge changes admit and retain an explicit output budget, pass it
to the sidecar, latch output faults and refuse persistence of the transient
budget. Main propagates admission through optional output writes and rejects
unsupported budgeted supplied/resumed/checkpoint or interactive paths. Every
function name is retained; changes are confined to those output paths and
their entry checks. Specializing exact `artifact_budget is None` predicates,
absence of the transient attribute, and the added keyword restores the
qualified65 AST in both files. The predicate/keyword specialization is an
external static review proof; the committed test continues checking exact
complete source-file hashes.

The eight other witnesses, all ten map members, the entire test body and all
assertions remain intact. Care phase, recorder, native09ec, simulation,
codec/mechanics and their source-binding constants stay byte-exact b952.
The entire product package, optional budget115, owner305 registration, six
skips, 623 subreport seal, 38 chunks, 335 selected source pins, dependency
locks and workflows are unchanged. The historical wealth-floor campaign's
separate m53b source registration remains bound to its original source.

A future cheap preflight should AST-read explicitly registered current-source
witness maps, verify each literal against its target bytes and report all
mismatches before a full CI dispatch. Historical experiment registrations need
their own source authority and should be classified separately. The preflight
must refuse drift and require review; it must never regenerate expected
digests automatically. No preflight helper is implemented in this repair.

This child has received source/Git/hash/AST checks only. Its tests and CI are
unrun. Independent source review and its own first CI remain required. Static
projection does not qualify actual default trajectories, output bytes, live
care capture, installed native API/schema, World/checkpoint/RNG replay,
owner/log/IPC aggregate enforcement, scientific efficacy or performance.
