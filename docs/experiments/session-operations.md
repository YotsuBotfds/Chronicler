# Explicit session submission and reconciliation

`chronicler-session-operation-v1` composes the accepted public
`experiment_sessions` APIs for detached M60a campaign and M68a memome sessions.
It submits one caller-supplied tick or batch, and offers a separate read-only
observation after a failed or uncertain commit. It adds no mechanic, simulation,
production registration, session schema, lock service, queue or retry loop.

The session envelope retains its reviewed kernel baseline HEAD
`208d140d47d9f2dee0788267f79fa7276df22b42` and tree
`0762c7cff65e28ff326291ce31111b71e1d61ae3`. The operation contract identifies this
composition seam; it does not authenticate the checkout or the caller.

## One explicit operation

```python
from chronicler import experiment_sessions as es
from chronicler import session_operations as operations

# transport is an explicit, validated es.TransportPolicy.
# submission is the UTF-8 JSON bytes of one complete public Tick or Batch.
try:
    receipt = operations.apply_operation(
        "session.json", transport=transport, submission=submission)
except (es.SessionError, ValueError, OSError) as error:
    receipt = error.operation_receipt
    # Inspect or retain the receipt. This exception never triggers a retry.
print(receipt.as_payload())
```

The operation loads and reconstructs the session, parses the submission with the
accepted bounded strict parser, decodes its exact typed kernel record and calls
the public apply function. Changed state is preflighted with `encode_session`
and `encode_envelope_text` to calculate its exact next-generation full-file
digest. It then calls `commit_session` once against the loaded generation and
full-file digest. That existing function remains authoritative for platform,
destination shape, `flock`, generation checks, replacement and durability.

The frozen receipt carries a `base` and an `intended` `SessionIdentity`, with
four distinct fields: `generation`, `file_digest`, `session_digest` and `turn`.
`file_digest` hashes every exact on-disk byte, including envelope metadata and
the final newline. `session_digest` is the public envelope's payload digest.
They are never interchangeable. A stage that failed before computing its
identity leaves that field `null`; an invalid/unreadable base has neither
identity, while a strict submission or preflight rejection may have only `base`.
Replays have an observed `base` and no intended new generation.

When a base was successfully loaded, `receipt.expectation` is a closed frozen
`ReconcileExpectation`: the caller's exact target path text, full transport
policy, kernel ID and kernel contract, observed base identity and optional
intended next identity. Changed submissions require intended generation exactly
`base.generation + 1` and turn exactly `base.turn + 1`. The operation checks that
the candidate retains that loaded session's genesis and complete prior history;
it accepts no arbitrary caller-supplied candidate session. It materializes the
receipt fields and exact intended digest before attempting the commit.

| Status | Meaning |
| --- | --- |
| `committed_durable` | The one public commit returned after its directory-fsync gate for the exact intended identity. Another writer may advance the target before this receipt is delivered. |
| `replay_no_write` | Identical historical submission; this operation did not commit. `base` identifies the observed generation/file digest and turn; `intended` is null. The observed version need not remain current. |
| `stale_conflict` | Another cooperating writer moved the expected file. No retry, reload, rebase or second commit occurs. |
| `rejected` | Validation, kernel, platform or prepublication persistence failure, with the original typed error. |
| `durability_uncertain` | Replacement occurred but directory fsync failed; intended bytes may already be visible. No rollback or durable-success claim. |
| `commit_outcome_unknown` | An unexpected exception escaped an attempted commit; publication cannot be ruled out. The precomputed expectation supports explicit readback, never automatic retry. |

Success returns the receipt. Failures raise the original exception, with its
original type and an `operation_receipt` attribute containing the status and
error type/detail. This preserves `TransportDomainError`, `IntegrityError`,
`StaleGenerationError`, `UnsupportedPlatformError`, `PersistenceError` and
`DurabilityUncertain`, as well as ordinary file and kernel errors. Known
precommit errors retain rejection/stale status. An unexpected commit exception
(for example, unlock/descriptor cleanup after publication) is conservatively
`commit_outcome_unknown`; no failed return is assumed to prove unchanged bytes.
Ordinary read errors before attempting commit remain `rejected`. Nothing is
clamped, rounded, automatically recovered or retried. M68a late replay retains
the latest ledger, including when the caller resubmits its original noncanonical
proposal order; it never persists the kernel's historical-prefix receipt view.

## Explicit read-only reconciliation

```python
observed = operations.reconcile_operation(
    "session.json", transport=transport,
    expectation=receipt.expectation)
print(observed.as_payload())
```

The supplied expectation must be an exact `ReconcileExpectation` record, with
exact `SessionIdentity` records, positive exact-integer generation, nonnegative
exact-integer turn, lowercase SHA-256 digest strings, valid next-generation/turn
relationships and matching kernel contract. The explicit path and transport
arguments must match that declaration before I/O. These are declared comparison
inputs, not authenticated provenance. Reconciliation loads the current file
through the public loader and full history reconstruction, then compares the
kernel contract and all four identity fields, including complete-file digest
and generation. Equal payloads at different generations do not match. Equal
bytes at two targets do not silently rebind the expectation to the other path.

