# Completed export-study reinspection — 2026-10-29

Status: both independent read-only audits completed successfully at frozen
reader `2b7a443e29e09051525d26f4e1c5b7e4cb75e7f1`. Each study passed all nine
original comparisons: **399 file pairs, zero differences**. This changes no
simulation source, output rule, native build or completed producer evidence.
The branch is `lead/completed-export-readers-draft-20261029`, separate from main.
This completed readout is a later documentation-only change; the preregistered
source and limits remain recoverable at the reader commit.

## Closed studies

| Study | Producer run / job | Producer control | Frozen baseline → candidate |
| --- | --- | --- | --- |
| Arc | 40793636869 / 123184654671 | `9e800f812dc884d70e16f49103e1542f6aface91` | `d0281e5f57c508f27cea1676f36e0e6ed1225c9d` → `249a4e1879cf5fbbb070de11f478f19825f51419` |
| Recovered | 40796958774 / 123195635121 | `8bbc8f00864c771ec3ad167bf7baf6510c6b0f79` | `2f9d618b70f3304c02dcaeef12996b4a99e074c0` → `c76efe8552b4c6c288ebb1f813e2c0a58e5957b1` |

| Study | Official artifact | ZIP bytes | ZIP SHA-256 |
| --- | ---: | ---: | --- |
| Arc | 12863585862 | 54791602 | `bfaa8fc0b7ae44fd9074c6ebad446706c8d0d95e62afdb09a1c8fb5654542d4c` |
| Recovered | 12864342689 | 54786758 | `36b26c277b961480f94389f36af7d3c668ad44367937922e55d399f06fa931e1` |

The registry also fixes original inventory, wheel, native and helper SHA-256
pins. Those identities were observed in the pinned archive or original official
producer log before verification. The reader checks exact official run/job/
artifact identity, source, attempt, success, sizes, digests and expiry; a producer
PASS alone cannot qualify the audit. Original metadata is retained separately.

Artifact download uses the connected GitHub artifact tool's official OpenAI
file reference, fetched through the inherited proxy with a byte/digest bound.
Signed download URLs are suppressed. The rejected direct GitHub storage CLI
route is not retried or bypassed. The inspection CLI itself performs no network
request and accepts only the two registered study names.

## Resource adaptation and unchanged comparison

The arc ZIP has 976 files expanding to 278,356,162 bytes; its largest complete
baseline/candidate case pair is 88,797,834 bytes. Full extraction can exceed
available headroom above the unchanged 3 GiB floor. The approved adaptation:

1. Validate the entire safe ZIP member set, then stream every file through
   SHA-256/CRC and require the exact complete original inventory.
2. Validate original before/after source snapshots against complete frozen
   Git trees: every tracked blob, byte count, SHA-256 and executable mode.
   Source modes are inferred as 0644/0755 from Git; no reconstructed-worktree
   cleanliness claim is made. Recompute each actual package digest too.
3. Materialize only exact tracked package Python files and the two frozen
   comparison scripts into a fresh read-only derived source view. Validate it
   before importing any frozen code and recheck afterward. The original
   helper is also the exact frozen Git blob.
4. Verify all original audits/probes, fixed matrix/caps, wheel-to-native-copy
   bytes, schemas and package/source identities. Check both complete nine-case
   sets independently of the comparator.
5. Copy one complete two-arm case into marked derived scratch, validate every
   copied byte, apply the original case contract and invoke the untouched
   candidate `turn_speed_identity.py compare` CLI. Retain its actual per-case
   outcome and count. Both roots contain exactly that named case directory.
6. Rehash copied files and source, then retire only that explicitly marked
   derived scratch. Original ZIP/raw evidence is never removed or rewritten.
   Recheck the complete frozen source snapshots and original ZIP afterward.

The comparator's loop has independent case calls and additive totals, so these
nine registered nonempty case invocations preserve its actual decisions. The
reader separately verifies all nine cases in both arms and validates the
original aggregate comparison log. It does not invoke `run`, create worlds or
pools, install an extension, or rerun the producer tests.

