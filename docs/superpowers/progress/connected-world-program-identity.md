# Final Connected World feature-off identity

Final candidate `830d0dc2ecc7caad12217f88e47d6ffeb21309c1` completed all nine
official V5 cases with zero subprocess failures. Both comparisons passed:

- Original feature-off `8abc1acb3adf978ea212a570fb1dfbbfe9723ec3`:
  **9 cases, 399 files compared, 0 differences**.
- Preceding integrated main `f76436ae37c735b2b856caf98033122798ac88d2`, using
  its identical reviewed tree `11467a46b957a364b3d4d4ba2ba1a4326adcc6c3`:
  **9 cases, 399 files compared, 0 differences**.

The preceding main and reviewed head have the same Git tree,
`0c7cdfdcde7ea05dcc30c6eaa25637c03977c1ce`. This is the real preceding
integrated source, not the original development base. Before accepting reuse,
all tracked `src/` bytes were checked against Git: 247 original files, 270
preceding files and 287 final files, each with zero mismatches. These source
checks and their digests were repeated after the final run. An earlier archive
labeled D1 was rejected because its Python files did not match that source;
the correct preceding tree was freshly exported and its baseline matrix run.

Every case file is compared byte for byte, including Arrow validation output.
Bundles are compared both decoded and as raw bytes with only
`metadata.generated_at` normalized. No faith-id projection or broader output
normalization was used. This establishes default-path identity on this declared
matrix; it does not test enabled effects or every possible world.

The official cases are agents-off seeds 42/7 for 300 turns; hybrid seeds
42/7/1234 for 200 turns; 48-region hybrid seed 42 for 150 turns and agents-off
seed 7 for 200 turns; and historical scaled configurations seed 42/30 turns
(target 18,800) and seed 7/20 turns (target 43,700). Historical case names are
not a claim about actual agent counts; declared-scale profiling records those
separately. Case commands and the comparator are in unchanged
`scripts/turn_speed_identity.py`, SHA-256
`a0f241a0d074050ecfefe2e696815fab2a6475fd9e08cfbf749d26e0867cc7df`.

The final matrix used CPython 3.13.5, a private clean source export, one serial
simulation process, `PYTHONHASHSEED=0` and `RAYON_NUM_THREADS=1`. The actual
imported final release extension hash is
`59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`.
The original baseline used the independently rebuilt original extension
`8926c45b87f80cea732439b0d0513debb3ea314fbc56938648cec5dd6bfc951e`;
the historical Claude binary was not claimed recovered. The preceding D1
extension was
`f2fb24f13c386c3965e485330499b9aa435f61a43e8fc02023f950fbf9664256`.
Actual Python and extension import paths are retained for all three runs.

The final source differs from the active-profile runtime `eaa4a5d3` only by
startup choice validation under `src/` (plus posthoc tooling, tests and docs
outside `src/`). The native source is identical. Independent review of that
runtime delta found no change to valid fresh-world configurations; the final
candidate itself was nevertheless rerun for the complete identity matrix.

Compact receipts, all comparison lines, final run timing/import logs and
source checks are in `connected-world-program-identity/`. The exact final run
can be reproduced with the verified native environment from its clean source:

```sh
PYTHONPATH=src /workspace/cw-evidence-native/bin/python scripts/turn_speed_identity.py run /workspace/evidence/final-identity-repeat --source-root "$PWD"
python scripts/turn_speed_identity.py compare /workspace/evidence/identities/reference/out /workspace/evidence/final-identity-repeat
python scripts/turn_speed_identity.py compare /workspace/evidence/final-program/identity/previous-11467/out /workspace/evidence/final-identity-repeat
```

Regenerate each baseline with its matching native artifact and source export
when those external output directories are unavailable. The raw retained final
outputs are under `/workspace/evidence/final-program/identity/final-830d0dc2/`;
no restart or container-retention guarantee is implied. The full identities
also passed on earlier candidates `ccc864a9` and `43f02cca`; these older runs
are preserved as development evidence rather than substituted for this final
source check. Enabled resume, browser, held screens, independent PR review and
exact-head CI remain separate gates owned by the lead.
