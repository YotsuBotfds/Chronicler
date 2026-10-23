# Read-only campaign admission from captured snapshots

Detached M60a input adapter, contract
`chronicler-campaign-snapshot-adapter-v1`, adapter version
`campaign-snapshot-adapter-v1`. Four added paths only:
`src/chronicler/campaign_snapshot_adapter.py`,
`scripts/campaign_snapshot_plan.py`,
`tests/test_campaign_snapshot_adapter.py` and this document. Every existing
source file, schema, fixture, test, native artifact, CLI registry entry and
reviewed kernel is unchanged. No dependency, lockfile, feature flag, production
hook or Python integer-limit change is included.

This is plumbing, not a new campaign algorithm. It turns one already captured
snapshot observation plus explicit caller logistics into a frozen admission
plan produced by the reviewed public M60a seam. It adds no simulation
mechanic, no runtime mutation and no enlistment.

## What it does

```python
from chronicler.campaign_logistics import Policy
from chronicler.campaign_snapshot_adapter import (
    RegionBinding, admit_snapshot_plan, plan_bytes,
)
from chronicler.turn_artifacts import AgentRows, Stamp

bindings = (
    RegionBinding(0, "r0", ("r1", "r2")),
    RegionBinding(1, "r1", ("r0",)),
    RegionBinding(2, "r2", ("r0",)),
)
plan = admit_snapshot_plan(
    agent_rows=AgentRows(Stamp(7, "phase10_entry"), captured_batch),
    expected_source_turn=7,
    civ_id=1,
    selected_ids=(7, 8),
    region_bindings=bindings,
    topology_version="existing-three-region-v1",
    policy=Policy(...),                 # mandatory, caller owned
    campaign_id="snapshot-plan",
    staging=1, target=2,
    kits={7: 8, 8: 8},                 # mandatory explicit sandbox kits
    morale={7: 800, 8: 790},           # mandatory explicit campaign morale
    stocks={0: 0, 1: 0, 2: 4},         # mandatory explicit sandbox stocks
)
```

`plan_bytes(plan)` is the canonical JSON document and
`plan_document(plan)` is the same value as plain Python data:
`json.loads(plan_bytes(plan)) == plan_document(plan)`. Tuple-valued record
fields such as `policy.ordering` appear as JSON arrays in that document while
the plan's own records stay tuples.

The document contains the copied inputs, the provenance block, the public
kernel admission result and one `plan_digest`. That digest is the SHA-256 of
the canonical plan body with the `plan_digest` key removed, so hashing the
emitted bytes as a whole does **not** reproduce it; a caller verifies it by
removing that key and hashing the rest.

The returned `AdmissionPlan` is a frozen slots dataclass carrying: the source
identity, campaign/civ/turn/objectives, the sorted selected ids, canonical
region bindings and their digest, a copied `Policy`, the rebuilt `Topology`,
the admitted `Soldier` and `Stock` records, the supplied kits and morale, the
kernel `Session`, its initial state digest and the plan digest. It contains no
borrowed Arrow, `AgentRows`, world or native object, and this module keeps no
decode cache.

The exact public surface is `admit_snapshot_plan`, `parse_side_inputs`,
`plan_document`, `plan_bytes`, `RegionBinding`, `SourceIdentity`,
`SideInputs`, `AdmissionPlan`, `CampaignSnapshotError`, `DEMANDED_COLUMNS`,
`SOLDIER_OCCUPATION`, `MORALE_LIMIT`, `COLUMN_LIMITS`, `CONTRACT`, `ADAPTER` and
`STAGE`. Everything else is private.

## The opt-in schema ratchet

`chronicler.bridge_contract.validate_snapshot_schema` is called here, and only
here. The adapter is the single new opt-in caller; validator behavior is
unchanged, `AgentRows`, snapshot capture and ordinary consumers are untouched,
and no consumer path gained a call. Only these four native fields are demanded
through the view:

| Column | Use |
|---|---|
| `id` | Stable agent identity, uniqueness and roster selection |
| `region` | Each selected soldier's start region |
| `civ_affinity` | Explicit selected civ check |
| `occupation` | Native soldier role check |

The ratchet runs before any value is decoded, so a schema violation costs no
decode. The remaining 19 fields are never read: the source identity records
per-column digests of exactly these four, hashed in stable-id row order, so
Arrow row order is not part of the identity while any real change to a demanded
value is. Changing `wealth`, `belief` or `loyalty` cannot alter a plan.

The content identity deliberately covers the **whole** demanded table, not only
the selected roster: a change to an unselected row's region, civ or occupation
changes `source.content_digest` while leaving the admitted roster and session
identical. That is the identity of what this boundary read, not a claim about
the rest of the snapshot.

