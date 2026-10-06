# Detached M60a campaign logistics

This implements experimental contract `chronicler-m60a-detached-v1` on private
baseline `0d462fd9a51a4dca694271b60465fcbfbf359c33`, tree
`c4a7948ffd1c24f138c93d068c257ddd0fc17e00`. It is a standalone logistics
prototype with illustrative parameters, not a calibrated campaign system or
production integration. The baseline's existing A01 native artifact-byte gate
remains withheld; this experiment does not change that gate.

Only four new files belong to this slice: the kernel, this document,
`scripts/campaign_logistics_demo.py`, and `tests/test_campaign_logistics.py`.
Existing production imports, schemas, native bytes, WAR, RNG, dependencies,
and artifacts are unchanged. No battle, deaths, conquest, territory ownership,
late recruitment, real enlistment, treasury commitment, or native synchronization
is implemented. No held serialization change is included.

## Run the ordinary table

```sh
python scripts/campaign_logistics_demo.py             # disabled receipt only
python scripts/campaign_logistics_demo.py --enable    # explicit seven-tick demo
python -m pytest -q tests/test_campaign_logistics.py
```

The driver prints canonical experiment JSON to stdout and creates no output
files. It is absent from the production CLI registry. Importing the kernel
uses only the Python standard library and has no side effects. The test command
uses the unchanged repository `conftest.py`, whose import requires Pydantic;
the detached kernel and driver themselves do not require it.

The driver reuses region adjacency from
`chronicler-agents/tests/test_behavior.rs:41-66`: 0 connects to 1 and 2;
1 and 2 connect only to 0. That native fixture contains farmers. The demo's
separate roster consists of supplied soldier-role IDs 101 and 202, with no
claim of native enlistment. These are ordinary input tables, not new worlds,
scientific campaigns, or seed sweeps.

| Tick | Action / phase after | Member locations | Carried kits | Local stocks (0,1,2) | Cumulative consumed |
| --- | --- | --- | --- | --- | --- |
| 0 | admit / rally | 1,0 | 8,8 | 0,0,4 | 0 |
| 1 | rally / ready | 1,1 | 7,7 | 0,0,4 | 2 |
| 2 | march / marching | 0,0 | 6,6 | 0,0,4 | 4 |
| 3 | continue / arrived | 2,2 | 5,5 | 0,0,4 | 6 |
| 4 | hold + local credit 2 + replenish 2 each / arrived | 2,2 | 6,6 | 0,0,2 | 8 |
| 5 | return / returning | 0,0 | 5,5 | 0,0,2 | 10 |
| 6 | continue / closed | 1,1 | 0,0 | 0,8,2 | 12 |
| 7 | terminal no-op / closed | 1,1 | 0,0 | 0,8,2 | 12 |

Initial food is 20. The unique tick-4 credit admits 2 units. Final accounting is
`20 + 2 = 10 local + 0 carried + 12 consumed + 0 deserted`.
Each returned soldier deposits a residual kit of 4 at staging.

## Explicit policy and inputs

`admit(...) -> Session` accepts mandatory frozen `Policy` and `Topology`, a
campaign ID, nonnegative admission turn, distinct staging and target regions,
fixed `Soldier` records, and sandbox `Stock` records. A session admits one
campaign. Stable integer agent IDs survive throughout; reusable native slots
and display names are not used. A soldier role is mandatory. Sparse admission
stock tables are expanded into explicit zero stocks for known regions.

`advance(session, policy=..., topology=..., tick=...) -> Result` returns a new
session and complete immutable receipt. Policy/topology versions and content
digests are recorded in the state and every receipt; changing either requires
a new session. Valid input permutations canonicalize to equal outputs.
All container fields are tuples; mutable nested data, floats, booleans in
integer fields, nonfinite values, duplicate IDs, illegal graph edges, unknown
regions, invalid kits, and malformed dates are rejected.

A tick supplies unique `Order` and `Credit` IDs, per-active-member `Condition`
and `Draw` records, and explicit friendly supply-source region IDs. No sources
is a valid, explicitly unreachable supply condition. Every active or
arrived-active member requires exactly one condition and independent draw
per tick, even when its current morale makes desertion impossible. Settled and
terminal members require none. Missing, extra, duplicate or out-of-range draws
abort before publication. No RNG or implicit draw cursor is consulted.

Morale, unmet needs, and information quality use integer thousandths in
`0..1000`. Independent desertion draws are integers `0..9999`. The caller's
policy defines ration demand and kit limit; per-edge and unreachable supply
stress; hunger, unmet-needs and information-loss stress; recovery; desertion
threshold/chance; and movement gates. Lifecycle and processing-order identifiers
are explicit policy fields; v1 rejects unsupported alternatives.

The demo's version is `m60a-demo-illustrative-v1`, with demand 1, kit limit 8,
per-edge stress 10, unreachable stress 100, hunger stress 120, needs stress 100,
information stress 80, recovery 20, desertion threshold 200, chance 5000/10000,
minimum movement morale 100, and full rations required for movement. These
values are illustrative caller data, not production tuning constants.

## Frozen tick order and lifecycle

