# Private second integration wave

Branch `private/integration-wave2-20261005` combines these exact reviewed inputs
without rewriting either history:

| Input | Drive ID | Bytes | SHA256 | Exact commit |
| --- | --- | --- | --- | --- |
| Seven-lane integration | 1XZ_oMjbco1cD0l7ULvjhcKHe_UYp-BmM | 13439509 | 71f39b39caf742a9a0f34d12e3190e2e0ddff6db82d8fc4340e4d2d2b2f26b4e | 56b3764b8436f92b05e958f53b32092ad6a5e463 |
| Detached governance harness | 1e7LjI63ImMWwZhTi9tvgq3CxUDO7ShlO | 346625 | 8438bb5c63cd87f0d2647ee1f8d0526666c871fc3e30719afc8a1864bc583066 | 8ed76bd4620d1aab509bf1ddc90f77ac80390482 |

Both derive from `edf72991cad58d6670b1f382c33d50d903a6054a`. The first
input tree is `a21cd74f3ca0821506eacb6e01bd6799487bd1df`. Whole archives,
exact member sets, member sizes/SHA256, both supplied verifiers, bundle
prerequisites, source bytes and input commit identities were checked before use.
The integration manifest has 541 payload files; governance has 32. Checkout
`.agents` and `.codex` directories were empty; no AGENTS.md or local skills were
present. The original checkout remains on its unchanged base.

Merge `686b1db1196843d8011207df524a9c3879ed2251` has the two input commits
as parents and adds exactly the 14 governance paths, byte-for-byte. It has no
conflicts or edits to existing files. Original seven-lane source refs,
corrected-baseline refs, governance original provenance refs and applied commits
are retained. `docs/governance/provenance.json` and the first wave's commit map
remain unchanged. The delivery's second-wave commit map records the complete
final graph and every new changed-path identity.

Governance remains a standalone synthetic-fixture experiment, disabled by
default. Production simulation, normal CLI, shared models, native bridge,
dependencies and lockfiles are unchanged from the reviewed integration. Fiscal
allocation/debt/rounding/carry/repricing, phase scheduling/reservations, elite/GP
calibration and conventions, succession/contribution handling and dedicated RNG
reservation remain explicit production gates documented in
`../governance/four-kernel-harness.md`. Synthetic tests satisfy none of those
gates. G05 remains permission-blocked and excluded: no access, reconstruction,
transfer attempt or substitute extractor. Original fishery/social and pandemic
work are outside this wave. No publication or external write is performed.

The only additional integration validation is
`tests/test_governance_dormancy.py` and its corrected-baseline artifact manifest.
The manifest is derived from the authenticated pre-optimization corrected
`423a67ce4a55dbce5ce131146736ac2bafdbab8e` report, never from this candidate.
Three workloads cover 120 complete turn snapshots, all ordered RNG primitives,
and all 20 output files. They run both with the modules present and with a
disabled harness call in a test-only callback after each turn: 240 total turn
comparisons and 40 file comparisons. Byte counts and SHA256 cover the complete
file set; no fields are removed and no numeric tolerance is used. The original
harness disabled-identity test remains intact. No production hook was added.

The existing replay fingerprint includes every Python module in the package, so
adding the five detached modules intentionally invalidates historical
checkpoints. This wave neither changes that rule nor adds checkpoint support.
Fresh checkpoints must use this combined source fingerprint; the established
off-mode-only envelope and pending stockpile bootstrap rejection remain.

Final acceptance requires fresh full Python and viewer tests, viewer build/lint,
the standalone synthetic example, dormant exact-output checks, and independent
read-only review against the final committed HEAD. Final logs, test skips,
environment identities and the review receipt are kept in the delivery evidence;
prior component counts are historical evidence only.

Native validation of this new combined HEAD is **pending**: no Rust toolchain or
compiled chronicler_agents extension is available here. The parent's separately
reported WSL qualification covers only original input `56b3764`: 3222 Python
tests plus 47 subtests passed, four skipped; 817 Rust passed, two ignored; 200
focused plus real-native hostage checks; 120 native-off snapshot/RNG/artifact
comparisons; 488 supported replay turns. Reported native binary SHA256 is
`1c4a2490df102c63ba067f2164e18a251c629fd70e5b94dfdcdca3b05edc4712`,
Rust 1.99.0, CPython 3.13.15. These are parent-reported results, not rerun here.
Hybrid snapshots and parsed outputs matched, but bundle bytes differed because
of household-stat key order, also reproduced on the unchanged baseline.
Optional Rust macro timing gates remain unaccepted because candidate and
baseline both timed out. No hybrid byte-exactness, timing gain, or qualification
of this new HEAD is claimed. The parent will coordinate native follow-up.
