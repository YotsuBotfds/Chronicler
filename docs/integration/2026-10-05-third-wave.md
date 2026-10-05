# Private third integration wave

The receiving checkout combines the reviewed second-wave baseline with the
opt-in fishery feature and reviewed mutual aid, including both native base-cargo
repairs. Public base is `edf72991cad58d6670b1f382c33d50d903a6054a`.
The original public checkout remains unchanged. The integration has no remote.
Final branch, HEAD, tree, native identities, results and package hashes are
recorded in the separate delivery receipt so that qualification can run on the
final committed HEAD without a subsequent documentation change.

| Input | Drive ID | Bytes | SHA256 | Source identity |
| --- | --- | --- | --- | --- |
| Second wave | 184pk4g5gLGW1gcD8KTcT_5ccyHk_5Ne- | 15657933 | 553ea21b3c167b56c2f7dc763c34737d0905bd134eccebd747494128c6826aa4 | 18c909eb3f9abd0b9e64b40e6cd1e09c5567e913; tree 91f539664691bcf6eab2f1e20480cb38cd6ef77f |
| Fishery | 1CxSnnuDP_5Lm-cRkbEWHnz1xSD6aSLJl | 434402 | f82f0e769276e184a06ef905040494d75e3e0af44cf95985d8957a7c30245f2a | feature 127499d7113663b3c25832bf29f95a3074643579; publication-source a9c1745ef7e054decb3cf925182cf0b4d9633585 |
| Aid/cargo qualification | 14DKcVcGy2yZlWU7NSuKNEf5CW-seo_NP | 6991544 | fdb186f55e5e18dcd42e4cf396c983b70e85e9cf6bec84391a3b2ef770af2e7b | executable cc2179a17c4da529315d3bae53015d48b8c75e3e; delivery-only 070d92d08b55e5370031fbdde9e17256d3a8f591 |

Supported Drive metadata/fetch tools materialized owner-only archives locally.
Whole sizes/hashes, safe member paths, manifests, nested archives, source copies,
bundle prerequisites, exact source commits/trees and public ancestry were checked
before assembly. Checkout `.agents` and `.codex` are empty; no AGENTS.md or local
skills were present. Supplied restore instructions and COMMIT-FILE-MAP.md were
read. The archived original aid candidate `58ee08bc690537cd0e42bbd696e46f2941336c3f`
is a provenance claim whose Git object was not supplied. Its archive restoration
is the distinct actual commit `960d39ed0f4cd717bdca5486b522792c44d659fb`.

## Composition and accounting

Merge `847bcfa` retains fishery **feature** history and its original evidence and
packaging script. The publication-source variant is restored separately under
`refs/integration-sources/fishery-publication-source`; all Python/native/tests
bytes equal the feature variant, while docs/evidence/package-script scope differs.
No publication was attempted. Merge `3234661c2a716af1673bea6d3c784020bf10efdc`
retains aid delivery history and executable ancestor. All prior second-wave refs
and governance provenance are retained.

There were no textual conflicts. Automatic overlapping compositions were
reviewed in simulation.py, main.py, models.py and native ffi/mod.rs. The
simulation retains both pre-turn stale-native fishery checks and lagged aid
dispatch: Phase 2 reads commitments, dispatches aid, packs the economy, settles
prior cargo/catch and observes stress. Phase 9 synchronizes regions, performs
ecology recovery/harvest, patches native yields, and then runs agent mobility
and deaths. Baseline performance/hostage/replay code remains composed.

Cargo repairs retain the supplied corrected accounting. Hybrid Loading departure
rechecks stock minus queued departures after consumption; unbacked reservations
cancel without return credit. Shadow diagnostic buffers retain abstract behavior.
Loading/Transit death releases accounting once before killing/reusing the pool
slot; surviving cargo statistics are refreshed after demographics. Both bugs
already reproduce on the public native base with aid absent. Changes to those
histories are intentional, and are not attributed to the flags.

