# Coherent constructor ownership successor — source only

The formal independent review of `0a0cfff2` remains **BLOCKED before execution**.
Its terminal reservation and `_directory_fd` repairs were source-clear; this
child addresses the remaining constructor ownership/error family as one region.
Only `ArtifactBudget.__init__`, appended test source and these two documentation
files change. The 11 writer files, all other module bodies and all terminal
byte/count/path protocols remain exact `0a0`. The complete prior 68 static case
bodies are retained as an exact source prefix, unregistered and unrun.

Initial parent open, every ancestor handoff, root acquisition/validation/map
insertion and final-parent close now share one handled ownership region. Parent,
untransferred child and root descriptors are tracked in explicit locals before
fallible I/O. A local is invalidated before each close attempt. The new child
becomes the parent only after the previous parent close succeeds; the root is
published to the facade only after final parent cleanup succeeds. Thus a final
cleanup-close failure cannot bypass the constructor's exception path with an
unreturned root descriptor and a healthy supplied ledger.

Every constructor I/O exit latches `io`, including initial-open failure.
Remaining known local descriptors receive independent best-effort close
attempts; a secondary cleanup failure cannot mask the original exception or
prevent the other closes. Bare re-raise preserves the first exception object
and its original traceback tail. Normal propagation adds caller frames, so no
claim of identical outer traceback-head identity is made. A close that raises
has unknown disposition and is never retried or reported as proven closed.
Any such outcome remains negative, even when a controlled fake removes the
handle before raising. No rollback, root adoption, directory deletion, new
writer operation or runtime probe is added.

Append-only primitive FakeOS contracts cover a clean nested-path constructor,
initial and both ancestor opens, mkdir/root-open failure, first/later ancestor
handoff close failures, root fstat and map insertion both before/after mutation,
secondary root/parent/both cleanup closes, otherwise-successful final-parent
close failure, and UID/mode rejection. Close fakes exercise failure before and
after fake handle removal, preserve an unrelated baseline handle, check original
exception/traceback-tail identity and one constructor frame, require one attempt
per uncertain descriptor, and account for remaining unknown handles explicitly.
The tests create no actual filesystem, native object, World or checkpoint.
All new and previous cases remain source-written only; none have been imported,
collected or executed.

Total count ceilings remain 65,536 attempts and 256 each for ledger paths,
live files and owned directories. Both root terminal paths retain their two
protected slots inside those totals; ordinary positive-reserve ceilings stay
65,534 attempts and 254 file/path slots. Ordinary/care halves stay 16 MiB each,
32 MiB total, with the same 128 KiB ordinary terminal reserve and 64 KiB care
metadata reserve. Reserve-zero ordinary-only fake semantics remain unchanged.
No owner/log/IPC/control integration, complete pilot aggregate enforcement,
actual Arrow equality, memory/physical-resource fit, installed API/schema,
bootstrap, enabled care/pilot/own-CP, efficacy or performance claim follows.

Independent full constructor source review and a separate root grant precede
any pure execution. The proposed limits remain 30 CPU seconds, 110 wall seconds,
512 MiB AS, one actual CPU, 256 MiB output and 2 MiB logs. No runner, registration,
execution, current-source CI/build/wheel, resource probe or study is supplied.
All earlier source-only and blocked records follow unchanged.

---

# Terminal headroom and directory ownership repair — source only

The dbbcdc54 source remains **BLOCKED before execution** by its independent
full-source review. This prospective child changes only artifact_budget.py,
its test module and these two documentation files. The 11 ordinary writer
integration files remain exact dbb bytes. No old source, freeze or test result
is rewritten; the entire prior test file and documentation bodies are retained.
All original 42 static logical cases remain unrun and unregistered.

A positive ordinary terminal reserve now protects both byte allowances **and**
two slots within the unchanged 65,536-attempt / 256-ledger-path / 256-live-file
ceilings. The separate 256-owned-directory ceiling also remains unchanged.
Ordinary traffic may use 65,534 attempts and 254 slots; successful terminal use
never returns those slots to ordinary traffic. Both terminal roles are direct,
once-only writes to the closed root-relative `terminal.json` and `freeze.json`.
Ordinary writes, descendants, directory creation and unlinks cannot claim those
reserved root names. The root is already owned, so neither protected record
needs a new ancestor-directory slot even when the directory ceiling is full.
Retained failed atomic temps count toward ordinary live-file occupancy; a
healthy atomic replacement is refused if its temporary duplicate would consume
one of the two protected slots.

