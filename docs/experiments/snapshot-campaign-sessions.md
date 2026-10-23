# Captured snapshots to portable campaign sessions

This opt-in bridge joins the existing snapshot admission adapter and the
existing M60a session manager. It uses their public APIs unchanged. It reads
only an explicitly supplied captured Arrow IPC file; it never acquires a native
snapshot, advances a production simulation, draws randomness or changes a schema.

The parent-reconciled experimental-import contract permits exactly one package
consumer of `campaign_snapshot_adapter`: this explicit
`src/chronicler/snapshot_campaign_sessions.py` bridge. The existing source-text
scan now requires that exact relative-path set instead of zero consumers; every
other original assertion is retained, and the old test bytes remain in accepted
history and the preserved snapshot pin `45dc49dbd997bac1331019d2e5bc0893025aa449`.
The bridge imports exactly the public `CONTRACT`, `AdmissionPlan`,
`CampaignSnapshotError`, `SideInputs`, and `admit_snapshot_plan` symbols. No second
adapter importer, package consumer of this bridge, initializer/main/registry
activation, schema or dependency change is authorized. AST/source boundary and
fresh-process poison controls enforce the one experimental consumer and no input,
kernel, commit, fixture or RNG work on import/disabled invocation. This is the
precise AM-01 contract revision, rather than hiding an import or filtering a gate.

Running `scripts/snapshot_campaign_session.py` without `--enable` prints a fixed
disabled receipt, including when file paths are supplied. No file opens and no
kernel calls occur. Enabled creation requires every input and an absent session
destination:

Creation retains its existing argparse behavior: optional syntax/type errors can
exit2 before disabled dispatch. The separate verifier retains its exact-enable/
help early dispatch and enabled syntax JSON exit3; this reader change does not
unify those CLI contracts.

```sh
python scripts/snapshot_campaign_session.py --enable \
  --snapshot captured.arrow --side-inputs side.json --transport transport.json \
  --path campaign.json --max-snapshot-bytes 8388608
python scripts/experiment_session.py inspect --path campaign.json --transport transport.json
python scripts/experiment_session.py verify --path campaign.json --transport transport.json
python scripts/experiment_session.py apply --path campaign.json --transport transport.json --batch tick.json
```

`captured.arrow` must contain exactly one IPC file record batch with the reviewed
native snapshot schema. A stream, multiple batches, changed schema, unknown
selected agent, mismatched epoch, non-soldier or wrong civilization is rejected.
The phase10-entry epoch is supplied explicitly by `source_turn` in `side.json`;
the IPC schema does not carry independent freshness proof. The library checks
an existing `AgentRows` stamp against that explicit turn.

Use the complete side-input shape documented in
[campaign-snapshot-adapter.md](campaign-snapshot-adapter.md): explicit contract,
source turn, civilization, selected stable IDs, campaign ID, topology version,
staging, target, complete policy, reciprocal region bindings, kits, morale and
stocks. No value is inferred. `transport.json` holds exactly the version and
four bounds described in [session-workflow.md](session-workflow.md), for example:

```json
{"version":"chronicler-session-transport-v1","max_bytes":8388608,"max_records":200000,"max_history":10000,"max_int_bits":4096}
```

All three file inputs delegate through `read_bounded_bytes` to the unchanged public
`experiment_sessions.read_regular_file_bytes`. It opens nonblocking, validates a
regular file on that same descriptor, then reads at most limit+1 once without
trusting pathname metadata. This refuses an initial FIFO or one exchanged before
open without waiting for a writer. Regular read symlinks remain supported; this
does not provide pathname containment or alter destination/lock protections.
Transport JSON has a 4096-byte bootstrap cap; side JSON uses the
explicit transport `max_bytes`; Arrow uses the mandatory `max_snapshot_bytes`
argument (exact positive integer, excluding bool, at most 67108864). Excess is
rejected before parsing. JSON uses the existing public strict transport/submission
parsers and `parse_side_inputs`, rejecting duplicate keys, nonfinite values,
floats, booleans in integer fields and missing/unknown keys. Arrow buffers are
copied out of the closed source; no borrowed file handle escapes.
Direct `read_bounded_bytes(path, *, limit, label)` calls retain the name/signature,
prior `Path(path)` coercion and exact-positive-limit validation. Its admitted domain
now follows the public reader: limit at most64MiB, label an exact nonblank string.
Previously arbitrary positive limits and unvalidated labels were accepted; those
direct calls are explicitly tightened and are not claimed compatible. Above-cap,
bool/nonpositive limits or malformed labels refuse before open, without clamping
or expanding the shared cap. All supported creator/verifier calls fit this domain.
Descriptor binding does not guarantee arbitrary-filesystem latency or coherent
concurrent in-place writes. Inputs are separate observations, not a simultaneous
multi-file capture or authenticated source freshness transaction.
The Arrow cap bounds source file bytes before parsing. It does not bound
decompression expansion, copied/serialized Arrow buffer allocations or allocator
overhead; those require a separate explicit resource contract (AM-06).

