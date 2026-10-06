# Durable local experiment sessions

Session contract `chronicler-experiment-session-v1`, envelope version 1. This is
operator tooling around the two already reviewed detached kernels. It adds no
mechanic, no milestone and no runtime integration.

Source baseline: accepted private candidate HEAD
`208d140d47d9f2dee0788267f79fa7276df22b42`, tree
`0762c7cff65e28ff326291ce31111b71e1d61ae3`. These identities were reviewed
against `COMMON.md` during independent review and match the hard-coded
`experiment_sessions.BASELINE_SOURCE_HEAD` and `BASELINE_SOURCE_TREE`, which are
re-checked on every read. The review also verified commit/tree/parent, the four
additive paths, blob and mode identities, a clean checkout with no remotes and
`git fsck` exit 0 against the delivered archive, so the earlier uncertainty about
`COMMON.md` is closed.

This increment adds exactly four paths:

- `src/chronicler/experiment_sessions.py` — the session library
- `scripts/experiment_session.py` — the standalone CLI
- `tests/test_experiment_sessions.py` — the focused gates
- `docs/experiments/session-workflow.md` — this document

Nothing else changes. The existing kernels, demo drivers, CLI registry,
snapshot and bundle schemas, native code, dependencies, viewer, fixtures and
reviewed evidence are untouched.

## What this is, and what it is not

It lets an operator stop a local detached run, inspect its receipt history,
submit the next explicit batch, and resume from a file without double-spending
rations or rolling cultural history backward. The two existing scripts remain
fixed scripted examples; this lane gives their reviewed mechanics a supported
operator workflow.

It is **not**:

- a milestone. M60a and M68a are unchanged detached experiments and M67 is not
  required for saving or inspecting detached records. This lane neither
  requires nor clears M67;
- a fix for kernel P3. M68a accepts a prestige of `10**5000`, but CPython's
  default 4300-digit integer/str conversion limit still makes `checkpoint_json`
  fail for that value. The transport policy rejects it explicitly below. The
  reviewed kernel is untouched and Python's process-wide integer limits are
  never changed;
- a change to kernel arithmetic, tuning, lifecycle or draw semantics;
- production serialization. Session files are experiment-only and are not a
  snapshot, bundle or checkpoint format the production code reads;
- a security protocol. The digests detect accidental alteration, corruption and
  mismatched configuration; they are not signatures, not encryption and not an
  integrity guarantee against an attacker who can rewrite the file;
- a scientific result. Every roster, policy, batch and draw is caller-supplied
  review-table data.

## Envelope

Every file is one canonical JSON object followed by a newline. The top-level
field set is closed: any missing, unknown or duplicate key is rejected.

| Field | Meaning |
| --- | --- |
| `contract` | `chronicler-experiment-session-v1` |
| `envelope_version` | `1` |
| `kernel` | `m60a` or `m68a` |
| `kernel_contract` | `chronicler-m60a-detached-v1` or `chronicler-m68a-detached-v1` |
| `source_head` / `source_tree` | the reviewed baseline identities above |
| `transport` | the explicit, versioned transport policy |
| `generation` | positive file generation, incremented once per committed write |
| `turn` | the latest committed turn |
| `genesis` | canonical JSON text: configuration plus complete admission/genesis |
| `history` | canonical JSON text: every admitted tick/batch in order |
| `latest` | canonical JSON text: the latest committed state and cursor/ledger |
| `genesis_digest`, `history_digest`, `latest_digest`, `session_digest` | SHA-256 over those exact texts |

`genesis`, `history` and `latest` are stored as nested canonical JSON text so
that every exposed record stays immutable and hashing is byte-exact.

For `m60a`, `genesis` carries the campaign `policy`, the `topology` and the
complete admission captured **before** the first tick: campaign ID, admission
turn, staging and target regions, the original roster with each member's kit,
morale, role and status, and the local stock table. `history` carries every
committed `Tick` in canonical form. `latest` carries the full `State` and
`Cursor`, including every receipt.

For `m68a`, `genesis` carries the genesis turn, the genesis participant roster
and the policy. `history` carries every admitted `Batch`. `latest` carries the
kernel's own `checkpoint_json` text, reused unchanged.

