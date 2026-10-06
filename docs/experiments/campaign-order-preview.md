# Explicit next-turn order preview

`chronicler.campaign_order_preview.preview_orders` compares caller-supplied
orders on one immutable `CampaignSession`. Every alternative starts from that
same opening state. The result is a report, with complete canonical public
kernel receipts and small food, movement, morale, grants and stock summaries.
It neither ranks choices nor estimates future probabilities. It creates no
advanced session, save generation, commit token, lock or sidecar.

The contract is `chronicler-campaign-order-preview-v1`. Call with an exact boolean
`enabled`, an exact `CampaignSession`, an exact immutable tuple of frozen
`Alternative(label, tick)` records, an exact positive integer `max_alternatives`
and an explicit valid `TransportPolicy`. Labels are unique, nonblank strings of
at most 128 characters. Ticks must be exactly the next turn. All required member
conditions and draws are supplied explicitly, even when desertion is impossible.
Only orders may differ; credits, conditions, draws, supply sources and turn must
agree after public kernel canonicalization. Reusing an ID between alternatives
is allowed; reusing an already committed ID is rejected.

The public encoder and reconstruction validate the complete opening campaign
and each hypothetical result within the transport domain. Generation 1 is only
an encoder validation argument, never a claimed observed or future generation.
The original stored history/state is used throughout. Failure of any alternative
rejects the entire request with its label and returns no partial report. Report
records and their canonical receipt/summary strings are immutable; `as_payload`
returns fresh JSON containers. The receipt contains every public kernel field.

Default-off API and CLI calls return the fixed disabled report without inspecting
optional values, consuming iterators, loading fixtures or applying a kernel.
Imports perform no input work. Explicit `--help` works without opening inputs.

## Runnable existing three-region example

From the checkout root, prepare an explicit regular-file example in an empty
temporary directory. This setup deliberately invokes the existing public writer
to save the opening fixture; the preview command below only reads it. Set
`PYTHON` to the environment's Python executable if needed.

```sh
PYTHON=${PYTHON:-python3}
example_dir=$(mktemp -d)
export example_dir
PYTHONPATH=src "$PYTHON" - <<'PY'
from dataclasses import replace
import os
from pathlib import Path
import runpy
from chronicler import campaign_logistics as cl
from chronicler import experiment_sessions as es
from chronicler.campaign_order_preview import CONTRACT

d = Path(os.environ['example_dir'])
table = runpy.run_path('scripts/campaign_logistics_demo.py')
policy, topology = table['illustrative_policy'](), table['fixture_topology']()
admitted = table['fixture_session'](policy, topology).state
session = es.create_campaign_session(policy=policy, topology=topology,
    campaign_id=admitted.campaign_id, turn=0, staging=1, target=2,
    soldiers=admitted.soldiers, stocks=admitted.stocks)
session = es.apply_campaign_tick(session, table['fixture_tick'](session.session, 1)).session
transport = es.documented_transport_policy()
es.commit_session(d / 'campaign.json', session, transport=transport,
                  expected_generation=None, expected_digest=None)
(d / 'transport.json').write_bytes(cl.canonical_bytes(transport))
base = table['fixture_tick'](session.session, 2)
alternatives = []
for label, kind in [('march', 'march'), ('hold', 'hold')]:
    tick = replace(base, orders=(cl.Order('choice-2', 2, kind),))
    import json
    alternatives.append({'label': label, 'tick': json.loads(cl.canonical_bytes(tick))})
(d / 'alternatives.json').write_bytes(cl.canonical_bytes(
    {'contract': CONTRACT, 'alternatives': alternatives}))
PY
"$PYTHON" scripts/campaign_order_preview.py --enable \
  --path "$example_dir/campaign.json" --transport "$example_dir/transport.json" \
  --alternatives "$example_dir/alternatives.json" --max-alternatives 2 --format json
```

Turn 1 is ready with both members at region 1 and kits of 7. At turn 2 march
reaches region 0 in phase `marching`; hold remains region 1 in phase `ready`.
Both consume one ration per member, leaving kits of 6. Food is exactly
`20 = local 4 + carried 12 + consumed 4`. Opening location is region 1, at the
supplied source, so distance stress is zero for either choice. Morale advances
from `(820,790)` to `(840,810)`; destination stress is not charged early.

The existing arrived-turn-3 table gives another fixed comparison. Supply source
is region 1, both members open at region 2 with kits of 5, morale `(830,800)` and
local stock 4. With the existing turn-4 credit of 2, hold/replenish grants 2 to
101 and then 2 to 202 at opening region 2. Return uses the same credit, conditions,
draws and source, and starts with the same stocks independently.

| Turn-4 orders | Phase after | Region after (both) | Grants | Local | Carried | Cumulative consumed | Morale after |
| --- | --- | --- | --- | --- | --- | --- | --- |
| hold + replenish 2 each | arrived | 2 | 2, 2 | 2 | 12 | 8 | 810, 780 |
| return | returning | 0 | none | 6 | 8 | 8 | 810, 780 |

Both satisfy `initial 20 + credit 2 = local + carried + consumed`. Grants use
the opening location and finite stock, with no cross-alternative depletion.
This is a tiny hand table, not a new seed/world experiment.

## CLI observations and limits

Enabled CLI requires `--path`, `--transport`, `--alternatives` and
`--max-alternatives`; `--format` accepts `json` (default) or `text`. The alternatives
document has exactly `{contract, alternatives}` and each array entry exactly
`{label, tick}`. Public strict parsing rejects duplicate/unknown keys, floating
numbers, nonfinite data and invalid integer types. Count is checked before record
decoding. Transport bootstrap reads at most 4097 bytes, accepting at most 4096;
alternatives read at most `transport.max_bytes + 1`, accepting at most the bound.
Only explicit regular files are supported; links, directories and special files
fail the preflight. Inherited special-file/open timing races are not repaired.

The accepted public session loader is called once. `cli_observation` retains
its actual observed file digest, generation and turn. The output describes those
verified bytes even if another writer replaces the pathname afterward. It does
not assert currentness, durability or suitability for blind submission and is
not an OCC token. A later real operation must use the existing submission API
and concurrency checks afresh. JSON and text output are assembled completely
before stdout emission. With valid CLI syntax, domain and input validation errors
emit one JSON error on stderr and return exit 3 with no stdout. Malformed enabled
CLI syntax, such as `--max-alternatives garbage`, `--format invalid` or `--path`
without a value, is handled by standard `argparse`: exit 2, usage/error text on
stderr and no stdout. There is no apply or output-path option.

Alternative count, serialized input bytes and complete-session transport domain
are bounded. Output bytes, replay time, decompression and global allocation are
not guaranteed. Complete public history verification can be expensive within
these bounds; no cache or private fast path bypasses it. Legal terminal no-ops
are hypothetical new turns, never historical replay. This detached report adds
no mechanic, production coupling, calibrated metric or full M60a claim.

The focused tests cover full direct-kernel receipt equivalence, exact hand
arithmetic, independent stock grants, reverse/concurrent equivalence, canonical
permutations, failure nonmutation, strict off/import controls, actual regular-file
CLI observations, one-read replacement, and identical literal-path process output
at hash seeds 0/42/101. Existing inherited I/O defects remain a separate owner’s
work; no whole-tree pass is claimed. Later composition with accepted I/O requires
rerunning read/preview/nonmutation gates on that actual combined source.