For callers already holding a captured view:

```python
from chronicler.snapshot_campaign_sessions import prepare_snapshot_session, read_snapshot
from chronicler.campaign_snapshot_adapter import parse_side_inputs
from chronicler.experiment_sessions import commit_session, submission_from_bytes
from chronicler.turn_artifacts import AgentRows, Stamp

# transport is an exact, explicitly validated public TransportPolicy record.
# side_bytes are caller-provided bounded UTF-8 bytes.
side = parse_side_inputs(submission_from_bytes(side_bytes, transport=transport))
batch = read_snapshot(snapshot_path, max_snapshot_bytes=8388608)
prepared = prepare_snapshot_session(
    agent_rows=AgentRows(Stamp(side.source_turn, "phase10_entry"), batch),
    side_inputs=side, transport=transport)
committed = commit_session(destination, prepared.session, transport=transport,
                           expected_generation=None, expected_digest=None)
```

Preparation returns an immutable `PreparedSnapshotSession` containing `plan`,
managed `session` and generation-one `envelope`. It calls `admit_snapshot_plan`
with every side field, then deliberately re-admits the plan's copied inputs via
`create_campaign_session`. This is admission, not advancement. Complete public
`canonical_bytes` equality of the two kernel Sessions covers state, cursor and
receipts. Encoding and public decoding validate the entire copied session under
the transport domain before any persistence or writer-lock creation. The library
accepts exact public `SideInputs` and `TransportPolicy` records; it offers no
forged-plan decode entry point.

Success prints the full existing `plan_document`, committed file digest and
session digest. The plan is a separate provenance receipt: **it is not persisted
in the unchanged session envelope**. Save stdout explicitly if that receipt is
needed; there is no sidecar and no two-file atomic guarantee. Session bytes alone
preserve campaign admission/configuration and future history, not source-column
hashes or named region bindings. Existing session tooling resumes and replays
the resulting `m60a` file unchanged.
Changing a valid unselected demanded row or consistently renaming region labels
can change the plan/source identity while leaving managed admission and envelope
identical. Session genesis therefore cannot recover original capture provenance.
The optional admission-equivalence/original-receipt verification workflow remains
deferred (AM-02); this contract revision adds no verifier or envelope field.

The only persistence operation is public `commit_session`, expecting an absent
destination. An existing file is never overwritten. Invalid inputs or exhausted
preparation bounds do not touch the destination or create the persistence lock.
The existing local POSIX locking, file fsync, atomic replace and directory fsync
contract applies. Durable success is reported only after it completes. Errors
print JSON on stderr and exit 3, preserving `DurabilityUncertain` and the existing
session error taxonomy; disabled invocation exits 0. A directory-fsync failure
may leave new bytes visible: read back and reconcile as described in the session
workflow. No retry or rollback is invented.

Focused offline controls reuse the existing 23-field Arrow schema, existing unit
roster and three-region adjacency. They cover public admission equality, exact
types and bounds, stream reads with misleading metadata, schema/epoch/selection
failures, default-off hooks, no-overwrite, portable load/resume/replay, truthful
provenance, unchanged envelope fields, CLI compatibility and fresh-process hash
seed determinism. No native, production, scientific or milestone acceptance is
claimed.