The existing rule is unchanged: `.log` and `run_manifest.json` are excluded by
the frozen comparator. Bundle decoding uses the frozen JSON codec, and only
`metadata.generated_at` may normalize. Each raw bundle must have exactly that
single timestamp key and exactly one original-regex match. The strict raw
bundle comparison also executes. There is no faith-ID projection, new field
omission, threshold change or rebaseline.

Arrow payloads are hashed and compared as raw bytes. This audit makes no Arrow
schema/decoded-value claim and no exact-resume, native checkpoint/RNG state,
feature-efficacy or performance claim.

## Fixed reader bounds and reuse

Before each derived copy, free disk must be at least **3 GiB + the complete
next copy's declared expansion + 16 MiB reserve**. There are at most 2,048 ZIP
entries, 32 MiB per member/JSON, 512 MiB total expansion and a **600-second qualification deadline**; each
comparator has at most 180 seconds within that shared deadline. Git commands
have separate 60-second bounds. The deadline prevents a late positive result;
it does not interrupt every streaming/Git phase. These audit invocations also
use an outer 610-second process-group timeout with a five-second kill grace,
retaining any partial failure without claiming qualification.
Directory records in the outer artifact are refused; safe wheel directory
records are allowed. Path, alias, encryption, file-type, count and content
ambiguities fail closed. Native code is never imported; the reader environment
must actually lack the native package. One CPU and the registered one-thread
caps apply to inspection/comparison.

The immutable completed reader is reused from
`default_output_identity_reader.py`, SHA-256
`2bacde640402ce64ac52e284f3eb63d3462e1b00ec299ae8a21e1b6f065c649c`.
A fresh private instance receives only the closed study identity pins. Its code
and normalization stay unchanged; result/probe/audit/JSON/path/comparison
validators are reused. Git-object verification is a reusable bounded module;
it avoids allocating three full source checkouts.

Source and limits are committed cleanly before the CLI can issue a result.
Reader/backend/core hashes, source Git SHA, official metadata hash, actual
reader environment, original runtime identity and every comparison command
are recorded separately. A positive result requires all nine comparisons and
all final identity checks. Any failure retains a negative stage/error result
and partial evidence; it is not relabeled as producer failure or success.

## Verification commands

```sh
python -m unittest discover -s tests -p test_completed_export_study_reader.py -v
python -m unittest discover -s tests -p test_export_study_git.py -v
timeout --kill-after=5s 610s python scripts/completed_export_study_reader.py \
  --study arc --archive ORIGINAL.zip --metadata OFFICIAL_METADATA.json \
  --git-repo EXISTING_OBJECT_REPOSITORY --output FRESH_EXTERNAL_DIRECTORY
```

The implementation's 18 pure contracts pass on Python 3.13.5. The unchanged
offline guard also passes them: 18 parent cases and 44 successful subtests,
with no loaded/attempted native package, runtime-factory calls or blocked IO. They cover
complete-set/hash/type failures, ZIP aliases/symlinks/directory records,
metadata numeric aliases, source-object corruption/modes, exclusive read-only
views, separate nine-case admission, nonempty exact comparison outcomes and
the full disk reserve formula. No study comparison, world, native pool or
Arrow decoding was run by those tests. Independent source review precedes the
real artifact inspection.


## Completed independent results

| Study | Stream-verified payload | Expansion bytes | Actual comparison | Reader result SHA-256 |
| --- | ---: | ---: | --- | --- |
| Arc | 976 files | 278,356,162 | 9 cases; 399 file pairs; 0 differences | `6a80ea16f8933ff0a76193a41aac723169d0dda9fb4458fa8aefb257724cb365` |
| Recovered | 976 files | 278,201,185 | 9 cases; 399 file pairs; 0 differences | `0ad84e3e4130446b284423fff59032af6cb01d22b9b26b5f519fb644d240b21d` |

