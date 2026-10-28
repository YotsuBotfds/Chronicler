# Rust qualification debug-info experiment

Registered 2026-10-28 before compilation. This is one isolated full Rust test
experiment at frozen `d051d7c0`, native crate tree
`a4703ef4e9a21b5dbb194d318536a46e6ca8b71c`. The installed receipt release
`fb20dbc8…`, source, Cargo lockfile and all shared build targets stay unchanged.

## Question and control

The previous full qualification passed 1,088 tests, with two existing ignored
release-hardware timing tests. Its copied warm target expanded from about
1.7 GiB to 8.3 GiB. Removing only that completed disposable target reclaimed
8,905,719,808 bytes during a real disk-floor incident. Can disabling test-build
debug information reduce this qualification artifact burden while retaining
the same complete tests, unoptimized code, debug assertions and overflow checks?

Set only `CARGO_PROFILE_DEV_DEBUG=0` as a profile intervention. Use a **fresh**
isolated target, one build job and one test thread, with the original toolchain,
PyO3 interpreter, linker library path and thread settings. Copy no build cache.
Do not change Cargo.toml/default profiles, enable release optimization, disable
assertions/overflow checks, rebuild/install a wheel, or alter the installed native
extension. Do not run the two ignored release-mode timing tests.

The previous 173.389-second Cargo command reused copied dependencies. This run
is cold at the target level, though registry sources and filesystem caches may
be warm. Neither total, compile nor test timing is a controlled speedup comparison
against that baseline. Target footprint is the more defensible comparison;
baseline allocation and peak sampling were limited, so distinguish its observed
cleanup-reclaimed/final size from this run's sampled peak and logical/allocated
bytes. No universal disk-saving claim follows from one source/platform.

## Preflight and effective-profile proof

Before compilation, record immutable source/lock/manifest, baseline receipt/log
hashes, installed extension hash, exact toolchain/Python identities, environment,
Cargo metadata, and all applicable Cargo configuration files. Reject extra
profile/Rust compiler overrides or custom dev/test profiles. Retain the official
Cargo profile reference showing that the default test profile inherits dev and
dev uses opt-level 0, debug assertions and overflow checks. Metadata alone does
not expose the final compiler profile.

Then compile once without executing tests:

```sh
CARGO_PROFILE_DEV_DEBUG=0 cargo test --locked --manifest-path <frozen>/chronicler-agents/Cargo.toml --jobs 1 --no-run --message-format=json-render-diagnostics --verbose
```

Retain every compiler-artifact profile and verbose command. Before allowing test
execution, require each native-crate library/test artifact to report opt-level 0,
debug info 0, debug assertions enabled and overflow checks enabled, with no
unexpected features. Build dependencies may have Cargo's ordinary build-override
settings and are reported separately. A failed profile check stops this attempt.

Run the original complete test command exactly once after successful verification:

```sh
CARGO_PROFILE_DEV_DEBUG=0 cargo test --locked --manifest-path <frozen>/chronicler-agents/Cargo.toml --jobs 1 -- --test-threads=1
```

Require all 37 suite summaries, 1,088 passes, zero failures/filtered tests, the
same two ignored cases, and the same individual test names/outcomes as the
preserved baseline log. Record build-only and test-stage wall time separately,
plus their combined time; retain all original stdout/stderr and failure receipts.

## Resource and evidence policy

Compilation waits for the lead's explicit CPU slot. Use a new output directory
and a new target outside source/shared targets. Record target logical/allocated
bytes, file counts and filesystem free bytes every second, and largest final
files. These are sampled target peaks, not an instantaneous peak or process RSS.
Two scholarship workers continue growing their output, so startup free space
alone is insufficient. Stop the owned process group if free space falls below
3 GiB plus a 512 MiB stopping reserve, or unique allocated target size exceeds
the registered 2 GiB cap;
report the trigger and preserve failure evidence. Sampling cannot guarantee an
instantaneous hard filesystem floor. Never signal another worker or clean a
shared target. No automatic failed-artifact deletion.

Verify source, configuration, toolchain inputs and installed extension again
after each stage. Keep evidence outside Git. Retain completed output until the
lead coordinates removal of this exact generated target; logs/receipts and the
original cache stay. Focused harness tests may use tiny fake trees/artifact
messages, never substitute for the actual full suite. No production adoption or
profile-default change is part of this experiment.
