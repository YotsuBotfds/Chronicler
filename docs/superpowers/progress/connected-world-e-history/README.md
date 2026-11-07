# Connected World E: linked histories and exact provenance

This evidence covers development validation of saved observations, not qualification or a default-promotion decision. Source code remains opt-in; the viewer reads recorded bundles without simulating or making paid narration calls.

## Development reader compatibility

The production TypeScript readers validated all **20 snapshots in 10 CW6 schema runs**, across FULL, A6R, D3R, D4C and SUP on template 5 and procedural 19. No package was malformed after the signed A6 correction. Receipts preserve exact raw-bundle SHA256, bundled-reader SHA256 and every package/snapshot status. These short runs test schemas, not active lifecycle coverage or policy efficacy.

The first FULL procedural-19 receipt rejected A6 at snapshot 2. Actual D3 evacuation supplied +0.20 destination scores; the old viewer accepted only negative inputs. The failing receipt is retained. The corrected reader accepts the actual combined ±0.3 native contract, and bounds tests cover positive evacuation/return inputs as well as excessive or nonfinite values. The corrected source is `230e484f` in the history lane (the integrated cherry-pick has a different commit id).

Reproduce one receipt using an existing raw bundle:

```sh
PYTHONPATH=src node viewer/scripts/validate-connected-records.mjs \
  --bundle RAW/chronicle_bundle.json --python NATIVE/bin/python --out receipt.json
PYTHONPATH=src NATIVE/bin/python scripts/connected_world_examples.py \
  RAW/chronicle_bundle.json --validation receipt.json --output examples.json
```

The second command refuses a receipt for different bundle bytes. Unobserved, disabled, missing, malformed or unavailable validation never supplies a natural story example. Exact `.lh` citations resolve actual rows/fields and retain an explicitly earlier nested source date. Mechanical observations contain no causal inference; a found adaptation/failure/mixed selection is an observation label, not an efficacy conclusion.

## Preserved browser failures

The D1 lane retains the first phone clipping failure and the subsequent fixed relief/league receipts. `branch-parent-status-before-fix.json` additionally preserves a real production journey that rendered named branch payments but incorrectly said no recorded package was recognized in its parent panel. The stronger journey checks both the parent status and the actual payments, payers, dated next-turn permission, region inspection, mobile explanatory bounds and browser errors. Earlier checks that omitted the parent-status assertion are not the final branch pass.

## Natural desktop and phone journeys

Production Chromium checks used actual file upload and keyboard timeline controls at 1440×900 and 390×844 with touch. The saved bundles remain unmodified. Browser receipts include raw-bundle SHA256 and all production asset hashes; newer receipts also record the exact journey-script hash and measured loading times.

| Journey | Saved simulation source | Browser result | Evidence |
| --- | --- | --- | --- |
| Named movement-branch dues and permission, snapshots 18 and 74 | `8fec1a4b`, template 23, 80 turns; post-presence correction | 38 checks pass; named payers, exact dues, permission available next turn, dated region jump, parent recognition, mobile bounds and console | [branches-presence.json](browser/branches-presence.json) |
| Public health, snapshots 6, 7, 23 and 24 | `2dd4af5d`, procedural 19, 200 turns; health-only development pilot | 82 checks pass; actual same-row supplies, cash versus internal allocation, funding and fractional carry, prior environment dates, delivered report IDs, prior fatality observation and stable guard IDs | [public-health.json](browser/public-health.json) |

The frontend for the health journey is source `876d3c3d`, including the explicit observation date and additional report delay. Its tracked source tree was clean when built. [viewer-source.json](browser/viewer-source.json) identifies the frontend independently of the saved simulations. Natural runs display no constructed-demonstration notice; explicit valid construction metadata controls that notice.

The health bundle loaded in 2,967 ms on desktop and 2,857 ms on phone; opening its systems panel took 749 and 569 ms respectively. These are single bounded measurements on the shared execution machine, not throughput qualification. Mobile screenshots were visually inspected: [public health](browser/public-health-phone23.png) and [named branch funding](browser/branches-phone74.png). Wide tables scroll independently; explanatory prose remains within the section.

Reproduce either journey after building the viewer:

