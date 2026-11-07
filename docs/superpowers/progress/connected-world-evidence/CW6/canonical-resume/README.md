# Canonical V6 checkpoint regressions with the final FULL program

Both playbook cases pass on clean runtime source
`eaa4a5d3e1cb5c958b5e32719601c28986c9f6ac`, imported native SHA-256
`59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`.
The driver uses the original `checkpoint_identity.CASES` seed, geography,
civilization count, horizon, target population and default checkpoint rule,
then appends the exact final FULL program flags. These explicitly include
all-region retail rules 2, workshop economics rules 2, funded movement branches,
repair infrastructure mode, strict native wealth observation, D3/D4/A6 active,
and joint timber/canopy supply. Procedural watershed flow is added only to the
procedural case. Original procedural 11 remains 32 regions/eight civilizations.

| Case | Turns | Resumed branches | Plain versus checkpointed | Result |
| --- | --- | --- | --- | --- |
| hybrid_s42_long | 200 | original 19-point spread | 112 files, zero differences | all 19 pass |
| proc32_hybrid_s11 | 40 | every checkpoint 1–39 | 41 files, zero differences | all 39 pass |

Every resumed exit is zero and every compared file has zero differences.
Native Arrow events are ordinary compared bytes. The existing comparator
excludes run manifests/logs and checkpoint files; it decodes the JSON bundle
and removes only `metadata.generated_at`. Per-turn validation files at/before
a resumed checkpoint are expected only on the uninterrupted side. Individual
file counts therefore vary; the actual reports retain them. These 58 branches
supplement the separately reviewed 22 active lifecycle branches, totaling 80.
They are checkpoint regressions on two fixed development worlds, not the
restricted 200-seed or procedural qualification gates and not held effects.

Actual command from `/workspace/cw-resume-final`:

```sh
PYTHONPATH=src /workspace/cw-evidence-native/bin/python /workspace/evidence/cw6/canonical_resume_orchestrator.py > /workspace/evidence/cw6/resume-canonical-final.log 2>&1
```

The saved driver refuses an existing output, wrong/dirty source or wrong
native extension and checks its complete identity after each case. It uses
one native child at a time and does not mutate the environment or raise the
offline timeout. The saved case selections pin the original and actual CLI,
turns and exact checkpoints. Elapsed time 920.933 seconds; summary SHA-256
`783cc756058d92d37e6a107bcc55a82f893c93cfc8db95f564dd6256283e8cba`.
Passing resumed outputs/checkpoints were deleted by the existing comparator;
raw straight outputs remain outside the checkout and their inventory is here.
Independent actual-source/result approval is recorded in the review receipt.

Independent actual source/configuration/result/Arrow readback approved the
completed cases. All six Arrow sidecars per case are readable, event spans
are 0–199 and 0–39, and native death/migration authorities close. Unknown
migration causes remain recorded (1,328/1,495 hybrid 42; 581/581 procedural 11),
not inferred as displacement or health benefits.
