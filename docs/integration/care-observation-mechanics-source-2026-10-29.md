# Care deterministic mechanics reader — source only, 2026-10-29

This source child of `494af08d27fdcf9cf28d9ea1744f3efe8fae6851` adds one pure,
unused mechanics module and 28 appended plain test contracts. It follows the
source proposal `c746172e17470133401851fe9363daae1713fd593206565fbc8eb0a34babb928`,
API `ca0668ad88e42295250bb86fb0c4705307bbccbd4809064487ffa42e7f2d2c96`
and proposal receipt `8435c656`. None of the new mechanics code or tests has
executed during implementation. Source/AST/hash inspection is not a test pass.

The entire native tree remains `09ec301efc5c52a0a75f7a6edd9b99636d2953ff`.
The codec remains SHA `e18a2aefa25a512d1073f77506517221f4b98766d45c0c0a79b5cb343e2a7349`.
Existing physics, health state, phases, defaults, dependencies, workflows and
manifests remain unchanged. No runtime hook, file writer, capture/retention owner,
native method, World, checkpoint or experiment activation is added.

`verify_care_mechanics` re-decodes actual frame bytes and predecessor ancestry
through the strict codec. It compares complete deterministic preparation, consumed
losses, labor adjustment, worked predicates, six scoped wealth witnesses, finish
liveness/statistics, necessary injury-row conditions and Python episode/regional
accounting. It returns a frozen report with component True/False/None values,
one bounded first-failure section/index, and fixed unqualified claims. Diagnostic
allocation failure returns missing evidence (`None`), without intercepting any
ordinary turn. Malformed/aborted frames are INCOMPLETE, mismatches are MISMATCH,
unsupported arithmetic/runtime is PARTIAL, and only matching mandatory components
produce DETERMINISTIC_MATCH. That last name is a conditional deterministic-data
comparison, not a producer truth, RNG, efficacy or scientific claim.

The report always leaves source-copy truth, army/city provenance, original raw
farmer count/factor and full goods production, non-farmer base-income origin,
native injury draws/outcome-set completeness, global RNG, display/event text,
ordinary-output parity, counterfactual benefit/science and performance unqualified.
Actual recorded new-row consequences can match without independently proving the
missing random draws that chose those rows.

## Arithmetic and the fixed integer bound

The private helpers represent a finite binary32/binary64 value as signed integer
significand times a power of two. Add/sub align exact integers, multiplication
uses the exact product, division uses quotient/remainder, and every source operator
rounds once to nearest with ties to even. There is no approximate f64-emulated
f32 expression, fused multiply-add, epsilon, reassociated loss sum or fsum.
Subnormals and signed zeros retain their exact bits. Required nonfinite operands
or results refuse arithmetic qualification; a captured output differing from a
finite recomputed output is a mismatch. Copy-only dead/skipped/uncharged facts may
still match with NaN payloads. Output `>0` predicates use exact IEEE classification.
An unqualified Rust max/clamp tie between opposite zero signs remains unsupported.

The fixed private integer guard is 8,192 bits. A finite binary64 operand has a
significand of at most53 bits and exponent-power range -1074..971. Add/sub alignment
therefore produces at most53+2045=2098 bits, or2099 after a sum. Multiplication
has at most106 significand bits and exponent powers -2148..1942. Division has at
most53-bit numerator/denominator and power difference -2045..2045. Rounding chooses
the actual leading exponent before scaling to normal precision or quantum2^-1074.
Using crude independent extrema, power -2148..2045 and output quantum -1074..971
bound the shift by3119. Even applying that shift to the largest2099-bit numerator
needs at most5218 bits; denominator/remainder/carry operations stay below5300.
Operation-specific bounds are tighter, but the coarse bound already proves8192
conservative. The guard is not an experiment
parameter or a grant to raise any frame/process cap. Widening b32 and casting
u32 are strict subsets of these bounds. Inputs through the public frame path are
validated fixed-width primitives, not caller-supplied arbitrary-size integers.

Typed native constants are pinned: adult20, idle0, Farmer0, BASE_FARMER_INCOME
b32 `0x3e99999a`, WEALTH_DECAY `0x3ca3d70a`, MAX_WEALTH `0x42c80000` and one
`0x3f800000`. Per-source subtraction, multiplication, addition and branch order
remain explicit, including the farm_productivity==1 branch and one health guard.

## Exact source distinctions