`BASELINE_SOURCE_HEAD` is part of the persisted identity. Any file written
against another head is foreign and fails explicitly; the constants move only
with a re-review of both kernels.

## Transport policy

Encoding and decoding require an explicit, versioned `TransportPolicy`; there
is no implicit default in the library. `documented_transport_policy()` returns
the illustrative subset used by the CLI's no-op output and by the tests.

| Field | Meaning | Documented value | Hard bound |
| --- | --- | --- | --- |
| `version` | must be `chronicler-session-transport-v1` | same | closed list |
| `max_bytes` | encoded file bytes and every caller submission | `8388608` | `1..67108864` |
| `max_records` | whitelisted records plus the records the reused M68a kernel checkpoint persists, counted in both directions | `200000` | `1..4194304` |
| `max_history` | committed turns, and the M68a genesis participant list | `10000` | `0..1048576` |
| `max_int_bits` | exact bit width of every transported integer, including kernel-derived receipt weights and thresholds and the outer envelope integers | `4096` | `1..14000` |

Out-of-domain values are errors, never clamped. A policy stored in a file must
equal the policy passed to the reader, so a session can never be read under a
narrower or wider domain than it was written with. The stored policy is decoded
through exact typed validation *before* any comparison, so a boolean or string
bound can never alias an equal integer through Python's `True == 1`.

Exceeding a byte, record, history, participant or integer bound raises
`TransportDomainError`, the one public type for genuine transport-domain limits.
Invalid *policy* values (a zero byte budget, an unknown version, a bound above
the supported maximum) remain `SessionError`, because no payload is at fault.

### Integer domain and the 121-bit cases

`max_int_bits` bounds `int.bit_length()` for every transported integer. Because
an integer needs at most `bits * log10(2) + 1` decimal digits, the hard bound of
14000 bits corresponds to at most 4215 decimal digits, which stays below
CPython's default 4300-digit conversion limit. No accepted value can require a
process-wide limit change.

The bounds are enforced **exactly** by `bit_length()`, not by a digit-length
approximation, on both sides of every path: each decoded record field and nested
container, the outer `generation` and `turn`, and every integer the reused M68a
kernel checkpoint persists, *including the kernel's own derived receipt weights
and thresholds*. A digit-count preflight runs before any decimal conversion, so
an over-wide literal never reaches CPython's converter.

That last point covers derived values: two 121-bit prestige weights produce a
122-bit electorate weight, so a 121-bit domain accepts those participants but
rejects the resulting ledger at its receipts.
- The independently reviewed 121-bit cases are supported. `max_int_bits=121`
  transports a prestige of `2**120` exactly; `max_int_bits=120` rejects the same
  value.
- `10**5000` needs 16610 bits and is rejected as an intentional
  transport-domain error **before any decimal conversion and before any write**.
- Nothing is truncated, rounded or replaced. The kernel still accepts the value
  and `sys.set_int_max_str_digits` is never called.

## Local persistence contract

One writer at a time, on supported POSIX local filesystems. `commit_session`
performs exactly these steps, in this order:

| # | Step | Failure outcome |
| --- | --- | --- |
| 1 | `platform-support`: POSIX, advisory lock, `fsync`, atomic replace, directory handle, existing directory | `UnsupportedPlatformError` before any mutation |
| 2 | `destination-shape`: destination absent or a regular file, never a link or directory | `PersistenceError` before any mutation |
| 3 | `writer-lock`: exclusive `flock` on the sibling `.<name>.lock` file, opened `O_NOFOLLOW` and rechecked as a regular file | `PersistenceError`/`OSError`; the destination is untouched |
| 4 | `destination-shape` recheck under the lock, then `expected-generation` | `PersistenceError`/`StaleGenerationError`; destination untouched |
| 5 | `checkpoint-validation`: full envelope encode, re-decode and complete reconstruction | `SessionError`; the destination is untouched |
| 6 | `temporary-write`: same-directory `O_EXCL` temporary file, mode `0600` | `PersistenceError`; prior bytes preserved |
| 7 | `file-fsync`: `fsync` of the temporary file | `PersistenceError`; prior bytes preserved, temporary file removed |
| 8 | `atomic-replace`: `os.replace` of the temporary file onto the destination | `PersistenceError`; prior bytes preserved, temporary file removed |
| 9 | `directory-fsync`: `fsync` of the parent directory | `DurabilityUncertain` |

