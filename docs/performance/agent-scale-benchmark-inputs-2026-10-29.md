# Agent-scale benchmark job identity and input validation

On the separate `lead/agent-scale-benchmark-inputs-20261029` branch,
`scripts/agent_scale_benchmark.py` refuses invalid workloads before creating
directories or launching children. Previously `--repeats 0` or an empty
`--targets` could finish successfully without measuring anything. A NaN
timeout was accepted and could disable the elapsed-time comparison.

Measured turns, repeats, concurrent jobs, regions and civilizations must be
positive. Warm-up and target populations may be zero; zero population retains
the existing capacity-multiplier mode. Multipliers and timeouts must be finite
and positive. Target/seed lists must be nonempty, well formed and unique after
integer parsing. Use `--repeats` for deliberate repeated observations.

Repeated profiles now include the repeat index: for example,
`t1000_s42_r0_default.prof` and `t1000_s42_r1_default.prof`. Previously repeats
used the same destination, overwriting prior profiles or racing when jobs ran
concurrently. Only the profile filename receives the index. Simulation arguments,
warm-up, measured turns, source/native selection and timing calculations remain
unchanged. Separate benchmark invocations should still use separate profile
directories. The filename change is intentional.

The complete affected guarded `turn-speed` selection passes **52 tests in
0.32 seconds**, including 31 new cases. It checks refusal before directory or
process creation, zero-target/warm-up compatibility, twelve distinct profile
destinations and identical simulation arguments across repeats. The guard
records no native imports, factory calls or blocked I/O. The unchanged
110-second chunk bound remains in place.

A separate stdlib-only before/after reproducer confirms that the old source
accepts four invalid input cases and reuses one profile path across three
repeats, while the correction refuses those inputs and generates three paths.
Unprofiled child arguments match after the interpreter/script selectors. Its
receipt SHA-256 is
`fb798dd43e8555e3f53041728f428ca798423e4a975391fd25c7af424b8646eb`.
The first new test run retained one fixture failure: argparse requires the
negative list spelling `--seeds=-2,42`; correcting that test invocation left
the existing signed-seed behavior intact.

No benchmark workload, world, native build or performance comparison ran.
This improves measurement reliability; it establishes no simulation speedup
or scientific qualification. Simulation source, native code and CI workflow
are unchanged. The bounded runner only adds the new pure test file to its
existing small chunk.
