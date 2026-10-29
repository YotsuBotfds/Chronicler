# Completed export-study reinspection — 2026-10-29

Status: preregistered read-only audit; independent verification results remain
unissued at this source freeze. This changes no simulation source, output rule,
native build or completed producer evidence. The branch is
`lead/completed-export-readers-draft-20261029`, separate from main.

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
