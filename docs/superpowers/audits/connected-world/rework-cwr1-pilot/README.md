# CWR1 official timing and schema pilot

All **24/24** declared cases passed at 120 turns: twelve arms on shared
procedural timing seed 19 and twelve on shared template timing seed 5.
The checks read every produced turn and the full Arrow event sidecar.
These are previously used development worlds, not fresh held evidence.
All outcomes, nulls and harms remain in [metrics](metrics.jsonl) and the
[report](report.md); none were used to retune the controls or simulation.

The immutable runtime was `8792be88dd36ba4d7c22e480de6a19dd64ea1300` in
`/workspace/cwr-final-runtime`. The imported native extension was
`b1d3ea5ac858681960b2cb880c534164905501f6ab4f6f3c94f7c9b5f66196cd`;
all 57 Rust/Cargo/build inputs and the native crate's pyproject matched the
fresh release-build receipt (input digest
`f55df55d453ac37694410246c4a9728c56f3f6148f679fde8efc21ffd8775acf`).
Source/native identities were checked before and after the run. The
[source receipt](source.txt) records the exact interpreter, imported paths,
runner/module/registry hashes and clean source state.

Simulation took **484.7 seconds**, extraction **68.5 seconds**, totaling
**553.2 seconds** in the generic runner's accounting. Six held worlds per
stratum project to **0.922 core-hours**; the fixed 1.5 margin gives
**1.383 core-hours**, passing the existing two-core-hour ceiling. No timing
amendment was needed. The full fresh runner subprocess used 553.267015
seconds of descendant user-plus-system CPU and 556.096743 seconds of wall
time. [Resource measurement](resource-measurement.json) labels peak RSS
accurately: 1,145,972 KiB is the lifetime maximum of one waited-for child or
descendant, not simultaneous process-tree memory or a subtractable maximum.
No `/usr/bin/time` dependency or system installation was used.

The [approved harness](run-official-pilot.py), SHA256
`157196785747f1af743ea658d0c12a88f5987cd18b0a5ace7dfa8f5a78b65e56`,
invoked the unchanged generic `pilot` command with one job and all four
thread controls set to one, followed by `check` and `report`. All commands
and the exact 24-case matrix are retained. [commands.json](commands.json)
reconstructs the child argument vectors deterministically from the frozen
arm and runner definitions; it is not an independent OS argument trace.
The three top-level commands are recorded in the original launcher receipt.

The generic report prints Markdown to stdout. The approved launcher retained
that output as `report.log`, so its original [receipt](launcher-receipt.json)
truthfully has a null `report_sha256`. After process closure and successful
report return, the output was copied byte-for-byte to `report.md`.
[The publication receipt](report-publication.json) records both matching
hashes and preserves the original launcher receipt. No simulation, source,
control, outcome, timing or budget changed during publication.

Raw output remains at
`/workspace/evidence/cwr-evaluation/pilot-8792be88-v1/`, including every
bundle, Arrow event sidecar and JSON world state for all 24 cases. These
commands did not request private checkpoints; that evidence belongs to the
separate profiling and exact-resume gates. The original
failed eight-turn development check, its incorrect `no_relief` assertion
and the corrected-readback evidence remain preserved separately. Positive
free food in `no_relief` is valid; that mode changes the title fraction and
uses L2 free-pool allocation without the retail means test. Unknown access
coverage remains unknown rather than becoming zero. Complete household-access
deficit is null in 12 of the 24 runs; AD-p19 has 248 unobserved populated
region-turns and AD-t5 has two. Observed subtotals are retained, and regional
availability shortfall remains a separate, fully recorded primary.

The independent stdlib arithmetic audit passed the complete matrix, source
receipts, control implications, rates/nulls, all planned contrasts and six
rendered primary rows. This is an arithmetic and evidence check, not an
independent observation of unseen raw frames or qualification. See the
[independent checker and audit](../rework-cwr1-independent/README.md).
The active protocol's freeze receipt, rather than the intermediate
[post-publication receipt](validated-pilot-receipt.json), records the final
independent-review disposition. No held seed was spent by this pilot.
