# Historical forensics

`chronicler.history_forensics` reads an existing bundle to answer: what did
the simulation record, what did its chroniclers say, which accounts still
stood at a chosen point, and which earlier events does the record cite as
dependencies? It makes no LLM calls, runs no simulation, and changes neither
the bundle nor its schema. It writes a report only when an output is named.

## Use

From the repository root, with Python 3.13+ and the project dependencies:

```sh
python scripts/history_forensics.py output/chronicle_bundle.json '63:famine:0'
python -m chronicler.history_forensics output/chronicle_bundle.json '63:famine:0' --as-of 70 --phase end
python scripts/history_forensics.py output/chronicle_bundle.json '63:famine:0' --json finding.json --markdown finding.md
python scripts/history_forensics.py output/chronicle_bundle.json '63:famine:0' --format json
```

Choose the exact `event_id` from `events_timeline`, not the narration's
`e<i>` fact id or an event's text. Quote ids containing spaces, such as
`'31:Mass Migration:0'`. An unknown, ambiguous or not-yet-known event gives
exit code 2 and an explanation. Diagnostics and a bounded partial report
give exit code 0; inspect `diagnostics` and `truncated_by`. Successful reports
always include the interpretation limits, selected event, dated ancestors,
dependency edges, accounts, limits and any diagnostics. There is no wall-clock
timestamp in the report, so the same source and options produce the same
bytes. File reports identify the source filename and SHA-256, without its
absolute path. Output paths cannot name the source bundle, including via a
symlink or hardlink.

The Markdown report is printed by default. `--format json` prints JSON;
`--json PATH` and `--markdown PATH` additionally save either format. Existing
report files can be overwritten when explicitly named. Markdown escapes
record content so descriptions are text, not HTML or active Markdown links.

## Time and accounts

The shared `historical_context.AsOf` convention applies: `--as-of T --phase
end` includes events and archive losses dated T. `--phase start` includes
only dates before T. The default is after the bundle's last completed turn
(`world_state.turn - 1`, or `metadata.total_turns - 1`); if neither horizon
exists, it is the latest dated event, account or account loss. A later
requested date adds no new knowledge beyond the bundle.

Each graph node separates the simulation record from accounts as of that
point. Accounts are read through `historiography.AccountIndex.as_of`:

| Status | What the report gives |
| --- | --- |
| `surviving`, `account` representation | The retained wording, stance, account citations and names of recorded bias transformations. These are claims, not the true event. |
| `surviving`, `plain_reference` representation | A compact `historiography.plain` reference. Its event summary is labelled as a summary, with no invented quote, stance or citations: the bundle omitted the original wording. |
| `lost` | Account identity, writing date, loss turn and loss cause. Text, stance, citations and transformation details are withheld, even though simulator storage may retain them. |
| `silent` | A recorded omission, with no text or claim details. |
| `undated` | An account whose writing cannot be placed in the view; wording is withheld. |
| `ambiguous` | Duplicate account identity; wording is withheld. |

A loss after the chosen point is not shown, and its still-standing text is
available before that loss. At the loss turn the text is redacted. Accounts
written after the point are excluded. Missing historiography or no matching
account is explicitly unavailable evidence; it is never labelled silence.
Chronicler names and event identities retain the bundle's canonical names;
this tool does not translate them or reconstruct a lost archive.

## Ancestry and limits

Only `Event.causes` creates a graph edge. The tool does not infer edges
from type-pair patterns, narration, a chronicler's citations, chronological
proximity or a repeated name. An edge says the simulation recorded a
dependency. It does **not** prove that removing that event would prevent the
effect; that requires a separate intervention or ablation experiment.
Absence of a recorded edge does not establish absence of a cause.

Ancestors are ordered by event turn, then timeline position and stable id.
Distance is the shortest number of recorded dependency edges from the
selected event. A breadth-first walk handles shared ancestry once; an
iterative depth-first check finds cycles in the visited subgraph. Diagnostics
identify dangling ids, duplicate ids, undated causes, causes after the chosen
point, future dependencies (including later emission in the same turn),
malformed cause lists and cycles. A future record's text is never included
in an earlier view. An ambiguous cause is not silently resolved to the first
matching event.

The defaults are `--max-nodes 200` (including the selected event),
`--max-edges 1000`, `--max-depth 20`, and `--max-accounts 20` per event.
These bounds appear in each report. `truncated_by` names each reached
limit, including account limits; no complete-ancestry claim is made for a
partial report. Limits can be raised within documented CLI validation
caps (10,000 nodes, 50,000 edges, depth 256, 1,000 accounts per event).
Indexing is linear in the input timeline and accounts; the file must still
fit in memory, and the shared decoder expands v6 history deltas. This is
not a streaming bundle reader.

## Library and compatibility

```python
from chronicler.historical_context import AsOf
from chronicler.history_forensics import HistoryForensics, Limits, inspect_path, render_markdown

report = inspect_path('chronicle_bundle.json', '63:famine:0', as_of=AsOf.after(70))
text = render_markdown(report)
# For repeated queries on an already loaded dict:
reader = HistoryForensics(bundle)
report = reader.inspect('63:famine:0', limits=Limits(max_nodes=100))
```

`inspect_bundle` is the one-shot dictionary equivalent. The module uses
the shared `bundle_codec` decoder for v6 and accepts older unencoded bundles,
the legacy `events` timeline name and timelines inside `world_state`.
It requires no valid current `WorldState` and invents no missing stable ids.
Records without ids are counted, and a failed selection explains this
legacy limitation. Historiography's stored `account_columns` order is
honoured. No new bundle fields are written. JSON report version 1 belongs
to this tool and is separate from bundle versions and narration provenance.

## Verification

`tests/test_history_forensics.py` covers loss-turn and phase boundaries,
silent/lost redaction in both formats, plain references, unavailable
historiography, later/undated accounts, duplicate identities, cycles and
dangling/future/undated causes, shortest paths, iterative deep traversal,
every report bound, v6 and legacy reads, account-column reordering,
deterministic ordering, input preservation, Markdown escaping and CLI
outputs/source protection. It has its own `history-forensics` offline oracle
chunk. No simulation or native code changes; no population gate or paid
narration qualification is claimed.

On the isolated branch from `cb9fe70c` (Linux, locked Python 3.13 environment),
the 31 new tests pass in 0.60 s under the offline guard: no native imports,
network or child-process attempts. The broader historical parity,
historiography and narration provenance run passed its other 107 tests and
skipped one native-only case; its importer allowlist was then extended to
name this read-only reader, and that architecture assertion plus the 31
new tests passed. Script and module CLI entrypoints work, and an external
CLI smoke report is byte-identical under `PYTHONHASHSEED=0` and `4242`.
