# Native shard context display: inactive V2 correction

The first hosted prototype at `847f164c99ea6974e197d6b95ab9ec9cd9f1e1c2`,
run `40858749837` attempt 1, **failed qualification**. Both native selections
finished without assertion failures: shard 0 reported 4,340 passes / 4 skips /
407 successful subtests; shard 1 reported 4,086 / 2 / 119. Their receipt writer
then failed on diagnostic context values: `bytes` in shard 0 and `inf` in shard 1.
Both receipts were absent, and both aggregate barriers correctly failed.
These test observations do not replace the missing qualification evidence.

The failed source, closed branch, old workflow/template and all first outputs
remain unchanged. The frozen negative pack is
`/tmp/chronicler-review-evidence/native-two-shard-qualification-40858749837/`;
its manifest SHA256 is
`55149d511b759161ff297a43a2e293b39357bdaa3e68be94f07e6371bbc1fc60`.
It retains eight original ZIPs / 87 outer members and all nine job outcomes.
Independent final negative peer SHA256 is
`5290e5bc339a01e364040eb2a249b828d72db24cc7676f3bf08255a80afefadc`.

Pytest 9.0.2's `SubtestContext._to_json` calls `dataclasses.asdict`, preserving
raw objects rather than guaranteeing JSON-safe values. The original local
qualification used 9.1.1, whose kwargs normalization masked this compatibility
boundary. The exact first offending context/node was not published; existing
source-level nonfinite/bytes examples are candidates, not recovered raw reports.

This separate V2 child changes **diagnostic context display only**. At each
report it formats raw `context.msg` and `context.kwargs` through pytest's
`saferepr`, capped at 256 and 1,024 characters respectively. A closed
`pytest-saferepr-display-v1` schema and 16 KiB JSON ceiling label these strings
as bounded display, **not lossless test inputs or authority values**. Capture
never calls `_to_json`, `asdict` or `deepcopy`, and retains no mutable raw label.
Labels can be truncated or identical; each parent/ordinal/outcome/report remains
separate in its original order and multiplicity. They are not identity keys.

Authority JSON still uses `allow_nan=False`. Parent phases, exact-once module
ownership, full collection, current-source wheel/package checks, the six
registered skips, 526 successful subtests and every aggregate barrier remain
unchanged. No assertion, skip, xfail, seed, simulation predicate, dependency,
resource limit or runtime code is changed.

The final affected module passed **97 pure cases / 0 skips** under the unchanged
110-second offline guard, using local pytest 9.1.1. A separately retained actual
`SubtestContext` case passed under the already installed **pytest 9.0.2**, including
raw bytes, nonfinite values, a policy object, cycles and a repr failure. It
forbids `_to_json` and exercises the strict complete report JSON/ownership path.
The broader fixtures cover repeated/mutable labels, display bounds and continued
global nonfinite-authority refusal. Both guards recorded zero native imports,
runtime factories and blocked IO. No full suite, World, native runtime, build,
network or hosted workflow was run by this correction.

Evidence: `/tmp/chronicler-review-evidence/native-two-shard-context-v2-20261029/`.
The 97-case receipt SHA256 is
`5000672fa5ef4295d0750c51b62d4c423f9a5ad864ce405f4f40e8a388140df0`;
the actual 9.0.2 metadata case receipt SHA256 is
`a303ee6e10ab6fe8aa9b9f41897b017178e933c89bfc71994a9572bedb6055ad`.
Actual interpreter/package-source hashes are retained separately for both.

`native-two-shards-v2.yml.in` is dormant. Compared with the original template,
it changes only its title and the closed future branch/path registration:
`lead/native-two-shard-qualification-v2-20261029` and
`.github/workflows/native-two-shards-v2.yml`. The old workflow stays byte-identical
and does not match that branch. All original other four gates, build/shard
resources and blocking barriers are preserved. A future one-file activation
copy is accepted by the contract only if byte-identical to this new template.
Source/peer/root review remains required before any push or fresh qualification;
there is no same-source retry, performance, science, reuse, main or adoption grant.
