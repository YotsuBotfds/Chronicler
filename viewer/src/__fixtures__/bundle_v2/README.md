# Bundle v2 Fixture Skeleton

These fixtures support pre-activation M62a contract tests.

- `small/manifest.json`: developer-scale valid manifest.
- `medium/manifest.json`: richer valid manifest with optional layers.
- `negative/missing_required_layer.json`: summary layer exists but is not required.
- `negative/unknown_layer_kind.json`: invalid `kind` value.
- `negative/malformed_manifest.json`: invalid manifest shape (`layers` is not an array).
- `large/PLACEHOLDER.md`: reserved slot for the accepted M61b-scale fixture.

The actual large fixture content is intentionally deferred until M61b accepted export artifacts are available.
