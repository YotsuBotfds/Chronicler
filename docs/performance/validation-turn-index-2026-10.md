# Validation turn-row indexing, October 2026

Loaded validation tables now index their rows by turn once. This removes
repeated whole-column filtering while preserving the selected rows and every
oracle calculation. It substantially improves the synthetic filtering boundary;
the retained small procedural seed did **not** demonstrate a reliable speedup
for complete validation. No simulation, snapshot writer, oracle method, sample
domain, matching rule, threshold or RNG behavior changes.

## Ownership and exactness

`validation_io._read_arrow_columns` returns a private dictionary subclass
whose data keys and values are unchanged. Its `_turn_rows` attribute holds an
immutable index separately from the schema. Monotonic turns use one `range`
per turn; shuffled legacy tables use read-only uint64 row-index buffers, in
original row order. Duplicate turns, agent IDs, edges and memories remain in
their original order. Numeric columns retain the existing packed `array('q')`
and `array('d')` representation; selected snapshot columns remain lists.

The owner lives exactly as long as the loaded columns. There is no global,
file-path or object-id cache. Reading a changed file creates a fresh owner and
index. Plain caller-owned dictionaries keep the original one-shot predicate
filter, so edits between calls are observed without stale metadata or synthetic
schema keys. Loaded tables are private read-only inputs throughout validation:
do not modify their mapping or arrays after loading. The index's immutability
does not make Python arrays immutable. Copy/pickle rebuilds an independent
index from the copied/restored data.

Needs, legacy graph/community/cohort and ablation readers that already call
the selection helpers reuse the loaded index. The separate spec-community
module retains its existing per-run index/cache; this change does not alter
that module or cache its computed communities. Joint-turn selection still
uses its existing snapshot construction and fallback rules. This keeps
malformed-input errors and legacy single-snapshot behavior in the same path;
removing those constructions is a separate optimization candidate.

## Measured boundaries

Measurements on 2026-10-28 used base `5b5252ed` and indexed source
`922d2a33`, committed before timing. The only later changes in this branch
are this note and the benchmark probe. Source SHA-256 for `validation_io.py`:

* Base: `dd73c1b5b3f0575fb7f2d0b12ab66cfd2c1965d13ab7128bf412b577810d0ecb`
* Indexed: `cb716ae3622ff48612b2a5b6d5ecdf1ba1d5f6352227c86ce60d1ba655d03b31`

Host: Linux x86-64, Intel Xeon Platinum 8573C, Python 3.13.5, 16 GiB memory
limit, CPU quota 4 cores (affinity exposed 5). One process at a time with
Rayon/OpenBLAS/OMP/MKL threads set to 1 and `PYTHONHASHSEED=0`. The coordinator
reserved a quiet window, but this remained a shared host; no claim of
exclusive physical CPUs is made. Five fresh-process pairs alternated order:
base/head, head/base, base/head, head/base, base/head. No new simulation ran.

The retained input was the existing procedural 48-region/10-civ seed 42
identity run, 150 turns. Its needs table has 9,742 rows over 16 sampled turns;
the bundle is 7,911,180 bytes. It predates this reader change and is accepted
with `legacy_batch=True` solely for re-scoring, not newly qualified as a
scientific gate.

Retained input SHA-256 values (the resource ledger is not a validator input):

| File | SHA-256 |
| --- | --- |
| `chronicle_bundle.json` | `83f66064d6f76e164fd6e734dbe99710fae46c02bc3bf6a3be8cdec702a6acc9` |
| `validation_needs.arrow` | `953e9dc69f67011662f6770f812fd9c54b1dfdbf34ba0baf221f0dc0f1e84a7f` |
| `validation_relationships.arrow` | `2d42bb9bb1001e7d9d780d9c58cb02512ec7bc061939308b6c339b39dc9bbe2e` |
| `validation_memory_signatures.arrow` | `183293e1b04716d1db997239a8af9bf60a42f50ab0dbbc8ddbb87360b5d67bd4` |
| `agent_events.arrow` | `07cb341f5bbf8406e0a2b9315f87223695612cfdd6243de2d3635e5294314535` |
| `validation_summary.json` | `fac9948c06b6b68615db1e13b15dd26d0ee9a5a70b22eb8b95fc097fbd20696a` |
| `validation_community_summary.json` | `a73e6a588e533b6d89c98bde6876ae5c22e8fad15840015ab51918a7fb7a8ed5` |

The probe measures Arrow read/compaction/index construction separately from
available-turn discovery plus selection of every sampled turn. Output hashes
are computed outside the filtering timers. Synthetic tables have three
columns (`turn`, `agent_id`, `value`); they exercise filtering volume and turn
count, not realistic graph detection or needs matching.