Value checks are separate from the schema ratchet, because the uncoerced
`to_pylist()` decode is uncoerced by design: every demanded value must be an
exact `int` (so `bool` is rejected) inside its own native unsigned domain, and
the four columns must be row-aligned with the batch's reported `num_rows`.
Uniqueness is checked across all snapshot ids; every selected id must exist
exactly once.

Scope of the semantic checks: native type, domain, alignment and id-uniqueness
apply to all four columns and all rows, while the bound-region, soldier-role and
selected-civ checks apply to the selected roster only. An unselected row may
therefore reference an unbound region or carry a non-soldier role without
rejection. That is not whole-world semantic validation and is not claimed.

## Explicit inputs, never inferred

The native snapshot carries no carried rations, no campaign morale, no unmet
needs, no supply stocks, no packet-derived information quality and no
eight-slot memomes. Kits, morale and local sandbox stocks are therefore
mandatory side inputs with exact coverage:

- `kits` and `morale` must cover exactly the selected roster, no more, no less.
  Kits are bounded by the policy's `carried_limit`; morale by `0..1000`.
- `stocks` must cover exactly every bound region.

Sandbox stocks are caller integers with no adapter-imposed ceiling, so a large
explicit value survives the whole seam unchanged; `Policy` and `admit` remain
the only authority on their own ranges.

Morale is never inferred from loyalty or satisfaction, stockpile floats are
never silently converted to rations, and threat intensity is never mapped to
information quality. `Condition` and `Draw` inputs belong to a future advance
caller, not to this adapter. Omitted, extra, duplicate, negative, float or
boolean values are rejected. Either a mapping or an immutable `(id, value)`
pair sequence is accepted, and both are copied, so later mutation of the
caller's mapping cannot change a returned plan.

## Region identity is explicit and stable

`RegionBinding(region_id, name, neighbors)` carries the stable native region id
alongside its label. Names are labels only. Adjacency is rebuilt from the
bindings themselves: every neighbor name must resolve to exactly one bound
region, edges must be reciprocal and non-self, and ids and names must be
unique. An unresolvable neighbor name is reported as an unknown region
reference; a name that resolves but is not reciprocated is reported as a
one-way edge. An isolated region is legal: the reviewed kernel permits a
disconnected graph, and an unreachable objective becomes a reason-coded stall
at advance time rather than a rejection here. Trade routes, sea routes,
k-nearest fills, display-name hashes and list order are never used, so
reordering a caller's binding tuple or neighbor tuple cannot remap a region
id, while genuinely relabelling regions is recorded honestly in the plan.

The test fixture uses the existing three-region adjacency from
`chronicler-agents/tests/test_behavior.rs:63-65`: region 0 connects to 1 and 2;
1 and 2 connect only to 0. Those native agents are farmers, so the adapter's
soldier roster is separate explicit caller data, as in the existing demo.

## Epoch honesty

The adapter takes an explicit `expected_source_turn` and requires it to equal
the borrowed view's `stamp.source_turn`; the view's stage must already be
`phase10_entry`. Both turns are checked for the same domain first: a
nonnegative exact `int`, so `True`, `1.0` and an `int` subclass are rejected
rather than compared loosely. `Stamp` validates the stage but not the turn, so
without that check a lossy turn value could equal an exact expectation and be
recorded in provenance as if it were exact.

The kernel admission turn is that source turn `N`. No `N+1` completed-turn label
is invented, because this adapter never completes a turn: a
`TurnObservation(N, N+1, rows)` is accepted and its rows plan at `N`, while
`expected_source_turn=N+1` is rejected. In the CLI path the epoch is the
side document's explicit `source_turn` label, which is stamped onto the view
this driver constructs; it is not independent proof of the capture's epoch from
Arrow metadata.

## The CLI

```sh
python scripts/campaign_snapshot_plan.py
python scripts/campaign_snapshot_plan.py --enable --snapshot captured.arrow --side-inputs side.json
python -m pytest -q tests/test_campaign_snapshot_adapter.py
```

Default invocation prints a fixed disabled receipt and opens no file, contacts
no native bridge and calls no kernel seam; supplying paths without `--enable`
changes nothing. Enabled invocation reads only the two explicit files: one
Arrow IPC snapshot file holding exactly one record batch, and one strict JSON
side-input document. A single zero-row batch is passed through to the adapter,
which then reports the absent roster as a structured refusal and exit 2 rather
than a reader error. It prints the canonical plan JSON to stdout and creates no
output files. It never calls native `get_snapshot`, never advances the
simulation, and is absent from the production CLI registry.

