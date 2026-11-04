# Consolidated review integration: exact-source CI qualification

**All six jobs passed** in [Tests run
40835337456](https://github.com/YotsuBotfds/Chronicler/actions/runs/40835337456), attempt 1, at source
`1205b6e48215c3e5c44d2bcb6376ca65827a7aab` on `lead/review-integration-20261029`. One authorized dispatch
was requested, with no retry, cancellation or local source checkout move. The source was already pushed
and independently reviewed by the lead.

This is a curated projection of the immutable 37-file pack, not the original evidence. It qualifies exact
source `1205b6e4`, not a later documentation head; the [JSON
companion](review-integration-ci-2026-10-29.json) supplies exact job, artifact, expiry and hash pins.

The runtime, tests, scripts, Viewer and Rust trees are byte-identical to qualified `9d5cb7e4`. All 1,049
non-doc Git mode/object/path entries match reviewed CI component `77e83c43`. The new executable CI
changes are two early guarded wrapper checks and their two separate three-file artifacts. Existing full
selections and the five original artifact layouts remain in place.

| Full Python lane | Parent passes | Skips | Successful subtests |
| --- | ---: | ---: | ---: |
| Native | 8,323 | 6 | 526 |
| No Rust | 7,990 | 325 | 526 |

These full-suite counts match qualified `9d5cb7e4`. Rust passed 1,118 tests with 2 ignored; Viewer passed
743 tests in 69 files plus lint and production build. Bounded offline passed 4,218 tests with 65 skipped
in all 35 chunks. Its 324 source hashes match this exact Git source; the maximum observed chunk was 38.99
seconds within the unchanged 110-second cap. The dependent native summary passed.

The early `wrapper-contract-native` and `wrapper-contract-no-rust` artifacts each contain exactly
`guard.json`, `pytest.log` and `junit.xml`. **Each independently verifies 2 passes / 0 failures / 0
skips**, the two exact original test identities, active offline guard, zero loaded/attempted native
imports, zero ecology/politics factory calls and zero blocked I/O attempts. Those four passes are
separate preflight executions and are **not added** to either full-suite count. The ordinary offline
lane's replaced oracle factories were intentionally invoked 168 times each; that is separate from these
zero-call preflights.

Official job timestamps place the native preflight at 07:25:44–07:25:46 UTC, before the build began at
07:25:47; no-Rust preflight finished at 07:25:45 before its full suite began at 07:25:46. This verifies
the intended gate order. It does not estimate a general wall-clock, CPU or RSS gain. Actual pytest clocks
were 550.31 seconds native and 345.83 seconds no-Rust; these are observations on this run.

Independent same-pack peer review is **CLEAR**, receipt SHA-256
`ef1a5e5ab07324b169988b3f4e665e8022855b214836ba3bc513af6f083e1678`.

Seven original official ZIPs were retained once, totaling 4,185,124 bytes. All match exact
source/run/nonexpiry/size/API SHA pins; every one of their 83 outer members passed bounded size, SHA and
ZIP CRC checks. Wrapper artifact IDs are `12879674969` (native) and `12880710984` (no-Rust). Native wheel
artifact `12880044713` has ZIP SHA-256
`3033dd722beb0d0c98350f5d41ef1088e511054cc8f3015baf927ecc7b2a5234`; its 3,915,399-byte wheel has SHA-256
`f827e8d4474bceb9bf176f07bfcd1481a0d9a1dc7543b0d3bef91985dc50c89e`.

Streaming the nested 13,695,168-byte native member yields SHA-256
`3ee06a53b3c16dcba01bc53c8fe1dd97e530754a61d65fe2c1396b158b48e6d0`, matching both the build manifest and
separately retained same-producer installed preflight. The latter records Python 3.13.17 and the real
AgentSimulator, EcologySimulator and PoliticsSimulator classes. No binary was extracted to disk or
imported during detached verification. Standard CI does not establish the natural study's
one-actual-CPU/thread environment.

Both genuine practice observer phase/fourteen-turn cases pass in each full lane, preserving within-build
normal state/events/allocations/debits and caller RNG. Seven compiled decision observer cases pass
natively and skip when the extension is absent. This remains within-build fixture evidence, distinct from
old/candidate whole-world parity or a causal growth/welfare result.

The strict saved-data reader, complete reconciled JSON, official metadata, completed decoded logs and
original ZIPs remain in the separate original evidence pack identified by the JSON companion. The
complete frozen pack manifest SHA-256 is
`15d2c3ee24b70200a03c7880a1878e0bd03a07324273d263e047ea5232b9cccb`. Earlier `b35ccd7d` failure evidence
and qualified `9d5cb7e4` records remain unmodified. No main merge, scientific/performance promotion,
historical-binary reuse grant or new study activation follows from this CI result.

These within-build fixtures do not establish 9d-versus-candidate export or raw/global RNG parity. No
default promotion or full scientific qualification follows. The lead reports that a separate C76→95
parity producer passed; its independent audit remains pending and is excluded here. Frozen C76 and its
natural study remain unchanged.
