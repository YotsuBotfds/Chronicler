# Recovery chain view (viewer, PL5c)

Lane PL5c of the phase "productive recovery and household livelihoods"
([plan](../superpowers/roadmaps/productive-recovery-phase.md)). The view lets a reader
follow, in one region of one loaded run, the phase's story: a community needs timber,
shifts labour to obtain it, repairs a granary, pays workers, and those households buy
food. Beside each link it shows the tradeoffs: farm labour away, the forest drawn
down, budgets short and people priced out. It is a viewer feature only: nothing in the
simulation changed, and every switch it reads stays default off.

Source:

- `viewer/src/lib/recoveryChain.ts`: the reader. It composes the packages' own strict
  readers and only selects one region's rows from what they accept.
- `viewer/src/components/systems/RecoveryChain.tsx`: the view.
- `viewer/src/components/systems/LivelihoodsPanel.tsx`: mounts it first on the
  **Livelihoods** tab when any snapshot of the run records repair projects (RS2),
  timber supply (PL1), recovery crews (PL3) or household retail (PL4). It reads the
  whole run, so it stays mounted while scrubbing, including at snapshots without a
  livelihoods record, where it says so.

## What it reads

| Record | Reader (unchanged) | What the chain takes for the region |
| --- | --- | --- |
| `livelihoods.repair_projects` (RS2) | `repairProjects.repairProjectsAt` | open projects and those closed in the source turn; this turn's receipts (stalled or worked, with reasons); workshop crews' wages; unmet needs |
| `livelihoods.timber_supply` (PL1) | `timberSupply.readTimberSupply` | the need row (want, free, on the road, gap, launch or refusal reason); live expeditions from the region (`home`) and those that ended in the source turn; their receipts (crew, stage, cut, wages, farm labour away, the forest slot's stock); the store row |
| `livelihoods.timber_stock` (L3) | `timberStock.timberStockAt` | the account of each forest slot the region's expeditions cut |
| `grain_reserves.storage` | `granaries.granaryStorageAt` | the region's granary condition and capacity |
| `livelihoods.recovery_crews` (PL3) | `recoveryCrews.readRecoveryCrews` | granary crews in the region: members by id, each member's wage, farm labour removed; granary receipts with nobody on the crew (shown as "no crew formed", not as a paid row); workshop crews' members and the farm labour they took (their wages are on the RS2 receipt) |
| `livelihoods.household_retail` (PL4) | `householdRetail.readHouseholdRetail` | pilot or not, provisioned persons and children, households buying, paid, sold, price, priced-out persons, children and households; the person sample's rows in the region |
| `livelihoods.remittances` (RS4) | `remittances.remittancesAt` | the region's inflow and recipients |
| `livelihoods.food_allocation` (L2) | `foodAllocation.foodAllocationAt` | the region's food sufficiency, beside the farm labour taken (retail's own sufficiency for a provisioned pilot region, which L2 leaves to retail) |

Each package at each snapshot is one of:

- **off**: no snapshot of the run records it. The view says "Off: … is off in this
  run" and leaves the link out of the turn table and the strip.
- **unknown**: the package is on but this snapshot does not say: no record here, no
  livelihoods record, or a null frame (a turn without Phase 2). The view says
  "Unknown, not zero". A frame that may be incomplete is not read as complete: when
  PL1 dropped need rows, a region without a row has an unknown need; when the PL3
  frame is at its row limit, the region's wages are marked possibly incomplete.
- **rejected**: the package's reader refused the record. The view says "Unknown,
  rejected as malformed" with the reader's reason when it gives one
  (`repairProjectsAt`, `timberStockAt`, `remittancesAt`, `foodAllocationAt` and
  `granaryStorageAt` return only null, so no reason is available for them).
- **known**: the record says; an empty value is "on, nothing happened" ("No repair
  project open in the region", "Not a pilot region this turn", "Nothing came in this
  turn", "Total paid in the region: 0 coins").

A link that lists something but not this turn's outcome is unknown, not recorded: an
open RS2 project whose turn's receipts are null (whether it worked or stalled is
unknown), and a pilot region that was not provisioned. The record-only retail control
is the exception: it provisions no one by design, and the view says so.