| Boundary (wall seconds) | Base median | Indexed median | Median paired speedup |
| --- | ---: | ---: | ---: |
| Retained needs: Arrow load + all-turn selection | 0.1154 | 0.0968 | 1.102x |
| Synthetic dense: 1,000,000 rows, 100 turns; load + selection | 5.5570 | 0.3531 | 14.993x |
| Synthetic many-turn: 200,000 rows, 400 turns; load + selection | 4.4758 | 0.0648 | 67.581x |
| Entire retained `run_oracles(['all'])` + report JSON | 2.0623 | 1.9426 | 1.018x |

The complete-validation paired ratios ranged from **0.627x to 1.215x**;
one indexed run took 3.8884 seconds. The medians therefore do not establish
an end-to-end speedup. Bundle loading, oracle work, imports performed by the
oracles and host variation remain relevant. Interpreter startup and importing
`validation_io` itself are outside that timer. JSON report encoding is inside.

All five raw complete-validation pairs (base/indexed wall seconds):
`1.813262/2.205558`, `2.062316/1.838657`, `2.323075/1.911400`,
`1.978170/1.942609`, `2.438236/3.888448`.

Process peak RSS was a median 189,728 KiB before and 189,760 KiB after. This
is the probe process's high-water mark across synthetic loading and retained
validation, not an isolated measurement of validator memory. The monotonic
index stores ranges proportional to sampled turns; the shuffled fallback
needs an additional eight bytes per row for index payload, plus containers.

A counted 2,000-row/100-turn fixture observed **202,000 turn-row visits**
before (turn discovery plus 100 predicate scans), versus **2,000** after
(one index build). Selected values still must be copied into each snapshot;
this does not eliminate their work or memory.

## Identity and checks

Every complete report was byte-identical across both sources and all five
pairs: 19,219 bytes, SHA-256
`a234081e20c0c686c3aecadd16af31469073304827c7690d7eb4a7670629da6e`.
All retained/synthetic filtered-output digests also matched. The retained
report has unchanged PASS/FAIL/PARTIAL/SKIP results and no ERROR; unchanged
failure results are not presented as a newly passing gate.

The focused selection passed 276 tests: validation, turn indexing, all
existing oracle methods, ablation/spec communities, comparator and manifest
coverage. The new file passed 22 tests under the offline guard (0.13 s).
Tests cover monotonic/shuffled/missing/duplicate turns, row/edge/memory order,
unaligned sampled domains, changed-file reloads, mutable caller dictionaries,
schema keys, cross-oracle reuse, packed values/nulls/signed zero, canonical
readers and copy/pickle ownership. No native rebuild or 200-seed simulation
gate is needed to re-score unchanged files; larger retained validation
cohorts are still needed to measure end-to-end gains.

## Reproduction

The exact probe is [`benchmark_validation_turn_index.py`](../../scripts/benchmark_validation_turn_index.py).
Retain both source worktrees and the unchanged real input directory. Generate
synthetic files outside the repository:

```python
import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc
from pathlib import Path

out = Path('/tmp/validation-index-bench')
out.mkdir(exist_ok=True)
for name, rows, turns in [('dense', 1_000_000, 100), ('manyturns', 200_000, 400)]:
    table = pa.table({
        'turn': np.repeat(np.arange(turns, dtype=np.int64) * 10, rows // turns),
        'agent_id': np.tile(np.arange(rows // turns, dtype=np.int64), turns),
        'value': np.arange(rows, dtype=np.float64) / 17,
    })
    with ipc.new_file(out / f'{name}.arrow', table.schema) as writer:
        writer.write_table(table)
```

Run the following once for each source in the alternating order above,
changing `--out` for each arm/pair. `--inputs` names the same retained seed
directory for every arm. Source and input paths do not affect oracle math;
report paths must match when comparing raw report digests.

```sh
RAYON_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONHASHSEED=0 \
  python scripts/benchmark_validation_turn_index.py \
  --source /path/to/before-or-indexed-worktree \
  --inputs /path/to/retained/procedural-seed \
  --synthetic /tmp/validation-index-bench/dense.arrow /tmp/validation-index-bench/manyturns.arrow \
  --out /tmp/validation-index-bench/arm-pair.json
```

Probe SHA-256: `65d2c06b5a761c2ab93a52dd8a62655c22dec4f53a2f5cccef313e980773665c`.
Synthetic file SHA-256 values:
`dense.arrow` = `c6bd6fc4c7ecbd75a8009a40a2778159ce6ba8509bef97c2763d845a076ed8d5`;
`manyturns.arrow` = `b397c1a7cf1944c07019aca0f6b6f3123bf4fd3276a53adde3b80e38004b86a9`.
