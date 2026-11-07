# Final enabled exact resume at observed active states

Runtime source: `eaa4a5d3e1cb5c958b5e32719601c28986c9f6ac`, clean
`/workspace/cw-resume-final`, imported native SHA-256
`59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`.
The final 120-turn FULL timing pilots template 5/procedural 19 selected the
states. No held world, altered world or invented activation was used.

Both cases pass. Uninterrupted versus checkpointed and every resumed output
compare through `checkpoint_identity.run_case` / `cities_identity.compare`:
all files byte for byte, JSON bundle decoded with only its generated timestamp
removed; manifests/logs and checkpoint files follow the existing comparator's
exclusions. The native untruncated Arrow events are compared as ordinary bytes.
Procedural 19: 10 resumes, each 16 files, zero differences. Template 5: 12
resumes, each 10 files, zero differences. Writing checkpoints also changes
nothing (16 and 10 files respectively). Both subprocess/driver exits are zero.

The public strict resume planner validates actual seed/geography, complete
120-turn horizon, exact FULL CLI, real active categories, JSON bundle SHA,
Arrow hash/bytes/counts and runtime identity. The recorded evidence driver
retains that immutable plan and adds real first D3 wounded/released/evacuated/
returned checkpoint boundaries and their preceding nonzero checkpoints. It
does not edit the public plan or claim the public `run` selected extra states.
All seven broad categories activate: army meal/requisition, injury/release,
escrowed moving timber, named paid maintenance, dated health report/guard,
A6 personal memory and X1 displacement.

Procedural checkpoints: 1,2,3,6,18,19,33,60,62,63. Positive army consumption is
saved at checkpoint 2; evacuation at 3; actual return at 19 (source turn 18).
Template checkpoints: 1,3,4,5,6,12,13,15,24,61,71,72. Actual wound before/after
5/6 and return before/after 12/13 pass. The first procedural wound/release is
source turn 0, so checkpoint 0 is unavailable: only completed-turn 1 is tested
there. Template 5 provides the separate wound before/after comparison. This
covers observed transitions, not every possible cargo/claim/birth/estate or
pool-reset lifecycle. The unit/native/compatibility suites cover those
contracts separately; canonical playbook cases are retained separately.

Source and selected states were independently inspected by the health agent
and its separate reviewer (driver SHA-256
`860d104c2f4815f51d00e95420a8354345b5277e2dd24091ba27c919c88913ec`).
The completed actual-result readback is recorded in the final evidence receipt.
No extension rebuild, environment mutation or offline timeout increase occurred.

Actual commands, with source/import/native checks in the saved driver:

```sh
cd /workspace/cw-resume-final
PYTHONPATH=src /workspace/cw-evidence-native/bin/python scripts/cw_integrated_resume.py plan /workspace/evidence/cw6/pilot-final/runs/FULL-p19/chronicle_bundle.json /workspace/evidence/cw6/resume-final-p19-plan.json --stratum procedural --seed 19
PYTHONPATH=src /workspace/cw-evidence-native/bin/python scripts/cw_integrated_resume.py plan /workspace/evidence/cw6/pilot-final/runs/FULL-t5/chronicle_bundle.json /workspace/evidence/cw6/resume-final-t5-plan.json --stratum template --seed 5
PYTHONPATH=src /workspace/cw-evidence-native/bin/python /workspace/evidence/cw6/final_resume_orchestrator.py > /workspace/evidence/cw6/resume-final.log 2>&1
```

The saved driver refuses an existing output, wrong source/dirty tree, changed
pilot JSON/Arrow/plan/configuration and wrong native artifact. New reproduction
must use new evidence paths; do not overwrite the recorded run. Raw retained
straight outputs remain under `/workspace/evidence/cw6/resume-final/` and their
compact file inventory is pinned here. Passing resumed directories/checkpoints
were removed by the existing comparator after comparison.
