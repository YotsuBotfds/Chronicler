# Compare supplied snapshot evidence with a saved campaign

The default-off `scripts/verify_snapshot_session.py` checks admission equivalence
and an optional retained plan expectation separately. It uses the public captured
Arrow adapter and complete saved-session decoder/replay. It submits no new tick,
acquires no lock and writes no session or sidecar.

Keep the creation driver's returned `plan.plan_digest` externally if you want to
check the supplied plan later. For example, an operator who retained the creation
receipt can copy that exact 64-character lowercase digest and run:

```sh
python scripts/verify_snapshot_session.py --enable \
  --snapshot captured.arrow --side-inputs side.json --transport transport.json \
  --path campaign.json --max-snapshot-bytes 1048576 \
  --expected-plan-digest <retained-plan.plan_digest>
```

The digest is the public plan's canonical-body digest, not a hash of the entire
receipt or of `plan_bytes` (which includes the digest field). The checker neither
saves nor imports a receipt. Omit `--expected-plan-digest` for an admission-only
check. `--format text` provides a text report; JSON is the default. Without
`--enable`, the fixed off JSON report is returned before optional value validation
or input work. `--help` needs no inputs.

`admission_equivalent` compares complete typed policy, numeric topology and
admission records, including every coefficient, soldier and stock. An advanced
campaign remains valid input: the saved history is replayed and verified, then
genesis is compared with the supplied admission. Current positions or rations do
not replace this comparison. The report gives each comparison dimension and the
saved generation/latest turn from the bytes actually read, never the preparation
envelope's generation one.

`plan_expectation` is `not_supplied`, `match` or `mismatch`. It only compares the
recomputed supplied plan with the explicit caller expectation. Even a matching
expectation can accompany a different saved admission; a digest says nothing
about which session it belongs to. `original_provenance` is always `unverified`.
When both checks match, the result is “admission equivalent; supplied plan matches
caller expectation; original provenance unverified.”

The accepted five-row/three-region controls demonstrate why these are different:

| Supplied change | Admission | Source/binding evidence | Original retained plan |
| --- | --- | --- | --- |
| Change unselected farmer id9's demanded region from 2 to 1 | Equivalent | Demanded-table source digest changes | Mismatch |
| Consistently rename binding `r0` and all its neighbor references | Equivalent numeric graph | Region binding digest changes | Mismatch |

Without the retained expectation both cases still report admission equivalence
and `not_supplied`. Region labels and unselected row contents cannot be recovered
from session genesis. Losing the external evidence is not recoverable through this
check. A user-supplied digest provides no authentication or trust chain and does
not prove original capture or historical creation.

Exit0 means a completed admission-equivalent check with no expectation mismatch
(or disabled mode). Exit1 means a completed comparison mismatch. Exit3 means
missing/invalid input or a bounded-read, parse or replay failure, with error JSON
on stderr and no partial positive stdout. Both renderers construct complete output
before emission. Exit0 certifies no origin, freshness, durability, scientific or
native validity.

Inputs must be explicit regular files. Transport is read under 4096 bytes, side
inputs and saved session under the supplied transport's `max_bytes`, and Arrow
under the explicit positive limit (at most 64MiB). Strict public readers preserve
duplicate/unknown-key, scalar-type, schema, stamp and transport checks. Snapshot
turn/stage are caller declarations; an Arrow file does not independently establish
its capture epoch. Preparation may call admission and verification may replay
saved historical turns; neither implies zero kernel calls.

The session is read once. `observed_session.file_digest` hashes those exact bytes,
separately from saved genesis/history/latest/session payload digests. A concurrent
replacement after that read does not change which version the report describes.
The path can subsequently name a different version. Four separate reads establish
no simultaneous multi-file snapshot, freshness or durable provenance transaction.
There is no reread-until-stable loop or commit.

All four input reads use the shared `read_bounded_bytes` delegation to the unchanged
public `experiment_sessions.read_regular_file_bytes`: nonblocking open, regular-file
validation on the opened descriptor, then at most limit+1 bytes once. Initial FIFOs
and regular-to-FIFO pre-open exchanges refuse without waiting for a writer. Regular
read symlinks remain accepted; no pathname containment is promised. Direct helper
calls now require an exact positive limit at most64MiB and an exact nonblank string
label. Old arbitrary larger limits and unvalidated labels are explicitly tightened,
with no compatibility claim for those direct calls. Prior `Path(path)` coercion is
preserved. Supported transport/side/snapshot/session callers fit the admitted domain.

The saved-session refusal occurs after supplied admission preparation; it does not
imply zero earlier admission calls. Saved-session decoding/replay has not occurred
at that refusal. The verifier still submits no new turn and writes nothing. Q's
guarded replay elsewhere is a point-in-time observation, not a durability proof.

Source byte caps do not bound Arrow decompression expansion, allocation, execution
time or output size. Nonblocking open does not guarantee arbitrary-filesystem
latency or coherent concurrent in-place writes. There is no reread/retry, lock or
simultaneous multi-file capture. The observed full-file digest remains bound to the
single saved-session byte string, even when the pathname is replaced later.
Authenticated provenance, atomic receipt persistence, native/scientific validation,
production activation and provider work remain separate unprovided contracts.
Actual-tree integration rechecks replay, nonmutation and observed-version controls
against the reviewed composed source.
