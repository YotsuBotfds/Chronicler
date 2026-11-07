# Independent civilian farm/title integration review, 2026-11-07

Reviewer: B3 integration owner, independently of the shared Python/native authors.
Actual source reviewed: `f05e4d30d1ba1febf608c32a21755c3acb823a5a`
(full care/guard prepared farm-time helpers) and
`64cf1febed1dab77af9dfc7b5f0e489f106569a8` (final civilian labor integration).
The four-file committed labor diff matches the previously inspected working
source. Supporting test/evidence-only source `11b8445b` and `0ee259ff` was
independently reviewed; the latter integrated as `efcc005c`.

**Source approval: no blocking finding.** This does not approve an unrun merge
or replace exact-head CI, whole-program compatibility/resume, held or profile gates.

The review followed the actual city-factor builder, native civilian farmer count,
native health deduction, shared work column, PL1/PL3 reservations, care/guard
preparation, RS2's explicit infrastructure settlement callback and retail title
check. The resulting contract is coherent:

- D4 installs the frozen service census before livelihood consumers, and its
  civilian urban/rural average uses the same remaining farmer denominator as
  native production. Named-work deductions divide by that civilian count.
- If rebinding a fresh native pool changes roster identities, the same health
  authority is prepared again before reserving livelihood work. This does not
  introduce a second health writer or RNG draw.
- Care and guard helpers expose complete, current prepared farm-equivalent
  shares. A failed wage or a truncated public frame does not restore time
  already removed from production. No historical/capped frame supplies title.
- Named infrastructure's actual delivered work enters per-person title removal
  and the shared granary-work subtotal. RS2 already settles it before retail;
  no new delivery allocation or settlement reorder is introduced.
- Retail captures the actual final float32 economy factor after all preparation
  hooks. It no longer checks titles against an intermediate factor from before
  late care/guard preparation. Its stable opening roster remains unchanged.
- All new functional paths are guarded by their existing opt-in features. No
  default-path provenance, merchant income location or casualty fix is inferred.

## Independent execution

On integrated root Python source `af697dc65d01b0eea0761ed86bff5d7ab0860850`
(only a viewer file was dirty), the native environment identity check passed
from the root checkout. The compiled extension was read-only at
`/workspace/cw-evidence-native`, SHA256
`59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`.

```sh
PYTHONPATH=src RAYON_NUM_THREADS=1 /workspace/cw-evidence-native/bin/python \
  -m pytest -q tests/test_connected_world_native_contracts.py \
  --basetemp=/workspace/evidence/b3/root-labor-review-native-stable
```

**16 passed in 6.10 seconds.** The native cases include explicit frozen-census
meal/income exclusion, later-recruit civilian entitlement, free and paid retail,
actual health loss with the civilian denominator, mixed urban/rural native
output, a natural 16-turn FULL development run requiring positive C2 farm
removal, final-input/title conservation, and native wealth-stage lifecycle
checkpoint restoration. They do not establish naturally activated IC/guard
work or exact resume of the entire active army/health program.

The first independent native attempt occurred during the lead's D1 cherry-pick
and stopped at collection on a conflict marker; no simulation ran. It remains
at `/workspace/evidence/b3/root-labor-review-native.log`. Running the environment
checker from the evidence checkout while deliberately importing root also
reported the expected checkout mismatch; rerunning from root passed. These
failures are not relabeled as native execution evidence.

An independent focused offline run on the contemporaneous root source produced
188 passes and three stale C2 expectation failures: provider-tail ordering,
the now-removed wealth exclusion, and the old assertion that only observers
follow care. These were sent to the health owner for reviewed contract updates.
That receipt is retained at
`/workspace/evidence/b3/root-labor-review-offline.log`; final integrated offline
CI must pass after those updates. No timeout or historical hash was changed.

Full active roster/health exact resume remains an integration gate: early D4
roster rebind changes the timing of that existing active-only path. The bounded
CW6 lifecycle runner must demonstrate exact continuation at actual transitions.
