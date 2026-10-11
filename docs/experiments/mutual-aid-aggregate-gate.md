# Aggregate follow-up on the unchanged executable repair

Executable repair commit: `cc2179a17c4da529315d3bae53015d48b8c75e3e`.
Executable/tested tree: `bf81fbfa24404416ee35b25a79beeb3141fe1c72`.
The earlier delivery commit `41d679d1fee70fb765c0196a7ac033330c952be7` added only
two documents. All 262 executable-source/build manifest entries remain unchanged.
This aggregate follow-up changes documentation only; no repair, policy, default,
new system or publication change follows the independently reviewed repair.

## Full default suites, not focused substitutes

The real native module was preloaded and checked for a compiled extension suffix,
three real simulator classes, and SHA256
`8f4ee68be6ce797854df323418789169ee113ee4f5f0e4508028dffee4a3e931` before full pytest.
Full native Python execution completed: **2951 passed, 4 skipped**. A second
complete run with skip reasons/JUnit confirmed **2951 passed, 4 skipped** in
118.28 seconds. Neither run restricted markers or test paths.

The exact Rust default command was
`cargo test --locked --manifest-path chronicler-agents/Cargo.toml --quiet`, using
the default/debug profile, PYO3_PYTHON=/usr/bin/python3.13 and the private
LIBRARY_PATH symlink workaround. All library, integration and doc-test executables
completed successfully: **821 passed, 0 failed, 2 ignored**. This is broader than
the earlier focused release-profile 373-library/38-merchant evidence.

Four Python skips remain explicit coverage limitations:

- M36 invest-culture directional test: 50 invested cases and zero non-invested
  cases, so its comparison lacks data.
- M38 full cascade: existing “Requires full world setup” skip.
- M38 pilgrimage frequency: existing calibration skip.
- M51 legacy determinism: imports eight low-level Rust names not exported through
  the Python module (including AgentPool and MemoryIntent). Its “extension not
  built” message is misleading; native was loaded and verified. Rust legacy tests
  are included in the full Rust default suite. No exports were added to satisfy
  this unrelated test.

The two ignored Rust cases are the existing `#[ignore]` 500-turn performance
benchmarks `regression_6k_24r_under_3s` and `regression_10k_24r_under_6s`. The default
suite ran completely; these explicitly skipped/ignored checks are not claimed as
executed assertions. No aggregate command is blocked.

## Default-off evidence kept separate from corrected cargo cases

Four freshly executed aggregate-off controls use 8 regions, 3 civilizations,
100 turns, and seeds 42,77,1337,2026. All normalized world histories compare
exactly between clean public Python source and repaired source. Only newly added
mutual-aid metadata is excluded. These aggregate-off cases do not exercise the
native merchant defects.

The existing 15-turn disabled-hybrid Python control compares clean public Python
and feature Python using the same repaired native package. Every normalized
history field, including commitments, is equal. It isolates default-off Python
feature effects and makes no assertion of equality to the buggy native kernel.

For affected cargo cases, a separate extension was built from clean public source
`edf72991cad58d6670b1f382c33d50d903a6054a`; its native SHA256 is
`dbdb0e194deb726c16073bc7c3e4ec5fe23694e575fd201b605ffb54bf2a6672`.
The probe imports no mutual-aid module and verifies aid is disabled. It injects
no merchant, cargo, ledger or buffer state.

Public native reproduces Loading departure overdraw: on turn 5, A has
4.3744096755981445 salt and queues 6 units, generating a raw
-1.6255903244018555 stock and matching positive clamp-floor correction. Repaired
native queues 4 units, leaves 0.37440967559814453 before consumption, and has zero
clamp correction. Exact native history equality is intentionally not required.

Both public and repaired probes record merchant agent 41 dying at turn 5 in
region 4, Way2, while carrying Transit cargo. Public native queues no return and
ends with live cargo zero but diagnostic outstanding cargo 0.9999997019767761
following graph shutdown and all surviving trips settling. Repaired native queues
one grain unit back to A and finishes with both quantities zero. The same death
occurs, so this evidence does not attribute the repair effect to mutual aid.

Both affected lifecycle files are identical between public base and the original
reviewed overlay; exact Git blob/SHA records accompany the runnable aid-free
probe and paired receipts. Concrete preconditions and minimal fixes are detailed
in the package's CARGO-BUGS.md and the original qualification report.

## Independent review and delivery

Fresh gpt-6.1-sol review approved the minimal repairs and independently confirmed
unchanged executable identity, full-suite logs and JUnit skip reasons, both native
binary hashes, source provenance, all four exact aggregate controls, and the paired
public/repaired probe events and accounting. No further source corrections were
required. New evidence/documentation is committed separately from executable
repair cc2179a.

The full default-suite gate has passed with the listed coverage gaps. Full hybrid
checkpoint continuation, new ecology scenarios, large-batch simulation validation
profiles, and publication remain outside this result. Publication is held.
