# Coherent dormant cache repair — 2026-10-29

This source-only successor of `1097b3148ab909b42433e56b86b671f5babfc2c5`
repairs independent findings C1/C2 (`cf28f06d…`). The original snapshot and
blocked review remain preserved. Only this helper, appended test contracts,
this dated note and an additive continuation header change. The workflow is
byte-exact1097 with literal flag **"0"**; all other parent entries remain exact.

After the prepared record's source inventory validates, both `admit` and `seal`
use a fatal prepared-source revalidation boundary. Failure to acquire the
physical snapshot (including Git/blob, mode, missing/unreadable/layout refusals)
becomes `SourceDrift`, as does returned-row content drift. BaseException
interruptions propagate. An initial `admit`/`seal` revalidation refusal stops
before context probes, result/output writes, timestamp writes, build-record reads
or cache sealing. Admission repeats that boundary immediately before its first
timestamp write. If a post-write snapshot refuses, `apply_plan` retains the fatal
`TimestampFailure` classification: earlier writes may exist, and no ordinary
fallback follows. Initial unsupported preparation remains an ordinary-build
fallback. Context,
cache miss/prefix and malformed metadata refusals retain their ordinary paths;
partial/post-write failures remain fatal `TimestampFailure`.

The exact unsupported names `COMPILER_PATH` and `GCC_EXEC_PREFIX` are rejected
while checking names, before selecting any values. Their values are neither
copied into context nor read/converted/hashed. This closes these two identified
GCC backend selectors; it does not claim complete discovery of all compiler
extensions or qualify a hosted tool/backend layout. Supported public inputs and
full context-key admission remain covered by a separate synthetic positive case.

The entire prior48,460-byte test file is preserved. Five appended functions
expand prospectively to16 pure cases: eight actual-main `admit`/`seal` snapshot
acquisition refusals with fake FS/Git tools and forbidden later operations; two
immediate-prewrite refusals; two initial-preparation ordinary controls; three
name-only selector refusals with opaque values; one supported-context admission.
All original69 cache cases and these16 new cases are **UNRUN**. The prospective
cache selection is85 cases and full module210; these are AST catalogs, not
collection or results. Registration, owners/skips/subreports,38chunks/110s,
dependencies/product/native09ec and all existing caps remain unchanged.

No reviewed import/compile, collection, pure test, probe, cache operation,
timestamp mutation, Cargo/build, native/World/checkpoint, network, Actions,
publication or activation ran for this repair. Independent successor source
review and a separately frozen/root-granted meaningful pure gate are still
required. Current-source CI, installed layout/fingerprint cause, cache
hit/freshness behavior, wallclock benefit and activation remain NULL or held.
The complete original dated note follows unchanged as historical source evidence.

---

# Dormant native release cache adapter — 2026-10-29

This source-only child of `65dd90e1f399b647a49b3f299039c7c6f86cf8f4`
adds a stdlib metadata/timestamp helper, appended fake contracts and dormant
native-builder steps. `CHRONICLER_NATIVE_RELEASE_CACHE` is the literal **"0"**.
The optimization has not been applied, tested or measured. Parent65's first CI
was pending when this source snapshot was written; qualified parent829's
first-run authority is root `f4bbc33a…`. Existing historical continuation bodies
remain intact. No current source CI, fast-path activation or experiment is claimed.

At829 the release cache was actually restored from25f, then the unchanged crate
compiled again for1m36s.25f restored6a2 and compiled for1m42s. Native crate09ec and
native SHA256 `1ec3282dd43bc1ecfa2459960f19047aec5d8744406b5655aef44202585eaf72`
were unchanged. Cargo dirty-reason traces and producer source/file timestamps were
not exported. Timestamp invalidation is **unconfirmed**, not an observed cause.
829's98-second build step/128-second builder and525-second whole workflow versus
25f's106/139/510 are uncontrolled observations, not a demonstrated gain. Avoiding
that96-second recompile is only an unmeasured potential builder ceiling before
verification/packaging/restore overhead, with no workflow-speed guarantee.

## Default-off composition

With flag0, the complete old release-cache restore, dependency installation,
manifest admission, preflight, maturin build, install, current record-build and
artifact steps remain in order with their exact bodies. All new steps require
flag exactly1. The only old-step addition is a condition that remains true for0
(and unknown values). The default-off projection removes marked new blocks and
that condition and reconstructs the entire parent workflow byte for byte. All
other jobs,304 owners, six skips/623 subreports,38 chunks/110s, native crate,
Python product code, dependency locks and existing timeout/resource caps are
unchanged. No whole-suite selection or skip adjustment is part of this source.

Flag1 would first probe actual installed context after dependencies, then restore
an exact content/context key. New actions reuse the existing cache action's exact
commit `0057852bfaa89a56745cba8c7296529d2fc39830`. The old cache restore is disabled
only for flag1 to avoid overlaying archives. The new integration requests no
prefix restore; the helper also refuses timestamp admission on any supplied
prefix/miss/old-format hit. Branch/default-branch cache visibility is not assumed.
A same key on a different branch need not be accessible. A different native tree
or semantic context cannot obtain admission by fallback; ordinary Cargo remains
the safe path. Concurrent old048/new09ec branch caches must retain their distinct
native keys. No cache operations were performed for this implementation.