Every actual case count matches both the fixed case admission and retained
original aggregate comparison log:

| Case | File pairs, each study | Differences, each study |
| --- | ---: | ---: |
| `off_s42` | 9 | 0 |
| `off_s7` | 9 | 0 |
| `hybrid_s42` | 111 | 0 |
| `hybrid_s7` | 111 | 0 |
| `hybrid_s1234` | 10 | 0 |
| `proc48_hybrid_s42` | 92 | 0 |
| `proc48_off_s7` | 15 | 0 |
| `scaled22k_s42` | 32 | 0 |
| `scaled52k_s7` | 10 | 0 |

The scaled case names are retained historical labels. Their registered targets
are 18,800 and 43,700 respectively, not observed agent counts.

These are two source-scoped studies. Each original producer ran 18 worlds and
3,200 ticks; the independent readers ran **zero new worlds**. The audit does
not turn repeated comparisons into additional independent simulation samples.
Both retained native copies have SHA-256
`06db5e19bdda13d7a536b236d677348f5ea7cb5adad2929962f0485192f9b4d6`.
Their exact compiled wheel members match those bytes. Arc wheel SHA-256 is
`54616417b94036ec91a40b69b94ad2b608d3b66666c93dd2b20e05af176cc58f`;
recovered wheel SHA-256 is
`bc17bb2561a4d014202c1f70846b31ace97ae00a98be2247dcfc3c4965b463ca`.
The common crate tree is `a4703ef4e9a21b5dbb194d318536a46e6ca8b71c`.
The reader checked every original source snapshot, package digest, audit and
probe, all nine original case contracts, complete payload inventories and
original before/after identities, then rechecked source and ZIP bytes.

Both outer commands exited 0, within their unchanged bounds. The readers used
Python 3.13.5, a genuinely absent native package, CPU affinity `[4]` and the
registered one-thread caps. The retained candidate source views contain 178
arc and 181 recovered files. A separate final receipt reconciles all existing
outcomes and confirms files remain mode 0444, directories 0555, both original
ZIP hashes unchanged, and marked per-case scratch absent. Its smallest recorded
case-admission margin beyond the full floor/copy/reserve requirement is
305,780,018 bytes for arc and 187,409,714 bytes for recovered.

The arc reader took 35.383 s and the recovered reader 31.768 s; these are audit
runtimes, with no simulation speedup implication. The common comparator Git
blobs are identical across all four simulation commits. No output fields or
comparisons were normalized beyond the original rule documented above.

Local immutable archives, official metadata, every comparison command/log and
terminal receipt are retained under
`/workspace/evidence/completed-export-studies-20261029/`. The compact
[machine-readable readout](completed-export-study-results-2026-10-29.json)
records the exact limits, sources and evidence hashes. The postflight summary
SHA-256 is `b97e02e69f6caf1fa2489a59f2782c4a9012539f0c119515f751e5d9b711dfd4`;
the 568-file, 125,044,032-byte local evidence index SHA-256 is
`0e6eaf700b946f925ab94efb709e37d12072b326f9622326118f1e63ea2dfbe8`.
The index excludes only itself. Retained official metadata reports artifact
expiry at **2026-11-28T00:32:11Z** for arc and
**2026-11-28T01:00:37Z** for recovered; this is the observed retention window,
not a promise of permanent GitHub availability.

Independent source review cleared the frozen implementation before inspection.
Independent final receipt review cleared the frozen code/source/artifact pins,
88 retained summary/input links, all case/count equations, terminal budgets and
full disk-admission inequalities. That peer did not reopen ZIPs, scan payloads,
repeat comparators/tests, import native/Arrow code or launch worlds. Its separate
receipt is `/workspace/chronicler-completed-export-review-evidence/final-review-001.json`,
SHA-256 `1e979851c885e6fbd474a5a6d917ff08ad418f39587eda2466e5a52b04103d74`.
