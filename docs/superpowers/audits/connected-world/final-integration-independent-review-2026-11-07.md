# Connected World integrated source review, 2026-11-07

Independent integration reviewer: B3 owner. This review covers the actual
`11467a46b957a364b3d4d4ba2ba1a4326adcc6c3` →
`ccc864a997134f0dcd4b05a7419a7bce203bfae7` diff (202 files), the shared
source corrections below, and the appended exact-inverse layer at
`0bf2832f39f21ff5794dcdb444ddff26f76ce8ca`. The review uses the original
A–E plan and amendment, lane contracts, actual source/diffs and tests. It
builds on the preceding independent native, D1, health, B3/B4 and accounting
reviews; it does not substitute a board status for implementation or execution.

**Integrated source approval: no remaining source blocker after the reviewed
corrections listed below, including startup guard `00374492`.** The later
runtime source through `b1603c56` and the reviewed E/compatibility follow-ups
were inspected separately from the original freeze. B3-authored changes were
independently reviewed by D1/D4 owners; this document is not self-approval of
those changes.

The source review is distinct from approval to merge: final exact-head Tests,
main CI, integrated lifecycle/resume, browser/old-bundle, held and scale gates
must carry their own receipts. No final whole-program execution result is
claimed by this document.

## Findings resolved during integration

- Timber aliases incorrectly used native pairwise purposes 8/9 through unary
  collection/credit calls. The actual FULL procedural-19 pilot failed before
  held use. `506498df` routes purchase to unary `wares_purchase` (7) and freight
  to `remittance` (4), retaining the separate `0xA430000 + order` namespace.
  Actual compiled payment and complete dispatch/delivery regressions retain
  stock, escrow, ceiling/refund and duplicate-call closure. FakeSim now enforces
  the native pairwise refusal. Neither change requires a different extension.
- `KNOWN_PURPOSES` omitted appended restitution purpose 10. Expanding accounting
  tuples also inserted new entries inside historical declaration order.
  `f81bc0af` appends the native purpose, freezes the historical withheld/lifetime
  prefixes (including the historical titled-trade repeat), and preserves the
  fourteen old typed-channel names. The reviewer independently compared actual
  values against Git `11467a46`: channels 14→20, withheld 7→11, lifetime 49→68,
  native purposes 10→11 and CLI choices 27→37 all keep their exact old prefixes.
- Timber procurement originally equated raw timber with commons food relief.
  Independently reviewed `a6904452` (integrated as `3f0d16a7`) replaces that
  dimension error with current measured workshop idle/road repair worker-turn
  stakes, bounded by remaining applicable work, per-turn capacity and imports.
  Unvalued granary inputs are reserved conservatively; irrigation precedes
  roads. Execution also scopes the finite envelope to its recipient region.
  The promise remains funded dispatch, never a claim of completed repair.
- D3 borrowed cumulative history/counters into old snapshots. `a13ca5f9`
  copies frame/history/counters; its regression proves a completed observation
  cannot acquire future events. The same change clears pool-scoped dedup keys
  and refreshes the current return-count after late events. Other new summaries
  copy cumulative totals and replace their per-turn containers; no equivalent
  cumulative alias was found in the inspected paths.
- A rebuilt pool could preserve an unrelated person whose numeric id matched
  an old roster. `c4c5b834` extends the existing opt-in identity repair to D4 in
  both modes, through ordinary `select_recruits`. Default, disabled and D3
  record-only paths remain unchanged. Exact checkpoint loading explicitly binds
  the marker to its restored simulator, preventing a fresh draft on exact restore.
- A6's unknown movement attribution can legitimately rehome X1's unclassified
  move. `b1603c56` keeps D3's personally remembered home/date and witnessed war
  instances separately. Return scores still require earlier formal peace,
  adjacency and a bounded window. Release reads only its bound T−1 OwnRow;
  a late refusal retains unknown and never reads the same-turn frame.

- The shared-configuration reviewer reproduced five orphan mode/rules options
  being silently ignored. Independently reviewed `00374492` checks their
  effective switches and conflicting saved values through the existing ownership
  registry before any setter. New/same-saved values remain accepted. The reviewer
  independently ran all 30 startup regressions: passed in 0.34s. The integration
  owner must enroll the new module in offline/native manifests.

## Shared authority and integration review

The independent D1 owner reviewed actual `eaa4a5d3` shared CLI/catalog/state,
manifest, oracle/native-shard registrations and turn order, plus `f81bc0af`
compatibility and generic CW6 delegation. All new substates remain optional and
excluded while never enabled; effective prerequisites match the catalog; the
five-option startup correction above resolves the one finding. Generic CW6
routes either screen syntax to the owned sidecar-aware runner and retains the
serial guard. It does not silently use the old stub or a generic extractor.

