# Diaspora ledger and remittances (RS4, `--remittances`, default off)

Recovery-skills phase, package RS4 ("migration, knowledge and household
support"; [plan](../superpowers/roadmaps/recovery-skills-phase.md), RS4). This
page records what the package implements, what it does not, and its evidence.
Merging it does not qualify it scientifically; every constant below is a
declared, uncalibrated modeling choice.

## Switch and modes

`--remittances` requires `--agents hybrid`. `--remittance-mode` chooses:

| Mode | Diaspora ledger | Eligibility and amounts | Money moves |
| --- | --- | --- | --- |
| `send` (default) | kept | computed | yes, one native pairwise operation per turn |
| `record_only` (control) | kept | computed identically | no |

A world that never enabled the switch has no container, snapshot key,
checkpoint flag or manifest entry (feature-off identity below). The snapshot
key is `snapshot.livelihoods.remittances`; the modules are
`src/chronicler/remittances.py` and `remittances_state.py`.

## The diaspora ledger

The native pool keeps only a person's birth region (`origin_regions`), and the
region a migrant last left exists only in `world.agent_events_raw`, which is
not checkpointed. The ledger is therefore the checkpointed record of who left
where. It is built in `after_agent_tick` from this turn's **applied** native
migrations: event type 2, which `tick.rs` `apply_migrations_observed` appends
for every move it applies (setting the region, displacement 5 and the
driver). L7 relocation moves are pending migrations applied by the same
function, so they are included; merchant trips, which change a merchant's
region without an event, are not migrations.

One entry per person, keyed by stable id: `{id, origin, departure_turn,
destination, arrival_turn, moves, qualified, last_sent_turn, sent_turns,
credited_milli}`.

| Applied move | Ledger |
| --- | --- |
| no open entry | opens one: origin = the region left (`departure`) |
| to the entry's origin | closes it as a `return` |
| anywhere else | `onward`: new destination and arrival turn; the origin is kept |
| no open entry and the ledger full | not recorded (`unrecorded`, counted as `entries_refused`) |

After the moves, an entry whose person is not alive in the post-tick pool
closes as a `death`. Two further closures are dated: `pool_reset` (below) and
`unobserved_gap`, when the ledger's last settled turn is not the previous
turn (the switch was off in between, so moves and returns may have been
missed).

Per region and turn the frame keeps losses and gains separately: departures
and arrivals (every applied move), returns home, qualified departures and
arrivals, and the stock of open entries after the turn in both directions
(`diaspora_out`: entries that left this region; `diaspora_in`: entries living
here), with the qualified share of each.

Knowledge flow. A mover who holds an RS1 workshop qualification at the
destination after the move (`apprenticeship.qualified_ids(world, to)`, the
RS0 seam: alive qualified ids present in a region) is a qualified departure of
the region left and a qualified arrival of the region reached; the entry
keeps the flag of its last move, and qualified returns are counted. Until RS1
lands the seam returns `[]`, so all these counts are zero; the counters,
frame fields and viewer columns are already in place and are tested with a
constructed `qualified_ids`.

## Remittances

Every open entry is evaluated each turn, in ascending id. The first failing
check is recorded:

| Check | Reason when it fails |
| --- | --- |
| adult (`age >= 20`, native `AGE_ADULT`) | `child` |
| settled: displacement 0 and `turn - arrival_turn >= SETTLED_TURNS` | `unsettled` |
| not on a merchant trip (`trip_agent_ids`) | `on_trip` |
| living at the ledger destination, outside the origin | `elsewhere` |
| has not settled a row this turn (`last_sent_turn`) | `already_sent` |

`elsewhere` is rare: in development runs it was a merchant left in another
region when a conquest unwound its trip (no migration event). Settled
excludes the many short famine moves (55–70% of moves in the audit) and every
onward or returning move, which resets the arrival.

An eligible sender then needs exactly one recipient among its own bonds
(`get_agent_relationships`): a Marriage (2) or Kin (5) bond with sentiment at
least `MIN_SENTIMENT`, whose partner is alive, living in the entry's origin
and not on a trip. The spouse comes first, then the highest sentiment, then
the lowest id. Bonds survive migration (sentiment decays about one point a
turn while apart) and the native death sweep removes bonds to the dead, so a
dead partner is never chosen. An eligible sender without one is **unmet**,
with the reason `no_bond` (no qualifying bond), `recipient_away` (partners
alive, none in the origin) or `recipient_on_trip`.

Amount, in whole milli-units of the sender's post-tick wealth `w`:
`gross = min(floor(SHARE × (w − RESERVE)), CAP)`, `fee = floor(FEE × gross)`,
`amount = gross − fee`. A linked sender with `amount = 0` is `no_surplus`.

| Constant | Value | Meaning |
| --- | --- | --- |
| `SETTLED_TURNS` | 5 | turns since the last arrival |
| `SHARE_PERMILLE` | 100 | 10% of wealth above the reserve |
| `RESERVE_MILLI` | 2000 | two wealth units the sender keeps |
| `CAP_MILLI` | 1000 | at most one wealth unit per sender and turn |
| `FEE_PERMILLE` | 150 | 15% of the remittance to the courier sink |
| `MIN_SENTIMENT` | 20 | bond sentiment a recipient needs |
| `MAX_ENTRIES` | 2048 | open ledger entries |

For scale: ordinary income is about 0.15–0.30 a turn and wealth decays 2% a
turn (`agent.rs`), so a sender holding 7.0 sends 0.5 (0.425 credited, 0.075
fee).

### The native pairwise operation

`wealth_transfer::remit(pool, turn, batch, rows)` (Rust), exposed as
`AgentSimulator.remit_wealth(turn, batch, [(sender, recipient, amount_milli,
fee_milli)])`, under purpose 4 `remittance` (appended by RS0):

- The whole call is validated first: unique senders, no sender as its own
  recipient, `amount > 0`, `fee >= 0`, `amount + fee` within the row limit,
  and an unused `(turn, purpose, batch)` key in the same key log
  `transfer_wealth` uses. A refused call changes nothing and consumes no key.
- Each row validates both parties before it changes anything: a dead, unknown
  (including a reused slot under another id) or travelling party makes the
  row `absent` and nothing moves.
- The sender pays `amount + fee`, limited by its own wealth (never below
  zero); what was taken is split pro rata between the fee (rounded down) and
  the carried amount. The recipient is credited the carried amount up to
  `MAX_WEALTH`, and the excess is refunded to the sender.
- Receipt rows `(sender, recipient, sent, fee, credited, refunded, status)`
  with status `applied` (0), `limited` (1: the sender could not pay in full,
  or something was refunded) or `absent` (2). `sent = fee + credited +
  refunded` always; the sender's net loss is `fee + credited`.
- Rows apply in order (ascending sender id), so a recipient's earlier credit
  counts towards a row it sends later. No random draws; the pool's agents are
  never added or removed.

A second read-only FFI method, `AgentSimulator.trip_agent_ids()`, returns the
stable ids of living agents on a merchant trip (loading or in transit),
ascending; the snapshot has no trip column, and `record_only` needs the same
trip filter without calling the transfer.

### Accounting

Per turn, checked before the frame is written (an imbalance raises):
`debited = credited + fee` and `sent = debited + refunded`. Per region, the
origin's `inflow_milli` (credited to recipients living there) and the host's
`outflow_milli` (its senders' net loss) and `fee_milli` are separate; summed
over regions they equal the turn's credited and debited totals. The fee goes
to a disclosed courier sink (carriers, tolls and losses on the road): it
leaves the economy, like the L7 travel sink, and is counted in `fee_milli`.
No treasury is touched, so no accumulator category is used. Nothing is
created: remittances move existing wealth between two living people.

## Placement, lifecycle and exclusions

- **Placement.** `after_agent_tick`, after the L7 fares (`relocation_costs`
  precedes `remittances` in `LIVELIHOODS_SWITCHES`; tested). It reads the
  post-tick pool: this tick's deaths, swept bonds and applied moves are in it.
  The credit is in the recipient's wealth before the next tick, so it reaches
  the household's pooled means from the next wealth phase on.
- **Failed tick.** Nothing is armed before the tick, and after-tick hooks run
  only after a successful tick (`livelihoods.wrap_agent_tick`), so a failed
  tick moves nothing and leaves the ledger unchanged (tested).
- **Exactly once.** `last_settled_turn` refuses a settled turn; each entry's
  `last_sent_turn` refuses a second row for one sender in one turn. The key
  log is transient, so the Python guards carry exactly-once across exact
  checkpoints (tested by resuming inside a live ledger).
- **Death.** A dead sender's entry closes as `death`; a dead recipient has no
  bond left; a party gone by the time of the transfer is `absent`.
- **Return.** A move back to the origin closes the entry; no remittance that
  turn or later until a new departure and settlement.
- **Household changes.** The recipient is chosen afresh each turn from the
  sender's current bonds, so a new spouse, a partner who moved away or a
  bond that decayed below the threshold change it; the credit goes to the
  recipient's own wealth, and the native household pooling does the rest.
- **Pool rebuild.** `on_pool_reset` (called by `livelihoods.bind_native_pool`
  when a run rebuilds the pool, as a legacy state-file resume does) closes
  every entry, recording `{turn, entries_closed, reason}`; it is silent when
  the ledger is empty, as in a fresh run.
- **Exclusions.** Remittances never touch the food allocation, never create
  income (no wage, no paid-work share, no registry reservation) and never
  replace inheritance (`household.rs`, inside the tick, unchanged).

## Observation and viewer

`snapshot_summary` copies the completed turn's frame, dated by
`source_turn`; when no turn was settled in the source turn every frame field
is `null` (unknown, not zero). The frame holds the funnel, the turn's totals,
region rows, bounded samples of moves (64), closures (64), receipts (64) and
unmet senders (32) with dropped counts, the last pool reset, lifetime
counters and the parameters. The full ledger is state, not observation; it
appears in checkpoints and the final `world_state`.

The strict reader `viewer/src/lib/remittances.ts` (`remittancesAt`) rejects a
misdated, malformed or half-observed record and any receipt or total that
creates or loses money, any money moved by `record_only`, and region sums that
do not match the totals. The panel
`viewer/src/components/systems/Remittances.tsx` names senders and recipients
by stable id with their bond and sentiment, origin and destination regions,
requested amounts, fees, credits, refunds and statuses (dated), the unmet
senders and why, the per-region diaspora (losses, gains, returns, skill
departures and arrivals, stock), closures and moves. It is not mounted; the
lead mounts it.

## Evidence

Native extension built from this branch with
`/home/user/wt/tools/build_native.sh` (SHA-256 in the lane report).

### Tests

- `chronicler-agents/src/wealth_transfer.rs` (`cargo test --lib
  wealth_transfer`): full payment; sender-limited with the pro-rata fee and
  an exact remainder; a zero-wealth sender; ceiling refunds (partial and
  total); dead, unknown and travelling parties; a reused slot under another
  id; refused calls change nothing; one key per (turn, purpose, batch), shared
  with `transfer`; ordered rows and conservation.
- `tests/test_remittances.py` (offline, constructed state with a fake pool):
  the ledger's departure, onward move, return and death, per region; the
  bound; knowledge flow through a constructed `qualified_ids`; pool reset and
  unobserved gap; spouse-first recipient order; amounts; every ineligible and
  unmet reason; `record_only` computes identical rows and moves nothing; a
  ceiling refund; an absent party; a returning or dead sender; once per turn
  and an exact JSON/pickle resume; dated snapshot copies; a failed tick; a
  stale native build.
- `tests/test_remittances_native.py` (real extension, template seed 7): every
  receipt against live bonds, settledness and the pool's wealth changes, with
  per-turn and per-region closure, over 24 turns with returns, deaths and
  unmet senders; direct native refusals, an unknown party and the shared key;
  a rebuilt pool; a `record_only`/`send` fork from one exact checkpoint;
  exact resume inside a live ledger; feature-off identity, and a
  `record_only` run whose history equals the feature-off run except its own
  snapshot key; ordering after L7 fares.
- Viewer: `viewer/src/lib/__tests__/remittances.test.ts` (constructed records
  and one natural record, `viewer/src/__fixtures__/remittances_natural_record.json`)
  and `viewer/src/components/systems/__tests__/Remittances.test.tsx`.

### Feature-off identity against the parent commit

The parent commit `52711f27` with the RS0 extension (`9277341a…`) against this
branch with its own extension, switch absent or `--no-remittances`: the
bundle (without `generated_at`), `state.json` and `agent_events.arrow` were
byte-identical for template seed 7 (40 turns), procedural 32×10 seed 11 (40
turns, `--no-remittances`) and template seed 7 with `--workshops
--relocation-costs --workshop-payroll` (40 turns).

### Development measurement (natural, not held)

Template seeds 7 and 23 and procedural 32×10 seeds 11 and 17, 80 turns, each
with `send` and its `record_only` control. Counts are lifetime; a
"sender-turn" is one open entry evaluated in one turn. Development only: four
worlds, nothing tuned, not a held screen.

| World | Arm | Moves | Returns | Deaths abroad | Sender-turns | Eligible | Linked | Unmet | Rows | Senders | Pairs | Credited | Fees |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| template 7 | send | 1686 | 222 | 247 | 13057 | 4582 | 522 | 4060 | 483 | 105 | 132 | 142.8 | 25.0 |
| template 7 | record_only | 1713 | 235 | 226 | 13496 | 5031 | 596 | 4435 | 549 (not sent) | 109 | 132 | 0 | 0 |
| template 23 | send | 1321 | 259 | 159 | 9490 | 3598 | 506 | 3092 | 496 | 83 | 115 | 213.0 | 37.4 |
| template 23 | record_only | 1311 | 238 | 139 | 10382 | 4255 | 560 | 3695 | 549 (not sent) | 91 | 116 | 0 | 0 |
| procedural 11 | send | 2332 | 253 | 535 | 20370 | 8230 | 759 | 7471 | 701 | 120 | 148 | 210.3 | 36.8 |
| procedural 11 | record_only | 2160 | 246 | 602 | 19135 | 7846 | 938 | 6908 | 872 (not sent) | 151 | 186 | 0 | 0 |
| procedural 17 | send | 3917 | 514 | 625 | 31494 | 11031 | 1393 | 9638 | 1244 | 251 | 323 | 343.7 | 60.0 |
| procedural 17 | record_only | 4155 | 515 | 567 | 33899 | 12427 | 1610 | 10817 | 1438 (not sent) | 279 | 336 | 0 | 0 |

- **Activation.** The first row came in turn 6–14. Of eligible sender-turns,
  9–14% were linked; nearly all unmet ones were `recipient_away` (95–97% of
  unmet): households move together, so the spouse and children are rarely
  left in the origin. `no_bond` was 2–4% and `recipient_on_trip` under 2%.
  Linked senders per turn (about 6–20) match the audit's 8–32 settled
  migrants with a strong bond in the region they left.
- **Outcomes.** Every row was `applied` except four natural `limited` rows in
  procedural 17: a sender holding 2.4 paid the fee to a kin already at the
  wealth ceiling, and the carried amount was refunded (0.127 in all). No row
  was `absent` and no ledger entry was refused. Natural examples: template 7,
  turn 11, #130 in Crystalfen Marsh to kin #219 in Iron Peaks (sentiment 51;
  0.028 credited, 0.004 fee). Of 105 senders in template 7, the stream ended
  for 49 because the recipient moved away, 20 by death, 18 by the sender's
  return, 5 with the recipient on a trip and 1 by bond decay.
- The two arms diverge after the first transfer (wealth feeds decisions), so
  end-of-run population and treasury differences between arms are trajectory
  noise at this size, not effects.

Reproduce (in a worktree with this branch's native extension):

```sh
PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 PYTHONPATH=src python -m chronicler.main --seed 7 --turns 80 \
  --agents hybrid --simulate-only --remittances --output out/t7_send/chronicle.md --state out/t7_send/state.json
PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 PYTHONPATH=src python -m chronicler.main --seed 7 --turns 80 \
  --agents hybrid --simulate-only --remittances --remittance-mode record_only \
  --output out/t7_ctrl/chronicle.md --state out/t7_ctrl/state.json
PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 PYTHONPATH=src python -m chronicler.main --seed 11 --turns 80 \
  --worldgen procedural --regions 32 --civs 10 --agents hybrid --simulate-only --remittances \
  --output out/p11_send/chronicle.md --state out/p11_send/state.json
```

The records are `history[t].livelihoods.remittances` in each
`chronicle_bundle.json` (read with `chronicler.bundle_codec.load_bundle`).
Constructed activation is in the offline tests (labelled constructed); the
natural examples above and the viewer fixture are from ordinary seeds.

## Limits and open questions

- The ledger starts with the first move observed while the switch is on; a
  migration before that is invisible, and an onward migrant keeps its first
  recorded origin as home (the region it left first, not the last one).
- Recipients are chosen from the sender's side of the bond; a reciprocal
  sentiment is not required.
- A recipient at the wealth ceiling still costs the sender the fee; the
  carried amount is refunded. The package does not judge whether a recipient
  needs support (a richer partner can receive).
- The courier fee is a sink, not income for anyone.
- No narrative events; remittances appear only in the snapshot, the state and
  the viewer panel.
- The constants are uncalibrated; the 200-seed and procedural qualification
  gates were not run.