| Observation | Meaning |
| --- | --- |
| `intended_visible_durability_unknown` | The current validated file matches the intended identity. Readback does not prove or repair a failed directory fsync. |
| `base_visible` | The current validated file matches the base identity. |
| `different_valid_file` | The current file reconstructs successfully but matches neither identity. No overwrite permission is inferred. |
| `unreadable_or_invalid` | Read/parse/reconstruction failed; `current` is null and error type/detail are retained. `missing=true` explicitly identifies `FileNotFoundError`. |

Reconciliation writes no bytes, creates/deletes no lock, performs no fsync,
rollback, rebase or automatic submission. Every observation is one read, not a
reservation or lock lease; another writer can subsequently move the file. A
replay expectation has no intended version and can report only base-visible,
different-valid or unreadable/invalid. A receipt with no base cannot supply a
reconcile expectation. Path matching is textual: aliases are not resolved or
merged, and relative paths remain relative to the caller's working directory.

## Command line

With no `--enable`, even supplied nonexistent paths produce the same fixed
disabled JSON receipt, exit 0, and no file I/O, decoding, kernel call or lock.
There is no illustrative-fixture mode or hidden input creation.

```sh
python scripts/session_operation.py
python scripts/session_operation.py apply --path nonexistent --transport nonexistent --submission nonexistent

python scripts/session_operation.py --enable apply \
  --path session.json --transport transport.json --submission tick-or-batch.json
```

The transport document is the existing exact five-field policy JSON. The
submission document is one complete accepted campaign `Tick` or memome `Batch`;
use the formats in [session workflow](session-workflow.md). The driver reads the
transport document with a 4096-byte budget, then the submission with the explicit
transport byte budget. Both reads use opened-file `limit + 1` checks before
parsing, without relying on file metadata. Session loading and persistence use
the accepted library unchanged, including its transport checks and limitations.
On this branch's accepted baseline the loader/current-destination check still
allocate the full session bytes before checking the cap. Bounded session
preallocation acceptance requires integration with the independently reviewed
session-read-bounds refinement; this module adds no duplicate private reader.
Source-byte limits are distinct from decoded record/history limits and stdout
size; the transport cap is not a report-byte or total-memory guarantee.

To reconcile, explicitly pass the complete `expectation` object from the
operation receipt as a JSON argument string. It contains exactly `target`,
`transport`, `kernel`, `kernel_contract`, `base` and `intended`; the last field
can be null for a no-write replay. For example, with that exact object retained
in a shell variable:

```sh
python scripts/session_operation.py --enable reconcile \
  --path session.json --transport transport.json \
  --expectation-json "$EXPECTATION_JSON"
```

Successful operation/observation JSON goes to stdout, exit 0. Typed operation
failures and unreadable/invalid reconciliation observations go to stderr, exit
3. Argparse retains its normal usage errors. A stdout failure after a completed
operation reports `output_delivery_failed` with the original operation receipt
on stderr where possible, exit 3. It does not undo the commit or reclassify it
as a rejected submission. If both channels fail, no usable receipt is delivered;
do not infer that the operation did not commit or rerun it automatically.
An observation of intended bytes
is always labeled durability unknown, even when inspecting a prior durable
success receipt. No error output authorizes a retry.

## Scope and focused gates

Cooperating same-path writers on a supported POSIX local filesystem already
serialize through the accepted `flock` protocol and reject stale generations.
This seam exposes those outcomes. It assumes one stable sibling lock name and
inode; lock deletion/replacement, path aliases, noncooperating writers and
network/distributed filesystems remain outside the accepted contract. There is
no multi-file or stdout/session atomicity claim.

The focused offline tests use the existing detached demo tables only. Two real
local child processes each load the same generation, signal a pipe barrier, and
are released only after both signals arrive. Different valid submissions yield
one durable winner and one typed stale conflict; identical contenders stay
stale until a separately invoked fresh apply returns replay/no-write. The
winner is deliberately unspecified. Child waits have explicit timeouts and
cleanup terminates only test-owned child processes. Further gates cover exact
digests and generation, late memome replay, malformed and resealed files, derived
integer limits, prepublication fsync/replace failure, postpublication directory
fsync uncertainty, postpublication unlock failure in a test-owned child with
descriptor cleanup, output failure after durable return, explicit target/policy
binding, equal-payload/different-generation cases, candidate swap refusal,
interleaved replay and later commit, read-only reconciliation, disabled
execution, isolated imports and fresh hash-seed determinism.

Run new and accepted regression suites under the coordinator's bounded offline
test environment:

```sh
python -B -m pytest -p no:cacheprovider -q \
  tests/test_session_operations.py tests/test_experiment_sessions.py \
  tests/test_campaign_logistics.py tests/test_memome_experiment.py
```

These synthetic gates establish an operator composition contract, not scientific,
native-byte, production or milestone acceptance.
