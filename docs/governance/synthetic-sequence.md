# Inspecting a continuous synthetic governance sequence

`chronicler-governance-sequence-v1` is a default-off, in-memory inspector of
already-produced public `GovernanceCapture` records. It checks recorded
correspondence and continuous carry under one complete declared policy. It
does not authenticate a historical execution: C records can be constructed
manually, and source revision, tree, label and origin remain caller declarations.
Execution replay or verified provenance would require a separate contract.

```python
from chronicler.governance_sequence import inspect_sequence, sequence_json

off = inspect_sequence()  # disabled_no_evidence; reads no optional input
receipt = inspect_sequence(enabled=True, captures=my_capture_tuple, max_frames=2)
print(sequence_json(receipt), end="")
```

Enabled inspection requires an exact immutable tuple and exact positive integer
cap. A tuple longer than the cap fails before any member is inspected. The cap
bounds supplied frame count; it does not bound every allocation, output byte or
runtime cost. The inspector calls public C `validate_capture` on each member,
then requires consecutive source turns in supplied order, complete adjacent
`previous.result.carry == next.opening`, complete `HarnessPolicy` equality,
complete source/origin declaration equality and equal identity registries. It
does not sort, deduplicate, truncate, consume generators or publish partial
receipts. Inputs and shared state stay untouched. No kernel runs during inspection.

An empty enabled tuple is explicit `no_evidence`, with no inferred policy,
registry, source declaration or epochs. One enabled capture is valid at any C
supported source turn and has zero adjacent checks. `full_policy_equal=true`
on nonempty input means every recorded policy equals the first, including the
singleton case; it does not establish causal authenticity. Disabled members
inside an enabled sequence are rejected. Invalid origin is a C rejection; the
current owner supports only `synthetic_four_kernel_harness`.

The report-only document/JSON envelope contains frame and adjacent-link counts,
first/last source and effective turns, declarations, policy ID, fixed-policy
result, and ordered rows with the validated capture's ownership epoch. Each row retains its full public owner
`measurement_json` byte string in `raw_measurement_json`. The summary copies
the owner's institution/enact/repeal/forced/neglect metrics with their exact
statuses, values and reasons. Forced repeal is counted once by that existing
measurement, although events and outcomes both record it.

Civilization summaries preserve owner order, opening/published institution
counts, opening/spent/post-spend/accrual/published capital and opening/published
ruler legitimacy. Only `derived_net_capital_change` is new arithmetic: exact
published minus opening `Fraction`, encoded through public `ExactFraction.of`
as `{"fraction":[numerator,denominator]}`. Net is distinct from spend, because
accession and accrual can change the wallet. Accrual's late-phase opening remains
separate from the original opening wallet. No legitimacy difference is claimed
as exact rational evidence.

Every existing unavailable metric remains present with its original reason and
absent value. No tenure/rate/distribution, window/censoring convention, PSI/MMP/SFD
producer, regime classification, cross-seed aggregate, demographic inference or
scientific threshold is added. Neither an arithmetic sum nor a two-turn fixture
is presented as a governance gate. JSON and text are built fully before stdout
publication. A public-domain integer beyond Python's ordinary decimal encoding
limit raises explicitly; this code does not widen global digit limits or add a
transport cap. Documents are fresh copies; the returned receipt and rows are
frozen and retain immutable owner records.

The only driver execution mode is explicitly enabled `existing-two-turn`:

```sh
python scripts/governance_sequence_report.py --enabled \
  --fixture existing-two-turn --max-frames 2 \
  --origin synthetic_four_kernel_harness \
  --revision 7d0f839381dcd8acf0dfcdbaaf96035a4bf6183a \
  --tree bfa934efd278f5167af8d2b34c9fb231d0430183 \
  --source-label 'caller-declared accepted C dependency' --json
```

Without the exact `--enabled` flag, malformed optional fixture/origin/bound/path
values are ignored before enabled validators and the driver reports disabled
no evidence. Explicit `-h`/`--help` shows normal full help. Enabled input requires
all declarations and a cap large enough for the two-frame fixture before any
fixture execution. `--json` selects JSON; otherwise enabled output is text.

The driver loads only the trusted local accepted C source script into an
unregistered private module via `importlib`, then calls its public
`capture_fixture` seam. This preserves C's exact codec restart boundary and
deliberately executes exactly two existing fixture kernel calls. It never calls
the legacy reporting wrapper, `runpy`, or patches `sys.argv`/`sys.modules`.
This is trusted local fixture reuse, not arbitrary Python containment. The
library imports no fixture and runs no kernel. C's report-only JSON cannot be
decoded into captures; it omits complete retained policy/observations/receipts.
There is no output file, resume, restore or JSON capture decoder path.

The unchanged fixture has source/effective rows 0/1 and 1/2, opening capital
3/10 in each, published capital 3/10 then 0, and derived net 0 then -3/10.
Its final carry is effective turn 2, exact capital `[0,1]`, legitimacy 0.6,
and one keyed ambition contribution. Each row retains 20 unavailable metrics.
These are tiny synthetic observations, with no production activation or adoption.

The focused tests cover default-off poison inputs, exact bounds, public C
validation, individually C-valid carry/policy/declaration/registry mismatch
cases, ordering, exact residuals, unavailable values, forced-repeal counting,
render failures without partial stdout, concurrent callers, fresh hash seeds
0/42/101, source-bound imports and absence of production consumers. Epoch and
commit-watermark inconsistency is already rejected by the owner; a same-epoch
valid carry cannot independently change its watermark. Source review and
independent acceptance remain separate from these tests.