Guarantees and limits:

- Durable success is reported only after step 9. The `CommitResult` is returned
  after the lock is released; nothing before that point is reported as durable.
- Steps 1 to 8 provably preserve the prior destination bytes.
- The destination name is validated twice: once before the lock and again inside
  it, and a third time immediately before `os.replace`. A shape change made
  between those checks by a noncooperating process is refused rather than
  committed, so a substituted link is never followed. The lock file itself is
  opened `O_NOFOLLOW` and rechecked as a regular file after opening.
- A step 9 failure is reported as `DurabilityUncertain` with an explicit
  "read the file back and reconcile it" instruction. It makes **no** claim about
  the previous content and performs **no** unchecked rollback: the new bytes may
  already be visible. The recovery path is to read the file, confirm the
  generation and session digest, and only then decide whether to retry.
- Directory `fsync` is deliberately **not** treated as best effort here. This is
  stricter than `artifact_io.atomic_write_text`, which silently tolerates an
  unsupported directory `fsync`; that helper is unchanged and is not used here.
- The lock file `.<name>.lock` (mode `0600`) is the only extra artifact. It
  carries no session state and may be deleted when no writer is active.
- One writer per session file. Concurrent writers are serialized by `flock`, and
  a writer whose expected generation is stale fails instead of overwriting.
- Network filesystems that do not provide a working `flock`, atomic
  same-directory rename or directory `fsync` are outside this contract. Such a
  failure surfaces as an explicit error; there is no silent weak fallback.
- `load_session` takes no lock and writes nothing. A successful read is already a
  verified resume, because reconstruction replays the whole committed history.

## Restore and verification semantics

### M60a

`create_campaign_session` admits the roster through the public `admit` and
records the admission inputs. Each `apply_campaign_tick` submits exactly one
explicit `Tick` through the public `advance` and stores the kernel's canonical
`receipt.inputs`, so the stored history is exactly what the kernel committed.

Reading rebuilds the session with public `admit` followed by public `advance`
for every committed tick, then compares `canonical_bytes` of the rebuilt
`Session` against the saved `State` and `Cursor`. The comparison covers the
complete state, cursor and every receipt. A recomputed digest alone is never
trusted, and no private kernel validator is called.

`campaign_logistics.py:212-219` requires `Session.state` and `Session.cursor`
together and `:408-440` validates their chain; this lane always persists and
restores them as one pair.

### M68a

`checkpoint_json` and `restore_checkpoint` are reused with their existing
semantics, including the strict replay validation the kernel already performs.
The envelope additionally stores genesis turn, genesis roster and every admitted
batch, and cross-checks them against the kernel checkpoint: policy equality,
genesis turn, genesis roster and the full admitted batch sequence must all
agree, otherwise the read fails.

`memome_experiment.py:302-352` supplies the strict checkpoint decoder. Its
`advance` at `:284-299` deliberately returns a historical prefix when an older
turn is replayed. The session manager therefore treats that prefix as a receipt
view only: the latest ledger, its admitted batch list and the persisted
generation are never replaced by it. The replay is matched against the kernel's
own canonical admitted batch from its validated prefix, so resubmitting the batch
in its **original proposal order**, or in any other order, is recognized as the
same committed transaction rather than reported as a contradiction. An identical
replay reports `changed=False` and writes nothing; a contradictory replay raises
and writes nothing.

## Command line

`python3.13 scripts/experiment_session.py` with no subcommand performs no file
read, no file write and no kernel call. It prints the closed command surface,
the baseline identities, the kernel contracts, the documented transport policy
and the commit order.

Every other subcommand requires `--transport`, a JSON file holding an explicit
versioned transport policy. Exit code `0` is success, `3` is a reported session
failure (a JSON error object on stderr), and argparse keeps its own codes.