The actual shared seams preserve one spendable native wealth balance. New
money routes validate complete bills before payment, use disjoint native keys,
return refused credit to its payer, and expose their uncapped exact MoneyBooks
to A1. Escrow is an explicit non-spendable customer holding until delivery;
restitution liabilities are not cash. A1 copies actual native income, withholding,
decay, clamp, birth, estate and transfer operands, with transfer rounding separate
from modeled sources. The older aggregate residual is explicitly labeled as such.

D4 freezes service identities before livelihood preparation. Civilian food,
farmer counts, urban shares, named work and title share the same census; later
recruits keep this turn's civilian entitlement and later releases keep the frozen
service entitlement. The final float32 labor factor is captured after late care
and guards. Actual infrastructure work enters the same shared storage-work
subtotal; no second allocation or settlement order was introduced. Complete
prepared care/guard shares remain economic costs even when payment fails.

X1 remains record-only with one Phase 10 writer. A6, public health and D3 use
registered read_frame/OwnRow/separation interfaces for T−1 data. The new saved
bundle identity reader is narrowly registered by exact module/function/path;
its tests reject live-state imports and other decision modules. Army attachment,
physical cargo position and native residence remain distinct. New native inputs
are validated atomically, consumed or canceled, and excluded from persistence.

Native A6 changes remain independently reviewed through `9e001701`; the compiled
release artifact is SHA256
`59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`.
Unknown foreign destinations use an own-home prior; personal work costs remain
unknown when title or mixed withholding is unobserved. Unsupported legacy driver
attribution refuses active A6 inputs rather than falsely assigning experience
to packet news or religion. Existing native migration/household gates remain
the movement authority. Default-path provenance-consuming decisions, merchant
income-location mismatch and natural-death casualty behavior were not silently
promoted to corrected defaults.

## Original program coverage

| Scope | Integrated implementation inspected | Required interpretation |
| --- | --- | --- |
| A1/A2 | Itemized native/package wealth, care/guard/crew income, exact fixed-enrollment wage analysis retained | Wealth is not globally conserved cash; wages raised credits at fixed enrollment, priced-out effect remained null |
| A3 | Existing real firm inputs/household demand plus actual work/training choice adapters | No replacement of earlier null/adverse findings by new source existence |
| A4/A5 | Titled food lifecycle, hostile physical custody, real army supply/restitution, cross-polity timber purchase/escrow/store delivery | Input dispatch, physical delivery, repair and liability/payment are distinct |
| A6 | Dated personal migration, work/training, information and food/timber trade experience with controls | Native remains sole mover; missing private costs and unsupported causal attribution stay unknown |
| B | Conserved procedural watersheds, irrigation/road condition, named PL3 works, canopy support loss, basin/context viewer and condition-unit war burden | Ports remain explicitly deferred for lack of a consumer; anonymous unpaid works remain only when PL3 is off |
| C | Real supply costs, service-based sanitation proxy, T−1 displacement crowding, delayed reports, explicit policy comparison and named guards | Regional epidemic fractions, individual injury/care episodes and mortality authorities remain separate |
| D1/D2 | Real relief food/funds, guild claims, paid local branches, exact event attribution | No positive relief delivery lower bound is established; no extra grievance stack or cross-pool person join |
| D3/D4 | Campaign-selected wounds, separation, dated evacuation/return, actual ration source/consumption, custody and funded restitution | No Python teleport, invented heir or new mortality authority |
| E | Strict linked person/household/firm/order/claim/army/work histories, basin context, chain/region/search entry points, exact citations, validated examples and constructed-world banner | Co-resident household keys are inferred current groups; firm controller is a polity, sampling absence proves nothing, and citation existence is not causal proof |

Earlier coverage gaps identified in the dated integration coverage audit now
have implementations and reviewed dispositions. Their runtime efficacy is not
established by this source review. Public-works/care/trade outcomes require the
final integrated evidence, including nulls and adverse outcomes.

## Exact-inverse admission

Every literal hunk was inspected against its actual change: FFI 14, household 2,
lib 1, pool 3, tick 11, manifest 4, manifest tests 2 — **37 hunks in seven files**.
The reviewer independently checked unique anchors, replayed each old→new patch,
reversed every new→old patch and compared complete UTF-8 bytes with Git
`11467a46`. All current and parent SHA256 values match the fixture. Only the
new `livelihoods_cwcomplete_source_inverse.json` was added under fixtures;
historical fixture blobs were unchanged. LAYERS retains its old prefix.