## Adapter contracts and closed limits

`prepare`, `admit` and `seal` expose injectable FS/tool/context boundaries. Import
only defines constants/functions/classes; it performs no probes or metadata reads.
The native key hashes full tracked crate path/mode/content including lockfile,
build.rs and crate pyproject, plus helper bytes/schema and actual semantic context.
Git100644 is checked against physical0644 and actual Git blob content. Untracked
crate inputs, path/git/alternative-registry dependencies, workspace topology,
Cargo/toolchain configs, unsupported flags/environment or tool/file layouts use
ordinary Cargo. No whole-environment digest, tokens or credential values are read
into the context. Public semantic environment names are closed; unknown names
reject admission. The context pins installed rustc/Cargo/sysroot/tool bytes,
compiler/linker identities, current maturin executable/distribution files/version, resolved compiler link inputs
and installed-tool dynamic-library pins, CPython executable,
library/headers/ABI, actual argv/features, public build paths and platform/image.
Actual completeness of the supported hosted layout is an activation review gate;
no current semantic context or Cargo-layout tuple was observed here.

Declared adapter bounds are4MiB per JSON body;4096 source files/32MiB;
32768 release files/1GiB;16384 files/512MiB per context inventory;
32768 directories per walk;128MiB per file;1024-byte relative paths;
65536 bytes and20s per tool probe. Child probe output has an RLIMIT_FSIZE bound.
Exceeding a metadata/layout bound is an ordinary-build fallback before timestamp
writes. These are additional adapter admission bounds, not enlarged CI/test caps.
Actual Cargo inventories/manifest size/footprint/mtime precision remain unobserved.

A producer manifest is sealed only after the unchanged current build/install/
record-build succeeds. It records source original mtime_ns, complete release
content/mode/mtime inventory and old producer commit/run/wheel provenance. The
manifest is outside release, excluded from its own inventory; wheels and old
build.json are never cached. Internal hardlinks are accepted only if the inventory
contains every alias (observed link count equals in-tree equivalence-class size),
with identical facts; outside aliases, symlinks or unsupported modes reject it.
Chronology requires actual local Cargo invoked.timestamp markers at or after all
recorded source timestamps. Original producer times are restored, never an epoch;
no fingerprint file is edited. Missing markers or imprecise archive timestamps
prevent admission rather than pretending it works.

All manifest/key/context/source/release/layout checks precede the first timestamp
write. Each write's exact precision is checked, followed by source/time rechecks.
Any partial write/post-write error is a fatal negative, not ordinary fallback;
source drift after preparation is fatal. Context is reprobed before admission and
sealing. Existing manifest files are retained without overwrite. Exact hits do
not get a new seal, but still undergo post-build checks. Source contents/modes
are checked around the build; current record-build also remains mandatory.

The normal maturin command is always invoked. A fresh empty current wheel output
is required for helper admission; the invocation's actual wheel is installed and
unchanged compiled-class/native-member/full-source/run receipts still run. The
cache manifest never substitutes for that receipt. An unchanged native digest is
allowed; a Cargo Fresh result must be described as reused compilation state plus
newly produced wheel, never relabeled a fresh native compile. Full protected/
package closures remain source-specific, not constant805/183 assertions.

## Held gates

All appended tests are unrun pure synthetic contracts. Later focused guarded
selection can use `-k release_cache`; do not infer a full-module125-case PASS.
No product/native import, local tool probe, utime, Cargo, build, pytest, World,
checkpoint, cache mutation, network or Actions operation was executed here.
The source reviewer must check the closed context list and workflow projection;
a separate meaningful focused pure gate must pass before any default-off CI.
Actual Cargo file layout/fingerprint cause, tool/ABI context, distribution and
linker-runtime closure/layout must be validated from an actual candidate worker
before fast-path activation. Unsupported probe outputs fall back to ordinary
Cargo; these source paths are not evidence that the actual layout is supported.

The proposed controlled experiment remains **UNAUTHORIZED**: three build-only
invocations P/A/B on one exact candidate/tool context; P seals an ordinary build,
A and B independently restore its same archive at canonical paths, with B alone
using verified timestamp restoration.900s total,240s/build+180s setup/seal,
at most2 CPUs/4GiB AS/2GiB retained and2MiB per log; stop on first failure with
no retry. Scratch/canonical-path rotation, archive copies, free-space admission
and retained footprint must be made concrete before grant. Do not move/delete old
sources, caches or evidence or assume they fit. Capture actual dirty reasons and
identities; one fixed-order pair is not a controlled wallclock efficacy claim.
Full standard CI on the eventual source is a separate later gate. Schema tuples,
new native API, source-copy truth, capture/retention/owner activation, positive
floating totals, actual World/CP/RNG/pilot/science remain NULL or held.
