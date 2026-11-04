# Native merchant observation receipts: pre-registration

Registered before implementation on `fd054a23`, 2026-10-28. This is a
default-off, read-only observability substrate. It creates no fee, insurance,
loan, firm, private cargo title or new economic settlement.

## Accounting boundary

Hybrid merchants reserve and move shared regional stock. Departure queues an
origin debit; arrival queues a gross destination credit. The following goods
economy consumes these queues and applies transit decay. A receipt of either
native operation is not a receipt of final macro settlement. Shadow-mode cargo
is virtual. The merchant's stable agent ID identifies its custodian, not the
legal owner of the goods. Region controllers are observations at the recorded
operation, not proof of cargo title or insurance liability.

Current merchant cash income is regional delivered margin divided among the
region's merchants; it is not a private per-voyage sale settlement. Grain
inspection fees and insurance liability are deferred until payer, receiver and
realized cash boundaries have an explicit closed contract.

## Frozen first slice

- Instrument the existing sequential merchant mobility loops: reservation
  committed, departure queued, reservation cancelled, route replanned, return
  queued, sea crossing/raid, arrival queued, and mobility-end active commitment.
- Include stable merchant ID and observed civilization, native source turn,
  semantic operation, from/to/origin/destination regions, good, gross quantity,
  observed regional controllers and physical-versus-shadow basis.
- Keep the old sea log, event/stat/snapshot schemas, arithmetic, stream draws
  and order unchanged. New buffers/configuration are derived native transients
  excluded from exact native payload bytes and schema identifiers.
- A read-only getter returns the same current frame on repeat reads. Default
  frame capacity is 4,096, with a maximum configurable bound of 65,536; excess
  rows increment an observable dropped count. It never silently truncates.
- The optional Python journal owns voyage identity. Only an actually observed
  reservation start creates `(stable merchant ID, start turn)` within a
  caller-provided trajectory namespace. Imported mid-trip commitments remain
  unidentified. A per-frame row position or elapsed-duration estimate is not
  a voyage identity.
- Persist only the active identity mapping, latest frame, its fingerprint and
  processed source turn, plus bounded aggregate counters. No policy or voyage
  history grows over time. Final active observations are from mobility end,
  before later tick deaths, not a promise the agent survives the full tick.
- A complete frame can refresh its observed-active mapping. An incomplete
  frame invalidates cross-frame identity continuity rather than inferring
  tracking closure or financial entitlement. All receipts remain explicitly
  unsuitable for automatic fees or claims in this first slice.
- Death and conquest cancellation occur outside these instrumented loops;
  their exact reasons/quantities are not claimed. Later disappearance from a
  complete mobility-active set is not itself a cargo-loss receipt.

## Acceptance and controls

Native controls run identical agents, regions, route graphs and seed streams
with recording off/on: pool/event/economy behavior and serialized native
payloads/schema must match. Test reservation shrink/cancel, departure, arrival,
route disruption, full-probability raids, virtual cargo, cap overflow, graph
replacement and repeated reads. Never run another raid RNG draw to log it.

Python controls cover observed-start versus imported mid-trip identities,
repeated identical frames, conflicting same-turn frames, reversed/future turns,
ownership labels, slot reuse through stable IDs, overflow invalidation,
disabled omission and exact continuation while active/in transit. Restoring a
checkpoint reconfigures the native transient recorder before the next tick;
the Python journal retains the preceding frame for historical viewing.

Runtime work is O(native mobility work + emitted rows), bounded by the chosen
frame cap, with no all-agent scan per receipt and no retained voyage history.
Recording does not alter the simulation; any performance overhead is measured
separately. A passing bounded selection is not scientific qualification for
future fees, standards, insurance or borrower behavior.
