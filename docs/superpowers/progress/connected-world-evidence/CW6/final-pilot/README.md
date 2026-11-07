# Final CW6 pilot and pre-held freeze

Runtime: `eaa4a5d3e1cb5c958b5e32719601c28986c9f6ac`, immutable native extension
59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617.
All ten cases pass strict extraction. Pilot development results informed schema,
mechanism coverage and timing only; no held seed was used before freezing.
The prior seven-failure native-payment pilot and pre-physics-fix 200-turn pilot
are preserved separately and do not qualify this runtime.

Commands run from `/workspace/cw-screen-final`:

```sh
PYTHONPATH=src /workspace/cw-evidence-native/bin/python scripts/cw_integrated_screen.py run /workspace/evidence/cw6/pilot-final --screen CW6 --cohort pilot --jobs 1 --keep-first
PYTHONPATH=src /workspace/cw-evidence-native/bin/python scripts/cw_integrated_screen.py check --screen CW6 --cohort pilot --metrics /workspace/evidence/cw6/pilot-final/metrics.jsonl
PYTHONPATH=src /workspace/cw-evidence-native/bin/python scripts/cw_integrated_screen.py report /workspace/evidence/cw6/pilot-final/metrics.jsonl --screen CW6
```

The receipt pins compact files. Full first bundles and Arrow sidecars remain at
`/workspace/evidence/cw6/pilot-final/runs/FULL-p19/` and `FULL-t5/`.
The screen report's generic fixed harm contrasts are control minus FULL;
CW6 outcomes explicitly labeled FULL minus control use the opposite sign.
Unknown cause loss feeds modeled C2 crowding as described in the preregistration;
this forbids interpreting lower classified displacement as a health benefit.
