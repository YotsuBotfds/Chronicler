# CI artifact intake capability — source proposal, 2026-10-29

The capture65 collector kept a literal destination from the earlier829 reader.
It wrote nine new ZIPs and replaced nine metadata files in the old evidence
namespace. Exit status alone did not detect the wrong destination. The original
first observations and failure remain preserved. Root's separately authorized
recovery restored the nine original metadata bodies and moved the nine new ZIPs
without reacquisition or producer replay. This proposal does not rewrite that
incident as a clean first collection.

`scripts/ci_artifact_intake.py` adds an unused stdlib helper. Its factory creates
a fresh root exclusively and issues a live single-caller capability tied to
repository, exact source commit, run ID, attempt, root path/device/inode, and a
closed exact artifact ID/name/size/SHA256 list. Existing files, directories, or
symlinks cannot be adopted. There is no load, resume, or replace API. Callers
must supply the expected namespace and binding again at ingress and finalize.
The held directory FD, actual named root, file identities/types/link counts,
finite inventory, and immutable capability body are checked before opening a
new output and before each payload or metadata write. Deterministic ID-based
filenames use exclusive creation; display names never become paths.

The default list contains exactly nine artifacts. A caller can explicitly
select one through sixteen, still as an exact closed list. Each opaque ZIP is
limited to8MiB; declared archives plus a prepaid1MiB control reserve must fit
inside24MiB. Names and root paths are limited to512UTF8 bytes, root paths to
sixteen components, and the flat root to35 files. Copies request at most64KiB
per read and permit4096 read calls. Capability and result records are at most
64KiB each, per-artifact metadata16KiB, and the manifest1MiB; all metadata
attempts share the prepaid1MiB budget. Debits include partial/failed attempts.
These limits bound retained logical content, not filesystem blocks, process
memory, available disk, or a complete simulation pilot.

The input reader supplies already downloaded opaque bytes. Intake never opens
a URL or parses/extracts ZIP content. Size and SHA256 must match the closed
allowlist; completed destination bodies are independently read back and pinned.
The generated metadata records are new intake receipts containing the binding,
exact supplied artifact facts, and copy disposition. They are not original HTTP
API responses and must not be described as preserving those responses. A future
collector integration must separately preserve and qualify its original
official metadata and approval/run/source provenance.

A bad binding, borrowed target, unknown artifact, duplicate, or declared cap
overflow refuses before a new artifact writer. Excess streaming bytes refuse
before writing those bytes. Any fault closes further intake. Each ID/output
name has one attempt; partial archives and metadata remain as negative evidence.
There is no overwrite, rename-over-old-file, deletion, automatic retry, or
recovery. Ordinary failures may add one exclusive bounded negative receipt if
the namespace still validates; metadata failures never retry the same name.
The original exception object is re-raised. Interruptions propagate after owned
writer cleanup without reader replay or a negative callback. Input readers
remain caller-owned. Known output/root descriptors are invalidated before close
attempts; an uncertain close is not retried and prevents a positive result.

Finalization closes ingress immediately, inventories the exact finite files,
and records missing/failed artifacts. It creates an exclusive manifest and
result marker, changes each file to0444 and the root to0555, rechecks exact body
pins and modes, then closes the owned root. Success is returned only after that
sequence completes. An on-disk success-path marker says `CLOSED_CANDIDATE`:
immutable bytes cannot attest to a later fsync or close. Reading that marker
alone does not establish successful finalization, cleanup, durability, or CI
qualification. A negative finalization can also freeze its retained evidence;
some failed namespace/metadata/close paths cannot produce a complete marker.

This is a single-caller correctness capability with a trusted injected backend,
not an adversarial Python/OS sandbox or concurrent IPC broker. Real POSIX syscall
semantics and durability are unqualified. No collector/workflow calls the helper;
no downloader, subprocess, Git, project import, native extension, World, RNG,
simulation, main, dependency, registration, or active workflow changes are made.

`tests/ci_artifact_intake_contracts.py` is intentionally NONDEFAULT: its filename
matches neither `test_*.py` nor `*_test.py`, and it is absent from native ownership
and offline chunk lists. Its34 plain functions expand statically to105 pure
fake cases: stale roots/bindings; existing sealed namespaces; identity, hardlink,
and capability substitutions; count/name/byte caps; size/digest/partial-copy
failures; metadata and FD failures; interrupts; finite negative closure; readonly
finalization; and root changes during copy or before metadata. All are UNRUN.
FakeFS/reader/writer/FakeOS operate only on in-memory dictionaries/bytes and
per-instance injections; they do not probe a filesystem or decode an archive.
The source-only catalog is not pytest collection or execution evidence.

This child changes only the helper, this explicit test module, this note, and an
additive continuation prefix. All other65 source entries, native09ec,184 product
Python modules,304 current native owners/six skips/623 subreports,38 offline
chunks/110seconds, workflows, dependencies, and333 current offline source pins
remain inherited unchanged. New tests are not current CI readiness. A different
reviewer must examine the complete frozen source and any concrete pure runner
before root can authorize a first bounded pure attempt. Actual intake, real OS
probes, candidate imports/compile/tests, builds, CI, push, and runtime approvals
are absent; no performance or simulation claim follows from source inspection.

The implementation handoff binds these incident authority bytes:

- Recovery receipt SHA256 `21abbf6b7a329f97fc1f15c78fa8e76c56b87559f8723d8f94081a94cfe87ad0`.
- Original recovery proposal SHA256 `2a033c72069f2f755b724015703e46dfca7c6a5e68e97fd492475ab8ff19f4f7`.

Original collectors/evidence and all prior frozen stores remain untouched.
