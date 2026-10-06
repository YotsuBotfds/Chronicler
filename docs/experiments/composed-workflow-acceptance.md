# Resumable experiment workflows — composed candidate acceptance

These scenarios use the existing campaign and memome tables, explicit local
regular files and the public session APIs. They are tests of composition, not
scientific or production acceptance. This candidate starts from the adopted
operator checkpoint642923af and composes the exact accepted repaired C7d0f8393
and snapshotcee4dfa3 source increments. Its I test/doc increment is new and needs
independent review of this actual tree. Governance and snapshot scopes are explicit
extras relative to the original14-path I-BD brief. The old held C06057a88 is
preserved as history; none of its superseded script bytes are copied here.

Use `tests/test_experiment_workflow_integration.py` to reproduce all three
scenarios. It writes a documented `TransportPolicy` JSON into its own temporary
directory, then actually runs these existing commands with literal target names:

```sh
python scripts/experiment_session.py create --kernel m60a --path campaign.json --transport transport.json --demo
python scripts/session_operation.py --enable apply --path campaign.json --transport transport.json --submission campaign-turn-1.json
python scripts/experiment_receipts.py --enable --path campaign.json --transport transport.json --turn 1
```

Replace the first command's kernel with `m68a` and target with `memome.json` for
the existing memome tables. The test prints no invented production data: its
submission files are JSON encodings of `campaign_logistics_demo.fixture_tick`
or the three batches in `memome_demo.unit_tables`. Fixture tick construction
uses the restored current session for each turn. The test executes every shown
invocation from the directory containing the declared files, using absolute
script locations; no `--enable` is added to the original create subcommand.
Each CLI command is also run from an independent copy of its pre-command files
under seed42, with exact stdout/stderr/return-code equality against seed0. The
complete resulting regular-file byte maps must also be equal, and per-file SHA256s
are retained alongside command receipts. Public session loads must match the
actual target-file digest and any CLI-reported identity. These gates add the
post-command file comparison missing from accepted dry-run evidencea689589f.
Run `PYTHONPATH=src python -B -m pytest -p no:cacheprovider -q -s
tests/test_experiment_workflow_integration.py tests/test_experiment_default_boundaries.py`
from this checkout to see the command arguments and output digests. This requires
the project's existing Python test environment; it installs nothing.

The campaign stops after turn2 at generation3, reloads, then proceeds through
turn7 at generation8. Turn4 credits two rations and replenishes two per soldier;
turn6 closes with local10, carried0, consumed12 and initial20+credit2. Turn7 is
a newly admitted terminal no-op receipt and advances the generation once.
Replaying original turn4 at the latest version writes nothing and repeats no
credit. Inspection can show turn1/4 while identifying the whole file as turn7.
Contradictory replay is rejected without changing saved bytes.

The memome run reloads after batch1 and ends at generation4/turn3. Historical
batch1 keeps minority/prestige acceptance and incompatible-candidate reasons;
batch3 retains `absent_candidate`. Replay in the original noncanonical proposal
order leaves later history and the latest file intact. Genesis/future selection
is unavailable, and individual votes/receipt chains remain unavailable.

The fault case is one bounded test-owned subprocess. After atomic replacement,
an injected directory-fsync error returns `durability_uncertain`. Inspection
and `session_operation.py --enable reconcile --path campaign.json --transport
transport.json --expectation-json ...` observe the exact intended visible file
and return `intended_visible_durability_unknown`, without another apply, rollback
or lock deletion. Visible bytes do not prove durability or authorize retry.

B/D use the same integrated public bounded reader. Oversized source bytes are
refused before decoding. This bounds bytes read, not FIFO opening time, all
decoded history, output memory or report bytes. Interval caps limit selected
turns. The old CLI growth-read gap, FIFO behavior and core postpublication
cleanup exception remain separately reported; B preserves an explicit unknown
outcome for unexpected commit errors. The existing contention suite is retained
and is not duplicated here. Source is read-only and optional inputs remain off
until each operator's explicit opt-in.