1. Validate the state/cursor/configuration and the whole proposed tick.
2. Admit orders and uniquely identified local stock credits. Apply replenishment
   orders in order-ID order, then ascending stable soldier-ID order. Each grant
   is bounded by requested amount, kit capacity, and stock at the member's
   actual start location. Partial grants emit stock-shortfall or kit-limit codes.
3. Consume `min(carried kit, ration demand)` for each active member. Compute
   supply distance from its frozen start region to the closest reachable source
   using sorted-neighbor shortest-path BFS; absence has a distinct stress/code.
4. Calculate hunger stress with ceiling division for the unfilled fraction of
   demand. Needs and information stress use floor division by 1000. Subtract
   their sum plus supply-distance stress from morale; if all stress is zero,
   add recovery instead. Clamp morale to `0..1000`.
5. Desert when resulting morale is at or below the threshold and supplied draw
   is strictly below chance. Move the deserter's remaining kit to the tracked
   deserted-food sink before considering movement.
6. Move survivors at most one legal edge. Hunger or low morale can stall a
   member under policy. Marching survivors stay together: one survivor's
   logistics stall holds the cohort. Dispersed rally/return members move
   independently. No route emits `destination_unreachable`; no teleport occurs.
7. Latch arrival or return, account for returned kits, close when all original
   members have returned/deserted, validate balances, then publish atomically.

Admission starts in `rally`. Reaching staging makes the remaining roster
`ready`; it never marches again on that tick. `march` in a rally tick permits
only rally movement. Once ready, an explicit later `march` begins travel to
target; no order in ready means wait. `hold` suppresses movement for that one
tick while still consuming food and applying stress. Continuation ticks keep
marching or returning without repeating the original control order.

At target, `arrived` latches and members remain arrived-active: they still need
food, conditions and draws, and can desert. They may hold, replenish or return.
Another march is rejected. `return` can be issued during rally or any
nonterminal phase, sets staging as the objective, and returns survivors along
legal edges. A member reaching staging deposits its remaining kit into staging
stock and becomes returned; it never consumes campaign food again.

`cancel` is limited to the first advance, before any movement, and cannot be
combined with replenishment or credits. It produces terminal `cancelled` and
freezes the dispersed local kits and roster at their supplied locations. It
does not relabel dispersed soldiers as returned or transport their food to
staging. No food, morale, draw or movement is spent. Subsequent terminal ticks
emit no-op receipts; they reject orders/credits and require no member inputs.
Closure/cancellation cannot be reopened.

## Conservation, receipts, and replay

Every published state satisfies both identities:

```text
original roster = active + arrived-active + returned + deserted
initial food + admitted credits = local stock + carried kits + consumed + deserted sink
```

The roster categories are exclusive and contain no deaths. Each member receipt
also balances `kit before + replenished = consumed + kit after + released`.
Cancelled rosters retain their existing categories, under a terminal phase.
Explicit reason-coded stalling is allowed; unbounded graph distance is never
replaced by a gameplay path cap.

Receipts include contract/campaign/turn/configuration identities, full canonical
tick inputs and order/source IDs, before/after state digests and phases, roster
counts, local stocks and food balance, per-grant stock debits, and every original
member's start/end location/status, intended path, supply distance, kit,
consumption, stress components, morale, supplied draw/result and reasons.
Settled members remain visible with no-op receipts.

Persist `Session.state` and `Session.cursor` together for local resume. Both are
immutable records; no production snapshot format or serializer is extended.
The cursor checks contiguous turn and state-digest chains, command/source-ID
uniqueness, and saved receipt digests. These guards detect mismatched or
accidentally altered local resume data; they are not signatures or an untrusted
storage security protocol.

Replaying an identical full historical tick returns its exact saved receipt
and the current session, even after later ticks. It does not roll state back,
spend food, consume draws or move again. A changed payload at a committed turn,
an order/source ID reused on another turn, a stale uncommitted date, or a future
gap aborts. Intermediate turns always require explicit inputs. Every rejection
leaves all caller objects unchanged.

`drive(..., enabled=False)` returns the identical supplied session object and a
disabled no-op receipt without inspecting/spending the pending tick. The CLI's
default invocation emits only that disabled receipt and does not admit a roster.

## Verification and remaining integration work

The focused tests assert hand-calculated states and complete member receipts for
the seven-turn trace, starvation/desertion, local replenishment and finite stocks,
hold, dispersed return, residual kit/sink accounting, draw boundaries, fixed-point
rounding, unreachable routes/sources, shortest-path ties and uncapped lengths,
invalid admissions/configuration/ticks, cancellation, terminal no-ops, replay and
resume, atomic rejection, input permutations, import isolation, and disabled
state/RNG no-op behavior. Fresh-process receipts are compared under
`PYTHONHASHSEED=0,1,42,101`; no scientific simulation seeds are introduced.

Real ownership/enlistment, native synchronization, committed treasury/provisions,
death/cancellation reconciliation, input adapters, production action wiring and
battle/occupation remain separately reviewed work. This detached prototype makes
no production integration, scientific fidelity, native-byte acceptance or
performance claim.
