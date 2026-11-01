# Explore a few real worlds

The small example generator uses the ordinary simulation CLI, always with
`--simulate-only`. It makes no narration or paid API calls. All bulky files stay
outside the repository; existing output folders are refused without modification.

| Example | Start and runtime | What to inspect |
|---|---|---|
| `aggregate-archive` | Template, seed 7, 24 turns, 6 regions/3 civilizations, no native runtime | Historical population, treasury, territory and events. Missing food stays unknown. |
| `grain-and-finance` | Template, seed 42, 60 turns, 8 regions/4 civilizations, hybrid | Public granary purchases/releases and finance. Granaries and transaction receipts explicitly enabled. |
| `procedural-health` | Procedural, seed 11, 40 turns, 12 regions/4 civilizations, hybrid | Generated geography, health-care observations and seats of learning. Care and scholarship explicitly enabled. |

These are naturally evolving runs from declared repository template/procedural
starts, with no manual state, stocks, treasury or dispatch edits. They are selected
examples, not a balance study. The constructed shipment and purchasing evaluation
fixtures are separate and explicitly labelled in their own reports. Neither
shortage-first purchasing nor delayed public grain shipments is enabled here.

## Generate in the current working session

The runtime activation below uses existing tools; it does not install or publish
environment configuration. Native inputs must match the selected checkout.
The generator verifies real compiled classes and records native hashes/imports;
it does not build or independently prove the native binary's source provenance.
Use the matching native build recorded in the active handoff.

```bash
cd /workspace/Chronicler-kimi
source /workspace/shared/chronicler-onboarding/runtime-6da9acae6bda6d7a.env
"$CHRONICLER_NATIVE_ENV/bin/python" scripts/create_example_worlds.py "/workspace/shared/chronicler-example-worlds-$(date -u +%Y%m%dT%H%M%SZ)" \
  --aggregate-python "$CHRONICLER_NO_NATIVE_ENV/bin/python" \
  --native-python "$CHRONICLER_NATIVE_ENV/bin/python"
```

Both selected interpreters must be Python 3.13 or newer. Aggregate uses a separate
native-absent environment, so its success cannot masquerade as native simulation.
`--commands-only` prints shell-quoted versions of the same CLI argument lists
without running them. `commands.sh` in the generated directory contains those
exact commands with existing-folder guards, `examples.json` records identity and
hashes, and `WALKTHROUGH.md` lists actual observed events and useful snapshot
turns. The recorded commands refuse existing sample folders; generate into a
fresh folder for new examples.

## Open and explore

```bash
cd /workspace/Chronicler-kimi/viewer
export PATH=/workspace/shared/node/node-v20.19.0-linux-x64/bin:$PATH
npm run preview -- --host 127.0.0.1 --port 4173 --strictPort
```

This serves the existing production build locally. Use `npm run build` first if
source changed. Open the local viewer, choose **Open Existing**, and load an
example's `chronicle_bundle.json`. Use **Saved world details** for its seed,
recorded range, mode and available history. A `state.json` is a forkable world
state, and a `.ckpt` is an exact-resume checkpoint; neither is a viewer bundle.

Select turn 10, choose a region or civilization, then open **Compare turns and
inspect history**. Compare 1 with 10. Unknown values remain unknown; inspect
events for recorded context and use **View turn** only when you want to seek.

Choose **Compare saved runs**, load two bundles, and inspect aligned population,
food and financial/conflict measures. Different example seeds, horizons and modes
make this an exploratory comparison. Download JSON or Markdown for another agent;
include `examples.json` for source provenance absent from older bundle metadata.

The generated walkthrough names observations that actually occurred. Do not
interpret nearby events as causes or deliberately constructed fixtures as
evidence about typical worlds.