Side-input keys are exactly `contract`, `source_turn`, `civ_id`,
`selected_ids`, `campaign_id`, `topology_version`, `staging`, `target`,
`policy`, `region_bindings`, `kits`, `morale`, `stocks`. Unknown or missing
keys, non-canonical decimal id keys (`"07"`), duplicate JSON keys, non-finite
constants, and booleans or floats where an exact integer is required are all
rejected. Parsing classifies JSON kinds and exact integers only; it restates no
numeric range, so a JSON policy is admissible exactly when the equivalent typed
`Policy` is — including a large `carried_limit`, which the public kernel accepts.
Roster coverage, binding validity and kernel rules stay with
`admit_snapshot_plan`.

`parse_side_inputs` preserves the order the document supplied for
`selected_ids` and `region_bindings`; canonical ordering by stable id happens in
the returned plan, not in the parsed record.

## Tests

`tests/test_campaign_snapshot_adapter.py` uses real Arrow record batches over
the untouched 23-field native schema and the existing three-region adjacency.
It covers: the complete admission equalling a direct public `admit` call,
including a large explicit sandbox stock; `plan_document` equalling the emitted
JSON value; plan-body digest sensitivity and the body-only digest scope; frozen
immutability and input copying; exact-integer `Stamp.source_turn` with `bool`,
float and `int`-subclass rejection; explicit soldier/civ selection with farmer,
merchant and foreign-civ rejection; duplicate and missing ids; zero-row
snapshots; per-field schema ratchets (missing field, extra, reordered, duplicate,
nullable, wrong type); null, float, bool, string and out-of-domain decoded
values; row misalignment and a misreported `num_rows`; unbound regions,
non-soldier roles and civ mismatches; unselected rows receiving native-domain checks with selection semantics scoped;
whole-table content identity including unselected rows; source-turn mismatch and
the `N` versus `N+1`
distinction; provenance scoped to the four demanded columns; binding and
neighbor order invariance; unknown references, one-way edges, self, duplicate and
malformed graph references, and a permitted isolated region; exact mandatory
side-input coverage and domain limits; JSON and typed policy equivalence across
the public domain; config and identity validation; kernel policy and objective
rules still applying; unchanged source objects with `weakref` proof that no
batch or view is retained while the plan stays usable; a recursive walk proving
no Arrow, world or native object escapes the plan; single decode per demanded
column via the reused `CountingBatch` double; strict side-document parsing; and
disabled/enabled CLI behavior including a zero-row IPC refusal and byte-stable
output across `PYTHONHASHSEED=0,1,42,101`.

Existing suites are reused, not modified: `CountingBatch` and `rows_for` come
from `tests/test_turn_artifact_views.py`, the policy and topology fixtures from
`scripts/campaign_logistics_demo.py`, and the strict JSON reader from
`chronicler/artifact_io.py`. The schema ratchet itself is exercised through its
reviewed public function with the existing `tests/test_bridge_contract.py`
expectations. No `WorldState`, no scientific scenario, no RNG seed and no native
build is involved. A subprocess probe asserts that importing the adapter and
running the driver imports no production world, simulation or native module and
consumes no RNG state; pyarrow's own transitive numpy import is permitted
because it is part of the allowed Arrow I/O. An AST check asserts the driver
performs no native snapshot query and no simulation advance in executable code.

One contract detail worth naming explicitly: the plan document contains both
this adapter's `contract` (`chronicler-campaign-snapshot-adapter-v1`) and, under
`admission.contract`, the reviewed kernel's own
`chronicler-m60a-detached-v1`. Neither replaces the other.

## Not implemented

Supply/needs/knowledge adapters for `Condition` and `Draw` inputs; soldier
exclusivity with a live world; death and cancellation reconciliation against
`AgentEventRecord`; treasury or native commitment; real enlistment or any
stock, provision or morale debit; turn scheduling or `advance` calls; M61 or
M67 gates; production action wiring, feature flags or shared CLI registration.

Also not implemented, and not to be inferred from the digest: whole-world
semantic validation of the snapshot. Only the selected roster is checked for
bound region, soldier role and civ; an unselected row may be a non-soldier of
another civ in an unbound region and still be admitted past, as long as its
native id, type and domain are valid. The CLI's `source_turn` is the side
document's explicit label, not independent proof of the capture's epoch from
Arrow metadata.

This lane makes no production integration, scientific fidelity, native-byte
acceptance or performance claim, and it does not change the documented native
object-key-order failure or the withheld full A01/native-byte acceptance.
Independent review of these exact source bytes precedes any private
integration.