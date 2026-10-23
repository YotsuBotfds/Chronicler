# Historical receipt inspection

`experiment_receipts.py` explains committed historical M60a campaign and M68a
memome decisions from an explicit saved session. It uses public `load_session`
with caller-supplied transport, including full reconstruction/replay validation.
It selects existing authoritative receipts and never submits a new experimental
tick, changes the session, generates draws or acquires native/world data.

Without `--enable`, invocation emits a fixed disabled JSON receipt before
opening supplied paths, decoding data or calling any kernel. Supplying paths or
`--format text` does not enable it. Enabled commands require an explicit session
and transport file, plus either one exact turn or an inclusive interval with all
three explicit bounds:

```sh
python scripts/experiment_receipts.py --enable --path campaign.json \
  --transport transport.json --turn 4
python scripts/experiment_receipts.py --enable --path memome.json \
  --transport transport.json --start-turn 1 --end-turn 3 --max-turns 3 --format text
```

`transport.json` has the unchanged version/four-bound shape documented in
[session-workflow.md](session-workflow.md). Its bytes come from public
`read_regular_file_bytes` with a 4096-byte cap and label `transport policy`:
one nonblocking descriptor open, same-descriptor regular-file validation, a read
request of 4097 bytes, and closure before UTF-8/policy decoding. A FIFO needs no
writer to refuse; a regular pathname exchanged for a FIFO also refuses. Regular
read symlinks remain supported. Unsupported nonblocking platforms propagate the
shared reader's refusal, without a blocking fallback. The existing strict policy
parser rejects duplicate, nonfinite, float and invalid exact-kind fields.

The current public session loader uses the same descriptor reader with
`transport.max_bytes`, requests at most `max_bytes + 1`, refuses over-cap bytes
before decoding and retains the digest of its one actual read. Inspection does
not duplicate that load or reserve pathname currentness. Replacement after a
file descriptor opens uses those opened bytes, including malformed old bytes;
it does not mix in a newer pathname version. Session history/record/integer/file
bounds remain those of the existing loader.
The bootstrap policy byte cap, decoded record/history/integer bounds and output
turn-interval cap are distinct. `max_turns` is not an output-byte or allocator
overhead cap; one selected turn may retain many records. Full history
reconstruction remains necessary even for a one-turn selection and legitimately
replays kernel validation. Read-only means no newly admitted ticks/frames and no
writes, rather than no kernel functions executing.

Library calls are also default-off:

```python
from chronicler.experiment_receipt_inspector import (
    inspect_receipts, inspection_document, inspection_json, inspection_text,
)

# transport is an explicit public TransportPolicy record.
selected = inspect_receipts("campaign.json", enabled=True, transport=transport, turn=4)
document = inspection_document(selected)
text = inspection_text(selected)
```

The enabled result is a frozen `ReceiptInspection` with frozen selected
`HistoricalTurn` records. `inspection_document` makes an independent plain JSON
view; `inspection_json` gives canonical sorted-key JSON and a final newline;
`inspection_text` gives deterministic tab-separated tables. Text cells escape
backslashes, tabs and newlines in caller labels. Numeric values use exact integer
rendering, including large weights; no float conversion or process digit-limit
change occurs.

An exact selection accepts only a nonnegative exact integer within the supplied
transport integer domain. Bool, float, negative and over-wide turns are refused.
An interval requires `start_turn`, `end_turn`, and exact positive `max_turns`
(at most 1048576); its inclusive span must fit the explicit cap. There is no
implicit window, truncation or latest fallback. Exact and interval arguments
cannot be combined. A valid requested turn with no committed receipt is marked
`available: false`, including a genesis/admission turn or a future turn. A
committed memome batch with zero proposals is available and has an empty receipt
list. This distinguishes missing evidence from an empty committed transaction.

Campaign sections include **every field** of the saved public Receipt: phase,
orders/credits, before/after counts and stocks, cumulative food accounting,
replenishment allocation, each member's path/supply distance, region/status,
ration changes, morale/stress components, explicit draw, desertion and recorded
movement/stall reasons. Stored cursor receipt digests and state-before/state-after
digests remain separately labeled. Derived per-member summaries are limited to
morale subtraction and classification of the receipt's released rations as
deserted or returned; they do not create new causes. The food record is cumulative
through the selected turn; member consumption/replenishment/release is per turn.

Memome sections include the admitted batch, **every field** of each historical
Receipt and the retained participants after that batch. Proposal/recipient/slot,
old and candidate traits, supplied draw, exact candidate/electorate weights,
threshold and kernel reason remain authoritative. Individual electorate vote
lists and per-receipt digest chains are not retained by this kernel and are
explicitly unavailable. The inspector does not reconstruct a new voter list
from the post-batch participants or invent a digest chain. It makes no claim
that memomes affect campaign morale.

Common file/generation/session/genesis/history/latest digests identify the fully
validated **whole saved file**, while campaign receipt/state digests identify
the selected historical records. The baseline source HEAD/tree in the unchanged
envelope identify its reviewed kernel baseline, not this inspector's revision.
JSON and text write only stdout; all session data, generations and lock files
remain unchanged. Malformed files, invalid transport and tampered/resealed
receipts fail through existing public replay validation. Errors print a JSON
object on stderr and exit 3; argparse retains its own validation exits. A
successful unavailable-turn report exits 0.

Focused offline tests reuse the existing campaign demo and memome unit tables.
They compare earlier/latest full receipts, missing/empty turns, bounded selection,
exact large integers, digest identities, untouched files/generations/directories,
resealed tampering, strict inputs, default-off forbidden hooks, fresh-process
imports and hash-seed determinism. No simulation, provider access, HTML/viewer
wiring, production registration, native change or milestone acceptance is added.

The bootstrap delegation deliberately changes two input diagnostics: oversized
policy bytes now report `the transport policy exceeds the 4096-byte transport
limit` instead of `transport policy exceeds the 4096-byte bootstrap limit`;
a directory reports `the transport policy is a directory: PATH` through the
same `IsADirectoryError` type. FIFO/special-file intake reports the shared
`SessionError` regular-file refusal. Ordinary open/read errors propagate, and
UTF-8/domain/parser errors, selection rules, successful reports, off output and
argparse behavior retain their existing contracts. Boundary evidence separately
records these input-only changes and compares all other supported command
streams and complete post-file bytes/modes/mtimes against accepted Q at seeds
0 and 42.
