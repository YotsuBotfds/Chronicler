# Next care/K2 consolidation: source assembly only

This assembly starts at `0d8c299e38ba5f3ce9dbaedeb657e237c77d8247`, including the
immutable-Git native-layout tool and exact care23 runtime. It imports the four
qualified care documentation changes at `156bfbf8` and the nine current-review
documentation changes at `7f1c0377`; only the continuation ledger is composed.
The [care CI result](retained-kin-care-ci-2026-10-29.md),
[original practice-byte audit](original-practice-byte-audit-2026-10-29.md) and
[checkpoint header result](wealth-floor-checkpoint-header-result-2026-10-29.md)
retain their exact historical sources and limits. No new combined CI or execution
qualification, default activation, adoption or main promotion is supplied.

The simulation Python, native crate, Viewer, dependencies, active workflows and
existing controller authority slots remain byte-exact to care source
`23d4d24659cfda848d5bda034760ab9d1e8b57fe`. The separately authored native batch API
is excluded. The source-only additions are the unwired K2 metadata module, its
unchanged test/FFI text fixture, six exact historical helper dependencies, and
bounded test-registration metadata. These helpers are not runtime wiring.

K2 is copied from `c5785e35cc42407c6a793a7c18fb1b5daf5d64be`. Its historical
[design/qualification](../experiments/wealth-floor-checkpoint-metadata-v2-2026-10-29.md)
remains byte-exact, including that branch's former runner registration. This
integration instead adds one dedicated `wealth-floor-checkpoint-metadata-v2`
offline chunk containing only `tests/test_wealth_floor_outcome_checkpoints_v2.py`.
The existing checkpoint and care chunks are untouched; every chunk keeps the
110-second deadline. The native manifest adds only that module to shard 1:
303 modules total (160/143), all 300 old owners plus two care owners retained,
six exact skip IDs and the 623 successful-subtest seal unchanged. Parametrized
K2 cases do not add pytest subtests. The manifest selftest pins all these facts.

The minimal import/test-read closure is explicit: K2 imports candidate proof;
that imports bridge/controller/hosted-deployment; controller imports bridge,
build-resources and hosted-deployment. The unchanged test also reads original
K34 for its SHA/function-AST comparison. Initialization performs stdlib imports,
module-path setup and finite constants/classes/function definitions only. Main
entry guards are not invoked. Scientific/native imports and owned process
operations remain inside uncalled functions; no workflow, binder or driver is
copied or activated. This is the import/test-read closure, not authority to run
the historical controllers or a complete new scientific-execution deployment.

| Exact imported helper | SHA-256 |
| --- | --- |
| `scripts/wealth_floor_candidate_proof.py` | `13239d13a68fee3e25732d9e1323edaaa20e117ce679b15a5c847585b383249f` |
| `scripts/wealth_floor_native_build_bridge.py` | `cb87ff673817fc655beb39cce88c39295cfa87dcd787e108e2cbf85026965373` |
| `scripts/wealth_floor_native_build_controller.py` | `60bb77212757f632d8d80ed226f94e6ef9864134c4453b5affeb51dc059b9dd1` |
| `scripts/wealth_floor_hosted_deployment.py` | `d52b3c2b9269eb67ef154006fe06429645f79052d3dbcd4b28e6b1479f39bfb8` |
| `scripts/wealth_floor_build_resources.py` | `44f1e1d23598283f0fa7b0580477e026bd3d13d515ec84202dab108cfb2db5b2` |
| `scripts/wealth_floor_outcome_checkpoints.py` | `34aa2afe4ec99422f88fd12ef7832c78d942810846550c4cf5fc9b1b743d7961` |
| `scripts/wealth_floor_outcome_checkpoints_v2.py` | `9576d9958e829d065d2467fc251b1360cd826a8d7b96f4281496a1019a89e24d` |

K2 remains `METADATA_ELIGIBILITY_ONLY`, pinned to historical 503/package 49d78e87.
It does not establish decoded Python/native/header coherence, physics validity,
checkpoint reuse or a scientific pass; original cohort 33d stays
`INCOMPLETE_MECHANICS`. The old 74 cases and prior 58 dictionary result retain
their own sources. No combined 132-case result is claimed. Fresh assembled
standard CI, enabled care World/checkpoint, default-output/global-RNG and
scientific/performance qualifications remain unrun. Root execution and promotion
authority are absent from this source freeze.
