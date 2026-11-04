# Household wealth migration damping correction — source only

This separate child of `701bd3fe960d1761e9aa3c7c5d1d7bf41d00464d` makes an
intentional default native mechanics correction. It is not an optimization,
coefficient retune, measured migration improvement, or scientific qualification.
The source branch is `lead/dev-household-wealth-damping-20261030`.

## Reachable input domain

`household::household_effective_wealth` returns personal wealth plus the wealth
of a live, identity-matching spouse, with no minimum for either balance or their
sum. A missing/dead spouse returns personal wealth. Marriage eligibility does
not impose a wealth minimum. Although new agents start at `0.5`, `wealth_tick`
adds income, multiplies by `1 - WEALTH_DECAY`, then clamps to `[0, MAX_WEALTH]`
(`MAX_WEALTH = 100`). A zero-income balance can decay below `0.01`; farmer
income can be zero with zero resource yields, and merchant trade income can be
zero. The optional credit transfer path also permits a balance to reach zero.
Neither starting wealth nor the clamp proves a `0.01` lower bound. This is a
source reachability argument, not a measurement of household frequency.

The decision stage runs for a non-displaced agent when pooled effective wealth
`e` exceeds personal wealth `p`. Previously it calculated:

```text
r = e / max(p, 0.01)
factor = 0.88 * (1 / r^1.20)
migration_utility *= factor
```

For `p = 0` and live spouse wealth `0.005`, `r = 0.5`, so the factor is about
`2.02`: it amplifies positive migration utility despite the damping intent.
For sufficiently small positive pooled wealth, the old `f32` power/reciprocal
can also cease to be finite. No native execution or observed population rate
is claimed here.

## Narrow corrected contract

Only the ratio expression changes:

```text
r = max(e / max(p, 0.01), 1)
```

The spouse lookup, `e > p` condition, displacement guard, denominator floor,
coefficients `0.88` and `1.20`, reciprocal/multiplication order, utility stage,
observer fields, gates and random draws remain in the same decision stages.
For the normal finite nonnegative wealth domain, an applied multiplier is
finite and in `[0, 0.88]`; it cannot amplify positive pre-wealth utility.
Unapplied cases retain factor `1`.

Old computed ratios at least one are unchanged, including ratios involving
personal wealth below `0.01` when the pooled balance reaches the floor. Only
old ratios below one change: with `p < e < 0.01`, the factor becomes `0.88`.
This also strengthens damping where the old factor was already below one;
the correction is not restricted to old factors above one. A negative utility
is still multiplied by the existing positive factor before the existing gate.
There is no new general validation policy for malformed/nonfinite pool state.

## Prospective regression coverage

Six new Rust unit tests call the actual decision evaluator using a small
`AgentPool`, live spouse resolution and a test-only observer. They check the
actual pre/post wealth utility stages, rather than a replacement multiplier:

- Zero personal wealth, equal tiny balances, below-floor personal wealth,
  smallest normal positive wealth and smallest positive subnormal wealth.
- Exactly the pooled floor, its next `f32` neighbour, ordinary ratios and
  balances at `MAX_WEALTH`; old ratios at least one retain old factor bits.
- Unmarried agents, a zero-wealth spouse, a dead spouse and displacement.
- Finite nonnegative factors at the valid wealth extremes, and a multiplier
  that does not increase as pooled wealth grows for fixed personal wealth.

All six tests are **UNRUN**. No candidate/native import, native build, Rust or
Python test, simulation, World tick, checkpoint decode or GitHub write ran for
this correction. Source review and metadata/diff checks do not replace those
gates. No serialization schema, RNG parity or trajectory equivalence result
is asserted.

## Historical evidence and remaining gates

Old valid captures can contain a finite factor greater than one. Historical
readers must accept and report that source-specific value, preserving the
recorded `f32` stage joins; they must not retroactively impose this correction
or clamp old evidence. Nonfinite consumed arithmetic remains a separate
reader refusal. Frozen `701`, timing and reader packets are unchanged.

Before integration, obtain a different-author source review, build a fresh
extension from this exact child, verify its actual compiled classes and source
identities, run the focused new Rust tests, full Rust tests and standard Python
CI lanes, and retain the resulting evidence. As a default mechanics change,
it also needs the documented before/after template **200-seed full gate** and
matching procedural subset/full gates, with fresh source/build identities and
the existing thresholds. See [the native/full qualification guide](../DEVELOPMENT.md#native-and-full-qualification).
All of these execution and scientific gates remain held; parent CI and an old
native binary do not qualify the new mechanics.