```sh
printf '%s' '{"version":"chronicler-session-transport-v1","max_bytes":8388608,"max_records":200000,"max_history":10000,"max_int_bits":4096}' > transport.json

python3.13 scripts/experiment_session.py create --kernel m60a --path campaign.json --transport transport.json --demo
python3.13 scripts/experiment_session.py apply  --path campaign.json --transport transport.json --batch tick.json
python3.13 scripts/experiment_session.py inspect --path campaign.json --transport transport.json
python3.13 scripts/experiment_session.py verify --path campaign.json --transport transport.json

python3.13 scripts/experiment_session.py create --kernel m68a --path memome.json --transport transport.json --demo
python3.13 scripts/experiment_session.py apply  --path memome.json --transport transport.json --batch batch.json
```

- `create` uses exactly one of `--demo` (the existing hand-calculated demo
  tables, loaded read-only without running the demos) or `--admission` (a
  caller-supplied typed admission document). Supplying both or neither is an
  error. `create` requires an absent destination.
- `apply` submits exactly one explicit batch: a `Tick` body for `m60a` or a
  `Batch` body for `m68a`, decoded through the same closed field tables used
  for files. It loads, applies, and commits with the loaded generation and
  digest as the expectation. An identical replay reports `"committed": false`
  and writes nothing.
- `inspect` prints the latest committed state, roster, food accounting, a
  per-turn index and the latest receipts. Read-only.
- `verify` performs the full reconstruction, which is also the resume, and
  reports the generation, turn, file digest and session digest. Read-only.

Neither command starts a simulation, draws an RNG, generates a world, or touches
production state, bundles or the CLI registry.

### Admission and batch documents

`m60a` admission:

```json
{"policy": {...}, "topology": {"version": "...", "regions": [{"region_id": 0, "neighbors": [1, 2]}]},
 "campaign_id": "...", "turn": 0, "staging": 1, "target": 2,
 "soldiers": [{"agent_id": 101, "region": 1, "rations": 8, "morale": 800, "role": "soldier", "status": "active"}],
 "stocks": [{"region": 0, "rations": 0}]}
```

`m68a` admission:

```json
{"policy": {...}, "genesis_turn": 0,
 "participants": [{"agent_id": "basic-0", "group": "basic", "slots": [4, 3, 2, 255, 255, 255, 255, 255], "prestige": 1}]}
```

`m60a` tick body:

```json
{"turn": 1, "orders": [], "credits": [],
 "conditions": [{"agent_id": 101, "unmet_needs": 0, "information_quality": 1000}],
 "draws": [{"agent_id": 101, "value": 9999}], "supply_sources": [1]}
```

`m68a` batch body:

```json
{"turn": 1, "proposals": [{"proposal_id": "minority", "recipient": "basic-1", "slot": 1, "candidate": 3, "draw": 199}]}
```

Every explicit caller document passes through **one** bounded strict decoder,
`submission_from_bytes`: a byte-length preflight before reading, duplicate-key
rejection, nonfinite-constant rejection, float rejection, and an integer-literal
digit preflight before any decimal conversion. Only then does the closed record
table decode it with exact fields and exact bit widths. A duplicate key therefore
cannot be collapsed into agreement with an integer field, and a malformed or
over-wide document is rejected before any apply or commit, leaving the
destination's bytes and modification time unchanged.

## Library surface

`create_campaign_session`, `create_memome_session`,
`campaign_session_from_payload`, `memome_session_from_payload`,
`campaign_tick_from_payload`, `memome_batch_from_payload`, `apply_campaign_tick`,
`apply_memome_batch`, `session_turn`, `encode_session`, `decode_envelope`,
`encode_envelope_text`, `decode_envelope_text`, `session_digest`,
`load_session`, `commit_session`, `session_report`, `submission_from_bytes`,
`transport_policy_from_text` and `transport_policy_from_payload`.

Errors form a closed tree under `SessionError`: `ContractError`,
`TransportDomainError`, `IntegrityError`, `PersistenceError` with
`StaleGenerationError`, `UnsupportedPlatformError` and `DurabilityUncertain`.
A malformed envelope scalar, an unhashable `kernel`, or a non-integer transport
bound is an ordinary `SessionError`, so a hand-edited file yields a JSON error
and exit code 3 rather than a traceback. Kernel rejections surface as the
kernels' own `ValueError`.

