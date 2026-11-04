# Household candidate: full Rust qualification

The separate household migration-journal candidate `ad887cc5` passed **1,093
Rust tests, with three ignored cases**, across all 37 suite summaries. Every
previous 1,088-pass/two-ignore test name and outcome remains present. The exact
additions are five household differential tests and one ignored prospective
benchmark. This qualifies the full Rust lane at the named source/build only;
performance acceptance and integration remain separate decisions.

## Frozen inputs

| Input | Identity |
| --- | --- |
| Candidate checkout | `/workspace/chronicler-household-candidate` |
| Source commit | `ad887cc507c1ee1289ad31de20ebf333c0100dce` |
| Repository tree | `e8cbd689e0a9a85c76f0f315e698a59919a2e9db` |
| Native crate tree | `f083f3da388312c66dc2820ddfe4e2369719d5ce` |
| Python package digest | `320316b63413ef814e231bddb42773c54697f000691e08932c86e27bfcae20b4` |
| Installed matching native extension | `9f494a2c6622f8ee80528abad378f3ec5c4e3663587a0400c73e6100208f86e3` |
| Matching release wheel | `192c5bab315153db85744d31987391a3dd957f3350d37412d299e74f5beacefa` |
| Cargo lock SHA-256 | `1a3fe8f890b8841f5be86059c5b6c276731c4009ef99d473ed5c7eb8858a2855` |

The preexisting wheel receipt names source `c6b7b33f…`; its actual native crate
tree was freshly checked equal to the candidate's `f083f3da…`. No rebuild or
installation was needed. The installed compiled submodule and all three real
native classes/schema receipts were checked before and after qualification.
Source cleanliness, package/Cargo/configuration identities, installed extension,
wheel/build receipt, compiler/Python/linker inputs and recorded environment all
matched. The source checkout remains separate from the integration branch.

The toolchain was the same rustc 1.99.1 / LLVM 23.1.1 and Cargo 1.99.1 used for
the prior frozen qualification. PyO3 used
`/workspace/chronicler-native-scaling-venv/bin/python`, CPython 3.13.5, with the
same `/workspace/chronicler-tooling/lib` linker path. No source, Cargo default
profile or installed runtime identity changed.

## Full commands and effective profile

The lead allocated one CPU slot while the existing scientific gates and another
native lane continued. The retained target from the prior debug-info experiment
was reused as a **sole-writer Cargo cache**:
`/workspace/chronicler-build-rust-debug0-d051-attempt-002`. No target was copied
or cleaned; Cargo validated fingerprints for the new source and PyO3 setting.
An accessible `/proc` executable/cwd/fd/maps scan found no other target user.
Unreadable privileged/zombie process fields are retained as a scan limitation.

The explicit `CARGO_PROFILE_DEV_DEBUG=0` setting retained unoptimized code,
debug assertions and overflow checks. One build job and one test thread were
used. First, build without executing tests:

```sh
cargo test --locked --manifest-path /workspace/chronicler-household-candidate/chronicler-agents/Cargo.toml --jobs 1 --no-run --message-format=json-render-diagnostics --verbose
```

Actual compiler-artifact records verified all **40 local artifacts**, including
**36 test binaries**, at optimization 0, debug information 0, assertions enabled,
overflow checks enabled and default feature only. This proof preceded every
full test execution. Then the canonical complete command ran once:

```sh
cargo test --locked --manifest-path /workspace/chronicler-household-candidate/chronicler-agents/Cargo.toml --jobs 1 -- --test-threads=1
```

It exited 0, with zero failed, measured or filtered cases. All old test
names/outcomes were compared as a multiset against the retained completed d051
debug-info-free full-suite log. The additions, all in `household::journal_tests`,
were exactly:

- `journal_retains_first_lookup_last_emission_and_reinsert_order`
- `journal_matches_reference_for_conflicting_shared_households`
- `journal_matches_reference_when_later_pairs_read_replaced_lead_decisions`
- `journal_later_pairs_observe_suppressed_rebellion_and_keep_prior_follower_records`
- `journal_matches_reference_for_seeded_conflicts_stale_and_recycled_slots`
- `benchmark_household_journal` — ignored, prospective benchmark

The two existing release-hardware timing tests also remain ignored. No ignored
benchmark budget, simulation scaling gain, full native Python lane or scientific
gate is newly qualified by this Rust result.

## Preserved monitor failure and resource scope

Attempt 001 ran 20:41:38–20:42:28 UTC and failed in the external storage monitor:
a rustc temporary directory disappeared after discovery but before `scandir`.
The wrapper terminated only its own Cargo process group; that build-only child
shows exit `-15`. **No full tests had run; this was not a Rust test failure.**
The original driver, failed receipt, partial artifacts and complete logs remain.

A distinct retry driver tolerates `FileNotFoundError` for vanished child
directories/stat races, while missing target root, permission errors and other
I/O failures remain fatal. A deterministic tiny fixture verified disappearing
directory handling, retained-file counting and propagation of `PermissionError`.
The new attempt reused normal Cargo fingerprints; it did not bypass source or
profile checks. Initial identities in both attempts are identical.

Attempt 002 completed 20:43:45–20:44:31 UTC. Build-only command wall time was
27.278 seconds, and full tests took 16.536 seconds, including monitor overhead.
Attempt 001 had already spent 48.730 seconds in build-only work. These are shared
host qualification timings with a partly rebuilt cache, not a speedup comparison.

The unchanged free-space floor was 3 GiB with a 512 MiB stopping reserve. The
declared reused-target allocation cap was 3 GiB. The monitor sampled every second
and checked terminal samples even after successful process exit. No storage
guard fired. Across 41 retry samples, lowest observed free space was
7,970,725,888 bytes. Sampled unique target allocation peaked/finished at
1,391,243,264 bytes (about 1.30 GiB); apparent logical peak was 1,437,689,652 bytes.
These are sampled cache sizes, not instantaneous maxima or process RSS. The
completed target remains retained for coordinated reuse, with no active writer.

## Evidence

All evidence is outside Git under
`/workspace/chronicler-household-qualification-evidence`. The complete retry is
`full-rust-ad887cc5-002`; `full-rust-ad887cc5-001` is preserved as a failed monitor
attempt. Drivers are external to the frozen source, and their exact bytes are
retained separately.

| Artifact | SHA-256 |
| --- | --- |
| Complete qualification receipt | `6c064a36a3a4f51390456b2557769b40d767a78a8c4ce519c5f77cc78994601e` |
| Effective compiler profiles | `c2585eaaca2e4c97993c2ca70caac9e4cb838770fc7642eddc4a77be22835a40` |
| Full test log | `6b761681ea21d3dc511fb4b529f306b156ab0a47999ff098b323a92b96f52027` |
| Storage samples | `f6b98bd687a7074c19dfb2d4c41ad5fe38610d3e9d2767e04eac0efb6c3600eb` |
| Preserved failed-attempt receipt | `eedbc620cdb1ddda703bb09cda12ffe1361155d7680aea10afe101f23032663e` |
| Retry driver | `04a7c83c1d2d54769077c31318c4adfe01c98fa27ebf068bc345e626a80c7317` |

The receipt also links full source/runtime/wheel identities, exact commands,
the original baseline log/receipt, all added test names, verbose compiler logs,
and pre/post identity equality. This evidence supplies the Rust qualification
requested for the candidate; it does not merge or promote it.
