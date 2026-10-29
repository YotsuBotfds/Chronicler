# Household migration at near-zero wealth

Isolated behavior-correction draft, 2026-10-29. Base is exact
`d0281e5f57c508f27cea1676f36e0e6ed1225c9d`, whose unmodified native crate tree
is `a4703ef4e9a21b5dbb194d318536a46e6ca8b71c`. This is separate from the
active frozen full-gate sources and recovered research integration.

## Defect and reachability

The decision code intends pooled household wealth to damp migration utility:

    ratio = effective_wealth / max(personal_wealth, 0.01)
    multiplier = 0.88 / ratio ** 1.20

It enters that branch when effective wealth exceeds personal wealth. The
denominator floor can nevertheless make the ratio less than one: personal
0.001 plus spouse 0.001 gives ratio 0.2 and multiplier approximately 6.071.
Personal zero with spouse 0.001 gives approximately 13.947. Thus a component
documented as a damper can amplify a positive move utility.

These are valid native balances, not negative or nonfinite inputs. The real
domestic-credit transfer API can debit merchant wealth pro rata down to zero,
or leave a small positive remainder. `wealth_tick` permits merchant income zero
and then decays wealth by 2%; it imposes no minimum positive balance. A new
regression uses two normally spawned married merchants, the actual credit
transfer function and the actual zero-income wealth tick to reach this case.
It does not assign synthetic tiny balances directly. This establishes source
reachability; no occurrence frequency or attribution to historical causal
failures is claimed. Domestic credit is default off.

## Narrow correction

Clamp the existing ratio to at least one. The private helper preserves the
existing additional-wealth condition, flat 0.88 factor, exponent, multiplication
order and placement before action gating. There is no change to RNG draws,
destination choice, household consolidation, needs, roots, constants or schemas.

For every ordinary personal balance at least 0.01, the condition already implies
a ratio at least one; the clamp therefore changes no ratio bits. It also leaves
unchanged subfloor cases whose original ratio is at least one. No added pooled
wealth returns the raw utility, including signed zero. A positive subfloor
pooled balance now receives at most the existing flat 0.88 factor.

Four Rust regressions cover the below-floor counterexample, absent additional
wealth, original-bit parity for ordinary/threshold balances and the actual
credit/wealth path. They are unexecuted. No local Rust compilation was attempted;
the registered environment's qualified binaries are not reused as evidence for
this changed crate. The inactive proposed Rust workflow is under
`docs/experiments/household-wealth-floor-workflow.yml`.

Before promotion, run these regressions and the complete Rust suite, then qualify
the changed extension and relevant Python/behavior gates at exact source. This
is an intentional correction, not a trajectory-preserving optimization, causal
target calibration, scientific gate pass or main-branch change.


## Independent review and test activation

Independent source review cleared `9f43bbb7`: the clamp preserves existing
ratio and multiplication bits whenever the old ratio is at least one, and
leaves other action/eligibility/RNG paths intact. The credit-transfer regression
establishes permitted native API reachability; it does not measure the frequency
under ordinary Python lending policy.

The isolated branch `lead/cloud-household-wealth-floor-20261029` runs the four
targeted Rust regressions before the complete Rust suite, plus all existing
native Python, no-Rust, bounded offline and viewer lanes. Native Python builds
the changed crate and verifies its actual compiled module/classes. No local
native compilation or scientific worlds preceded activation. Results remain
pending; tests cannot substitute for a future full outcome gate. This intentional
behavior correction stays separate from main, the recovered research integration
and the running frozen full cohorts. No checkpoint is loaded across changed
native binaries.
