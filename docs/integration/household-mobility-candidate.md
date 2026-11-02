# Household mobility under a liquid-reserve constraint

This hybrid-only candidate is off by default. Run with
`--agents hybrid --simulate-only --household-mobility-liquid-requirement 1`.
The finite control is bounded to0–1000 native wealth units per moving person;
zero disables it. Saved settings persist, stay dormant with agents off, and
cannot change during exact resume. A different setting requires a declared fork.
This is a liquidity eligibility proxy, not a travel payment, household food
inventory, borrowing facility or calibrated migration rule. No wealth is spent.

After existing household consolidation and before decisions are applied, the
native gate checks actual proposed moving groups. Where the origin's then-known
food sufficiency is below1, the moving adults' actual liquid wealth must cover
the configured requirement for the moving people, including child followers.
Stable live identities and the consolidation's actual follower assignment bind
the group. A blocked group stays together; displaced non-migration primary
actions are restored. Forced relocations remain separate. Unknown adjacency,
on-trip or non-distress proposals have explicit eligibility reasons; a passed
gate does not establish that a move subsequently occurred.

The version1 `history[n].household_mobility` observation labels source turnN,
completed snapshotN+1, native people/groups and native wealth. It contains full
aggregate proposal/pass/block counts and at most128 stable group samples, plus
the omitted sample count. The existing Migration inspector pages retained
samples involving a selected region, shows the recorded local food and required/
available liquid wealth, and distinguishes actual movement evidence. Older,
stale or malformed observations stay unknown. No model-population estimate or
future regional outcome enters the decision. Eligibility reasons describe this
gate; they are not a complete causal explanation of migration or recovery.

## Actual checks and scope

The fresh locked CPython3.13 wheel has SHA-256
`b0b634e5df0ce8c84cb88386df56d22be9cbaa0818dba2dbc96c7899374d92b5`;
the installed compiled extension matches its embedded binary, SHA-256
`ed78df1c972a5ef05dd67b42d9f2e6147e54eb2106ef646fb3113d3462d0d88b`.
Rust source tree is `a682ac190d03662012533fc599904bffbb6e0842`.
Seven native gate and11 existing household Rust checks passed during kernel
development; the fresh build's seven gate checks passed again. The actual FFI
probe rejects invalid input without mutating native state, and frame reads are
read-only. Source projection is checked separately from runtime parity.

The declared constructed seed42 five-region/two-civilization world starts with
100 grain in region0 and empty other markets, using actual native wealth and
decisions. From its same turn1 checkpoint and RNG, fixed requirement1 versus0
produced26 proposals:13 sufficient and13 insufficient singleton groups. The
gated arm recorded13 actual moves, the off arm26; blocked agents stayed in
their origins. Their chosen adjacent destinations had higher recorded food
sufficiency. A checked blocked agent's wealth was identical across arms, not
debited by the gate. This documents an adverse constraint, not policy superiority.
Exact continuation retained the setting, complete observation history, events,
world, native bytes and Python RNG. The fixture is one exploratory case, not a
held-out distributional evaluation or a general claim about household behavior.

Four-mode seed42/eight-turn old/new binary pairs with the candidate disabled
matched all39 artifacts, decisions, global/RNG traces, world JSON and24 native
turn states, without stripping any observations. Combined focused Python/native
checks passed384 tests; guarded contracts/metadata passed239 with no native
imports or blocked IO. The viewer passed1,124 tests before the last focused
paging/format correction; that correction passed five focused tests, lint/build
and the full real-browser journey. Broader final CI is recorded in the roadmap.

Desktop/390px production checks loaded the actual constructed four-turn bundle,
selected a region, inspected turns1/2/4 and returned to1, checked sample values
against source and verified paging resets. Old bundles stayed unknown, document
width remained390px, and no page errors occurred. The initially failed paging
receipt is retained. Negative zero and singular person labels were corrected.

## Running and inspecting

From a checkout with its matching extension and locked dependencies:

```bash
PYTHONHASHSEED=0 python -m chronicler.main --seed 42 --turns 8 \
  --agents hybrid --simulate-only --household-mobility-liquid-requirement 1 \
  --checkpoint-every 2 --output output/mobility-example/chronicle.md \
  --state output/mobility-example/state.json
cd viewer
npm run dev
```

Choose the generated `chronicle_bundle.json` in the loader, select a region,
then open its History/Migration evidence. The ordinary launch above generates
its own initial world; it is not the explicitly constructed acceptance fixture.
The already generated constructed example, checkpoints, screenshots and exact
commands are under `/workspace/shared/chronicler-crisis/m4-integration`.

Limits remain: no household credit/food accounting, no new care-obligation
decision rule, no long-run unequal-recovery qualification and no scientific
promotion. Existing farmer illness/care work is a distinct mechanism; this gate
does not establish that every caregiver or institution has a feasible move.
