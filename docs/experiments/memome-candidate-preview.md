# Explicit memome candidate preview

`chronicler.memome_candidate_preview.preview_candidates` reports explicit next
batch candidate choices against one complete immutable `MemomeSession`. Each
alternative starts from the same opening ledger, with its existing membership,
contact groups, prestige weights, traits and illustrative policy. Only proposal
candidates may differ. There is no automatic choice, ranking, sampling, saved
branch, checkpoint, commit token or production activation.

The report contract is `chronicler-memome-candidate-preview-v1`. Enabled calls
require an exact `MemomeSession`, `TransportPolicy`, immutable tuple of frozen
`Alternative(label, batch)` records and an exact positive integer
`max_alternatives` (bool excluded). Labels must be unique, nonblank strings of at
most 128 characters; batches must be exactly the next turn. The entire request
fails with the alternative's label if any alternative is invalid or the
canonical proposal-ID set, recipient, slot, draw or turn changes. Proposal order
may vary. IDs may be reused between isolated alternatives, but committed IDs
remain unavailable and each batch permits only one proposal per recipient.

The complete opening session and each hypothetical result undergo public
encoding and reconstruction. Generation 1 is solely an encoder validation
argument; it is never a claimed observed generation or predicted commit. The
original session and history are retained. An explicit empty next batch is
legal and represents a hypothetical new turn, not a historical replay.

Reports and nested records are frozen. `as_payload` returns fresh containers;
JSON/text renderers retain every public kernel Receipt field, the canonical
admitted batch, and the previous/resulting slot value from the actual opening
and hypothetical participant records. The kernel owns frequency, compatibility,
threshold and reason precedence. Reasons remain exactly `accepted`,
`probability_rejected`, `incompatible`, `unchanged`, `absent_candidate` or
`empty_electorate`. No individual voter list or per-receipt digest chain is
available. Thresholds and weights remain exact illustrative integers, not
empirical success estimates or calibrated scientific outcomes.

Default-off API calls return a fixed report before inspecting optional inputs,
validating a policy, consuming an iterator or calling any kernel. This facade
does not call the kernel's disabled advance path, which itself validates inputs.
Imports do no input work. No preview operation calls persistence or consumes RNG.

## Runnable existing unit-table example

From the checkout root, prepare an explicit regular-file session using the
existing demo's small table. This setup deliberately invokes the existing
public writer; the subsequent preview command only reads. Use a supported
Python interpreter, setting `PYTHON` if necessary.

```sh
PYTHON=${PYTHON:-python3}
example_dir=$(mktemp -d)
export example_dir
PYTHONPATH=src "$PYTHON" - <<'PY'
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import runpy
from chronicler import experiment_sessions as es
from chronicler import memome_experiment as mm
from chronicler.memome_candidate_preview import CONTRACT

d = Path(os.environ['example_dir'])
table = runpy.run_path('scripts/memome_demo.py')
people, _ = table['unit_tables']()
session = es.create_memome_session(policy=table['illustrative_policy'](),
                                  genesis_turn=0, participants=people)
transport = es.documented_transport_policy()
es.commit_session(d / 'memome.json', session, transport=transport,
                  expected_generation=None, expected_digest=None)
encode = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
(d / 'transport.json').write_bytes(encode(asdict(transport)))
proposal = mm.Proposal('choice', 'basic-1', 1, 3, 199)
choices = [
    {'label': 'candidate 3', 'batch': asdict(mm.Batch(1, (proposal,)))},
    {'label': 'candidate 0', 'batch': asdict(mm.Batch(1, (replace(proposal, candidate=0),)))},
]
(d / 'choices.json').write_bytes(encode({'contract': CONTRACT, 'alternatives': choices}))
PY
"$PYTHON" scripts/memome_candidate_preview.py --enable \
  --path "$example_dir/memome.json" --transport "$example_dir/transport.json" \
  --alternatives "$example_dir/choices.json" --max-alternatives 2 --format json
```

At genesis the basic group has slot-1 traits `(3,1,5)` and unit weights. Candidate
3 for basic-1 has candidate weight 1, electorate weight 3 and integer threshold
200. Draw 199 accepts and changes 1 to 3. Candidate 0 with the same proposal ID,
recipient, slot and draw has weight 0, threshold 0 and reason `absent_candidate`;
the slot remains 1. Both alternatives observe the same genesis.

The distinctive synchronous control proposes candidate 3 to basic-1 at draw 199
and basic-2 at draw 200 in one batch. Both see opening weights 1/3 and threshold
200: the first accepts, the second is `probability_rejected` and retains 5. The
first success does not increase the second threshold to 800. In the existing
named pair, candidate 2 for ordinary-1's slot 2 has weights 5/6 and threshold
961; draw 960 accepts and draw 961 rejects. Existing incompatible proposals
retain the kernel's `incompatible` reason and their previous value. These are
fixed small hand tables, not world or seed experiments.

## CLI observations and errors

Enabled CLI requires `--path`, `--transport`, `--alternatives` and
`--max-alternatives`; `--format` is `json` (default) or `text`. The alternatives
document has exactly `{contract, alternatives}`, with an array of entries having
exactly `{label, batch}`. Count is checked before decoding records. Public strict
parsing and batch decoding reject duplicate/unknown keys, floating/nonfinite
numbers, bool integer aliases and malformed schemas. All output is assembled
before stdout emission. Both malformed enabled syntax (including bad integer,
bad format and missing option value) and valid-syntax domain/input errors emit
one JSON error on stderr, exit 3, and no successful stdout. Successful previews
exit 0. Explicit help exits 0 before optional validation or I/O. Without
`--enable`, malformed optional values and nonexistent paths still return the
fixed off report without I/O.

The accepted public regular-file reader bounds transport bootstrap to 4096
bytes and alternatives to `transport.max_bytes`, reading at most limit plus one
from an opened descriptor. The accepted public session loader reads once and
verifies complete history. Existing reader behavior for links is preserved;
FIFO and directory inputs are refused by the public seam. No custom stat/read
path is added. No output-file or apply option exists.

`cli_observation` separately reports the actual observed path, generation, turn
and exact file-byte digest. The hypothetical result has no generation. A later
pathname replacement does not change the opening version used by the report.
The observation asserts neither currentness nor durability and is not an OCC
or submission token. Real submission must use the existing operation API and
concurrency checks afresh.

Bounds cover alternative count, serialized input bytes and the complete-session
transport domain. They do not guarantee output-byte size, total allocation or
execution time. Complete public replay is required; no cache/private fast path
skips it. Existing extreme integer JSON limits are preserved: unsupported
rendering fails before publication, and no global digit limits or integer values
are changed. Full M68 depends on M67; this detached illustrative report adds no
M68b effects, synergy boost, production coupling, qualification or calibration.

Focused gates cover exact full direct-kernel receipts, all reason strings,
synchronous opening electorate, boundaries/empty batches, candidate-only
canonical matching, malformed/committed/historical inputs, immutable reports,
parallel call equivalence, actual CLI parser/domain failures, public bounded
reader refusals, one-load replacement, and exact bytes/digests/mtimes/inventory
nonmutation with literal-path output equality at hash seeds 0/42/101. The wider
memome/session/I/O/receipt-inspection suites and preserved probes run separately.
Independent review precedes integration. When only these four additions are
composed with an accepted successor, repeat loader/replay/observation/no-write
interaction gates on that exact source. M has no dependency on S, P, E or V.
