# Detached memome demonstration

Contract: `chronicler-m68a-detached-v1`. This is a default-off, standard-library
prototype for immutable eight-slot storage and synchronous transmission. It
does not complete M68a or M67 and is not connected to AgentPool, WorldState,
the runner, native code, snapshot schemas, the production CLI or the viewer.
Independent review of the exact delivered commit is required before private
integration.

## Planning basis and limits

The governance roadmap at
`docs/superpowers/roadmaps/chronicler-phase8-governance-roadmap.md:1272`
lists eight slots, D=2 conformism, prestige and compatibility, with M67 as the
full milestone prerequisite. Its pre-lock decision at line 1288 specifies the
algebraic probability. The design discussion at
`docs/superpowers/design/phase8-9-brainstorm-synthesis.md:234-267` describes
the broader intended production feature.

The current `chronicler-agents/src/culture_tick.rs:82-108,143-196` uses three
cultural values and production RNG; it is not an eight-slot memome. Only stable
unit subject labels from its basic and named weighting tests at lines 204-239
are reused here. Their explicit eight-slot assignments, contact groups, weights
and draws are ordinary unit tables, not simulated agents or new scenarios.

No production wealth is read. Supplied weights do not claim to implement wealth
or named-agent prestige semantics. Candidate selection is explicit caller input;
sampling, personality, environmental coupling, synergy amplification, M68b
behavioral effects and production adapters are deferred. Performance claims
from planning documents have not been measured or adopted. M71 is not
implemented. Held serialization `507ef977`, closed V3 recovery and scientific
worlds/seeds/campaigns are outside this increment.

Full A01/native-byte acceptance remains withheld. This increment preserves the
baseline failure at `root.metadata.household_stats[0].keys/order`; it neither
rebuilds native code nor changes key ordering.

## API and exact semantics

`advance(ledger, batch, policy, enabled=False)` returns a frozen `Result`.
All records are frozen dataclasses and all collections must be immutable tuples.
Participants have a supplied nonempty stable ID, contact group, exactly eight
byte-sized trait slots and a positive exact integer prestige weight. Booleans
are rejected wherever an integer is required.

The mandatory illustrative policy supplies its exact contract version, a
distinct byte-sized empty sentinel, a nonempty trait domain, eight allowed-slot
domains, a complete symmetric compatibility table, diagonal semantics and a
positive integer draw scale. Empty slots cast no vote and cannot be adoption
candidates. Empty allowed-slot domains can intentionally disable a slot.
Diagonal values 0 and +1 permit repeated traits; -1 diagonals are unsupported
in v1. Every starting participant must be pairwise compatible. Compatibility
-1 blocks adoption; 0 and +1 permit it without any probability boost.

V1 makes frequency **slot-local**: within the recipient's frozen contact group,
each participant with a nonempty trait in the proposed slot casts one vote
weighted by that participant's supplied prestige. The recipient is included
when their slot is nonempty. Other slots and contact groups do not vote. For
candidate weight `w` and electorate weight `W`, use exact integer arithmetic:

```text
f = w/W
P = w² / (w² + (W-w)²)
threshold = floor(draw_scale * w² / (w² + (W-w)²))
accept if draw < threshold
```

`W=0` has threshold zero. Draws are supplied exact integers in
`[0, draw_scale)`. One proposal per recipient per tick is permitted, with a
globally unique proposal ID. Every proposal is validated before computation.
All frequencies and compatibility checks use the frozen previous ledger.
Compatibility checks exclude the replaced slot and inspect every other
nonempty slot. Outputs are sorted by stable participant ID and proposal ID.

Receipt reason precedence is `unchanged`, `incompatible`, `empty_electorate`,
`absent_candidate`, `probability_rejected`, `accepted`. Each receipt includes
the supplied draw, old and candidate traits, slot, weighted numerator and
denominator and integer threshold. This makes zero-electorate and incompatible
outcomes explicit even when several rejection conditions apply.

The batch must advance exactly one turn; gaps require explicit intermediate
batches. Policy, participant membership, groups and prestige remain fixed for
a ledger. Comparing supplied weight changes requires a separate starting
ledger. No automatic production weight update is implied.

## Replay, resume and disabled behavior

The ledger retains genesis plus the policy and every canonical admitted batch,
resulting participant table and receipt. Admission covers all proposals,
including rejected ones. Admitted IDs cannot be reused on later ticks, with
either identical or conflicting payloads. Identical batch replay returns the
original tick's ledger and receipts with `replayed=True`; a conflicting replay
aborts. Replaying an older tick returns its historical prefix, not the newest
ledger: callers should use this result as a historical receipt and retain their
latest cursor. History is never silently pruned.

`checkpoint_json(ledger, policy)` persists the entire experiment ledger and
admission history together as canonical JSON. `restore_checkpoint(text)`
requires exact fields, rejects duplicate keys and nonfinite constants, and
recomputes every transaction from genesis to verify saved state and receipts.
Checkpoint parsing does not load a production snapshot. History validation
uses O(history × participants × proposals), intentionally favoring reviewable
correctness over large-scale performance in this bounded demonstration.

Disabled calls validate the policy, ledger and proposed transaction, then
return the caller's exact unchanged ledger, no receipts, no admitted IDs and
`disabled=True`. Invalid requests still fail. The kernel reads no clock,
environment, files, RNG or production modules and mutates no caller object.

## Run and verification

From a restored checkout with Python 3.13:

```sh
PYTHONPATH=src python3.13 -m unittest discover -s tests -p test_memome_experiment.py -v
python3.13 scripts/memome_demo.py
python3.13 scripts/memome_demo.py --enable
PYTHONHASHSEED=1 python3.13 scripts/memome_demo.py --enable > /tmp/memome-1.json
PYTHONHASHSEED=999 python3.13 scripts/memome_demo.py --enable > /tmp/memome-999.json
cmp /tmp/memome-1.json /tmp/memome-999.json
```

The suite uses `unittest` so no production fixtures or additional dependencies
are needed. The supplied environment has Python 3.13.5 and no pytest; the
standalone suite is the focused verification path. No repository dependency
file changes are needed.

Tests cover hand-calculated `f=0,.5,1,1/3,2/3,5/6` cases and exact draw
boundaries; empty voters; slot locality; supplied weight changes; initial and
adoption incompatibility; diagonal/+1 semantics; malformed policies, ledgers
and mixed batches; boolean rejection; immutability; reversed table order and
synchronous votes; replay conflicts, gaps and proposal-ID reuse; interrupted
resume and corrupted receipts; default-off behavior; fresh subprocess output
under different hash seeds; and import/global-RNG isolation.

The demo explicitly admits three ticks, including minority and majority
adoption, a supplied weighted pair, an incompatible attempt and an absent
candidate. Each tick round-trips through a checkpoint. All table choices and
the Knowledge/Cunning incompatibility are illustrative, not calibration.

## Ownership and handoff

This increment adds only:

- `src/chronicler/memome_experiment.py`
- `scripts/memome_demo.py`
- `tests/test_memome_experiment.py`
- `docs/experiments/memome.md`

All baseline source, dependencies, schemas, fixtures, production defaults,
native code and CLI registries remain byte-identical. The private review bundle
contains the complete offline Git bundle, these four files, validation evidence,
their manifest and restore instructions. Restore into a new private checkout,
verify archive hash/size and safe members before extraction, verify the payload
manifest and exact Git identities, and rerun the focused suite. Do not integrate
until an independent reviewer has assessed the actual commit bytes.