Global spouse and finish lookup retains the last alive physical slot, including
raw ID0. Kin lookup is separately rebuilt from eligible workers and retains the
last eligible physical slot. Duplicate raw IDs can make those answers differ;
the reader reproduces that distinction rather than imposing idealized uniqueness.

A live eligible rawID0 Marriage donor can be reserved, deducted and counted while
the unchanged assignment giver sentinel remains0 and its care bits+0. The later
Kin pass may still fill that row. The reader reproduces those source accounting
effects and does not normalize them into a different physics rule. First Marriage
order remains significant; multiple-Marriage release fallback and debug assertion
behavior depend on the explicitly bound native build profile. These constructed
edge fixtures are not claims that normal Worlds produce those states.

Initial regional f32 loss accumulation visits the deduction map in physical-slot
order. Kin additions then occur in patient-row order. A four-slot .5/.2 fixture
therefore expects `0x3fb33334`, while an incorrect final-H resummation yields
`0x3fb33333`. The final consumed vector alone does not supply its accumulation
order; the complete preparation facts and exact source algorithm do.

Wealth uses captured current stable IDs, occupation, region, liveness and actual
six numeric witnesses. Dead/invalid/non-farmer/stale/zero-loss branches stay
distinct. No cost is inferred from final wealth, no stock debit is invented, and
zero monetary cost remains possible. Complete consumed-vector/loop coverage proves
only the recorded call's health-charge scope; the later owner must separately
bind once-delegated whole turns and retention.

Finish liveness rebuilds all current IDs/regions/alive slots, with its own current
capacity. Injury checks preserve source short circuits, sorted result order and
duplicate-worker tuple multiplicity. Threshold underflow can make a new row
impossible; missing draws never become an assumed full outcome set.

Python recovery uses actual incoming episode order and widened assignment b32
care, not the original control's b64 fraction. Recovery/new injuries charge work
region; final episode counts use current region. Censoring precedes assignment
lookup, new episodes do not recover on onset, equal-ID sorting is stable, and
last new-row alive updates govern duplicate-ID post counts. Incoming duplicate
episodes refuse preparation, while post duplicates can arise and fail only the
next preparation. Existing mutated episodes are not silently revalidated as new
Pydantic models. A fully recovered old patient may have an invalid current region
that is never indexed; a kept/new episode needing a missing region cannot match
a successfully completed ordinary source transition.

## CPython total aggregation is a separate gate

Regional recovery uses explicit b64 +=. Top-level floating totals use the actual
Python built-in sum in dictionary insertion order; CPython3.13 improved summation
is not a naive left fold. The reader admits that operation only with actual
matching CPython3.13.17 implementation/version/full runtime string and binary64
float properties bound to the producer context. It calls that actual builtin,
not a guessed replacement. Context fields do not fake the running interpreter.
The local pure-check environment's actual3.13.5 therefore cannot qualify this
step: otherwise matching frames return PARTIAL with floating_totals=None.
No new skip is added. Source-owned context is not an independent hardware or
producer attestation; those truths remain outside this conditional reader.

## Unrun verification and unchanged budgets

Exactly28 plain parents are proposed/appended to the existing care-policy module,
with its entire previous59,930-byte file preserved as a prefix. No subtest,
parameterized parent, skip or module owner is added. All303 owners/six skips/
623 subreports and the38 whole-module offline chunks/110-second bounds remain
unchanged. With the two selected care modules,88 parents/97 old subreports is a
source-derived prospective count only, not an observed collection or pass.

The implementation grant retains stricter future focused-run ceilings than the
proposal:110-second wall,30-second CPU,512MiB address space,one CPU,256MiB owned
output and2MiB streamed log. There is no execution grant in this source change.
Keep first failures and stop rather than raise bounds or remove selections.
Actual memory/headroom, focused run, applicable CI and a different nonauthor's
frozen-source review remain unrun/separate. Source inspection by a former codec
reviewer is not independent review of this newly authored mechanics module.

Same CAREOBS1/retention limits remain:131072 bytes/frame,4096 row counts,32768
active/relevant relation positions,32 ordinals/4194304 encoded chain bytes,
16711680 aggregate frame bytes plus65536 metadata inside16MiB diagnostic and
32MiB whole evidence. This module retains no extra file/payload. A later owner
must account any aggregate report bytes inside the existing metadata reserve;
capture truth, native API/actual schemas, default/global-RNG, genuine enabled
World/own-checkpoint, owner/retention, held pilot and scientific/performance/main
promotion gates remain separate.
