# Native diagnostics/index integration candidate — 2026-10-29

`lead/native-diagnostics-index-integration-20261029` starts from exact Stage 2
`feb98c0d1907ffb2c79397add853b191ebfe48a9`. That source passed all six standard
jobs in [run 40817155088](https://github.com/YotsuBotfds/Chronicler/actions/runs/40817155088),
including 11 new Rust and seven compiled API cases. Its producing branch/ref
and Stage 1 `e99c0fd5` remain frozen and separate from this candidate.

The only integrated runtime commits are the reviewed native index work:

| Original reviewed source | Local cherry-pick | Change |
| --- | --- | --- |
| `c60fde977d0865fbe651c3f716067d2de5c1a548` | `2bc54bd9` | Reuse post-migration region partition for readonly memory-intent collection and demographics |
| `e2b7c940a86911a5ae57a74e0b4df3db6dbd3717` | `86772a66` | Retain only dense needs-phase ID lookup through drift, knowledge and pre-decision household use |

All native source merged automatically. The sole cherry-pick conflict was the
continuation header; resolution retained both Stage 2/Stage 1 notes and the
index note without importing unrelated parent documentation. No wealth-floor
correction, scientific policy, threshold or sample change is included.

## Preserved boundaries

Stage 1 read points and Stage 2 household/application hooks stay in their
original phases. The BTreeMap provenance sink and bounded frames remain
default-off. Applied ordinals remain indices of the full native event batch.
No observer population is defined by a retained Stage 1 prefix.

The shared dense lookup contains identity/slot correspondence only; consumers
still read current co-location, sentiments and other pool values. Sparse maps
are dropped at their original needs-count boundary and rebuilt at original
drift/knowledge/pre-decision points, preserving RandomState construction and
lexical lifetimes. Demographic liveness/identity changes invalidate the old
lookup and retain fresh later indexes. The post-migration partition is shared
only across the original readonly intent interval into demographics; the
post-demographic partition stays fresh. No loops or arithmetic were combined.

## Genuine legacy determinism contract

The historical Python `test_legacy_determinism` imports Rust-only `AgentPool`,
`MemoryIntent` and memory helpers. The module's Python entry registers only
the three Simulator classes. Its native-present skip therefore indicates an
unavailable low-level Python interface, **not absence of the compiled module**.
The original Python testcase, skip reason and previous CI evidence are kept
unchanged; no public Python/Rust API is added solely for a test.

The Rust integration suite gains one ordinary unignored
`test_independent_parent_child_legacy_sequences_are_identical`. It ports the
same parent persecution memory at turn 10 and child inheritance at turn 50
using current `expected_agent_id` guards. Both independent runs require exact
nonempty extracted intensities **-45** and **-22**, stored parent/child values
**-90/-45**, timestamps, child decay override and actual legacy bits. It then
compares all memory arrays, counts, gates and legacy masks. This adds genuine
low-level determinism coverage; it does not reinterpret the old Python skip
as a pass or claim Python inheritance execution.

## Qualification status

This composition is a concrete source candidate. Independent component CI,
source review or benchmark results do not qualify the combined source.
No local native build/import, Rust/Python test, pool, world or replay ran.
Source diff checks are the only local verification so far. The next Python
adapter work will use a child branch in this same checkout; final frozen-source
review and one combined standard CI run follow. Later whole-world/observer
proof requires its own admitted source-bound execution. No merge to review or
main, default promotion, controlled performance gain or population outcome is
claimed here.
