# Explore a world, inspect its history, then try one bounded change

This walkthrough uses the existing simulation CLI, saved-world loader, regional
history inspector, completed-run comparison and paused live session. The small
wrapper `scripts/world-laboratory-example.sh` supplies a fixed recipe; it does
not add a simulation service or edit initial state. It always uses
`--simulate-only`, including the exact what-if continuations.

The natural example is template seed 42, 24 turns, eight regions and four
civilizations in hybrid mode, with public granaries and transaction receipts
explicitly enabled. It saves exact checkpoints at turns 8, 16 and 24. It does
not enable shortage-first purchasing or delayed public shipments. This single
selected run is an example, not a balance study. The later stability override is
a deliberately constructed intervention.

## Generate the fixed example

Use Python 3.13+ and a real native extension built from matching Rust inputs.
Activate the existing tools without running the environment installer:

```bash
cd /workspace/Chronicler-kimi
source /workspace/shared/chronicler-onboarding/runtime-6da9acae6bda6d7a.env
scripts/world-laboratory-example.sh commands \
  /workspace/shared/chronicler-world-lab-example-20261102 \
  "$CHRONICLER_NATIVE_ENV/bin/python"
scripts/world-laboratory-example.sh generate \
  /workspace/shared/chronicler-world-lab-example-20261102 \
  "$CHRONICLER_NATIVE_ENV/bin/python"
```

Generate after the what-if backend has been integrated, from committed simulation
source. The wrapper rejects dirty simulation/native source, output paths inside
the repository, and any existing destination. It sets `PYTHONHASHSEED=0` and
`RAYON_NUM_THREADS`, `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS` and
`MKL_NUM_THREADS` to 1 for both generation and live resume. The native probe
checks compiled classes and records the actual binary hash; the active handoff
supplies the separate matching-build evidence.

Before running the simulation, the wrapper writes `example-manifest.json` with
the plan, command, source Git SHA/package digest, native hash/tree, interpreter
and thread settings. On completion it adds raw artifact hashes and actual
observations. A failed run retains its failed manifest and log. Bulk output is
outside Git in a private directory:

| File | Purpose |
| --- | --- |
| `original/chronicle_bundle.json` | Viewer bundle with snapshots 1–24 |
| `original/state.json` | Exported world state; useful for a fork, not an exact runtime checkpoint |
| `original/checkpoints/turn_0008.ckpt` | Exact common runtime at completed turn 8 |
| `original/checkpoints/turn_0016.ckpt`, `turn_0024.ckpt` | Later exact checkpoints |
| `original/run.log` | Ordinary CLI output |
| `example-manifest.json`, `commands.json` | Generation identity, hashes and exact argument lists |
| `OBSERVATIONS.json` | Actual granary flows, event examples and living civilizations at turn 8 |

Do not claim a particular famine, release, migration or policy benefit from an
enabling flag. Use the observations actually written by this fixed run; no
stocks, treasury, population or other opening state are changed to force one.

## Load and inspect recorded regional history

Start the current viewer in another terminal. These commands use the existing
Node toolchain; build dependencies must already be available:

```bash
cd /workspace/Chronicler-kimi/viewer
export PATH=/workspace/shared/node/node-v20.19.0-linux-x64/bin:$PATH
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open [the local viewer](http://localhost:5173), choose **Open Existing**, and load
`original/chronicle_bundle.json`. **Saved world details** identifies the recorded
range, seed, mode and available history. Neither `state.json` nor `.ckpt` is a
viewer bundle. Loading a completed bundle does not restore the native runtime
needed to run an exact what-if.

Select a region and open **Compare turns and inspect history**. In **Region
history**, choose **Regional model population**, set **From turn** to 1 and
**Through turn** to 16, then compare it with **Native agents alive (separate from model)**. The former
is actual completed regional model state; the latter is a separately recorded
alive-agent count. They can differ in shadow or demographics-only worlds. Do
not replace missing older observations with civilization totals.

Choose **Food / need**, inspect the recorded values and coverage, then use
**Events in this window** for context. The event list and metric table are
paged. An event's snapshot is its source tick plus one: snapshot 10 describes
completed tick 9. Nearby events provide context and do not establish a cause.
Enable **Include controller event context** only when that broader context is
useful. **Inspect turn** seeks deliberately; changing the inspected interval
alone does not change the selected world turn.

Use a granary flow or event listed in `OBSERVATIONS.json` as a concrete entry
point. Inspect that region's population and food trajectory around its recorded
snapshot, then open Trade/Food or Finance for the same recorded turn. A zero
flow remains zero; a missing food observation stays unknown.

## Resume the exact common point and prepare a manifest

Keep the same simulation package, interpreter, native binary and thread settings.
In a terminal using the same runtime activation, run:

```bash
cd /workspace/Chronicler-kimi
scripts/world-laboratory-example.sh live \
  /workspace/shared/chronicler-world-lab-example-20261102 \
  "$CHRONICLER_NATIVE_ENV/bin/python"
