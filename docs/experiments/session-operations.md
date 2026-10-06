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
| `committed_durable` | The public directory-fsync gate completed for the exact intended identity, including a typed completed-cleanup outcome. Another writer may advance the target before this receipt is delivered. |
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
precommit errors retain rejection/stale status. An unexpected commit exception without a confirmed completed identity is
conservatively `commit_outcome_unknown`; no failed return is assumed to prove
unchanged bytes. Accepted `CommittedCleanupError` instead carries an exact
completed publication after successful directory fsync. Its result must match
the operation's entire intended envelope and identity to report
`committed_durable`; the exception retains its cleanup cause. Cleanup never
triggers another submission.
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
transport byte budget. Both reads delegate to the accepted public
`read_regular_file_bytes` reader: one nonblocking open, descriptor regular-file
check, and `limit + 1` read before parsing, without trusting pathname size.
FIFO and other nonregular inputs are refused before operation work; directories
retain `IsADirectoryError`, and ordinary open/read errors keep their types.
Read symlinks retain the accepted library behavior. Session loading and
persistence use the same accepted library unchanged. Bounds cover serialized
reads, not arbitrary-filesystem latency or concurrent in-place mutation.
Input oversize diagnostics now read `the <label> exceeds the <limit>-byte
transport limit` instead of `<label> exceeds the <limit>-byte limit`; this is an
input-only wording change, with the same `TransportDomainError`, rejected
receipt and exit 3. It does not change operation or cleanup diagnostics.
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

## Preview one choice, submit once, and inspect the saved receipt

Use a supported interpreter and a new empty temporary directory. From the
checkout root, set `CHECKOUT` to its absolute path and `PYTHON` to the interpreter:

```sh
export CHECKOUT="$PWD"
export PYTHON="${PYTHON:-python3}"
export PYTHONPATH="$CHECKOUT/src"
example_dir=$(mktemp -d)
cd "$example_dir"
```

The following preparation writes only scratch input documents. It uses the
existing five-participant memome demo, with two explicit alternatives sharing
proposal `choice`, recipient `basic-1`, slot 1 and supplied draw 199. No ranking
or automatic choice policy is involved.

<!-- r007-step: prepare -->
```sh
"$PYTHON" - <<'PY'
from dataclasses import asdict
import json
from pathlib import Path
from chronicler import experiment_sessions as es
from chronicler.memome_candidate_preview import CONTRACT

encode = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
Path('transport.json').write_bytes(encode(asdict(es.documented_transport_policy())))
proposal = {'proposal_id': 'choice', 'recipient': 'basic-1', 'slot': 1, 'candidate': 3, 'draw': 199}
choices = [
    {'label': 'candidate 3', 'batch': {'turn': 1, 'proposals': [proposal]}},
    {'label': 'candidate 0', 'batch': {'turn': 1, 'proposals': [dict(proposal, candidate=0)]}},
]
Path('choices.json').write_bytes(encode({'contract': CONTRACT, 'alternatives': choices}))
PY
```

The explicit create subcommand now mutates the scratch experiment, establishing
generation 1/turn 0. Keep the exact opening bytes for the later comparison.

<!-- r007-step: create -->
```sh
"$PYTHON" "$CHECKOUT/scripts/experiment_session.py" create --kernel m68a --path memome.json --transport transport.json --demo
```

<!-- r007-step: copy-opening -->
```sh
cp memome.json opening.json
```

<!-- r007-step: preview -->
```sh
"$PYTHON" "$CHECKOUT/scripts/memome_candidate_preview.py" --enable --path memome.json --transport transport.json --alternatives choices.json --max-alternatives 2 --format json
```

At this opening, candidate 3 has candidate weight 1, electorate weight 3,
threshold 200 and draw 199: it is accepted and changes slot 1 from 1 to 3.
Candidate 0 has reason `absent_candidate`, weight 0 and threshold 0; slot 1
remains 1. Preview leaves the saved file untouched. Its observed identity is
informational and is not an OCC or submission token.

