# Independent CW6 source review by the health lane

Reviewed candidate: `d11bbb2a5d4e1bc41413f5b76c1acaa69858f8c9`, in the isolated
`cw-integrated-screen` worktree. This review did not author the runner or its
fixes. It examined the actual source, diff, preregistration and focused tests
for `cw_integrated_screen.py` and `cw_integrated_resume.py`.

Disposition: **source approved**, subject to the execution gates below.

The five arms preserve a fixed all-region retail enrollment rule. Three
whole-world primaries include zero-activation worlds; the explicit negated
readers yield the labeled FULL-minus-control contrasts. The joint timber and
canopy control cannot isolate either mechanism. Unknown native migration cause
255 is retained as a measurement loss, with all-migration counts checked against
the untruncated sidecar; it cannot establish reduced displacement.

Findings raised and verified fixed during review:

| Finding | Verified behavior in reviewed source |
| --- | --- |
| Guard lifecycle selector used nonexistent aggregate wage fields | Reads actual named members' positive paid wages. |
| Paid infrastructure selector could qualify a material coin sink | Requires delivered work and a named member's positive work and wages. |
| Requested pilot labels were not tied to actual world identity | Requires metadata/world seed 5 or 19, 8 template or 32 procedural regions, correct geography and complete 200-turn metadata/history. |
| A1 stale, incomplete or inconsistent primary records could pass | Requires current source/frame/native dates, typed completeness, exact post-turn-zero continuity and opening/closing/delta closure. |
| Requisition source split was not checked | Commons, granary and titled removals must sum to total removal before ration/destruction closure. |
| A missing event sidecar could become observed zeros | Requires present sidecar, nonempty bytes and hash, valid dates/drivers, aggregate migration agreement and native death agreement. |
| Resume plan did not pin the external sidecar | Preserves its complete measured identity and compares the freshly loaded sidecar at execution. |
| Mutable resume CLI/transition choices could mislabel tested state | Recomputes exact FULL CLI and actual transition selection at execution. |
| Generic runner default was three concurrent simulations | Defaults to one and rejects any other CW6 job count or duplicate declaration. |
| Enabled funded movement branches were absent from strict institutional checks | Validates all three D1 dated frames and their declared modes, including the movement-branch reader. |

Independent verification on the exact candidate:

```sh
PYTHONPATH=src /workspace/shared/chronicler-venv/bin/python -m pytest tests/test_cw_integrated_screen.py -q
# 24 passed in 0.18s
PYTHONPATH=src /workspace/shared/chronicler-venv/bin/python scripts/cw_integrated_screen.py check --screen CW6
# Seeds and extractor/packages/5 arms/131 outcomes/3 primaries: OK
```

These checks use constructed schemas and perform no native simulation. Actual
integrated-source pilot schema, timing, activation and compute projection are
still required before a committed freeze and any held execution. Enabled exact
resume must report which lifecycle categories actually activated, which were
missing and which could not be resumed. No held result, native identity test,
browser journey, qualification gate, CI or merge is claimed by this source
review. Any later shared health-extractor integration requires another diff
review and actual pilot validation.