```

This invokes the ordinary `--live --resume` CLI, validates the exact checkpoint
without `--resume-allow-mismatch`, and starts paused at completed turn 8. The
live destination must be fresh. `live/launch-receipt.json` records the selected
source/runtime and original checkpoint hash before launch.

Open the complete **Open viewer** link printed by that process, including its
session token. The default link uses the development viewer at port 5173. If
using the supported preview server at port 4173 instead, change only the link's
viewer origin and preserve its query string. The original simulation remains
paused while the what-if pair runs.

In **Try a bounded what-if**:

1. Choose the first living civilization in the list. Set **Set stability to**
   **70** and **Additional turns** to **8**. This is the constructed intervention;
   its effect may be neutral or adverse.
2. Select **Prepare comparison**. Review the displayed civilization, its actual
   before value, seed, hybrid mode, common turn 8 and endpoint 16. Expand **Source
   and runtime identity** to inspect the exact checkpoint and current identities.
3. Before starting, the server has already written
   `live/what_if/<server-generated-id>/manifest.json` and `common.ckpt`. This
   durable manifest defines both arms and the intervention before execution.
4. Select **Run both continuations**. The backend restores that same common
   runtime twice: an unchanged baseline and an arm applying `set CIV stability
   70` at the pause. Both use the existing interactive exact-resume CLI with
   simulation only. The source world remains paused at 8.

The saved snapshot at turn 8 precedes the override. Compare subsequent snapshots
9–16 for its observed consequences. If the before value already equals 70,
report that honestly as an unchanged intervention; do not search for a more
favorable civilization or seed.

## Compare the actual results and retain their provenance

After both arms complete, choose **Compare what-if results**. The existing
completed-run view receives the two actual bundles and their raw hashes. Its
provenance panel should identify the exact common turn, stability override and
eight-turn horizon. Compare population, unweighted regional food, population-
weighted recorded food, and an additional financial/conflict trajectory at a
shared snapshot such as 16.

Weighted food uses the stored Phase 2 population and controller IDs from each
food measurement. Completed population and later ownership are different epochs
and cannot replace that denominator. Missing observations and unmatched tails
remain gaps. A weighted mean of clipped/rounded regional sufficiency is not an
exact physical food inventory ratio.

The server keeps each arm under the same job directory:

```text
live/what_if/<server-generated-id>/
  manifest.json
  common.ckpt
  baseline/chronicle_bundle.json
  baseline/final.ckpt
  baseline/process.log
  intervention/chronicle_bundle.json
  intervention/final.ckpt
  intervention/process.log
```

Both bundles deliberately include `metadata.what_if` arm labels before their
identity hashes are computed. Preserve the original files, manifest, generation
receipt and comparison JSON/Markdown export together. A loaded state file is a
fork; it cannot supply this workflow's exact native runtime. A comparison of
unrelated saved bundles is exploratory and does not become an exact pair merely
because their seeds match.

Only stability values 1–100 and 1–20 additional turns are supported here. One
paired trajectory describes this checkpoint and intervention, not a population
causal estimate or general policy benefit. A cancelled or failed arm retains its
partial output and cannot be presented as a completed comparison. No narration
or paid API calls are part of this workflow.

## Session verification status

At this guide's initial commit, shell syntax and command/guard checks are the
local wrapper checks. Actual generation is deliberately pending integration of
the what-if backend, so the exact checkpoint is produced by the same package
that resumes it. The real turn-8 manifest, completed pair, observed values and
browser screenshots remain pending until recorded by the integration owner.
Do not treat the documented commands or UI labels as evidence that those steps
have run. The completed producer slice has its own separate regional-observation
parity evidence; that does not qualify this new end-to-end walkthrough.
