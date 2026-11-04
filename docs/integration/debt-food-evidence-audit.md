# Food coverage audit and fiscal payment evidence

This slice audits the existing Food, Granaries, Transactions, Finance and
DebtHolders views, then adds a focused payment ledger for the actual uncovered
finance fields. It changes only new viewer files. No backend, export, model,
default, shared panel or dependency lock changes are included.

## Food: existing coverage and one wording correction

There is no new food widget. The existing UI already exposes the supported
stored/flow/in-transit evidence, phase boundaries and navigation:

| Evidence | Existing UI/code | Existing regression |
| --- | --- | --- |
| Selected-region stored grain, target, purchases, releases and spoilage; keeper versus territorial controller; history stops at selected turn | `components/systems/Granaries.tsx`: granary selector, charts, keeper strip and selected snapshot table; `lib/granaries.ts` | `Granaries.test.tsx`: “renders exact historical stocks, targets, flows and keeper with navigation”; “scrubs keeper changes without retaining future selection data” |
| Unknown historical stocks/targets, no final-world fallback | `Granaries`: unavailable record states; `granaryAmounts` target coverage | “does not infer old missing stock from the final world or next observation”; “keeps an unobserved stock target unknown in the summary as well as the table” |
| Pending paid cargo distinct from stored grain; dispatch and arrival; original dispatch payment not charged again; arrivals release next turn | `Granaries`: “Public grain shipments” section and caption, `granaryShipmentsAt` source validation | “shows observed in-transit cargo, dispatch and arrival without adding cargo to stocks or charging arrival again” |
| Individual releases and recorded food-sufficiency before/after, purchases with sent/received/transit loss and treasury payments | `Granaries`: completed-turn movements table and goods-unit/phase note | “renders exact historical stocks, targets, flows and keeper with navigation” |
| Native mobility versus public procurement, source dates, completeness, unknown/partial frames, projected treasury legs versus whole-turn balances | `Transactions.tsx`, `lib/transactions.ts`, `transactionTypes.ts`: independently validated domains and source clocks; retained-frame history with seek | Existing `Transactions.test.tsx` source/frame regressions |

`grain_reserves.open_granaries` releases stocks into food sufficiency and market
supply before people eat (source lines 283–310); it does not export a separate
measured consumption total. The audited Granaries tile's `eaten this turn`
detail therefore needs the narrow wording `released before consumption this
turn`. That shared-panel edit and actual browser review are integration-owned.
Release, reserved/stored stocks and consumed quantities must not be relabeled
as interchangeable. Neither stock deltas nor ratios establish production or
consumption totals. The supported distinction is already represented by the
existing records and UI; duplicating them adds no evidence.

## Concrete finance gap

`FinancePanel.tsx` shows current public-finance stocks/indicators, debt/revenue
and price histories, aggregate totals and finance events. `DebtHolders.tsx`
shows creditor composition, current paid interest, boundary interest due,
arrears/default strips and write-off context. They do not display the exported
per-borrower fiscal borrowing, service and paid-interest fields together as a
chronological, source-addressed payment ledger. `DebtEvidence` fills that gap
and leaves the existing debt-holder breakdown in place.

The source audit confirms the exact arithmetic and scope:

- `finance.py:1284` sets `last_service = interest_paid + principal_paid`;
  `:1285` sets `last_interest = interest_paid`. The export at `:1486`/`:1487`
  carries these as `debt_service` and `interest`. Thus the latter is **paid**
  interest, not accrued/due interest. Principal paid can be shown as their
  difference, including prepayments made by the fiscal tick. If components
  are missing, invalid, or service is less than interest, principal is unknown.
- `last_borrowed` is fiscal `_borrow`, exported as `borrowed`. `extend_loan`
  can also add a later-phase loan without changing this field. The ledger
  labels fiscal borrowing and does not claim to reconcile whole-turn debt.
- Boundary `debt` is all outstanding principal; `foreign_debt` is a subset.
  They are displayed together and never added. No principal repayment is
  derived from changes in either stock, new loans, write-offs or global totals.
- `shortfall` combines unpaid upkeep and unpaid service. It is not an isolated
  principal/interest arrears amount. `arrears_turns` is running turns;
  `defaults` and optional per-borrower `written_off` are cumulative observations.
  The first known cumulative value is not interpreted as a current-tick loss.
- `domestic_credit.holders` supplies explicit named claim balances and boundary
  rates when recorded. These are not interest-payment receipts. No borrower
  payment is allocated to a creditor from a boundary share, and missing named
  allocations remain unknown. Each claim, rate and cumulative write-off retains
  its actual nested source pointer.
- Finance events use first actor borrower and later actors named creditors for
  `loan_taken`, `state_default` and `debt_written_off`; `fiscal_strain` identifies
  a subject. Event text remains context, with no parsing of numeric amounts or
  invented causal attribution. Duplicate selection keys cannot be pinned.
- Transaction receipts cover merchant mobility and public-granary purchases.
  They do not export debt-payment receipts or establish lender cash receipts.

All amounts use nominal treasury units, not goods, inflation-adjusted purchasing
power or personal wealth. Snapshot T follows completed tick T−1; events at tick
T become visible from snapshot T+1. Opening boundary 0 does not establish an
executed fiscal tick, so its flow columns stay unknown.

## Mount API and bounds

```tsx
<DebtEvidence
  bundle={bundle}
  currentTurn={currentTurn}
  civilizationIndex={stableWorldCivilizationIndexOrNull}
  onInspectEvent={(event) => { /* inspect, preserving selected turn */ }}
  onViewRecordedTurn={(turn) => { /* deliberately seek */ }}
/>
```

`window?: number` optionally supplies a fixed turn-window width. Otherwise a
native 10/20/50-turn selector is available. The model caps windows at 100 turn
positions, explicitly including unknown gaps; it does not mean the last N saved
rows. Events render the most recent 40 within that dated window. The wide ledger
scrolls inside a keyboard-focusable region, with scoped dark styles, native
disclosures and 44px controls for phone use.

Civilization identity is the supplied world-array index. A name is exposed only
after a dated civilization/finance/event observation through the selected turn;
duplicate canonical names refuse identity attribution. The exact selected
snapshot supplies balances and claims. Missing snapshots, absent borrower rows,
unavailable subsystem records and duplicated snapshots remain unknown, with no
carry-forward or final-world fallback. Input order and bytes remain unchanged.
All source references are bundle JSON pointers, not private paths or URLs.

## Checks and remaining integration

On Node 20.19.0 with existing shared dependencies, no installation or lock edits:

- 19 new model/component tests pass; the affected existing Granaries,
  Transactions and DebtHolders tests bring the focused run to 37 passes/5 files.
  Regressions cover mixed loans/write-offs versus explicit paid-principal
  arithmetic, malformed/old fields, paid-interest versus claims, source clocks,
  pruned/sparse rows, duplicate identities/keys, future-secret data, opening
  boundaries, window bounds, keyboard controls and independent inspect/seek.
- Full viewer lint, TypeScript project build and Vite production build pass.
- External logs are in
  `/workspace/shared/chronicler-multiwave-evidence/debt-food/`.

AppShell mounting, the shared release-caption correction, full viewer checks and
actual browser/phone validation remain root integration work. No broad browser
or simulation qualification is claimed by this new-file slice.