Production still prepays exactly 131,072 bytes: at most 8,192 terminal bytes and
122,880 freeze bytes, within the original 16 MiB ordinary half. The 16 MiB care
half, its 65,536-byte metadata reserve, 32 MiB total and every study/resource cap
remain unchanged. A reduced **zero** terminal reserve is explicitly an ordinary-
only fake configuration: it retains the original full ordinary count ceilings
and accepts no terminal role. This preserves the old zero-reserve boundary
contract exactly; it is not the held pilot's production configuration. Other
reduced fake reserves keep both count slots, including a possible zero-length
freeze allowance. No cap borrowing, refunds or posthoc omission is introduced.

Directory traversal now tracks an opened child until ownership transfers to it.
An fstat or identity-map insertion failure therefore leaves both the child and
current parent available for independent close attempts. Each local is cleared
before its close attempt. A parent close that raises is never retried, because
its disposition is unknown and its descriptor might have been reused. Cleanup
errors latch `io`, do not mask the identical original exception, and never earn
a successful-cleanup claim. The repair adds no writer/path features or filesystem probes; only the required
error-cleanup close operations change.

Append-only primitive FakeOS contracts reach ordinary zero-byte attempt/path
limits, ordinary live-file and failed-atomic-temp boundaries, and a full
directory ceiling before retaining **both original** reserved role bodies.
Separate existing/new/owned-prefix directory cases inject keyed fstat and
identity-map insertion failures, compare live handles with their entry baseline,
and check original exception identity. Close failures before versus after fake
handle removal retain explicit unknown status; the other local descriptor is
still closed and an uncertain descriptor is attempted once. Neither these new
cases nor the preserved old cases have been imported, collected or executed.

The proposed pure lane remains 30 CPU seconds, 110 wall seconds, 512 MiB AS,
one actual CPU, 256 MiB output and 2 MiB logs. Independent narrow source review
and a separate root grant precede any execution. Registration, owner/log/IPC/
control integration, actual Arrow equality and memory fit, current candidate
CI/wheel/schema/bootstrap, resource admission, pilot and own-CP bindings remain
NULL. There is no complete-pilot aggregate-enforcement or tangible care claim.
The earlier source-only standing follows unchanged.

---

# Optional ordinary-artifact admission — source only, 2026-10-29

This child of `829d467dfc6017b5c44cb526fa847534b596e24d` adds an unused, explicit
ordinary-output budget API and its writer propagation. No tests, test collection,
project/native imports, compilation, build, World, checkpoint, profiler, network,
push, CI, resource probe or enabled study ran in this source step. The new
`tests/test_artifact_budget.py` is intentionally **unregistered**; both native
ownership and guarded selection need a separate source decision before CI.
Parent qualification describes the parent only. No passing result is claimed
for this child.

The held care pilot stays six fresh Worlds, 192 ticks, eight regions, four
initial civilizations, seeds 2000/2001, four recorded runs and two same-arm
seed 2000 recording-off controls, 32 turns each and zero exact checkpoints.
No source here activates it or changes care controls, defaults, physics, RNG,
serializer formats, ordinary save schedules, comparison exclusions or caps.
Main and other active refs are untouched.

## API and exact debit

`artifact_budget.py` provides a pure `MonotonicArtifactLedger`, frozen one-use
`WriteAdmission` tokens and a caller-owned POSIX `ArtifactBudget` facade. No
other production module imports it automatically. The optional keyword-only
`artifact_budget=None` follows the selected main→memory/world/history/language/
atomic/bundle/bridge/validation-sidecar/production-and-reserve-ledger path.
The original None branch keeps its literal calls and serializer arguments.
No default attributes, persistent World/config fields or checkpoint data are
added. An explicitly budgeted bridge/sidecar holds only a transient reference;
its checkpoint serialization refuses. Budgeted main refuses supplied/resumed
Worlds, exact checkpoint schedules and unsupported modes before generation;
its saved exact-checkpoint callback also refuses. The existing read-only
turn-boundary collector remains possible.

The constants stay ordinary 16,777,216 bytes, care 16,777,216, total 33,554,432,
ordinary terminal reserve 131,072 and care metadata reserve 65,536. This stage
implements the ordinary ledger only; care and shared owner integration are
not implemented. The ordinary ledger prepays its terminal reserve and debits
the actual full encoded body before a nonterminal write. A reduced synthetic
ledger is allowed for fake contracts; its capacity/reserve cannot exceed the
production maxima. The two prepaid ordinary metadata roles are bounded to
8,192 terminal bytes and 122,880 freeze bytes, once each, including after the
first fault. These are byte limits only; the future owner still must qualify
their schemas/path inventory and failure publication.

Every attempt consumes its full debit permanently, including normal state/
memory rewrites, atomic temporary duplicates, short writes and failed flush,
fsync,close or rename. Rename, unlink, truncation or descriptor closure never
refunds capacity. Token object identity, issuer and one-use state are checked;
a copied/forged/replayed token refuses. The first closed fault stays sticky.
Bridge’s existing snapshot exception handlers explicitly latch active output
faults that occur before a facade write is reached, so logging a swallowed
serializer/read exception cannot make that ledger healthy again.

