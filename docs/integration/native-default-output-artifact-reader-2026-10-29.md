# Closed completed C76 to 95 artifact reader draft

Status: source-only draft. Focused pure contracts and unfiltered workflow lint
have passed locally; actual reader inspection has not run. No artifact transfer, reader audit, native
import, build, installation or new world is claimed. Separate root and peer
source review precedes workflow activation or artifact transfer. This record
does not change the completed producer's result.

The sole admitted producer is `74b2904dfc4acceb6c5c03a57aa8c2b6406ce4a6`,
GitHub run `40834257046`, job `123315234223`, attempt 1. Its registered artifact
is `12880510564`, exactly 75,556,121 bytes, SHA-256
`4afbb62db5d63165a42c5aa11e5740a665a514016eb9a5a339bb97ad48553fc3`,
with original expiry `2026-11-28T07:19:53Z`. Baseline source is
`c76efe8552b4c6c288ebb1f813e2c0a58e5957b1`; candidate is exactly
`95f73a74f809d7e10f09a1241c98014864350ffb`.

Nested input publication checks remain fail-closed against the current audit
time. Their earliest expiry, `2026-11-12T05:15:05Z`, is the effective audit
cutoff; the original outer artifact expiry above remains unchanged.

| Arm | Native crate tree | Retained wheel SHA-256 | Retained native SHA-256 |
| --- | --- | --- | --- |
| C76 baseline | `a4703ef4e9a21b5dbb194d318536a46e6ca8b71c` | `2e491456d01c2dd7bb2f7688e6acbc06b614610bbbe5be5ea6f0832ae220759a` | `06db5e19bdda13d7a536b236d677348f5ea7cb5adad2929962f0485192f9b4d6` |
| 95 candidate | `912a1a2489f8f8c548df19302bb2c0a4365fc32e` | `b0896cd9a03ae89f26a93748fd85717c1f6110d2d45e2d623fb3406c3f24d64b` | `3ee06a53b3c16dcba01bc53c8fe1dd97e530754a61d65fe2c1396b158b48e6d0` |

The baseline wheel was built from D028 with the a470 crate and used by the
completed producer with fresh C76 Python. The two wheels and native copies
remain distinct. Neither wheel may be installed by the reader. The wealth503
candidate wheel inside an older retained input grants no world or runtime use.

`scripts/native_default_output_artifact_reader.py` owns one closed registration.
Its default command is inert `describe`; `audit --execute` owns the remote
bootstrap, while its private inspect path performs only export inspection and
comparison. The following qualified `2b7a443e29e09051525d26f4e1c5b7e4cb75e7f1`
kernel files are retained byte for byte:

| Kernel | Bytes | SHA-256 |
| --- | ---: | --- |
| `completed_export_study_reader.py` | 27,953 | `ab0168bed9d97f4b9d96a7eec5d792e934214bf50858ce69644267039b19bc31` |
| `default_output_identity_reader.py` | 27,754 | `2bacde640402ce64ac52e284f3eb63d3462e1b00ec299ae8a21e1b6f065c649c` |
| `export_study_git.py` | 20,231 | `80434ebb0d455ce3f2d329efd5878c2ae28dd9fca652581e9210d242ae2c53fc` |

Both historical registry entries, original inputs, helper, comparator and
tests remain untouched. The new reader must not invoke the old frontend's
`inspect`, rebind old scalar identities or project the actual result into an
old schema. Only generic membership, stream/copy, Git snapshot/view,
case-contract, comparison and comparison-parser kernels are reusable.

The revised reader requirements are concrete validation boundaries:

- Authenticate all kernel and frozen producer/helper bytes before importing
  them; use authenticated source without stale bytecode. Verify complete
  before/after committed blob/mode snapshots for C76, 95 and producer74b, exact
  per-arm crates, and shared driver/comparator/codec/lock/project identities.
- Admit the regular outer ZIP by complete registered size/SHA before ZIP
  allocation. Check safe canonical names, aliases, types and encryption, bound
  2,048 entries, 32 MiB per member/JSON and 512 MiB expansion, then stream every
  member through hash, CRC and EOF checks. Inventory and result hashes are not
  preobserved: derive them only after outer admission, require the actual
  result's inventory pointer, and record this compositional seal explicitly.
- Validate actual74b's qualified result, exact producer/status/normalization,
  ordered 18 complete rows, per-arm wheel/native maps and final candidate arm.
  Independently verify both wheel compiled members against their native copies.
  Recompute all three retained input archives and the full input-admission
  graph, including original before/after publication observations and member maps.
- Validate all 36 probes and 18 driver records against verified source package
  digests and arm-native/schema pins. Link source/native descriptors, historical
  paths, common runtime, interpreter, one-CPU affinity, numerical/thread caps,
  dependencies and result maps. Historical absolute paths are provenance strings.
  Reconcile environment-preparation and installer receipts with original logs;
  the unretained uv executable's recorded checksum cannot be recomputed.