The compact independent receipt is
[final-inverse-verification-2026-11-07.json](final-inverse-verification-2026-11-07.json).
This proves source lineage; it does not prove runtime identity or qualification.

## Tests and evidence inspected

Counts below retain their actual source scope rather than being added into a
fictional single final run:

- B3 final `be524a60` has independent review and full bounded offline/native,
  browser and declared-scale receipts in its dated integration evidence.
- L9 roads `7cc0c89e`: 248 focused passes; natural procedural 31, 72 turns,
  funded-road checkpoint 66 exact history/world/state-file resume passed in
  8.68s. Nine progressing road receipts delivered 20.40 work / 10.20 timber
  and 10,196 milli actual named wages. The missing-channel and two real
  integration failures are preserved in the source record.
- Independent actual integrated native rerun on `af697dc6`: 16 passed in 6.10s
  with the artifact above and explicit root import identity. It includes natural
  positive late C2 work, final-input/title closure, mixed urban/rural census
  conservation and native wealth lifecycle restoration. It does not replace
  whole-program active army/care/order checkpoint tests.
- D4 fresh-pool repair `c4c5b834`: 47 focused passes, independently repeated by
  the D4 reviewer. Timber work-stake correction `a6904452`: 171 focused passes,
  independently repeated by the D4 reviewer.
- D1 `11467a46`: independent source and evidence audit, 60 unique held rows with
  no failed run, relief activation 0 template / 2 procedural, guild activation
  0 / 6. Relief strata below the minimum have no primary mean. Guild purse
  mean was −0.164888, not a benefit finding. Raw lower estimates remain preserved
  but invalidated. Supplementary `338d8e6f` recomputes the two valid individual
  control contrasts without a stratum summary; raw SHA256 matches.
- E reviewer independently inspected strict history/citation source and ran
  39 Python provenance/example checks. Mixed observation dates, person epochs,
  current household inference and polity firm ownership were reviewed directly.
  The same reviewer spot-checked E16a/E0b (`b85b3d4f` / `1c40ed62`) and ran 13
  focused viewer tests: missing optional dimensions remain neutral, explicit
  invalid polity references and future firm lifecycle markers are rejected.
- The external serial 14-case profile tool and metadata follow-ups were reviewed
  independently, including source/artifact guards, actual agent counts, CPU/RSS,
  strict checkpoint IO and final post-exit Arrow/file/metric byte measurements.
  Tool approval makes no claim that all profile cases have completed.

An early independent root focused run had 188 passes and three stale C2 contract
failures; the reviewed integration updates those assertions without weakening
prerequisites or raising a timeout. One native review attempt stopped during a
D1 cherry-pick conflict before collection; a clean verified rerun passed. No
historical hash or offline 110-second limit was changed to hide these failures.

The FeatureOptions timeout repair was reviewed separately: it splits availability
and forwarding/drop journeys, seeds the second with exactly the first's final
prerequisite state, preserves every assertion and leaves the five-second limit.
It changes no production UI behavior.

## Remaining gates and explicit boundaries

The lead retains responsibility for final V0–V13 receipts: completed guarded
73+ chunk offline run, full Python/native/Rust checks, catalog/compatibility,
feature-off identity against `8abc1acb` and preceding main, active-transition
exact resume, old bundles, final production desktop/phone journeys and natural
examples, held reports and declared-scale profiling. Each must name actual
source/import/extension and preserve failures, missing measures, costs and
harms. The final CW6 horizon was reduced before held use to fit the unchanged
compute ceiling; it is a bounded screen, not either restricted qualification.

At the last independent GitHub check, PR #95's exact reviewed head `11467a46`
had all nine Tests jobs green (run `42384860718`) and merged through its PR as
`f76436ae37c735b2b856caf98033122798ac88d2`. Main run `42386261493` was still
in progress; B3 main run `42382492574` was successful. Later final-feature
PR/main CI must be checked on their own exact heads. Red main blocks feature
merges.

Additional explicit model limits remain: irrigation is a declared sanitation
proxy; gross food exports prevent a relief lower-bound proof; conservative timber
stakes leave some real granary/irrigation demand unfunded; unknown personal title
costs are not zero; personal restitution promises lapse on death/pool reset;
retention caps make omitted rows unknown; formal peace does not prove safety.
No defaults, paid narration, purchases, deployments, credentials/sharing changes
or restricted full 200-seed/procedural qualification were authorized by this
review.
