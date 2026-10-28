# Global health censor observations: reader compatibility correction

Independent review of the [native publication composition evidence](scientific-publication-native-results-2026-10-28.md)
exposed an observer error. Production `finish_health_care` intentionally records
`censored_episodes` globally, without assigning a current living region to an
agent absent from the living pool. The previous audit required this optional
field in every regional row whenever it appeared globally, producing 112
false errors per fourteen-turn/eight-region proof bundle.

Observer correction `9c0e26a3c29955318877b0a6c0e00f483a4b792f` validates and
aggregates the global count independently. It checks a regional sum only when
all regional rows explicitly supply valid optional values. Missing regional
detail remains unavailable. Global censor aggregation also stays unknown if
any inspected health section omits or invalidates the optional field; a later
valid zero cannot turn missing earlier coverage into a known total. No censor
count is interpreted as a clinical outcome or cause of loss.

The source change is confined to the read-only audit. Production simulation,
bundle fields, native binary and raw evidence were not modified.

## Verification and unchanged historical failure

Python 3.13.5 offline verification passed **150 tests in 0.81 seconds**:
69 expansion-audit, 49 science-receipt and 32 comparison tests. The 13 new
cases cover the actual global-only production shape, negative/fractional/
non-finite global counts, mixed old/new optional coverage in different orders,
complete regional disagreement and partial regional coverage. The guard
recorded no native imports, network/subprocess attempts or oracle runtime calls.

The eight native composition bundles and 24 retained original three-system
development bundles were read with both the prior `ed17e1a4` and corrected
observer. All 32 input SHA-256 values were unchanged between scans.

| Existing evidence | Previous audit errors | Corrected audit errors | Warnings / truncation |
| --- | ---: | ---: | --- |
| Eight native composition executions | 896 | 0 | None |
| Original 24 development executions | 1 | 1 | None |

The one genuine historical seed-43 shuffled forecast error remains: negative
warning increment in the original `527a9ff8` study. Its bundle SHA-256 remains
`2f98dd603b57f85dd710202c17badcaf13ca7e4861b41e1da65ac94016cc8415`.
The fix removes the regional censor false positives without suppressing that
failure. Original data and all earlier readouts remain intact.

## Independent native composition review

The review checked all **230** inventoried proof files and found no missing or
changed inventory member. For each seed, both comparisons had the complete
23-file comparison set. Raw sidecars matched; only the bundle bytes differed.
The complete decoded legacy direct/resume difference was its generation
timestamp. The direct-v2/fork difference was exactly the source-2 prefix rule
plus resume/experiment metadata and generation timestamp. Actual serialized
native-agent bytes and the producer-captured final global Python/NumPy RNG
digests matched. No boundary-3 global RNG equality was inferred.

Both v2 fork bundles now have complete audits with zero errors or warnings.
At source 3 each recorded archive count two with neutral current policy belief;
at source 14 four/five seats paid and allocated 2/3 versus 1/3; at source 15
archive counts were ten/twelve while current policy confidence returned to .5.
These are dated archive/applicability/expense observations, not efficacy
estimates or certified independent units. No separate v2 no-op or information-
control comparison was added by the review.

| Retained external review artifact | SHA-256 |
| --- | --- |
| Prior 32-bundle audit index | `ee3770a2654e32437524f27e149bb940017c06f8739e52735ce529e3ffafb1eb` |
| Corrected 32-bundle audit index | `31f043373accdd58209fa96524fcbf650c706c51cf89b862b4e7034bda0e8d78` |
| Independent inventory/comparison/two-fork review JSON | `e547425d728a4a26b947dac7dbb3dac30ff96c4bc4f86390c6b1ec78f76428bd` |

The proof writer, registration and original reader hashes matched their
retained report/readout. A separately reviewed reader IO correction
`78bc4bae` rejects inventory escapes and existing/aliased outputs; that
hardening does not rewrite or invalidate the original safe-destination readout.
