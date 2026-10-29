# Native tick index reuse — source draft, October 29

This isolated `lead/native-tick-index-reuse-20261029` draft starts at
`9b3cd4b56a2b5f4a23219d9326b703b3450ab4d1`. Its native source starts at the
same `a4703ef4e9a21b5dbb194d318536a46e6ca8b71c` crate tree as frozen C76.
The producing C76 checkout, native binaries and evidence remain unchanged.
No native build, Rust test, world, parity comparison or benchmark was run for
this draft. The structural work counts below are not measured speedups.

## Partition ownership

The post-migration partition is built after decision application and spatial
drift. Memory-intent collection only reads the pool and appends intents;
demographics can consume the same region buckets in the same region and
ascending-slot order. This removes one capacity scan and one set of region
buckets per tick. The partition after demographic deaths, aging and births
is still rebuilt for culture and conversion.

The new `test_memory_and_demographics_use_post_migration_census` reconstructs
the pre-demographic census from initial live slots and migration events. It
checks bit-exact expected mortality and current-turn conquest memories in
survivors, with a dead slot and a required migration exposure. It is unrun.

## Dense identity lookup ownership

The needs-only helper constructs `IdSlots` at the original co-resident bond
counting point, after needs decay and after wealth/settlement work. It returns
the lookup only if the existing constructor selected its dense table. A sparse
lookup is dropped at the counting boundary before restoration. Relationship
drift, knowledge and the pre-decision binding retain their original fresh
constructor and drop scopes whenever no dense lookup was returned. Public
standalone phase APIs still construct fresh lookups. Knowledge still returns
before constructing a lookup for an empty live set, and otherwise constructs
after observation.

No phase from needs through household consolidation writes IDs or liveness.
Merchant mobility and return can change regions; the retained lookup stores
only IDs and slots, and consumers read current pool regions, sentiments and
other fields at their original phases. Bond counts are never carried across
drift or movement. The retained lookup's last use is consolidation; demographic
death handling and all post-birth/slot-reuse work keep fresh lookups. The
pre-decision binding retains its original function-wide lexical drop scope.

`IdSlots::new` and its threshold, ascending-slot fill, ID-zero handling and
last-live-duplicate behavior are unchanged. Sparse fallback still constructs
`std::collections::HashMap` at each original eligible phase, preserving the
number and placement of `RandomState` constructions rather than assuming its
thread-local seed progression is unobservable to later maps. Dense reuse adds
no hasher or simulation RNG operation.

Let C be pool capacity and M the largest live ID. On ticks where all four old
constructors would run and choose dense tables, four constructions become one:
six C-length slot scans, three allocations and three zero fills of M+1 entries
are removed. Empty-knowledge short-circuiting can reduce that saving. Sparse
pools retain all original eligible constructions and claim no scan saving.

New unrun Rust contracts compare complete persisted needs, relationship and
knowledge state and knowledge statistics against standalone phase APIs for
dense and sparse pools. They cover live ID zero, a pre-needs death, current
region reads after a merchant-like move and bond counts recomputed after
drift. Pool contracts cover dead high IDs, ID gaps, duplicate last-slot
resolution, the exact dense threshold and fresh lookup requirements after
death, birth and slot reuse.

## Qualification still required

Source review and these unrun contracts do not establish compiled parity or
performance. Before adoption, build and identify a fresh candidate extension,
run the focused and existing Rust/native checks, and compare exact native
state, events and RNG-sensitive histories against the original source across
the listed lifecycle boundaries. Any timing study needs controlled original
and candidate builds and complete workload clocks. Full milestone standing
still requires the documented 200-seed before/after gate.
