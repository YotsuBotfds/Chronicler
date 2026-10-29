# Combined decision delivery and native index reuse: first-attempt CI

The exact combined candidate `95f73a74f809d7e10f09a1241c98014864350ffb`
passed all six standard Tests jobs on attempt 1 of
[run 40821282241](https://github.com/YotsuBotfds/Chronicler/actions/runs/40821282241).
The separate branch is `lead/native-decision-delivery-python-adapter-20261029`.
No main merge, scientific study, default activation or performance promotion
is implied by this result.

The candidate combines native integration `e40108ed`, the separately preserved
Python observer source `a7f74df8`, and the exact wheel-retention patch originally
reviewed at `13628a05`. The Rust tree remains byte-identical to `e40108ed`.
The adapter exposes the existing bounded Stage 1/2 frames only after complete
normal bridge processing. Its default path creates no observer attribute,
optional import, delivery-native call or I/O. It changes no physical decision.

| Lane | Actual completed result |
| --- | --- |
| Rust | 1,118 passed; 2 ignored; 0 failed or filtered; 37 summaries |
| Python with real native extension | 8,206 passed; 6 skipped; 526 successful subtests |
| Python without native extension | 7,873 passed; 325 skipped; 526 successful subtests |
| Bounded offline | 4,103 passed; 65 skipped; all 34 chunks passed |
| Viewer | 743 tests across 69 files; lint and production build passed |
| Python-native barrier | Both required native execution and Rust jobs succeeded |

The native JUnit contains all seven new compiled bridge cases, executed and
passed. Six cases cover both bridge entry points in hybrid, shadow and
demographics-only modes, comparing normal results, Python world writeback,
native snapshots and future checkpoint bytes with observation off/on. Both
hybrid cases require actual applied-move links. The seventh checks Python
pickle and native restore transience, including the recorded native schema
fingerprint. The no-Rust lane skips exactly these seven cases; those skips
are not used as their native qualification. The five Stage 1 and seven Stage 2
direct native API cases are also present in the native JUnit.

The new offline chunks pass all 80 fake/Arrow adapter contracts and 27
build-provenance contracts. The longest of all 34 chunks took 38.178 seconds
against the unchanged 110-second ceiling. All guards passed, loaded no native
modules and recorded no blocked I/O. Existing Python oracle tests called the
replacement ecology/politics factories 168 times each; these are guarded
Python replacements, not native constructors. The two new chunks called
neither factory. All 320 recorded source hashes match immutable Git blobs at
the candidate commit. These CI timings do not establish a speedup.

The newly retained wheel is linked through the completed producer, official
artifact metadata, manifest and separately retained installed-extension
receipt. Verification used stdlib ZIP/JSON/XML/hash reads only, without
installing or importing any native binary locally.

| Identity | Exact retained fact |
| --- | --- |
| [Wheel artifact](https://github.com/YotsuBotfds/Chronicler/actions/runs/40821282241/artifacts/12875201593) | ID `12875201593`; 3,850,596-byte ZIP; SHA-256 `f411d352e1e537607e8eacfa6b3061f05cb45f3dc9149a347a2a60b4c6719c90` |
| Wheel member | `chronicler_agents-0.1.0-cp313-cp313-manylinux_2_34_x86_64.whl`; 3,915,402 bytes; SHA-256 `b0896cd9a03ae89f26a93748fd85717c1f6110d2d45e2d623fb3406c3f24d64b` |
| Actual compiled member | 13,695,168 bytes; SHA-256 `3ee06a53b3c16dcba01bc53c8fe1dd97e530754a61d65fe2c1396b158b48e6d0` |
| Producer runtime | Python 3.13.17; real compiled AgentSimulator, EcologySimulator and PoliticsSimulator |

The actual compiled member was streamed and hashed from the retained wheel.
It exactly matches both the wheel manifest's installed-native digest and the
separately retained same-producer native-test preflight receipt. All five original artifact ZIPs
match GitHub's sizes/digests; all 75 outer members were read, CRC-checked and
SHA-256 indexed. Neither the wheel nor native member was extracted to disk or installed locally.
Retention is 14 days under the unchanged workflow policy.

Two local metadata-reader issues are retained separately from the successful
CI: the connector's compact job response omitted source/attempt fields, so
the first local readout refused to publish; the full official REST response
then supplied them. A derived JSON field collision initially replaced the
offline passed count with its boolean status. The original reader/result and
correction receipts are preserved; the final reader keeps integer counts and
boolean status distinct. Neither issue changed producer evidence, source or
the workflow run, and no CI rerun was requested.

The [JSON companion](combined-native-decision-delivery-ci-2026-10-29.json)
records job IDs, exact counts, all artifact/member hashes and wheel identity.
Original ZIPs, decoded job logs, official metadata, source pins and reader
history remain outside Git under
`/workspace/chronicler-recovered-evidence/decision-delivery-combined-ci-20261029`.
The closed 34-file evidence-manifest SHA-256 is
`f013f50ec5b14f17f2cd57a01b548a3028a6423de453a2c8c8f36c46c528754a`.
Independent final review reconciled all five archives, 75 outer members,
actual inner native bytes, JUnit counts and source/guard facts; its receipt is
`7298985273ac9e34c010ba667e92c5eac3d57dee4235a1a7d7b1c110420a9487`.
Lead review also freshly checked all six official job outcomes and the five
current artifact identities/source links. This is evidence reconciliation,
not runtime adoption.

This qualifies the exact combined source's CI contracts, including genuine
within-build observer off/on checks on the controlled bridge fixtures.
Complete old/new world parity, scientific before/after gates, larger-world
CPU/wall/RSS benchmarks and any downstream binary reuse each need their own
explicit qualification. Dense-index retention can extend allocation lifetime;
fewer scans do not by themselves prove lower peak RSS.
