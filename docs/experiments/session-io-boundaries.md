# Session I/O boundaries

This local experiment companion repairs three inherited operator limits: an
unlock error that concealed a completed durable commit, the original CLI's
stat-then-unbounded read on a growing file, and blocking session reads on FIFOs.
It changes no kernel, storage envelope, transport policy, default CLI output,
or automatic retry policy.

`read_regular_file_bytes(path, *, max_bytes, label)` is the public shared reader
used by session loads, expected-generation checks, and the original operator
CLI's policy and submission inputs. The maximum is an exact positive integer
within `MAX_TRANSPORT_BYTES`; invalid bounds fail before opening. It opens once
with `O_RDONLY | O_NONBLOCK` (and `O_CLOEXEC` where available), checks regular
file type through `fstat` on that descriptor, then requests at most `max_bytes
+ 1`. Excess bytes fail before UTF-8/JSON decoding. A stale path size never
controls the read. A regular path replaced with a FIFO before open is refused
without waiting for a writer; replacement after open leaves the opened file
identity intact. Directories retain `IsADirectoryError`; ordinary open/read
errors retain their type and cause. Other nonregular files raise `SessionError`.
Read symlinks retain their existing behavior. This is not a new global symlink,
filesystem containment, or concurrent in-place mutation protocol. Unsupported
nonblocking open is refused before reading. Concurrent growth after the read
may remain unseen; successful reading observes one bounded descriptor read,
not a promise of the latest path contents.

The durable gate is successful file fsync, atomic replacement, and successful
parent-directory fsync. Commit identity is materialized before publication.
After that gate, failure of directory close, writer unlock, or writer close
raises `CommittedCleanupError`, a `SessionError` distinct from
`PersistenceError` and `DurabilityUncertain`. Its `result` is the exact
`CommitResult` for the completed publication; `cleanup_error` and `__cause__`
are the original cleanup exception. Its message states completion, advises
readback to reconcile current identity, and forbids automatic retry. Another
writer can advance the head after cleanup, so the result describes this
publication rather than guaranteeing the current file identity. No rollback
is implied. Cleanup is attempted once; failures do not trigger another write.

An actual directory-open/fsync failure after replacement remains
`DurabilityUncertain`. A later directory-close or writer cleanup error cannot
mask that primary failure; secondary context is retained with exception notes.
Before publication, the existing primary validation/write failure likewise
wins over cleanup, with secondary notes. Temporary cleanup remains the existing
best-effort behavior. This does not resolve interruptions outside ordinary
exception handling or assert that a failed close released an OS descriptor.

The operation wrapper assigns `committed_durable` to the typed cleanup outcome
only when its completed path, kernel, policy, generation, file digest, session
digest, and turn match the attempted intended identity. The raised exception
still carries its cause and an operation receipt with cleanup diagnostics.
Contradictory metadata and unforeseen postpublication exceptions remain
`commit_outcome_unknown`. Reconciliation is read-only and never proves a
previously failed directory fsync completed. The original CLI emits
`committed: true`, `status: committed_durable`, and exact completed identities
on stdout, cleanup diagnostics on stderr, and exit 3. Normal successful and
default-off output bytes are unchanged.

The old operation test that injected a real postpublication unlock failure
previously required raw `OSError` and an unknown receipt. That exact failure
trigger is now tested as a typed proven-durable outcome; its descriptor closure,
read-only reconciliation, visible generation, unchanged committed bytes, and
no-temporary-file assertions remain. A separate actual postpublication
`RuntimeError` test retains the unknown-outcome contract. Existing read-bound
test hooks now observe builtin `open` on the actual integer descriptor instead of `Path.open`; every original
substantive assertion remains, and `TrackedHandle` keeps its existing API.
New boundary tests cover actual descriptor growth/substitution, six bounded
FIFO child cases, exact bounds, cleanup causes/identities, directory fsync
uncertainty with simultaneous cleanup errors, and explicit CLI diagnostics.