## Verification

The focused suite is standard-library only, so it runs either way:

```sh
PYTHONPATH=src python3.13 -m unittest discover -s tests -p test_experiment_sessions.py -v
PYTHONPATH=src python3.13 -m pytest -q tests/test_experiment_sessions.py
PYTHONPATH=src python3.13 -m unittest discover -s tests -p test_memome_experiment.py
python3.13 -m pytest -q tests/test_campaign_logistics.py
```

These commands are listed for reproduction; no execution result is claimed here,
because this increment was authored without command execution. The coordinator
runs the focused suite, the unchanged external reviewer probes and the existing
kernel suites against the exact repaired bytes.

The pytest path uses the unchanged repository `conftest.py`, whose import needs
Pydantic; the library, the CLI and the `unittest` path do not.

What the focused suite covers: both hand-calculated demos reproduced exactly,
seven sequential commits, interrupted resume equal to the uninterrupted receipts
and ledger, identical replay writing nothing for both kernels, contradictory
replay, gaps and reused command IDs staying atomic, older memome replay leaving
the latest ledger and generation intact **including the original, unordered
proposal order and a reordered equivalent**, strict duplicate/unknown/missing
fields, nonfinite values, floats, booleans in integer fields and malformed tuple
containers, changed policy, source, history, state and checkpoint content
rejected after the digests are resealed, transport version and bound
enforcement, exact bit-width enforcement on every decoded record field, nested
container, outer envelope integer and kernel-derived M68a receipt integer
(including the 122-bit weight that two 121-bit prestiges produce), 121-bit
support, `10**5000` rejection before any write, limits never clamping content,
record immutability, foreign records rejected without touching state, stale
expected generations, injected write, file-`fsync`, `replace` and directory-
`fsync` failures with their asserted file outcomes, unsupported platforms
failing before any mutation, a foreign file never being overwritten, destination
shape rechecked under the writer lock, a non-regular lock file refused, the
single private lock file, fresh-process and hash-seed determinism for both the
library and the CLI over a full create/apply/verify/inspect workflow, duplicate
and malformed CLI submissions rejected before any commit with unchanged bytes and
modification time, the no-op default invocation, and an import scope that admits
only the standard library and the two reviewed kernels with no RNG, native or
production module.

Existing kernel suites supplement these gates; the session tests do not replace
them. No scientific workload, seed sweep, world generation or dependency,
schema or native change is involved.

## Limitations and non-claims

- Single writer per file, single machine, POSIX local filesystems only. The
  generation/digest check is a cooperative guarantee between well-behaved
  writers; the path-safety checks additionally refuse a destination that is or
  becomes a link, but they are not a defence against a hostile concurrent
  mutator of the containing directory.
- No locking across machines, no leases, no fencing tokens, no repair tooling
  and no backup rotation.
- `DurabilityUncertain` is a report, not a resolution: reconciliation is the
  operator's next explicit step.
- History is never pruned, so file size grows with committed turns and is bounded
  only by the transport policy and the kernel's own receipt cost.
- Reading is `O(history)` for both kernels, because correctness is favored over
  speed in these bounded review tables. No performance claim is made.
- M67 is not required and is not cleared. Full A01/native-byte acceptance stays
  withheld and the documented native object-key-order failure is unchanged.
  Kernel P3 remains open with its source owner.
- Serialization `507ef977` stays held and permission-blocked; G05 stays
  excluded. M71's cancelled launch, permanently closed V3, and all new
  scientific worlds, seed sweeps, calibration campaigns and scale runs remain
  out of scope.
- This lane is one of three parallel lanes and imports neither of the others.
  Combination is a separate, separately reviewed assembly task.

## Handoff

Independent important-code review of the actual delivered commit bytes is
required before integration. A delivery should state the exact commit, tree and
parent, the four added paths with blob IDs and modes, the transfer archive's
size and SHA-256, the private manifest and restore identity, clean-tree and
no-remote evidence, the commands run with their exit statuses, and the
deterministic session-digest and file-digest values for the demo workflows, plus
the limitations above. No public write, production activation or public
publication is performed or implied.