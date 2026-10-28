# Lossless parent-extra archive protocol — 2026-10-28

Preregistered from integration `bf7c98de5c314948c4e765eb9d590f939cd51822`.
This follow-up adds a standard-library, one-parent storage tool. It does not
change a simulation, validation decision, live gate, or existing receipt.

The archive command will require an explicit complete batch manifest SHA-256
and finalized seed. It selects only direct `state.json`,
`state.historiography.json`, `state.languages.json`, and `memories_*.json` files.
Any selected manifest input is refused. Every parent file, including currently
unhashed validation ledgers, bundles, events and checkpoints, is inventoried
before and after; every manifest input remains present with its original hash.
Source/native identities and the manifest hash anchor the new index.

Each invocation has fixed file-count and byte bounds and preserves a 3 GiB
free-space reserve. A fresh external destination holds deterministic individual
gzip streams, raw/compressed hashes, metadata and an immutable hashable index.
The command must perform an actual restore into a second fresh external
destination and verify every restored byte before reporting success. Separate
restore and verify-only operations require the caller's explicit index hash.
Canonical relative paths, regular unaliased files, exclusive outputs, bounded
single-member gzip decoding, and repeated source checks fail closed. Failed or
interrupted outputs remain evidence; an existing destination is never resumed.

There is no raw deletion operation or flag. No live cohort will be archived in
this implementation task. Actual cohort archiving must wait for its official
gate, forks and final identity checks to finish. A future raw-duplicate cleanup
requires its own reviewed contract; a successful archive does not authorize it.
This version preserves bytes and records metadata; it does not promise portable
restoration of ownership, ACLs, filesystem allocation or cross-platform modes.

Validation will use small synthetic completed batches, actual restored files,
determinism, manifest/input changes, protected paths, output aliases, corrupt
indexes/streams, truncated or concatenated gzip members, decompression bounds,
and interruption/failure evidence. Portable tests do not launch subprocesses,
import native code, access the network, or touch the active cohorts.
