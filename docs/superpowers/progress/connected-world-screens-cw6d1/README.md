# D1 recovery and integration evidence (2026-11-07)

This record separates recovered D1a/b implementation, frozen held source and the corrected integration candidate. D1c is a later lead-integrated opt-in contract. No defaults or qualification gates were promoted.

## Source and review

- Recovered remote D1 head: `e12ba7ec596a57811a3d188102f66a9d083abf18`; integrated X1 main in `f81a9cdb` and independently corrected/reviewed candidate `7cfe289b2268d0d5011270c22fe80de0500f3ab6`.
- CW6D1 held preregistration froze at `808726b8c886306229d3e08d76fdee9e6f580dde`, before held use, with no tracked code changes. The only dirty tracked file was the lead-reserved registry copy. Held source and evidence are preserved unchanged.
- Integrated B3 main `4cabac21f41ba6683f4fd7106bd5c11292c4978b` in `23053bde5201a267c45358adc7ef5aede52c8503`, preserving both switch orders, money purposes, manifests and historical pins. Independent B3 review applied the three literal inverse hunks and recovered parent bytes/SHA exactly; landed historical inverse fixtures were unchanged.
- Corrected relief delivery provenance in `eda3ea07399a909035ddd6b743f68c91aa7e11b6`. Independent actual-source review approved the delta: no gross-outbound evidence means no positive lower delivery bound. Raw historical estimates stay in original evidence, but the viewer and extractor distinguish them from established delivery. No food, money, needs or decisions changed.
- D1c new-file core `2e1e162622077db9dedfd82015ef7c6c536028fb` and viewer/native contracts `4956c5af8ab0d07ccb7d6576544c11706ff4a21c` were independently reviewed from actual source/spec/tests. The lead owns shared CLI/schema/money/FFI integration; native owner integrated dated one-tick input and cancellation guards. D1c execution below uses actual lead source, not the standalone unmounted branch.

## Evaluations

[CW6D1 held evaluation](held/report.md) retains all 60 runs, non-activation, missing measures and adverse outcomes. Relief activated in zero template and only two procedural worlds; the preregistered minimum suppresses its primary summaries. Guild claims activated in six procedural worlds, with a negative mean civic-purse difference. Neither supports default promotion. Historical lower delivery estimates were invalidated after independent gross-export review; no primary uses them.

[Declared-scale profile](profile/report.md) retains 14 paired runs, real output/sidecar/checkpoint bytes, CPU/RSS and checkpoint IO timings. All 14 returned zero; no proposed threshold was exceeded. Scale targets and constructed rescaling are disclosed rather than inferred from directory names.

## Verification

Copied console text logs normalize trailing whitespace; original per-world metric/source files remain byte-for-byte unchanged.

D1a/b used a dedicated read-only native environment, extension SHA256 `f2fb24f13c386c3965e485330499b9aa435f61a43e8fc02023f950fbf9664256`, with `PYTHONPATH` verified to each intended checkout. Rust is unchanged from preceding B3 main. [Identity check](checks/integrated-native-identity.txt) records interpreter, source and compiled artifact.

- Integrated focused Python 441 and catalog 125 passed; viewer 11 passed; lint/production build passed. After the observation correction, Python 30 and focused viewer 6 passed.
- Real native integrated six passed, including active relief purchase/fund and guild holding-fund exact checkpoints; corrected relief native three passed again. Tests use real transfers, native agents and exact restored output, not a stand-in bridge.
- The lead's feature-off run at reviewed `7cfe289b` matched both original `8abc1acb` and preceding integrated main: nine cases, 399 file comparisons, zero differences for each. Final reviewed-head CI and subsequent main CI remain the lead's merge gates; this evidence record does not claim an unobserved CI result.
- [Full offline final integrated lane](checks/offline-integrated-receipt.json): PASS, 73 chunks in 302.0 seconds. The slowest chunk was 31.9 seconds against the unchanged 110-second limit.

Two preliminary offline attempts on frozen source are retained as failures rather than relabeled: the lead's copied registry was first noncanonical, then its newly added cohort entries conflicted with old source's historical registry projections. Neither timed out; final integrated source and its own tracked registry supersede that mixed-state check. Historical expected hashes were not changed to bless a mismatch.