```sh
npm --prefix viewer run build
NODE_PATH=BROWSER_NODE_MODULES CHROMIUM_EXECUTABLE=/usr/bin/chromium PYTHONPATH=src \
  node viewer/scripts/qa-connected-world.mjs --build viewer/dist \
  --bundle RAW/chronicle_bundle.json --out browser-receipt \
  --python NATIVE/bin/python --journey public_health --turns 6,7,23,24
```

Use `--journey branches` with the template-23 bundle to select its first and last naturally funded branch receipts.

## Preserved preliminary whole-program observations

`pre-fix/` retains source `43f02ccaf66489f31529b27cf5bea8d5705db044` whole-program procedural-19 development evidence. It is **not the accepted final timber evaluation**: subsequent independent dimension review corrected the timber provider's original raw-timber-to-commons-relief stake. It was never admitted to held evaluation. The original failed native unary payment alias pilot remains in the lead's CW6 evidence as well.

The preliminary bundle's 200 snapshots pass all 2,000 checks from ten actual package readers. Its first-match finder records 22 exact-pointer observations without narration calls; the mechanical provenance audit has no flags. Two selections remain null: an unpaid positive guild claim, and a completely unobserved relief delivery. No failure was invented to fill those categories. These saved preliminary results establish historical reader/provenance compatibility, not efficacy of the corrected timber policy.

The first browser journey at snapshot 200 assumed that person 13 would still have a project link in the last 24 displayed rows. Their actual repair was at snapshot 27. The failed check is preserved in [history-late-page-assumption-failure.json](pre-fix/history-late-page-assumption-failure.json). Corrected QA selects an actual current-turn named repair receipt, expands earlier observations and verifies the exact individual wage and withheld ordinary income. The preliminary snapshot-27 journey passes 20 desktop/phone checks, including person→project and timeline links; its source pointers identify the actual receipt. The stronger 30-check [navigation journey](pre-fix/history-navigation.json) also passes chain→person, regional inspector→region history and search→the same recorded region, without a future jump. Its 200-turn bundle loaded in 3,903 ms on desktop and 3,309 ms on phone; initial systems-panel times were 9,369 and 9,199 ms. These remain preliminary-source UI measurements.

## Review and remaining lead gates

Independent source/specification review found two substantive E issues: mixed-clock health rows could be backdated as a whole, and equal scalar numbers from unrelated identity namespaces or rebuilt native pools could authorize a causal join. The reviewed corrections use path-specific health clocks and explicit person identity namespaces/epochs. No aggregate polity, project or expedition number proves an individual identity. Focused corrected provenance tests passed (84 Python and 25 viewer checks, plus TypeScript/lint); production historical snapshot citations retain their prior behavior.

A constructed real-native contract independently exercises actual carrier debit, origin credit, destination escrow, physical transit decay, PL1 store delivery, freight credit and payer refund. It verifies duplicate dispatch rejection and money, escrow and store closures. This is a native payment/custody regression, not a natural activation claim.

The accepted post-correction evidence is below. Active lifecycle resume, declared-scale simulation profiling, held screens and final CI remain separate lead gates. No qualification or default-promotion claim is made here.

## Accepted final whole-program development evidence

The frozen CW6 pilot's natural procedural-19 FULL bundle contains **120 turns**, 32 regions and 10 initial polities. It uses simulation source `eaa4a5d3e1cb5c958b5e32719601c28986c9f6ac` and reviewed extension SHA256 `59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`. The raw bundle is 37,962,968 bytes with SHA256 `f6cb5562a4aaec888b6f2a03b4c4b01bd1e8d49737aec22673034eba30ce0ee2`. This is the registered development pilot with corrected timber work stakes and anchored return experiences; it is not held qualification. Its command and actual import paths are retained in [simulation-source.txt](accepted/simulation-source.txt).

The production TypeScript readers accept **all 1,200 package/snapshot observations** across ten connected packages, with zero malformed records: [reader receipt](accepted/full-p19-validation.json). The exact-pointer finder records **21 of 24 declared categories**, with zero schema errors, skipped validations or mechanical narration audit flags: [examples and audit](accepted/full-p19-examples.json). Three categories honestly remain null in this 120-turn world: positive guild claims receiving no payment, partially paid guild claims, and unobserved/zero-upper-bound relief deliveries. Earlier preliminary examples remain under `pre-fix/` and are not substituted for these nulls.

Some reproducible exact-record observations are:

