# Completed C76 to 95 artifact reader V2 source correction

Status: V2 is a source-only correction draft. Actual audit has not been activated or
executed. Focused pure source fixtures passed; independent root/peer review is required
before a separate activation decision. The original producer is unchanged;
this work creates no new worlds or native execution and reruns no parity study.
Both V1 source documents remain preserved byte for byte.

The first actual reader attempt used source
`bc39d59342b08641af07582a81feef2c5e249b92`,
[run 40843215377](https://github.com/YotsuBotfds/Chronicler/actions/runs/40843215377),
job `123344349616`, attempt 1. Hosted CPython 3.13.17 passed the 25 pure
contracts in 0.204 seconds. The controller passed its initial 12 GiB disk/
2 GiB visible-RAM admission, then failed in bootstrap with `SnapshotError`
after 0.381 seconds. No controller source-object fetch, environment installation, 75 MB original
artifact transfer, export inspection or comparison occurred.

The completed failed job published negative artifact `12883502650`, exactly
1,137 bytes, SHA-256
`8e53f7c3b502ab12e71990f65404a32c0640d92a2ab02954ca3329f0a79951e2`.
The external failure pack records verification of all three archive members,
their CRCs and complete inventory. The retained error exposed only its class;
the exact `SnapshotError` message was lost. This draft does not invent that
message or treat the failed reader attempt as a failure of producer74b.

Checkout logs show `--filter=blob:none`. The qualified immutable Git backend
sets `GIT_NO_LAZY_FETCH=1` and `protocol.allow=never`, and its complete-tree
verification needs committed blobs beyond the small sparse filesystem view.
That observed checkout/backend mismatch motivates V2's explicit object
hydration. The missing exact error detail limits the diagnosis: the correction
is not yet a demonstrated runtime fix.

V2 keeps sparse materialization and obtains complete fixed commit objects
through the controller before invoking the immutable Git backend. After the
initial admission, the controller supervises this command for the actual
current control commit and each of the three frozen source roles:

```sh
git -c core.fsmonitor=false fetch --refetch --no-filter --no-tags --depth=1 origin SHA
```

The registered roles remain baseline C76, candidate95 and producer74b. The
current control SHA is the actual V2 push source, not a substituted historical
control. These fetches stay inside the existing 600-second controller clock
and original supervised resource/cleanup boundary. They require no full
checkout, producer worktrees, broader sparse patterns, immutable-kernel edit,
lazy-fetch allowance or relaxed Git protocol policy. Source-only fixtures must
check exact flags/roles and ordering before the first backend call. V2 also
retains a bootstrap stage and bounded safe error detail for negative evidence;
credentials and signed storage URLs must remain absent from logs and receipts.

The intended input remains the same completed producer
`74b2904dfc4acceb6c5c03a57aa8c2b6406ce4a6`, run `40834257046`,
job `123315234223`, attempt 1, artifact `12880510564`: exactly 75,556,121 bytes,
SHA-256 `4afbb62db5d63165a42c5aa11e5740a665a514016eb9a5a339bb97ad48553fc3`.
Its sources remain C76 `c76efe8552b4c6c288ebb1f813e2c0a58e5957b1` and
candidate `95f73a74f809d7e10f09a1241c98014864350ffb`. Nested publication checks
make `2026-11-12T05:15:05Z` the fail-closed effective audit cutoff; the original
outer artifact expiry remains `2026-11-28T07:19:53Z`.

The three qualified `2b7a443e` kernels remain byte-identical, as do historical
registries, original helper, comparator and inputs. V2 keeps actual per-arm
native/wheel/schema/probe/input validators, complete source snapshots, the
final retained baseline-driver rehash, outer-SHA inventory seal composition,
and the exact no-flags nine-case comparison schedule. Both decoded and raw
bundle checks retain only `metadata.generated_at` normalization and original
`.log`/`run_manifest.json` exclusions. Arrow remains opaque bytes. Neither
retained wheel is installed by the reader; no wealth503 runtime or world is
admitted. The [preserved V1 protocol](native-default-output-artifact-reader-2026-10-29.md)
records the unchanged lower-kernel and export-validation boundaries.

The new [dormant V2 template](../experiments/native-default-output-artifact-reader-v2-workflow.yml)
uses only a push changing
`.github/workflows/native-default-output-artifact-audit-v2.yml` on
`lead/cloud-native-default-output-artifact-audit-v2-20261029`. Its sole job is
`native-default-output-artifact-audit-v2`, guarded to that repository,
workflow/ref and first attempt. It stays outside `.github/workflows` until
separate review authorizes an exact-byte active copy. The V1 workflow and
V1 activation history remain unchanged.

One depth-1 sparse control checkout materializes only the explicit reviewed
scripts, tiny pure test, root manifests and V2 dormant template. The workflow
sets up CPython 3.13.17, runs stdlib pure contracts and inert `describe`, then
invokes the same script and CLI:

```sh
timeout --kill-after=5s 610s python -B control/scripts/native_default_output_artifact_reader.py audit --execute \
  --evidence "$RUNNER_TEMP/native-default-artifact-audit" \
  --prefix "$RUNNER_TEMP/native-default-artifact-reader-env"
```

The 15-minute job retains original one-thread numerical/Rayon caps, one actual
allowed CPU, hash seed zero, no user site, `-B` and optimization zero. Initial
12/2 GiB admission precedes controller setup and transfer; supervised children
retain 3/1 GiB admission and a 20-second cleanup reserve within the shared
600-second deadline. Every derived copy requires 3 GiB plus its full declared
next size plus 16 MiB reserve. Setup, object hydration and comparator children
use original private-session/boot/birth/pidfd cleanup. Direct `own_source` Git
probes retain 10-second limits; the immutable Git backend retains 60-second
bounded direct-process cleanup. No generic private-session guarantee is made
for those Git probes. Comparators stay within 180 seconds and the shared
remainder, with quiescence and rehash before marked case-scratch retirement.

The always-upload step selects only
`$RUNNER_TEMP/native-default-artifact-audit/publication/`, using prefix
`native-default-output-artifact-audit-v2` and 30-day retention. It publishes
bounded complete positive or negative authority, never the raw ZIP, native
copies, wheels or source views. Negative-first finalization and completed
job/publication attestation remain required; partial output earns no positive
audit. This V2 draft supplies no artifact-read, checkpoint/RNG-state,
performance, broader science or runtime-adoption qualification.

The V2 focused selection passed30 tests and51 successful subtests in0.165s
under a strict no-subprocess/network/project-native-import observer. The12
saved original-producer metadata forms still match their expected acceptance
states; failed-audit provenance is separately rejected as an original target.
Pinned95 source descriptor fields also match fixture shapes without importing it.

The workspace capacity hold was preserved. Qualification used an authorized
275,312-byte,13-file selected-TEXT view on `/tmp` device34, reconciled to the
unchanged read-only workspace device27 before/after. The real fixture/evidence
write device retained the same3GiB+8MiB pre-run reserve,512KiB fixture cap,
128KiB output cap and30-second outer bound; CPU4 and thread caps1 applied.
No full checkout, Git object database, binaries, dependency setup or original
archive was created by these synthetic contracts. Versioned observer/guard/log
and source-view manifest are retained under
`/tmp/chronicler-native-default-reader-v2-qualification-20261029/`; only a small
pointer is written to workspace. These results do not qualify a real V2 audit.