## Browser journeys

Real production Chromium journeys upload natural saved worlds, seek historical snapshots using the timeline, and compare actual payment/delivery/claim values against an independent Python bundle decoder at desktop 1440×900 and phone 390×844. Final fixed relief journey 24 checks and leagues 14 checks passed, including note bounds, no document overflow and no JavaScript errors. [Relief receipt](browser/qa-relief-fixed/report.json) and [league receipt](browser/qa-leagues-fixed/report.json) retain raw bundle/build SHA values and PNGs.

The initial document-overflow-only journey missed a phone clipping bug: wide tables expanded an implicit grid track and clipped explanatory notes. [Preserved stronger-check failure](browser/qa-relief-bounds-unfixed/report.json) and its phone PNG remain. Five table wrappers fixed it; independent visual inspection confirmed wrapped notes and separately pannable tables. The earlier limited pass is not presented as the final mobile gate.

Recreate the natural inputs with a verified native interpreter and dummy narration:

```sh
PYTHONPATH=src /path/to/native/python -c 'from chronicler.main import main; main()' --seed 42 --turns 100 --agents hybrid --simulate-only --food-allocation --household-retail --reform-services --output output/relief/chronicle.md --state output/relief/state.json
PYTHONPATH=src /path/to/native/python -c 'from chronicler.main import main; main()' --seed 13 --worldgen procedural --regions 32 --civs 10 --turns 125 --agents hybrid --simulate-only --food-allocation --household-retail --guild-leagues --output output/leagues/chronicle.md --state output/leagues/state.json
```

The production journey runner is `viewer/scripts/qa-connected-world.mjs` from the lead's history integration; its required runtime is Playwright plus Chromium (`CHROMIUM_EXECUTABLE=/usr/bin/chromium` was used here). Example:

```sh
PYTHONPATH=src CHROMIUM_EXECUTABLE=/usr/bin/chromium node viewer/scripts/qa-connected-world.mjs --build viewer/dist --bundle output/relief/chronicle_bundle.json --out output/relief-browser --python /path/to/native/python --journey relief
```

## D1c execution and limits

[Native two-test receipt](checks/branches-native-root.log) passed on lead source `c3fe2b6c` with final reviewed extension SHA256 `59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617` (source aggregate `38b21020673a028ce6bcd76e19fb3e0c01eed5893b89f1ce6ff6eda6cf8925a2`). One test constructs only initial home/foreign membership, then uses actual named 10-milli debits and exact checkpoint restoration with permission due next tick; the second verifies record-only native world/history identity. This is mechanism evidence, not a natural efficacy screen.

Initial external-worktree test collection silently prepended that worktree's `src` using pytest configuration and failed on unrecognized flags. [That failure](checks/branches-native.log) remains; explicitly setting `-o pythonpath=/workspace/Chronicler/src` selected the verified integrated source and both tests passed. Verifying a shell import alone does not verify pytest's post-configuration import path.

[Six natural development runs](branches-development/metrics.json) completed on template 23/procedural 13 over 80 turns, all three modes, no constructed memberships. Funded template branches recorded 63 funded rows and 2.680 units of real dues; procedural branches 24 rows/0.750 units. Cost-only collected 0.180/0.360 units; record-only collected zero. Membership and payment populations diverge after treatment, so totals do not isolate an equal-enrollment causal effect. These are previously used development worlds, not fresh held seeds. Full 200-seed/procedural qualification remain restricted.

D1c bounds identities at 256 lifetime branches, 32 payers per branch and 512 per turn. Local named adult members fund a host's actual meeting permission; only dated T−1 branch rows can affect next-tick ordinary native recruitment/lapse. Current public hostility and quarantine can deny permission. There is no transported home-news mechanism or extra grievance/influence bonus. A later independently reviewed correction `c0e63bf9` excludes roster members deployed away from native residence using current public army attachment; same-residence off-duty members can participate. It changes no residence or native membership authority. Guild-city organization stays in D1b; other movement creeds retain existing rules. Record-only observes without payments/native effect; cost-only pays without permission.
