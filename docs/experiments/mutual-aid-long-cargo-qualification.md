# Private mutual-aid long-cargo qualification

This is private qualification work. Publication remains held. No GitHub writes,
production defaults, policy constants, new institution systems, or checkpoint
implementation were introduced.

The owner-only Drive archive `1jBFoY9DN7VP4Jg2ijnlYTgMXrmCr50rn` was downloaded
using supported Drive metadata/fetch tools into this executor. Size: 633949;
SHA256: `3c150a9a02c93059ff3b73fe184209562dbdf63ce27821ab2bb25021c9097e5f`.
It has 31 regular-file members, including 30 verified manifest payloads. All 19
source/build overlay files were compared byte for byte after applying the patch
on public base `edf72991cad58d6670b1f382c33d50d903a6054a`. The archive references
reviewed candidate `58ee08bc690537cd0e42bbd696e46f2941336c3f`; its Git object is
absent here. Do not present the locally restored commit as that original commit.

Branch: `qualification/mutual-aid-long-cargo` in isolated worktree
`/workspace/Chronicler-qualification`. The initial checkout `/workspace/Chronicler`
remains clean at the public base.

| Identity | Value |
|---|---|
| Restored overlay commit | `960d39ed0f4cd717bdca5486b522792c44d659fb` |
| Restored tree | `cc6211e1be40678b71078c56b54e35db7ce793a0` |
| Original failing fixture commit | `1392fd4229270a5a3089591ea1b8f843946cb530` |
| Repaired tested source commit | `cc2179a17c4da529315d3bae53015d48b8c75e3e` |
| Repaired tested tree | `bf81fbfa24404416ee35b25a79beeb3141fe1c72` |
| Restored native SHA256 | `bf9ebd4b50a655df38610545f0c779c5495c7450b0e26006189f649885e9b08a` |
| Repaired native SHA256 | `8f4ee68be6ce797854df323418789169ee113ee4f5f0e4508028dffee4a3e931` |

The compiled module is
`.venv/lib/python3.13/site-packages/chronicler_agents/chronicler_agents.cpython-313-x86_64-linux-gnu.so`.
The test runner verified its extension suffix and real native simulator classes.
Python: CPython 3.13.5; Rust: 1.99.0, Linux x86_64. The package records every
tracked Python/Rust source and all five build manifests in
`TESTED-SOURCE-SHA256.json`, plus actual runtime package versions and `rustc -Vv`.
Build manifests remain exactly as supplied. The supplied uv.lock omits the
scientific packages required by pyproject.toml; the reproduction instructions
explicitly install the tested versions without changing the tracked lock.

## Failures and minimal repairs

The original fixture has two 20-agent donors with grain/salt stocks 180/30 and
30/180, two recipients, and a directed four-hop merchant route. Cargo comes from
the real native planner; no ledger, merchant, or delivery-buffer injection occurs.
At economy turn 5, six reserved salt units depart A even though consumption left
only 3.024605274 salt (aid enabled) or 4.374409676 (aid disabled). Both failing
receipts preserve pre-turn state and native identity. The merchant implementation
was unchanged from the public base, so this is a pre-existing lifecycle defect.

The repair rechecks Loading cargo against physical stock minus already queued
same-turn departure debits. An unbacked reservation is cancelled without a return
credit. Older in-flight cargo is already debited and is not subtracted again.
An explicit internal buffer flag gates this check to hybrid mode: shadow mode
also has a diagnostics buffer, so buffer presence alone was insufficient.
Both graph-construction paths and the mode setter maintain this flag.

After that repair, a longer run exposed an orphaned unit of cargo after a merchant
death: surviving Transit quantity 8 disagreed with cumulative departures minus
arrivals and returns, 9. The intermediate native SHA is retained in the failing
flight receipt (the intermediate binary itself is not bundled). Death processing
now releases trips before killing/reusing the slot: Loading cancels; Transit
returns original cargo once. Both catastrophe and demographic death batches use
this path. Active-trip count and cargo quantity are recomputed after demographics.
Same-turn death retains both its departure debit and corresponding return credit.

