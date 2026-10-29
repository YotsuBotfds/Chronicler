# Full population gates — 2026-10-29

[Run 40791402289](https://github.com/YotsuBotfds/Chronicler/actions/runs/40791402289), attempt 1, completed **SUCCESS**. All four original strict gates **PASS**. Both template and procedural comparisons are strict **NO_REGRESSION**, comparable, with no unverified fields, mismatches, method drift or rebaseline. Scientific comparison and pipeline/publication qualification **PASS**.

The separate causal-required adjudication **FAILS in all four on kin roots**; the joint-needs causal component passes in all four. Original reports and decisions remain unchanged. Community specification stays informational FAIL; determinism stays SKIP (no duplicate-seed pairs).

Exact sources: **2f9d618b70f3304c02dcaeef12996b4a99e074c0 → d0281e5f57c508f27cea1676f36e0e6ed1225c9d**. Control: **27f0f3d11a1a171e1539353eb2c3a0fb896f0939**. Shared crate tree: a4703ef4e9a21b5dbb194d318536a46e6ca8b71c; native SHA-256: 06db5e19bdda13d7a536b236d677348f5ea7cb5adad2929962f0485192f9b4d6; wheel-file SHA-256: 049f91bbd03582240491e0c487d560deebb31a2ab9754d2c5bac2a7804206f64; build-manifest SHA-256: 013a57c5e59993587acd65eb33c6ff1d16984796de11dbec81df686eb33210d3. This does not qualify c76, 49b, arc249a or wealth503 outcomes.

| Cohort | Job ID | Original strict | Joint needs | Kin roots | Job s | Cohort step s | Helper s | Raw upload s |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: |
| template-baseline | 123179513015 | PASS | PASS | FAIL | 5,189 | 5,051 | 5,050.323 | 120 |
| template-candidate | 123179512938 | PASS | PASS | FAIL | 4,098 | 3,992 | 3,992.254 | 89 |
| procedural-baseline | 123179512973 | PASS | PASS | FAIL | 9,118 | 8,970 | 8,969.883 | 132 |
| procedural-candidate | 123179513201 | PASS | PASS | FAIL | 7,613 | 7,481 | 7,481.648 | 113 |

The run spans **00:02:31–02:41:00 UTC**, 9,509 s. Builder job: 312 s; builder helper: 263.401 s. Pure contracts: **107 parent cases + 36 successful subtests**, 22.18 s within a 24 s step. Final comparison job: 21 s; comparison step: 3 s; publication step: 2 s. These are distinct clock scopes. Concurrent arms ran on separate hosts, so their elapsed differences are not a speed benchmark.

Full coverage is **600 parents + 6,800 forks = 7,400 executions / 402,800 physics ticks**. Per arm: template 200×500 parents + 1,600 forks (133,600 ticks); procedural 100×300 parents, 32 regions/10 civilizations + 1,800 forks (67,800 ticks). Template fork labels are 100/200/300/400; procedural labels are 100,120,…,260. Label T loads T+1, advances 21 actual ticks through T+22 and measures 20 turns. The four schema smokes are separate: 24 executions / 1,336 ticks, excluded from full totals.

Both source pairs have equal saved oracle result values; report differences are only four provenance leaves. No universal production-output identity follows. Template kin RR is **0.9877**, two-sided CI [0.9754,1.0001], one-sided upper 0.9981; procedural RR is **0.9956**, CI [0.9862,1.0051], upper 1.0035. The registered target remains RR≤0.85 with an upper below 1. Non-member RRs are 0.9874/0.9929; no new member-specific contrast test is claimed.

All four raw publications are run/control-bound and nonexpired. The frozen retention observer recorded success at **02:40:50.883052 UTC**; current official API metadata was rechecked by **02:49:55 UTC**. These are official **archive** SHA-256 values, distinct from wheel-file/native digests.

| Artifact | ID | ZIP bytes | Archive SHA-256 | Reported expiry UTC |
| --- | ---: | ---: | --- | --- |
| template-baseline light | 12866350645 | 4,860,400 | e9d24d62030ba9e734eb1c606381136af816d2ba8cca3d7068d2a6ca43effa52 | 2026-11-28T01:32:59Z |
| template-baseline raw | 12865419980 | 891,261,255 | 1f9a2f89a0d6dbb036812a7b0867fb21da761d654c772004fb8f53a13529553f | 2026-11-28T01:33:05Z |
| template-candidate light | 12864154643 | 4,860,197 | 745443ffe29595cc96a7f1d6b58b13d5f974a2abb43954299e8227b80d95c786 | 2026-11-28T01:15:20Z |
| template-candidate raw | 12865287568 | 891,194,242 | ac1132176349bee3a82bcfffef9ee29abccf424920711ca635d07d616598e1ae | 2026-11-28T01:15:25Z |
| procedural-baseline light | 12868368429 | 1,768,638 | cda1ac31b8a7a8dc57c512089f1bb5e1b738c17da598d056ce313ab6b17629b7 | 2026-11-28T02:38:19Z |
| procedural-baseline raw | 12868314984 | 1,235,683,012 | 0bf5b9309be1cd0b72324a1bb8f27b9036fd9b1a2a8f74a143f63112ddbfa78d | 2026-11-28T02:38:22Z |
| procedural-candidate light | 12868305362 | 1,768,422 | 9c6117236e0ab51671c2ded18c1536ca27d129f8976c30dd96f21a34f5f500aa | 2026-11-28T02:13:31Z |
| procedural-candidate raw | 12867956553 | 1,235,585,452 | 1ebd660a76acf26106d9205729f56aadeb59e8c5633a044faa5a5b1c32e928a8 | 2026-11-28T02:13:35Z |
| final comparison | 12868832709 | 24,835 | 08a96322a503f33a4b068ead2e0832af6eb4f972e7de32bced87c01462fb5646 | 2026-11-28T02:40:55Z |

Four light ZIP hashes and 36 indexed files were independently checked; the final ZIP and its ten derived receipt payload hashes verify. The final comparison JSON hash is **6343e81b4332786353c4bf83ed0c50e30db84ca10c8a428112efa5da7ba61889**; independent verification receipt hash is **77ba85fec25c88325c283d31042d5645282c093669131bce9c6ef8613d73165e**. **Full cohort raw contents were not downloaded or independently rehashed.** The last baseline light ZIP was inspected in memory to preserve the disk floor. All 21 publication records, exact timestamps, build/wheel/contract pins and verification scopes are in the [JSON readout](full-population-gates-2026-10-29.json).

Original failures remain visible. Activation **40790686772 / d2331dd172bedf0b639ee401a13aaee14c0509c6** failed pure contracts (**13 failed, 92 passed, 36 successful subtests; 23.60 s**) before native build/worlds. The repair made synthetic fixtures adjudicate saved JSON wire order and added contract-result retention; production reader/gate/oracle scripts did not change. In this successful run, all four 2-seed/125-turn schema smokes completed and published, while their original subset scientific verdicts remain **FAIL, exit 2**. Smoke execution success is not scientific qualification. The older cb9/5b/native432 study retains its separate original and causal verdicts.

Original build facts are exact where recorded: **rustc 1.99.1** (58cf8f9c35b355199727627d07ae34a4e2846d67; 2026-10-13; LLVM 23.1.1), **cargo 1.99.1** (5f94df478; 2026-08-27), **maturin 1.15.0**, **uv 0.13.6**, CPython 3.13.17. Explicit command: maturin build --release --locked --manifest-path … --out …. Frozen Cargo source declares release codegen-units=1, LTO=true, opt-level=3; crate maturin configuration declares pyo3/extension-module. Workflow values are CARGO_BUILD_JOBS=1 and CARGO_INCREMENTAL=0.

Builder raw artifact **12861268992**, 5,188,363 bytes, hash **bb81630553ae81754fca8802aad88cba3bf907b618fa4d8c687cf6c00c3204eb**, was hashed in RAM; only selected version/build logs were checked against its inventory. No archive was stored or build run. **Inherited effective flags, target overrides, linker identity and full compiler/linker argv remain unknown. Version matches do not establish whole toolchain identity or authorize native baseline reuse.**
