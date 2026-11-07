# Final program evidence: independent review

Reviewer: B3 integration owner, independently of the evidence author. Result:
**APPROVE** the evidence and its stated interpretation at profile commit
`9d0a9780c18a10c9901dbcd36a096198435858d5`, identity commit
`bbf456a81c091fd579c260f925039a2db3e2b168` and the metadata-only digest
clarification `0f28c598f221371273054f6313bf8a3d5679d6a8`.

This is an evidence review, supplementing the separate final integrated source
review. It does not substitute for the final enabled resume/held/browser/offline
gates, reviewed-head Tests, or main CI. Those gates remain lead-owned.

## Actual inputs and checks

Read the original plan of record and amendment, V5/V11 verification playbook,
the two final reports, the actual profiler and identity comparator, all fourteen
plans/profiles, parent process receipts, output hashes, native build receipt,
import logs and source receipts. Recomputed the measurements from their operands
and inspected the actual retained outputs. No simulation or native test/build
was rerun during this review.

The accompanying JSON retains the independent calculations and byte-check
results. Raw outputs were still available at the documented external paths at
review time; their persistence after container reclamation is not promised.

## Declared-scale profile

All fourteen parent exits are zero. All plans and profiles use frozen runtime
`eaa4a5d3e1cb5c958b5e32719601c28986c9f6ac` and the same 344-input digest
`faa94c0cad6d097d3b6f53230563f23efa18aa2efad9c5fe494e7da368623d5d`.
Recomputing that digest from the retained runtime agrees. The retained runner
hash is `1c21d7db60cfe9d9a3d60f4ed06fe2ff0117762aed51cdd26dee71b7d7d0d410`,
matching every plan/profile. The release artifact is
`59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`,
matching the independently reviewed build receipt and actual artifact bytes.
The Rust/build input fingerprint remains
`38b21020673a028ce6bcd76e19fb3e0c01eed5893b89f1ce6ff6eda6cf8925a2`.

Independently checked every declared turn/count row, all 52 checkpoint turns,
sizes and source/native identity headers; all seven FULL extractor problem
lists are empty. Verified all 84 Arrow-file hashes, all 80 retained
bundle/state/checkpoint hashes, and all fourteen physical file maps and total
bytes recorded after child exit. This avoids treating an unflushed child log
as a final directory-size measurement. The profiler actually calls the exact
checkpoint reader, rejects mismatches and checks restored turns; this is not a
claim of future-trajectory equality from these reads alone.

Every reported pair ratio agrees with independent recomputation. CPU ratios
range from 1.8111 to 6.9021; bundle ratios from 2.1261 to 3.9446. Maximum run and
process peak RSS are both 1,941.707 MiB. Maximum measured checkpoint write/read
times are 3.3476/4.2155 seconds. All seven pairs cross the proposed CPU review
threshold and double bundles; procedural 31 doubles a matched checkpoint, and
procedural 19/31/48 exceed the additional-500-MiB RSS threshold. The report
preserves these adverse outcomes and the lead's explicit opt-in experimental
cost acceptance. It makes no optimization, throughput or qualification claim.

Actual initial counts are equal within every pair. The historical `scaled22k`
case initializes 18,801 and peaks at 22,952 OFF / 24,571 FULL; its 6.90× CPU
ratio is retained. Historical `scaled52k` initializes 43,700 and peaks at
49,507 OFF / 53,138 FULL. It is not an initial-52,000 experiment. Under the
lead's explicit conditional instruction, FULL reaching 52,000 means the extra
initial-52,000 pair was not required. Historical filenames do not set scale.

OFF is the documented productive-recovery/all-region-enrollment cost control,
not the no-switch default. FULL includes physical, decision and record effects;
population and activity differ. Single shared-host pairs cannot isolate their
individual costs or establish performance qualification. The four screen-world
pairs ran 200 turns, procedural 48 ran 150, and stress worlds ran 30/20. No held
or restricted qualification cohort was used by this profiler.

## Final feature-off identity

Independently compared all tracked source bytes to Git: original 247 files,
preceding 270 files and candidate 287 files, with no mismatches. Recomputed all
three reported source digests using Git path order and
`path UTF8 + NUL + bytes + NUL`. The metadata clarification states that framing
correctly. Rehashed the actual imported extensions: rebuilt original
`8926c45b87f80cea732439b0d0513debb3ea314fbc56938648cec5dd6bfc951e`,
preceding `f2fb24f13c386c3965e485330499b9aa435f61a43e8fc02023f950fbf9664256`
and final `59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`.

Verified that preceding main `f76436ae37c735b2b856caf98033122798ac88d2`
and reviewed head `11467a46b957a364b3d4d4ba2ba1a4326adcc6c3` share tree
`0c7cdfdcde7ea05dcc30c6eaa25637c03977c1ce`. The rejected mislabeled archive
is not used as evidence. Final candidate is
`830d0dc2ecc7caad12217f88e47d6ffeb21309c1`, with all nine generation exits
zero. The identity script hash and each actual import path match the receipt.

Replayed the official comparator against the already generated raw outputs,
independently obtaining **9 cases / 399 files / 0 differences** against each
of original `8abc1acb` and true preceding `11467a46`. All actual case files are
included: no ignored manifests or logs exist inside these case directories.
The comparator checks bundle decoding and raw bytes with only
`metadata.generated_at` removed; no faith projection or additional
normalization was requested. Commands and outputs are in the accompanying JSON.

The only `src/` difference between profiled `eaa4a5d3` and final `830d0dc2` is
the fifteen-line startup choice-validation guard in `livelihoods.py`; native
inputs are identical. Read the exact delta: it refuses orphaned/disabled or
conflicting saved options before mutation and leaves these valid fresh-world
profile configurations accepted. The report appropriately pins the profile to
the source actually run and the identity to its separately rerun final source.
Default identity on nine declared cases is not proof of enabled behavior or
every possible world.

## A4-W scope disposition

Read the original roadmap §5.7, A4 audit proposed slices and lead disposition
`e1669bf9bfd466fc0fff1aef983f0b52a525785a`. The plan of record adopts titled
food, A4-2 lifecycle integration and A4-3 timber/escrow; the audit separately
proposes A4-W. Cross-border owned wares is absent and explicitly described as
an unadopted proposal. Local A3 wares sales and native commons wares are not
presented as its implementation. The disposition is consistent with the
specific adopted contract and does not waive adopted A–E obligations. Extending
owned wares carriage needs a later explicit market/title contract and evidence.

There is no blocking evidence discrepancy in these reviewed commits. Material
limitations are the measured enabled cost, bounded/single-run scope, external
raw-output retention, and the separate uncompleted-at-review-time final gates;
none is silently converted into qualification or default-promotion approval.
