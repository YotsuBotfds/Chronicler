# Source, recovery and archive index

Updated 2026-11-04 after PR #69. This is the starting map for future agents;
dated reports keep their original source, platform and qualification limits.

## Current source and evidence

Use fetched `main` for new work. [PR #69](https://github.com/YotsuBotfds/Chronicler/pull/69)
merged on 2026-11-04 at `cc4f70e29166c6bf083abdcd99b0fb5acc3d6594`.
The merge tree `54904da5dc1a37f2cb67826874dd1e1ab983ab63` equals the trees of
reviewed head `16dbcc9600ac3844825c46f9599cdce4f23c262c` and premerge CI's synthetic merge
`d3958b3b04afc04a40cb8ac397e8b7bd3a2ae5fe`. Older dev/recovery/integration
branches preserve history; they are not the onboarding target.

[Main Tests run 41783128849](https://github.com/YotsuBotfds/Chronicler/actions/runs/41783128849)
tested the merge SHA on `push`, attempt 1, and completed successfully with nine
successful jobs: bounded offline Python, no-Rust Python, Rust, viewer, one native
wheel builder, two native module shards, native execution aggregate and native
gate. Some optional cache steps were skipped; no job was skipped. Premerge
[Tests 41725860477](https://github.com/YotsuBotfds/Chronicler/actions/runs/41725860477)
and [actionlint 41725860471](https://github.com/YotsuBotfds/Chronicler/actions/runs/41725860471)
are separate evidence. Inspect checks for any later source SHA independently.

For what changed and why, read the [integration ledger](integration/integration-ledger-20261103.md),
[review handoff](integration/review-handoff-20261103.md),
[release qualification](integration/release-qualification-20261103.md),
[crisis roadmap](integration/crisis-recovery-roadmap.md) and
[held results](integration/crisis-held-results-2026-11-03.md).
The [continuation ledger](CONTINUATION.md) retains older recovery history;
[development setup](DEVELOPMENT.md) supplies portable setup commands.

## Private external archives

These Drive links require the owner's authorized account/access. A link in this
public repository does not grant access. Do not change sharing, publish archive
contents, commit credentials or invent replacement URLs. If access is refused,
record the exact missing item and continue with Git source and committed reports.
The folders and selected instructions were readable through the connected account
on 2026-11-04; future agents must recheck their own access.

| Location | Contents and limits |
| --- | --- |
| [PR #69 merge evidence](https://drive.google.com/drive/folders/1lH6bMYqZXJj1o_feQHo4EJClNApun_55) | Owner-only premerge artifacts/logs, archive manifest and main-CI receipt; details below. This is not a complete archive of all final scenario/browser/local qualification data. |
| [Chronicler Archives](https://drive.google.com/drive/folders/1NfGQsBD4fvqus3qXM-8-xImPSWOX0gEm) | Older source bundles, worlds/checkpoints, evidence, manifests and restore chains. Keep all older copies and negative results. A bounded folder listing is not a complete inventory. |
| [Chronicler LLM research and setup packets](https://drive.google.com/drive/folders/1VwstWo-hr4vqgS4gz5jGp9FUa7ANEdWu) | [Mac M5 24GB](https://drive.google.com/drive/folders/1o9ype3Cxw3PAoVzSgQYY5BuMggV0I9Ed) and [Desktop RTX 4090](https://drive.google.com/drive/folders/18prLPHDqHxBZFV69-OkoJcvph0TqTcRx) packets. Each lists README, SETUP_AGENT, benchmark protocol/cases and result/config/final-report templates. These are research/setup inputs, not evidence of completed benchmarks or a qualified default narrator. |

### PR #69 merge-evidence inventory

The folder lists 13 objects: nine premerge artifact ZIPs, one ZIP containing ten
job logs from the premerge Tests/actionlint runs, and three JSON records:

- [Archive manifest](https://drive.google.com/file/d/1U_CR1Y-3GlmU8qKzEN0FzjSd4wIqmwZP/view),
  `chronicler-pr69-archive-manifest.json`: original artifact IDs, SHA-256 values,
  canonical Drive links and prior digest verification; log-ZIP and evidence hashes.
- [Premerge evidence](https://drive.google.com/file/d/14UBHAJaMKOfqfn2WCfQIbsszugJdNuad/view),
  `chronicler-pr69-premerge-evidence.json`: retained premerge check evidence.
- [Main CI receipt](https://drive.google.com/file/d/1TeyL3G_kPjHbBymVJDNDajtGonG9XxhO/view),
  `chronicler-pr69-main-ci-verified.json`: merge/head/tree identities and completed
  main run/job results. This receipt is distinct from the premerge artifact ZIPs.

The nine artifact names cover `native-shard-build`, `native-module-shard-0`,
`native-module-shard-1`, `native-module-aggregate` (run 41725860477, attempt 1),
plus `python-offline`, `python-no-rust`, `rust`, `wrapper-contract-native` and
`wrapper-contract-no-rust` (suffix `d3958b3b04afc04a40cb8ac397e8b7bd3a2ae5fe`).
The log file is `chronicler-pr69-ci-job-logs.zip`. Use exact names and hashes
from the manifest when downloading. GitHub retention may expire independently
of Drive. The archive does not itself supply a complete final-source Git bundle;
the merged source is available through Git.

### Older recovery chains

Use the original manifests and instructions for byte counts, per-member hashes,
omissions and producer identities. The links below preserve the existing chain,
including checkpoints that captured running or failed CI. A later receipt must
not rewrite a failed result into a pass.

| Checkpoint | Recovery entry and dependencies |
| --- | --- |
| Exploration closeout, code `13871eb3`, final docs `6ff45ec3` | [Closeout report](integration/closeout-correction-2026-11-02.md), [original restore instructions](https://drive.google.com/file/d/1Iak62MEAfj0M8RlpRJsPRZzP43EptgIo/view), [final restore instructions](https://drive.google.com/file/d/1CE8V8yioD1tZSq4ZpoU5snx4Di3DYl5p/view), [CLOSEOUT-RELEASE.json](https://drive.google.com/file/d/1d8X-ABpcJG-dWhNFr8VQMYLLfupNNbB5/view). Final instructions include source, matrix receipts, native checkpoint runtime and CI supplements. |
| Crisis M3 `8ad00910` | [Restore](https://drive.google.com/file/d/1mQzQQTgFhM3-NcnHV0m661CXIpi45Fl7/view), [verification index](https://drive.google.com/file/d/1nngG4dTvbmdnc51y8e2Gj6JfKg0uVqO4/view). Base evidence layer for the later crisis chain. |
| Crisis M5 `d7061f42` | [Restore](https://drive.google.com/file/d/1gsPONxyUGQwjMErFMqUrFB8EAIm2dey5/view), [verification index](https://drive.google.com/file/d/1uAPjR4vj_Ovlkl_85eEZdQk9sOeL9YV_/view). Two evidence parts; prior M3 data and omitted-member proof remain necessary. |
| M6 source `3e852333`, checkpoint `8beb6e4f` | [Restore](https://drive.google.com/file/d/1IkWe1bSHpxao7V041Jfb576wvF6VOR5Z/view), [verification index](https://drive.google.com/file/d/18dJ0vMzeLl5RkVuIZ5q3lUNWcNCa6Ps-/view). Preserves 43 refs and incremental evidence; restore M3 then M5 first. |
| M7 `16376f90` | [Restore](https://drive.google.com/file/d/1EQQqVW37aRlx-CXxkXSh5kq8roW53jF6/view), [verification index](https://drive.google.com/file/d/1cu0ir5uw2D8KGDGkGJVyzCKtgbq6N15c/view), [omission proof](https://drive.google.com/file/d/1nDEUz8u3y0DIMHgotiTqWYlFkDCu7-Ce/view), [failed CI receipt](https://drive.google.com/file/d/1b5fXjyHd1KSFp2HGOxLgRxv2OA6EDNDn/view). Follows M3/M5/8beb layers; retains the skip-audit failure. |
| M8 `0fb973cf` | [Restore](https://drive.google.com/file/d/1nB9U33JBLx0TzZQmUd_V3A9NRNuds5R5/view), [verification index](https://drive.google.com/file/d/1V1qIyOFiDQbt6i1GwleQXNAljOs5H-cx/view), [omission proof](https://drive.google.com/file/d/1lwxT7pUeOrnJ-cAaca0_cURol6DC1xpg/view). Follows all prior crisis layers. Separate [native identity](https://drive.google.com/file/d/14KZfLHAnrHU7bWJtSKU3fMq0fsDJ3vUC/view) and [final CI receipt](https://drive.google.com/file/d/191zX6APtyYIDT8Rfnv4DwPUGNxDWF4HK/view) supplement the running-CI capture. |
| Post-M8 `03062059` | [Supplement instructions](https://drive.google.com/file/d/1XXFKebqkgqK300Jjk36Tcj5kVYjKgUp1/view), [source increment](https://drive.google.com/file/d/1BpAb-sIFIsfSgZ724OP3PQBPJLCZe7le/view), [evidence supplement](https://drive.google.com/file/d/1mjDnnongBk6TGAkiGyzaChkBTpBBQyw7/view). Requires the M8 source commit `0fb973cf169ce0ee34dda7a437cfe7fde0c8b85b` plus prior evidence layers. The instructions retain their original local-capture wording; the three Drive objects are now discoverable. This is an older snapshot, not the final PR #69 evidence set. |

The closeout's three split evidence files are the authoritative historical copy:
`Chronicler-eddad48c-evidence-4217e8cc.part001`, `.part002`, `.part003`, in that
order. Their concatenation is 87,816,343 bytes, SHA-256
`4217e8cc7c87fe06f38f4df0b01e78101bfe474cc9e50f501efeca9d093e9576`.
The redundant monolithic upload had size/access verification only. Follow the
final restore instructions for the correction, matrix and checkpoint-runtime
supplements; do not substitute the main archive for them.

## Safe restoration on another machine

For current development, clone main into a new directory and make a personal
branch. Inspect status/worktrees before changing an existing checkout:

```sh
git clone --branch main https://github.com/YotsuBotfds/Chronicler.git Chronicler-fresh
cd Chronicler-fresh
git status --short --branch
git switch -c work/my-followup
```

For historical recovery, download through authorized Drive access into a new
private staging directory outside the active repository. Read that checkpoint's
restore instructions and verification index first. Verify each object's size and
SHA-256 before use (`sha256sum`, macOS `shasum -a 256`, or PowerShell
`Get-FileHash -Algorithm SHA256`). Verify split parts individually and the
reassembled bytes. A checksum printed without comparing the expected value is
not verification.

For a full Git bundle, initialize a new empty repository, run `git bundle verify`
there, list its heads, then fetch only the required ref and check out its exact
recorded SHA. Run `git fsck --full`, confirm HEAD/tree identity and clean status.
For an incremental bundle, restore its stated base first in isolation; verify
the increment against that repository before fetching it. Missing prerequisites
must stop the restore. The post-M8 increment cannot initialize an empty repo.
Keep recovered WIP refs separate from qualified source.

List archive members before extraction. Reject absolute/traversal paths and
unexpected links or special files; extract only to a fresh private destination.
Restore crisis evidence in order: **M3 → M5 → 8beb → 16376 → 0fb → post-M8**,
when recovering the full chain. Keep each layer's manifest separately before the
next layer replaces same-path metadata. Check regular-file sizes/hashes and
omitted-member proofs against the actual prior layers. Never extract over an
active checkout or original worlds. Restore closeout supplements in the separate
order specified by its final instructions.

Source restoration does not provision an environment. Use the recorded source,
native wheel/binary, interpreter/ABI, dependency and thread identities for exact
checkpoint continuation. Rebuilt binaries can differ even at identical source.
Refuse mismatches; do not silently substitute the current wheel. Viewing an old
bundle and resuming an exact checkpoint are different operations.

## Scope, unavailable evidence and remaining gates

All nine main jobs passed; bounded native/no-Rust/offline, Rust and viewer checks
qualify their declared inputs. The twelve held trajectories use three seeds and
two families with mixed outcomes. They do **not** complete the unfinished
200-seed scientific gate, establish a general policy ranking or qualify household
welfare/actual meals. Resource-backed service pause restores legacy scholarship,
not zero learning. The one-client live contract and six-comparison session-memory
gallery remain; reload clears the gallery. Twelve moderate development-tool npm
findings were documented premerge, with zero production audit findings at that
time. Reusable cloud-environment publication remains deferred.

Paths such as `/workspace/scratch/`, `/workspace/shared/chronicler-crisis`,
`/workspace/shared/chronicler-multiwave-evidence` and machine-specific home paths
in dated reports identify historical sessions. They are not portable links or
proof the bytes exist in a new task. PR #69's Drive archive covers the listed CI
objects; it does not establish off-machine recovery of every final local native
qualification log, browser receipt, scenario output or checkpoint. If an item is
absent from the accessible archive manifest, mark it unavailable until recovered.
The older thread's inaccessible uncommitted work is not claimed recovered.
The Living Atlas Library reference/access gap remains recorded in
[the continuation history](CONTINUATION.md#product-gaps-to-carry-forward).

On 2026-11-04 this documentation update checked Git merge/tree identity, main-CI
run/job results, folder listings, and selected restoration text/record metadata.
It did not freshly download and hash every historical binary archive or repeat
the historical restore campaigns. Prior independent-download/member-verification
claims belong to the linked dated receipts. No sharing settings were changed.