| Observation | Exact fact | Recorded outcome |
| --- | --- | --- |
| Personal adaptation | `s100.lh.adaptive_livelihoods.frame.offers.75` | Person 1108 declines an academy-training offer after the recorded prior-experience rule would decline; this is an offer decision, not a completed job or a welfare conclusion. |
| Delivered timber with a mixed outcome | `s66.lh.timber_orders.closed.0` | Order 0, carrier 1083: 0.482 timber delivered, 0.015 lost, 0.113 coins credited and 0.887 unused escrow refunded. Physical goods and money are separate units. |
| Failed timber order | `s70.lh.timber_orders.closed.1` | Carrier 4 died; the order delivered nothing, deposited 2.000 surviving timber as commons, and refunded 1.000 coins to the payer. The 0.026 purchase cost was not freight income. |
| Unmet army demand | `s10.lh.war_requisition.frame.events.7` | Army `army-2` consumed zero of three demanded rations. A preceding zero-demand row is deliberately excluded from failure selection. |
| Partial patient supplies | `s18.lh.public_health.supplies.1` | Region 3 received 0.455 food against 0.705 need; 1.000 cash was charged and internal value was zero. Supplies did not remove the physical shortfall. |

The finder was corrected after the saved natural bundle exposed a zero-demand army row with adequacy zero. Failure selection now requires an actual positive unmet demand; a focused regression preserves that distinction. This changes only post-hoc example selection, without changing simulation, control arms or held enrollment.

The accepted production frontend was built from clean, immutable isolated worktree source `e69f823b03e22242e59a3007667e1cabcab8fa9e` (see [viewer-source.json](accepted/viewer-source.json) for the authoritative full hash). It includes the reviewed mixed-clock/person-epoch corrections, missing-polity compatibility guards and future-firm date guards. TypeScript/build passed; the only build warning was the existing large-chunk advisory.

The [final browser receipt](accepted/history-browser.json) records **30 passing checks** across desktop and phone using the actual full saved bundle. At snapshot 27, person 13's exact repair receipt pays 2.000 coins and records 0.09490852802991867 ordinary income withheld. The journey expands earlier rows, follows chain→person→project, seeks the recorded snapshot, opens the regional inspector and reaches the same region from historical search. Individual participation and region-only context remain distinct, actual pointers resolve, explicit construction metadata controls the banner, and there are no console errors or document/explanatory-text overflow. The [phone screenshot](accepted/history-phone27.png) was visually inspected; wide tables scroll independently.

On the shared machine the accepted 120-turn bundle loaded in 2,397 ms desktop / 1,926 ms phone. Initial Livelihoods opening took 4,893 / 4,768 ms; complete journeys took 15,287 / 17,620 ms. The connected-history index is computed when first opening that panel, so this remains a visible latency limitation. These bounded measurements do not establish a hardware-independent throughput guarantee.

Reproduce the final connected-history journey with the frozen development pilot bundle:

```sh
PYTHONPATH=src node viewer/scripts/validate-connected-records.mjs \
  --bundle RAW/chronicle_bundle.json --python NATIVE/bin/python --out receipt.json
PYTHONPATH=src NATIVE/bin/python scripts/connected_world_examples.py \
  RAW/chronicle_bundle.json --validation receipt.json --output examples.json
NODE_PATH=BROWSER_NODE_MODULES CHROMIUM_EXECUTABLE=/usr/bin/chromium PYTHONPATH=src \
  node viewer/scripts/qa-connected-world.mjs --build viewer/dist \
  --bundle RAW/chronicle_bundle.json --out browser-receipt \
  --python NATIVE/bin/python --journey history --turns 27
```

The raw pilot remains in the execution evidence workspace; the repository retains these compact receipts, hashes and commands. Re-running the registered development pilot reproduces the raw observation source; no fresh held seed or paid narration call is needed.

## Explicitly constructed browser demonstration

The separate [constructed visibility packet](constructed/README.md) derives a labelled copy of the accepted bundle while preserving the natural artifact unchanged. It redacts one person's income-cost observations consistently across PL3 and A6, preserves observed pay and all physical/cash accounts, and verifies the positive constructed-banner path on desktop and phone. Its exact patch, reproducible artifact hashes, 1,200-reader receipt, mechanical provenance and 34 browser checks remain separate from the natural evaluation above. No simulation or paid narration ran.