This is conservative exact-attempt admission, not an exact live-size allocator.
It may refuse while a directory’s current st_size sum is below 16 MiB. Ordinary
replacement of an intermediate version stays distinct from deleting finalized
study evidence after outcomes. The optional atomic branch preserves owned
failed temps; the original None cleanup path remains exact. Direct-write
failure may leave the actual truncated/partial current file, which is retained
as incomplete evidence; the old version is not falsely claimed preserved.

## Owned paths, byte encoding and Arrow

The facade creates a fresh absolute root exclusively, with mode0700. All writer
paths must be absolute descendants. Directory-FD traversal uses O_NOFOLLOW;
existing files must match this instance’s owned single-link regular inode.
Deterministic exclusive temp names use the finite attempt ordinal and no new
secret/RNG call. There are finite 512-byte relative paths, 16 components, 256 owned
paths/directories and 65,536 attempts. No public descriptor, stream, append,
seek,truncate or hole API is supplied. Internal direct replacement opens and
checks the owned inode before admitted truncation. Root/caller-private Python
state is not an adversarial sandbox; foreign mutation invalidates evidence.
All writers must still be selected and reviewed by the future owner.

Text uses the original serializer. The budgeted facade supports only an actual
POSIX LF/UTF-8 encoding shape: explicit UTF-8 or the actual default UTF-8 text
encoding. Unknown encoding/newline runtime shapes refuse before budgeted file
I/O. Character counts are never admission bytes. Oversize inputs can refuse
early, but only actual encoded lengths can be admitted. Production default
encoding behavior remains unchanged on the None path.

Budgeted Arrow serializes the same schema,batch order,IPC options,compression
selection and footer into `pa.BufferOutputStream`, then admits its actual bytes.
The existing OSFile branch is retained for None. Actual empty/nonempty/null/
zstd/non-zstd buffer-vs-OSFile byte identity has **not** been run. Buffering and
native/model serialization memory fit under the unchanged 1 GiB worker AS is
also **unqualified**. This source does not use table size estimates or introduce
compression, truncation, digest substitutes or omitted bodies to buy fit.

## What remains absent

No owner IPC, cross-process/concurrent admission authority, controller JSON/
progress/log sink, worker/controller stdout/stderr boundary, resource admission,
deployment, schema/API bootstrap, capture adapter, pilot or own-CP integration
is implemented here. There is therefore **no complete pilot aggregate-enforcement
claim and no proof ordinary outputs fit**. The ordinary ledger is single caller;
a future owner must serialize all reservations or enforce a reviewed fixed
partition. It must retain all original ordinary outputs, comparison/model/native/
RNG/schema bodies, metadata, logs and seals inside the existing ordinary half.
The sole registered comparison normalization remains the validated generated_at
string; no file/glob/per-turn exclusion is added.

Logical encoded-file bytes differ from allocated blocks, directories/inodes,
journals,xattrs,RAM and pipe buffers. This API supplies no physical disk quota,
free-space reservation, protected mount or global resource guarantee. Standard
block quotas and RLIMIT_FSIZE alone do not prove the held logical aggregate.
The actual 3 GiB floor+8MiB reserve, 1 CPU/thread caps, 1 GiB AS, 600-second worker and
proposed 3750-second whole-owner deadline remain held and unchanged.

## Source contracts and later qualification

The unregistered test module contains only ledger/facade fake contracts and
an artifact_io None-delegation contract. Its FakeOS replaces the budget module’s
os reference, not interpreter-wide filesystem functions. It creates no real
output root and imports no World/model/native/PyArrow code. Contracts cover
shared remaining capacity, terminal reserve, UTF-8 length, token replay/issuer,
path escapes/aliases, owned-inode checks, same-path/atomic no-refund, short/write/
flush/fsync/close/rename failures, first-error preservation, partial-temp
retention, denied-write nonmutation, closed/checkpoint/raw-FD/seek rejection,
sticky upstream faults and unchanged None helper calls. All are source-written
and **UNRUN**.

Independent full source review must precede a separate root grant for the
proposed pure fake lane: 110 wall seconds, 30 CPU seconds, 512 MiB AS,one actual CPU,
256 MiB output and 2 MiB logs. This proposal changes no established guard bound.
Registration, test counts/outcomes, full CI/build/current wheel, actual encoding/
Arrow identity, memory/resource fit, complete owner/log enforcement, bootstrap,
held pilot activation/result and own-CP gates remain NULL/unqualified. Neither
a default promotion nor main merge follows from this isolated source commit.