Corrected control `e425020` starts from exact second wave and applies only the
four reviewed native repair/test files. It is a newly assembled cargo-only
control with its own fresh build/tests, not an inherited qualified binary.
Producer native hash `8f4ee68be6ce797854df323418789169ee113ee4f5f0e4508028dffee4a3e931`
is historical evidence only. The receiving final binary is recorded separately.

## Joint qualification and control repair

`scripts/qualify_third_wave.py` runs complete `run_turn` ordering with real native
ecology/economy/mobility/demographics. The 00/10/01/11 flag matrix uses seeds 42
and 77 with directed 3- and 5-hop merchant networks, two donors, and two competing
recipients. All worlds/native snapshots and receipts are compared as exact
parsed values on repeated executions. Fixture route margins/network are explicit
scenario inputs. No cargo, ledger, delivery buffer or agent state is injected.
Fishing suspends at turn 16; routes shut down at turn 23. Separate cancellation,
in-flight return and turn-2 catastrophe-death (1000 per region) cases inspect
cleanup through the same full turn loop.

An independent double-precision per-region/per-good stock oracle uses packed
starting stocks, live farmer/population counts, and lifetime cargo counter deltas.
It computes production, proportional food consumption, salt preservation/storage
decay and caps, checks grain/salt/fish stock-plus-cargo balances, and requires
zero clamp correction. The float32 ABI tolerance is 1e-3 per cell. Prior fish
catch caps are checked against the previous independently audited biomass debit;
recovery, harvest, biomass bounds, rest recovery and yield caps are checked.
Aid checks per-good encumbrances, donor reserves, capacities, transit survival,
queued treasury debits and independently replayed treasury keep flushes. Repeated
same-turn aid and commitment reads are checked. Stock outputs are checked again
at the end of the entire turn. Existing direct-ABI original 180/30 fixtures and
eight 28-turn cargo cases complement full-ordering tests, including economy-only
replay and Rust pool-slot reuse checks.

Raw historical artifact checks initially fail because the new model schema adds
default-valued experiment fields. A narrow **test-only** repair asserts every
removed field equals its specified default and compares all remaining artifact
content/formatting to unchanged independent golden hashes. It also repairs the
aid-only legacy control's fishery metadata comparison. Goldens and production
serialization are unchanged. Raw artifact failure evidence remains in delivery;
projected equality is not described as unmodified raw artifact equality.

The corrected cargo control separates intentional base corrections from flag
effects; its full shared world values, native snapshots, stocks/cargo/treasury
are compared with final 00 cases. Python-off historical snapshots and ordered RNG
remain exact. Native hybrid object-key order is compared via parsed values when
appropriate, preserving the known raw-byte limitation.

## Limits and reproduction

All final results, commands, skips, failures, native source/build/binary hashes
and independent review are in the restore package's REPORT.md and DELIVERY.json.
Use Python 3.13+, `uv sync --frozen`, and the explicit scientific dependency
install from the supplied aid restore instructions; do not rewrite uv.lock.
Build native with `maturin develop --release --locked`; use writable UV/CARGO/
RUSTUP caches. For full Python, preload and verify the real native classes and
run unfiltered pytest with CHRONICLER_UNTOUCHED_SOURCE set to the corrected source.
Run default `cargo test --locked`, viewer npm test/build/lint, and joint pytest.

These bounded fixtures do not qualify full hybrid checkpoint continuation,
scientific population improvement, calibration, timing gains or production
deployment. Yield-famine predicates/events and stockpile food sufficiency remain
distinct observations; none alone establishes population benefit. The known
hybrid object-key byte-order limitation remains. Permission-blocked serialization
correction `507ef977` was not reconstructed, imported or accessed through another
route. G05 is excluded; governance remains byte-identical, detached and off.
No private frozen b665 changes, public GitHub writes or production flag activation
occurred. Parent owns private backup/publication decisions.