Run totals add known snapshots only and name the links unknown at some snapshot,
wholly or in part (a wage source unknown, an expedition's receipts, a forest account
or the store's holders unknown). Every total over a link with an unknown snapshot
(stalls, timber delivered, farm labour, wages, purchases, remittances) reads "at
least …", and a snapshot's wage total with an unknown source reads "unknown" or "at
least …": an unknown is never summed as zero.

## The links and how they are joined

| Link | Joined to the chain by | Why |
| --- | --- | --- |
| Repair need (RS2) | stable id | the project id names its asset, region and this turn's stall reasons |
| Woodcutting expedition (PL1) | **region only** | PL1 plans one timber need per region, summed over its open projects; the expedition, its need row and its crew are by id |
| Forest stock (L3) | stable id | the expedition's receipt names the forest region and slot of the L3 account; that account's extraction can include other cutting |
| Timber store to repair | **region only** | the store is per region and a project's receipt does not say how much of its timber came from it. When the store held timber for repairs and only one project in the region held timber that turn, the view says the store's hold can only have gone to it (and how much of its hold came from the region's other free timber), and still calls the link regional. When the store held nothing, the view says the repairs' timber came from the region's other free timber: an expedition delivers in its homecoming, after the turn's repairs have taken their timber (snapshot 27 in the fixture: 15.17 delivered, 0 held, while project 0 held 1.97) |
| Granary condition | stable id | a granary project's asset is the granary's region index |
| Wages paid (PL3, RS2, PL1) | stable id | each receipt names its project or expedition and the workers' stable ids; wages are placed in the project's region (PL3, RS2) or the expedition's home region (PL1) |
| Food purchases (PL4) | **region only** | the snapshot sums the native money rows to region totals |
| Remittances in (RS4) | **region only** | the region's inflow total |

What cannot be linked by id, and is not claimed:

- **Who bought food.** Purchases survive only as region totals. By id only the
  24-person retail sample survives, with a ration and a status, not a payment. The
  view lists sample rows in the region whose person was paid in the region at this
  or an earlier snapshot, or who is in the household keyed by such a worker (a
  household's key is the smaller id of a co-resident couple, and a child takes a
  parent's key), with the snapshot of the worker's first wage there. A turn's Phase 2
  wages are paid (`livelihoods.finish_phase2`) before that turn's agent tick
  provisions households, and both are recorded at the same snapshot, so a wage of
  this snapshot already counts. The offline finder
  (`scripts/productive_recovery_examples.py --chain`) is stricter: it counts only
  wages of an earlier snapshot. A worker keyed by a spouse's id is found only when
  sampled; with 24 people a turn, no match is no evidence.
- **Who was paid, by id.** A PL3 member counts as paid when their own wage is above
  zero (a wage the wealth ceiling refused, or rounded to zero, does not count). An RS2
  workshop crew or a PL1 crew counts as paid when its receipt paid wages and the
  ceiling refused none; with a refusal the receipt does not say who went unpaid, so
  nobody on it is counted.
- **Which project an expedition served** and **which project used the store's
  timber**: regional, as above.
- **Per-person wages of RS2 workshop crews and PL1 woodcutters**: their receipts
  carry the crew's ids and one total, so the view shows the total and the ids, not a
  split. PL3 records each member's wage. A workshop crew that PL3 widened has its
  wages on the RS2 receipt (PL3 records them as zero), so they are counted once, from
  RS2.

## The view

- **Heading** `Recovery chain · snapshot N`, the run's switches on and off, and a
  **Region** picker (a labelled select). It starts on the shell's selected region,
  else on the region whose chain goes furthest (the most of: a stall for want of
  timber, timber delivered home, the store holding timber, wages paid, food bought;
  then the most timber delivered), marked "(fullest chain)". A region the reader
  picks stays picked.
- **A run summary** for the region: stalls, expeditions, timber delivered, farm
  labour taken from farming by source (PL1 woodcutters, PL3 granary crews, PL3
  workshop crews; each source said off when it is), granary condition first to last,
  wages by source and people paid by id, purchases and priced-out snapshots,
  remittances in.
- **The chain at the scrubbed snapshot**: one row per link with what the record says,
  how it is joined, and its tradeoff (budget limits on the repair and the expedition,
  farm labour away with the woodcutters beside the region's food sufficiency, the
  forest's share of capacity and its change, farm labour taken by PL3 granary and
  workshop crews and wages refused by the wealth ceiling, people priced out). At
  phone width each row stacks with its labels; the table keeps explicit ARIA roles.
- **The chain over snapshots**: a strip (one row per link that is not off: recorded,
  tradeoff, unknown) and its text form, a turn table of every snapshot the strip draws
  (any link recorded or unknown, and the current one; the note says how many where
  every link recorded nothing are hidden), 25 rows at a time ("Show 25 more (N not
  shown)", then "Show the last N"), "Show every snapshot" for all. Each row's snapshot is a button that seeks the timeline, and the
  current row is marked. The strip's rows are images named by their runs (for
  example "Repair need (RS2): recorded, snapshots 13-14; stalled, snapshot 15"); a
  run never spans a missing snapshot.

## Tests

- `viewer/src/__fixtures__/recovery_chain_natural_records.json`: eleven snapshots of
  a natural run (template seed 23, 60 turns, every chain switch; the command and the
  extraction are in its `note`), the chain of granary project 0 in Sapphire Coast.
  It was written from the run's bundle by keeping, for snapshots 13, 14, 15, 20, 21,
  22, 23, 26, 27, 28 and 29, the livelihoods `schema_version` and the seven chain
  records unchanged, and `grain_reserves` as its `source_turn` and `storage` only.
- `viewer/src/lib/__tests__/recoveryChain.test.ts`: the natural chain link by link
  (stall, expedition and crew, delivery, store hold, PL3 wages and crew ids, repair,
  completion, purchases, the sample by id from the snapshot of the wage); off,
  unknown, zero and rejected; RS2 and PL1 receipts, a pilot's provisioning, a forest
  account and the store's holders unknown, each kept out of the totals; partial wage
  sources; need rows dropped; the granary joined by kind and asset, not by region;
  a workshop crew's wages counted once and its farm time counted; empty granary
  crews; budget limits (a no_coins stall, a recall, an unpaid woodcutting turn, a
  refused wage) and who counts as paid; runs with only some switches. Constructed
  variants remove or edit records of the natural run with the helpers in
  `recoveryChainFixture.ts`, which keep each reader's books closed, and are labelled.
- `viewer/src/components/systems/__tests__/RecoveryChain.test.tsx`: the view's text,
  joins and tradeoffs at natural snapshots (including the store that held nothing at
  snapshot 27), the region picker, the strip and its turn table (unknown snapshots
  listed), seeking, off/unknown/zero/rejected wording, "at least" totals, empty crews,
  refused wages, the record-only control (a natural record of template 7), subsets,
  table roles, and mounting on the Livelihoods tab.

## Browser QA

`viewer/scripts/qa-recovery-chain.mjs` (opt-in; Playwright and Chromium) runs the real
simulation on a development world, one process at a time, and checks the view on a
production build. It refuses any seed outside the development worlds (template 1, 3,
7, 9, 11, 23, 42; procedural 32x10 7, 11, 13, 17, 21, 31). From `viewer/`, after
`npm run build`:

```sh
PYTHONPATH=../src PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 \
  node scripts/qa-recovery-chain.mjs --out /path/outside/the/repo \
  --python ~/.venvs/native-hrn2/bin/python --seed 23 --turns 60
```

`--out` must be a new directory, or one an earlier run of the script created (it
writes `.qa-recovery-chain-output` there and empties only such a directory). It
refuses the current directory, the repository, `viewer/`, anything that holds them
and anything inside the repository. `--python` must import `chronicler` and a native
extension built from this source's Rust (`scripts/check_python_env.py --expect native` runs first; its output is in the
report). The chain run uses `--agents hybrid --simulate-only --grain-reserves
--public-grain-shipments --scholarship --techniques --academy-services --grain-storage
--food-allocation --workshops --operating-wear --repair-projects --timber-stock
--household-retail --household-retail-boundary paid_work --timber-supply
--recovery-crews --remittances`. Parts (`--parts chain,variant,subset`):

- **chain**: at 1440x900 and 390x844, the bundle is opened with "Open saved world
  file". The expected chain of every region and snapshot is read from the bundle with
  `chronicler.bundle_codec`, independently of the viewer's readers. The default
  region must have a real chain and go furthest by the same rule. At the stall, the
  delivery, the first store hold, the first paid granary crew, a purchase and the last
  snapshot (reached with slider keys), every link's text must show that snapshot's
  values and its join: stall reasons, expeditions, the store row and whose hold it
  can be (attributed by elimination only when the store held timber), granary
  condition, PL3 wages and crew ids, the farm labour PL3 granary and workshop crews
  took, pilot persons and purchases, remittances. The run's first repair that held
  timber while its region's store held none is visited too, wherever it is. The
  region picker moves to another region and back; the strip
  is a labelled group whose stalled runs are exactly the turn table's stalled rows and
  the bundle's; "Show every snapshot" lists every snapshot; a seek button moves the
  slider. No NaN or undefined, no console errors, no page overflow at 390 px.
- **variant**: a constructed variant (labelled, written to `--out`) with remittances
  removed at one snapshot, the retail frame and PL3 receipts blanked at the next and
  timber supply misdated at the one after: the view must say unknown, not zero, and
  rejected as malformed there, the run's wage total "at least", and read the next
  snapshot normally.
- **subset**: a second run of the same world with only `--food-allocation --workshops
  --repair-projects --recovery-crews --household-retail --household-retail-boundary
  paid_work`: the view mounts, names the off switches, says off for the expedition,
  forest, store and remittance links and leaves them out of the turn table.

Run on 2026-11-06 after the review fixes (production build of
`claude/pl5c-chain-viewer`, extension `101a4cd5…` in `~/.venvs/native-hrn2`, Chromium
153 from the pre-installed Playwright): template seed 23, 60 turns: chain 329/329,
variant 10/10, subset 26/26 checks, no console or page errors. The default region was
Amber Valley (stall 28, delivery 32, store hold 33, granary crew first paid 27,
purchase 28); the store that held nothing was Sapphire Coast at snapshot 27.
Procedural seed 31, 120 turns (`--worldgen procedural --parts chain`): chain 323/323;
default region Methys Shore (stall 13, delivery 17, store hold 18, crew paid 18,
purchase 19); the store that held nothing was Tanis Coast at snapshot 31. On that
bundle the Livelihoods tab with the chain opened in about 0.4 s, and the run summaries
of Jamagur Grasslands and Chajak Downs gave 108.6 and 14.85 farmer-turns taken from
farming, the bundle's own sums over the three sources.
