# Workflows

The nine files in `.github/workflows/` stay in place. Three run on this
repository's normal branches; the other six were written for one dated run on
a `lead/*` branch and are kept as records, mostly because tests or scripts read
or hash their bytes. Do not edit or delete a record workflow without updating
the pin that names it.

## Live

| Workflow | Runs on |
| --- | --- |
| `tests.yml` | pull requests, pushes to `main` (and older dated `lead/*` branches) and manual dispatch: the Python, native, viewer and Rust lanes |
| `validation-gate.yml` | manual dispatch only |
| `workflow-semantics.yml` | pull requests that touch `.github/workflows/**` or the actionlint config, and manual dispatch |

`tests/test_native_build_lanes.py` requires the four native jobs of
`tests.yml` to equal the jobs of `native-two-shards-v2.yml.in` here after
parsing, with one reviewed exception (`python-version`).

## One-run records

Each pushes only from its dated `lead/*` branch (or on manual dispatch).

| Workflow | Pinned by |
| --- | --- |
| `native-two-shards.yml` | `tests/test_native_ci_shards.py`: byte-identical to `docs/workflows/native-two-shards.yml.in`, which is pinned by SHA-256 |
| `native-two-shards-v2.yml` | `tests/test_native_ci_shards.py`: `docs/workflows/native-two-shards-v2.yml.in` must equal the v1 copy with its branch, path and name replaced; `tests/test_native_build_lanes.py` reads both `.github` files |
| `named-context-benchmark.yml` | hashed by `scripts/benchmark_named_context.py` (`file_pin`) and parsed by `tests/named_context_benchmark_contract_cases.py` |
| `paired-context-benchmark.yml` | hashed by `scripts/paired_context_benchmark.py` (`file_pin`) |
| `kin-decision-capture.yml` | nothing in `tests/`, `scripts/` or `src/`; only the 2026-11-08 audit and specs name it |
| `native-functional-smoke.yml` | nothing in `tests/`, `scripts/` or `src/`; only the 2026-11-08 audit and specs name it |

`native-two-shards.yml` and `native-two-shards-v2.yml` are byte-for-byte the
same apart from those three replacements; both stay because of the pins above.

## This directory

`native-two-shards.yml.in` and `native-two-shards-v2.yml.in` are the reviewed
copies the tests compare against. The dated `native-two-shards-*.md` notes
record the 2026-10-29 qualification runs, and `native-manifest-git-ref.md`
describes the immutable-ref shard-layout check. Run
`scripts/refactor_preflight.py` on any file here before changing it.
