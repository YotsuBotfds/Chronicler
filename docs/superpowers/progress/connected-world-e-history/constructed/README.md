# Explicitly constructed visibility demonstration

This is a deliberately edited copy of the accepted natural FULL procedural-19 bundle. It demonstrates a paid individual receipt whose personal income cost is unknown. It is an illustration, not evidence of natural activation, an alternative simulated history, policy efficacy or qualification. No simulation or paid narration call ran; production source and the reviewed native extension were unchanged.

The original natural bundle remains byte-for-byte unchanged:

- Original SHA256: `f6cb5562a4aaec888b6f2a03b4c4b01bd1e8d49737aec22673034eba30ce0ee2`.
- Derived SHA256: `019f4b17c49f4e5960e5130b747e3790680312483e95d23eed50b33b29066d89` (37,963,691 bytes).
- Original simulation: `eaa4a5d3e1cb5c958b5e32719601c28986c9f6ac`; frontend: `e69f823b03e22242e59a3007667e1cabcab8fa9e`; extension: `59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`.

The derived raw artifact is `/workspace/evidence/history/constructed-demo/chronicle_bundle.json`. The compact committed [manifest](manifest.json) and [reproducer](reproduce.py) preserve its exact edits and recreate it from the hash-checked original. The original natural evidence under `../accepted/` is untouched.

At snapshot 27, person 13's saved granary-repair wage remains 2.000 coins. Exactly three receipt fields are edited: PL3 `income_replaced` becomes null instead of `0.09490852802991867`; the matching A6 `withheld_milli` becomes null instead of 95; and its source text explicitly names the constructed redaction. A6's dependent `net_milli` was already null and remains unknown. Cash, work, cargo, aggregate accounting and later simulated choices are retained observations from the original run; this copy only demonstrates redacted individual visibility. `metadata.constructed.from` contains the original SHA256 and `metadata.constructed.edits` explains all edits in the UI. Undoing precisely these fields and removing the marker reproduces the complete decoded source, including types and key order; the reproducer verifies that invariant and the unchanged original hash.

All **1,200 observations** pass the actual production strict readers: [validation](validation.json). The first-match finder retains the construction marker and yields 21 declared examples with zero schema errors, skipped validation or provenance flags: [finder receipt](examples.json). Two additional mechanical entries cite the edited PL3 and A6 rows by exact pointer and source turn 26, with zero audit flags: [edited-record provenance](edited-provenance.json). All narration here is mechanical saved-data text.

The actual production Chromium history journey passes **34 checks** on desktop (1440×900) and phone/touch (390×844): [browser receipt](browser.json). It opens the constructed notice, checks the exact original hash and every edit, then exercises the real person/project/chain/region/search links and verifies the preserved wage with unknown individual income cost. There are no console errors, explanatory clipping or document overflow. Both expanded banners were visually inspected: [desktop](desktop-banner.png), [phone](phone-banner.png). The evidence-only [wrapper](qa-banner.mjs) adds notice assertions/screenshots to the unchanged frozen journey; [harness identities](harness.json) retain both script hashes, and [identity](identity.json) retains the unchanged frontend/native identities.

Reproduce from the unchanged natural bundle and existing frontend build:

```sh
DEMO=docs/superpowers/progress/connected-world-e-history/constructed
PYTHONPATH=src python "$DEMO/reproduce.py" --source NATURAL/chronicle_bundle.json --out DERIVED
PYTHONPATH=src node viewer/scripts/validate-connected-records.mjs \
  --bundle DERIVED/chronicle_bundle.json --python python --out DERIVED/validation.json
PYTHONPATH=src python scripts/connected_world_examples.py DERIVED/chronicle_bundle.json \
  --validation DERIVED/validation.json --output DERIVED/examples.json
NODE_PATH=BROWSER_NODE_MODULES CHROMIUM_EXECUTABLE=/usr/bin/chromium PYTHONPATH=src \
  node "$DEMO/qa-banner.mjs" --source-script viewer/scripts/qa-connected-world.mjs \
  --build viewer/dist --bundle DERIVED/chronicle_bundle.json --out DERIVED/browser \
  --python python --journey history --turns 27
```

The recorded production build is the unchanged `e69f823b` build; its complete asset hashes are in the browser receipt. This packet adds no simulation, checkpoint or runtime feature behavior.
