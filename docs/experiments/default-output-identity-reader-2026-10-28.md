# Prospective reader of the completed default export artifact — 2026-10-28

Status: DRAFT; no reader execution and no active reader workflow. This fixes a
reader procedure before extracting or reinspecting the artifact. It is not a
preregistration of the already completed simulations: their positive 18-case
summary and the pins below are already known. No new worlds, simulation turns,
native simulator pools, benchmark, or revised acceptance threshold are requested.

## Inputs fixed before reader execution

| Input | Pin |
| --- | --- |
| Original run / control source | 40786065030 / db7ec48b738fa841f1b951c3ae810aa121ef1918 |
| Artifact ID / name | 12859762876 / default-output-identity-40786065030-1 |
| Artifact ZIP bytes | 54,788,314 |
| ZIP SHA-256 | 025f4c215b1a2e3a556af45dc9d099c9f14343d0ba50ba9c896d8e92be37e8ff |
| inventory.json SHA-256 | a25a2148d0259bfcc53acb74d5a29acb1e173c3e1a8f105c825c777cc99819cb |
| Baseline source | 2f9d618b70f3304c02dcaeef12996b4a99e074c0 |
| Candidate source | d0281e5f57c508f27cea1676f36e0e6ed1225c9d |
| Retained wheel SHA-256 | ef15138971a6c0597987aebb4070d47f6940ea5ab0659e552f907a30d046057a |
| Retained compiled native SHA-256 | 06db5e19bdda13d7a536b236d677348f5ea7cb5adad2929962f0485192f9b4d6 |

The original summary reports 18 completed cases, 3,200 simulated turns and
545.199251514 elapsed seconds. Elapsed time is resource accounting, not a speed
result. The reader independently checks the retained evidence; it does not
treat this prior summary as sufficient proof. The actual compared-file count
is presently unknown and will be obtained from the artifact, never assumed 399.

## Procedure

Four separate source checkouts are used: reader controls at the actual reader
workflow SHA, original controls at db7, baseline at 2f9 and candidate at d028.
A fresh external Python 3.13 environment uses the unchanged candidate uv.lock,
without installing the project or any native wheel. The original qualification
helper is hashed against the pinned freeze receipt before its module is imported.
Only its pure contract/source-inspection functions are called. The reader refuses
an environment containing chronicler_agents and verifies it was not imported.

The original artifact is downloaded once or supplied as a local ZIP. Its exact
size and SHA-256 are checked before extraction. The Actions read token is sent
only to the fixed GitHub artifact API. Automatic redirects are disabled; every
HTTPS storage redirect gets a new request without Authorization. Download hosts
are limited to GitHubusercontent and Azure Blob storage. Neither signed URLs,
tokens nor raw network exception messages are printed.

Extraction goes into a fresh external output. Bounds are 4 GiB total,
256 MiB per file, 4,096 files, 8,192 explicit or implicit entries and
512 characters per path. Traversal, absolute or noncanonical paths, drive names,
backslashes, encrypted members, special files/symlinks, duplicate/case-aliased
paths and file/directory conflicts are rejected. Only stored/deflated ZIP entries
are admitted; streamed bytes must equal their declared sizes. JSON reads are
bounded to 32 MiB and reject duplicate keys, nonfinite values and numeric overflow.

The inventory bytes must match the fixed pin. Every extracted payload file's size
and SHA-256 and the exact file set must match it, excluding precisely
inventory.json and result.json as in the original contract. The outer ZIP pin
binds those two files, including the final result receipt.

The original result must have qualified=true, all fixed source/native/wheel/
inventory identities, the original normalization label, no retained execution
error and exactly 18 unique complete (arm, case) rows. Each row's audit hash,
each audit's complete raw file map, case seed/horizon/mode/region/civ shape and
nonempty required exports are rechecked with the frozen original contracts.
All 18 raw bundles must independently satisfy the original sole
metadata.generated_at-key rule. No faith projection is permitted.

The 36 before/after probes and 18 driver provenance files must be complete and
consistent with the source, native schemas, package digests and one-CPU receipts.
The retained wheel, retained binary and sole compiled member of the wheel must
match their pins; no binary is installed or loaded. Original freeze/sources-after
records must be identical and match the tracked bytes/modes of all three frozen
source checkouts. The original helper hash and fixed nine-case matrix must agree.

Only the frozen candidate scripts/turn_speed_identity.py compare is executed.
It gets the frozen candidate source path and no token or extra CLI switches.
Its output must contain precisely the nine registered case summaries, their
actual per-case compared-file counts and an exactly reconciled aggregate with
zero differences. Original .log/run_manifest.json exclusions and sole
metadata.generated_at normalization remain unchanged. Comparison timeout is
180 seconds and retained comparison output is bounded to 2 MiB.

Finally, the full payload inventory, original ZIP and frozen tracked-source
snapshots are checked again. Any failure keeps the reader result negative.
Synthetic contract tests must pass before an actual artifact read.

## Evidence and scope

The reader emits compact JSON on stdout and retains its own reader-result.json
and compare.log. A lightweight Actions artifact also retains contract-test output.
The original artifact is not rewritten or reuploaded as new simulation evidence.
The actual payload count and compared-file counts are recorded when observed.

Passing establishes read-only reinspection of these completed default exports
under the original comparison rule. It does not establish checkpoint, native
pool-state or RNG equivalence; feature efficacy; performance gains; or coverage
of the inaccessible newer local finite-research integration.

The proposed workflow is stored only at
docs/experiments/default-output-identity-reader-workflow.yml. Moving it into
.github/workflows and activating lead/cloud-identity-reader-20261028 requires
the root lead's code review within the user's existing separate-branch
authorization. No user approval, PR, comment, main merge or world rerun is added.
