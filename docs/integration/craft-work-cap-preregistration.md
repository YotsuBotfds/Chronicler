# Crafts capacity consumer preregistration

Recorded 2026-10-28 before source edits. Base:
`c1a9844bbd2bb67bca598b1d67c5e6da9e2a583d`; isolated branch
`lead/public-production-audit`. This narrow slice implements the shared
consumer identified by the [source audit](public-workshop-source-audit.md).
It does not implement or activate a work planner.

## Frozen contract

Add keyword-only `craft_work_caps: Mapping[int, float] | None = None` to
`cities.economy_columns` and `cities.with_economy_columns`. Keys are region
indices, values are finite nonnegative raw loads this call can work. Unlisted
regions retain the existing ceiling. A listed region receives
`min(existing_craft_raw_demand, cap)`. A cap can never raise capacity, create a
city, change farming allocation or change per-capita wares demand. Zero closes
that region's craft step for this call. Absent city columns remain absent.

The cap constrains the existing native raw-demand/production ceiling, not an
independent work field: it also reduces demand for raw materials. It neither
certifies labor/power nor attributes output to a site. Active effects may
change regional prices, income, trade, needs and later demographics; there is
no active-economy identity promise.

Validate keys as integer region indices (excluding bool), in range; values as
real numbers (excluding bool), finite and >=0. Reject malformed caps instead
of silently ignoring them when city columns can be built. A float32 Arrow
conversion must not round a binding cap upward: represent binding capacity at
or below the requested raw-load bound. Default `None` must execute the existing
arithmetic/Arrow path without new rounding or allocation. An empty mapping is
an identity request. Inputs and world/snapshot state must not be mutated.

No CLI option, WorldState field, native ABI/payload/schema change, event, RNG,
asset, payment or planner hook. No extra all-agent scan. This is used directly
by the existing city economy-column builder rather than a detached simulator.
Runtime callers continue to omit the argument.

## Prespecified regressions

1. `None` and empty mapping equal the legacy reference city-column values and
   Arrow batch bytes. Existing no-city/off/no-snapshot paths stay unchanged.
   World JSON and Python RNG state are unchanged by the call.
2. Only listed raw ceilings shrink; farm factor, wares demand, other columns
   and unlisted regions equal baseline. Large/equal caps cannot raise the
   ceiling. Validate negative, nonfinite, invalid-index and invalid-type data.
3. A binding nonrepresentable float32 cap stays <= the supplied value through
   the Arrow boundary, including a positive subnormal-underflow cap.
4. Calls zero -> partial -> omitted restore baseline with no cached cap;
   multiple cities in a region share one regional cap rather than receiving
   each a fresh allowance. No-city/empty-agent input cannot gain capacity.
5. If the existing native extension is available, feed the resulting columns
   to the real unchanged economy: zero/partial/full capacity changes actual
   wares output monotonically, is bounded by raw inputs, and never adds a
   second subtraction to farm labor. Repeated omission restores baseline.
   Native simulator payloads before/after pure input construction are equal.

Run focused Python checks with one worker and record concurrent machine load.
No Rust build, generated study, full simulation gate or performance benchmark
is required by this no-native-source slice. The existing bounded oracle lane
must cover the pure consumer checks without raising its 110-second limit;
native checks are explicitly marked and skipped there.

## Acceptance and stop rules

Accept only if all pure regressions pass and default construction remains
byte-identical. Report native checks as run/skipped independently. Do not
activate a runtime planner, relax the clamp, add a multiplier or select pilot
parameters to obtain positive effects. The workforce, public budget, output
attribution and water/power blockers in the audit remain explicit follow-up
work, even if this consumer passes. Keep evidence separate from prior source
and frozen qualification trees.