This example assumes no intervening writer between preview and apply. B's CAS
protects the version B loads when apply starts; it does not bind the earlier
preview. A review-bound submission under concurrent writers requires an
explicit product/API decision. Do not add a shell precheck or an automatic
re-preview/apply loop. Select the input batch explicitly by label from the
input document; a preview report is never a submission.

<!-- r007-step: select -->
```sh
"$PYTHON" - <<'PY'
import json
from pathlib import Path
choices = json.loads(Path('choices.json').read_text())
selected = next(row['batch'] for row in choices['alternatives'] if row['label'] == 'candidate 3')
Path('submission.json').write_bytes(json.dumps(selected, sort_keys=True, separators=(',', ':')).encode())
PY
```

<!-- r007-step: apply -->
```sh
"$PYTHON" "$CHECKOUT/scripts/session_operation.py" --enable apply --path memome.json --transport transport.json --submission submission.json
```

Expect `committed_durable`, base generation 1/turn 0 and intended generation
2/turn 1. The intended full-file digest identifies the actual saved bytes,
including their envelope and newline; it is not a hypothetical preview digest.
The opening copy stays exact. Reopen the saved history for the full receipt:

<!-- r007-step: inspect -->
```sh
"$PYTHON" "$CHECKOUT/scripts/experiment_receipts.py" --enable --path memome.json --transport transport.json --turn 1
```

The canonical admitted batch and every retained kernel receipt field must match
candidate 3's hypothetical row: proposal ID, recipient, slot, previous value,
candidate, draw, candidate/electorate weights, threshold and reason. The
inspector's `participants_after` confirms basic-1's slot 1 is 3. This comparison
links the displayed choice to the one saved result; it makes no scientific
claim about the illustrative threshold.

Re-submit the identical explicit batch once to exercise the historical replay
contract. It returns `replay_no_write`, with intended null, and preserves
generation 2/turn 1, every saved byte, mtime, and the original receipt. It does
not append a second batch or update the trait again.

<!-- r007-step: replay -->
```sh
"$PYTHON" "$CHECKOUT/scripts/session_operation.py" --enable apply --path memome.json --transport transport.json --submission submission.json
```

<!-- r007-step: inspect-replay -->
```sh
"$PYTHON" "$CHECKOUT/scripts/experiment_receipts.py" --enable --path memome.json --transport transport.json --turn 1
```

<!-- r007-step: compare -->
```sh
"$PYTHON" "$CHECKOUT/scripts/compare_experiment_sessions.py" --enable --left opening.json --right memome.json --transport transport.json --format json
```

Expect `left_history_prefix`, shared committed count 0, last shared committed
turn null, and latest turns 0/1. Genesis is not a receipt. The result follows
complete recorded history, rather than merely comparing generations. Inspection
and comparison leave both saved files untouched.

Separately, demonstrate an input-file refusal; do not continue a write sequence
after it. This preparation writes only an oversized transport document, and
the apply command must exit 3 with a pre-operation `rejected` receipt and no
observed base or intended identity. The saved session and existing lock stay
untouched.

<!-- r007-step: invalid-prepare -->
```sh
"$PYTHON" - <<'PY'
from pathlib import Path
Path('oversized-policy.json').write_bytes(b'x' * 4097)
PY
```

<!-- r007-step: invalid-refusal -->
```sh
"$PYTHON" "$CHECKOUT/scripts/session_operation.py" --enable apply --path memome.json --transport oversized-policy.json --submission submission.json
```

Malformed CLI syntax, pre-operation input refusal, typed operation failure, and
output-delivery failure occur at different stages. Use the existing outcome
and reconciliation tables above. An output failure after commit never
justifies rerunning apply. This walkthrough assumes regular scratch inputs;
R's B delegation does not repair other drivers' historical input-open limits,
including the receipt-inspector and campaign-preview transport readers.