- Compare each of the original nine case pairs with the unchanged candidate
  CLI and no optional flags. Validate original audits and complete case sets,
  recompute nonempty counts, and reconcile the full original comparison log.
  Keep decoded and raw bundle checks with only `metadata.generated_at`
  normalization and original `.log`/`run_manifest.json` exclusions. Arrow remains
  opaque bytes. Never assume 399 file pairs before observing the file maps.
- Enclose setup and comparator children in original boot/birth/private-session/
  pidfd cleanup and resource admission. The immutable Git backend keeps its own
  bounded direct-process lifecycle; no generic private-session guarantee is
  inferred for that interface. Rehash copied bytes and source views after writers are
  quiescent, then retire only marked derived case scratch. Preserve original
  archive and audit inputs through runner teardown. Reader-specific negative-first
  finalization uses the actual reader start and the shared deadline; the original
  helper's 80-minute elapsed-time formula cannot finalize this 600-second reader.

The dormant template is
[`native-default-output-artifact-reader-workflow.yml`](../experiments/native-default-output-artifact-reader-workflow.yml).
Its only trigger is a push changing the exact registered active path
`.github/workflows/native-default-output-artifact-audit.yml` on
`lead/cloud-native-default-output-artifact-audit-20261029`. The sole job is
`native-default-output-artifact-audit`, guarded to the original repository,
exact workflow/ref, push and attempt 1. Activation requires an exact byte copy
of the reviewed template. The controller verifies the active workflow through
the current commit's Git blob and the physical dormant template.

One depth-1 sparse control checkout materializes only explicit root manifests,
reader/producer/kernel files, the small pure test and dormant template. Fixed
C76/95/74b Git objects are fetched by the admitted controller; no producer
worktrees or full checkout are required. The workflow sets up CPython 3.13.17,
runs only stdlib pure contracts and `describe`, then calls:

```sh
timeout --kill-after=5s 610s python -B control/scripts/native_default_output_artifact_reader.py audit --execute \
  --evidence "$RUNNER_TEMP/native-default-artifact-audit" \
  --prefix "$RUNNER_TEMP/native-default-artifact-reader-env"
```

The controller owns the single 600-second budget for initial 12 GiB disk/
2 GiB visible-RAM admission, exact uv setup, fresh frozen no-project/no-build
environment, fixed Git fetches, artifact transfer and inspection. It proves
physical absence of native package/distribution and guards native imports in
the inspector; comparator children use the same physically absent prefix.
Children retain 3/1 GiB admission, one actual allowed CPU and original caps.
Every derived copy requires 3 GiB plus the entire next declared copy plus
16 MiB reserve. Comparator limits are at most 180 seconds within the shared
remainder; Git commands retain 60-second limits. Inspection cannot reset the
deadline. Supervised children stop admission 20 seconds before that deadline
to leave cleanup/finalization time; this does not extend the qualification
budget. The outer job has 15 minutes; no workflow pip/uv/dependency install
or artifact download occurs outside the controller.

The wrapper prepares a bounded `publication/` authority set for a negative or
positive outcome, with metadata, inventories, source links, commands, logs and
receipts plus a prepublication inventory. The always-upload step selects only
that directory, named
`native-default-output-artifact-audit-${{ github.run_id }}-${{ github.run_attempt }}`
with 30-day retention. Raw ZIPs, native copies, wheels and source views are
excluded. A positive reader receipt still needs completed audit-job and
publication attestation. Partial authority cannot represent a positive audit.

This draft supplies no checkpoint/RNG-state, wealth503, 9d/1205, performance,
broader science or runtime-adoption qualification. Local disk headroom does
not admit transfer or execution. Source freeze, tiny pure/static validation
and independent review remain required before the separate activation step.

The first bounded source check passed22 tests and49 successful subtests in
0.155s on Python3.12.14, with no subprocess/network/project-native import
attempts. It exercised all12 retained official metadata snapshots (5 complete
accepted,7 incomplete refused) and matched source/native/environment descriptor
field sets to the pinned95 batch_manifest source without importing it. Tiny
temporary fixture I/O was allowed; observed case-boundary fixture bytes were
75,938. Later focused source/fault changes receive separate final receipts;
these stdlib tests do not qualify the registered3.13.17 reader runtime.
After the additional input-graph/installer and terminal fault coverage,24
tests and49 successful subtests passed in0.161s with the same zero blocked
attempts/project-native modules and all12 metadata/source-shape checks intact.
Exact source and test hashes/results are retained externally under
`native-default-output-artifact-reader-source-qualification-20261029`.
The first frozen reader `c0b988c8` and its unpushed activation candidate are
preserved. Its source-review finding led to a narrow child: rehash the retained
baseline driver against the verified Git blob descriptor before positive
finalization, with same-size and changed-size mutation contracts.
The narrow child passes25 tests and51 successful subtests in0.236s under the
same guard; all12 metadata checks and pinned source-shape checks still match.
The prior24/49 result and c0 source finding remain retained separately.
