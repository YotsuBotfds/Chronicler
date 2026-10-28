# Lossless parent-extra archive protocol — 2026-10-28

Preregistered from integration `bf7c98de5c314948c4e765eb9d590f939cd51822`.
This follow-up adds a standard-library, one-parent storage tool. It does not
change a simulation, validation decision, live gate, or existing receipt.

The archive command requires an explicit complete batch manifest SHA-256
and finalized seed. It selects only direct `state.json`,
`state.historiography.json`, `state.languages.json`, and `memories_*.json` files.
Any selected manifest input is refused. Every parent file, including currently
unhashed validation ledgers, bundles, events and checkpoints, is inventoried
before and after; every selected run's manifest input remains present with its
original hash. Other parents are not repeatedly hashed by this one-parent tool.
Source/native identities and the manifest hash anchor the new index.

Each invocation limits the selected raw files to 256 files / 64 MiB, and the
whole parent to 12,000 directory entries / 10,000 files / 512 MiB. Enumeration
is bounded before sorting or hashing. Hash and compressed-input readers stop
at the recorded size plus one byte for change detection; decompression checks
the declared raw size before writing. Per-block space checks reserve the next
write plus 1 MiB above a 3 GiB floor. Index/status/receipt JSON is encoded and
checked against the shared 32 MiB reader cap before exclusive creation; each
metadata write reserves its exact encoded size plus 1 MiB as well.
Concurrent external disk growth can still
cause an IO failure; failed evidence remains and no source file is removed.
A fresh external destination holds deterministic individual
gzip streams, raw/compressed hashes, metadata and an immutable hashable index.
The command must perform an actual restore into a second fresh external
destination and verify every restored byte before reporting success. Separate
restore and verify-only operations require the caller's explicit index hash.
Gzip headers use an empty filename and zero mtime at compression level 6;
identical input gives identical output with the same runtime/compressor.
Compressed-byte identity across different zlib implementations is not promised.
Canonical relative paths, regular unaliased files, exclusive outputs, bounded
single-member gzip decoding, and repeated source checks fail closed. Failed or
interrupted outputs remain evidence; an existing destination is never resumed.

There is no raw deletion operation or flag. No live cohort will be archived in
this implementation task. Actual cohort archiving must wait for its official
gate, forks and final identity checks to finish. A future raw-duplicate cleanup
requires its own reviewed contract; a successful archive does not authorize it.
This version preserves bytes and records metadata; it does not promise portable
restoration of ownership, ACLs, filesystem allocation or cross-platform modes.

The index records mode/mtime/ctime and file identities to detect source changes;
restoration checks bytes and does not attempt to set those identities or times.
Source/native identities are the hash-anchored original manifest identities,
not a claim that this storage tool loaded or reran that simulation runtime.
Directory fsync is used where exposed by the POSIX API; file fsync is required
on all platforms. Windows directory power-loss durability is not qualified.

Validation uses small synthetic completed batches, actual restored files,
determinism, manifest/input changes, protected paths, output aliases, corrupt
indexes/streams, truncated or concatenated gzip members, decompression bounds,
and interruption/failure evidence. Portable tests do not launch subprocesses,
import native code, access the network, or touch the active cohorts.

Usage (replace both hash placeholders with actual retained SHA-256 values;
destination parent directories must already exist):

```sh
python scripts/archive_parent_extras.py archive --batch finished/batch_42 --seed 42 --manifest-sha256 MANIFEST_SHA256 --output archives/parent42 --restore-output restores/parent42
python scripts/archive_parent_extras.py verify --archive archives/parent42 --index-sha256 INDEX_SHA256
python scripts/archive_parent_extras.py restore --archive archives/parent42 --index-sha256 INDEX_SHA256 --output restores/parent42-again
```

`archive` succeeds only after compression, actual exclusive restore, decoded
verification, and final parent/manifest rechecks. The printed completion receipt
contains the immutable index hash and actual-restore receipt hash. Verify-only
checks the indexed compressed/raw byte proofs without writing an output; it
does not claim an actual filesystem restore. Restore works after the original
batch has moved, but refuses destinations inside its recorded original path.
None of these commands reclaim raw source storage.

The earlier copy-only two-parent probe restored 14 files exactly and preserved
all originals (external receipt SHA-256
`c0e7122e1ebfc647b0f5dabd2aeec6ccc8ae008c5ece134b130646e59aec4b89`).
That probe is separate from this tool's synthetic tests and does not establish
a cohort-wide compression ratio or permission to delete originals.

Local focused validation on Linux / Python 3.13.5 without the native extension:
**66 passed in 1.63 seconds**. This includes actual synthetic archive/restore,
unchanged protected files, deterministic bytes, alias refusal, source/manifest
changes, ctime, bounded enumeration/read/write checks, malformed indexes and
truncated/multiple-member/bomb streams, and pre-creation metadata size/reserve
checks. Alias and filesystem change-time checks
are capability-dependent and belong to the full filesystem test lane; the
remaining small-file cases can run under the offline guard. No Windows/macOS
execution, full new-source qualification, real-cohort archive or reclaimed-space
measurement is claimed.

After integration, the 58 portable archive cases joined the existing bounded
qualification-tool selection: **112 tests passed under the offline guard in
3.41 seconds**. The eight alias/change-time capability cases remain in the full
filesystem suite. The merged guard recorded no native module, blocked I/O or
runtime execution. This focused result does not extend b257's frozen full-suite
or 28-chunk qualification to later source commits.