Runtime edits are limited to 58 added lines across three existing native files:
`merchant.rs`, `tick.rs`, and `ffi/mod.rs`. No Python aid policy code changed.
The source/test follow-up against the restored overlay is seven files,
584 insertions and 15 deletions. Documentation is a separate evidence commit.

## Fixtures and independent accounting

The Python policy fixture uses synthetic snapshots and commitments, with three
simultaneous donors and two competing recipients. Independent hand-calculated
first edges are A→First 1 grain sent/0.95 received, B→First 1.55 salt,
B→Second 0.95 salt, C→Second 2.5 grain/2.375 received. First reaches its 2.5 delivery
cap. Repeated turns exhaust free donor surplus at reserve floors while treasury
remains funded. Region-order reversal, one-unit funding, and default-off cases
are checked. This is Python-only evidence.

Eight direct-ABI cases run 28 turns each: 3/4/5 hops at seed 42, five hops at seed
77, aid disabled, Loading route cancellation, in-flight route disruption/return,
and catastrophe deaths. Current cases use 50 grain/50 salt per donor to retain
both donors through the stress window. Native aid uses both donors over successive
turns; simultaneous recipients share a donor's turn capacity. The synthetic lane
additionally checks simultaneous competition across three donors. The exact
original 180/30 fixture at commit 1392fd4 was separately rerun against repaired
native code for 28 turns with aid enabled and disabled; both pass.

The independent stock oracle derives ingress from lifetime departure/arrival/return
counter differences, consumption from live population counts, then grain/salt
storage preservation and caps. It never uses reconstructed native conservation
outputs or resulting stocks as expected-value inputs. Per-region/per-good stock
and stock-plus-outstanding-cargo balances hold; grain transit survival is 0.95,
salt survival is 1. All current cases finish with no cargo or reservations. Maximum
current per-cell stock error is 2.87e-6 (ABI float32 tolerance 2e-4). Original
fixture reruns have maximum error 1.83e-6. Clamp-floor correction is zero.

Reads are repeated to prove they do not drain commitments or counters. Aid is
replanned in the same turn to prove no second debit or dispatch. A second economy
call without an intervening merchant tick independently verifies consumption
continues but arrivals, departures and transit losses are not applied twice.
Targeted Rust tests inspect actual pool phases, reservations and delivery buffers
for competing departures, death, exactly-once release, and slot reuse.

## Executed verification

Aggregate follow-up completed full default suites on unchanged executable repair
cc2179a: native Python 2951 passed/4 skipped; Rust default 821 passed/2 ignored.
See mutual-aid-aggregate-gate.md/json for exact reasons and separate unaffected
default-off equality versus corrected public-native accounting.

| Lane | Result |
|---|---|
| Initial Python-only aid suites | 39 passed, 7 skipped |
| Final native aid, new cargo, economy and simulation suites | 313 passed, no skips |
| Same suites in separate environment with no extension | 297 passed, 16 skipped |
| Rust library tests | 373 passed |
| Rust merchant integration tests | 38 passed |
| Independent fresh gpt-6.1-sol review | Approved; independently ran 11 new tests, one Rust death regression, five updated prior tests |

The prior 15-turn fixture still dispatches on turns 4/5 with limited funding;
repaired native lifecycle changes later recovery, so funded reactivation is now
exactly turn 12. Tests retain strict streak and pre-reactivation comparisons.
Fresh disabled-hybrid Python control compares all 15 normalized history rows,
including native commitments, against untouched public Python source using the
same repaired native package. It isolates the aid feature's default-off behavior;
it does not claim equality to an unrepaired native kernel.

A freshly executed aggregate control (agents off, seed 42, four complete turns)
has exactly equal normalized worlds against the public base. Historical later
aggregate logs outside the supplied archive were not inspected. Failure logs from
test development are retained alongside final passing logs and labelled by filename.

## Remaining gaps

There is no full hybrid checkpoint/restore qualification, ecology run, production
scenario, full validation profile, famine/population benefit calibration, or
publication approval. Native routes and margin inputs are explicit scenario
inputs and production is zero. The stock oracle shares native ingress counters;
direct Rust pool/buffer assertions complement that evidence but do not establish
all possible trip histories. Full original-native behavior equality is not claimed
after the intentional accounting repairs. Publication remains held.
