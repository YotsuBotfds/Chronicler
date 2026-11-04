# Bounded viewer index equivalence tests

The exhaustive `bundleIndex.test.ts` fixture comparisons now run in groups
of 20 turns. A failure identifies both the fixture and the affected turn
range. The default five-second test timeout is unchanged, as are production
code and the offline Python oracle's 110-second chunk limit.

The former single test per fixture performed all timeline comparisons and
all technique comparisons together. On a loaded host the systems, movements
and learning fixtures could exceed five seconds despite passing every
assertion. The new tests split that work without reducing its coverage:

| Fixture | Timeline turns checked | Technique turns checked |
| --- | ---: | ---: |
| systems | 122 | 122 |
| transport | 12 | 12 |
| cities | 252 | 252 |
| movements | 502 | 502 |
| learning | 502 | 502 |
| sample | 12 | 12 |
| Total | 1,402 | 1,402 |

Each original ordered turn list is sliced, and a per-fixture assertion checks
that concatenating the slices reproduces that entire list exactly. Fixture
domains still run from zero through the maximum recorded turn plus one.
Optional `VIEWER_EQUIVALENCE_BUNDLES` inputs retain the original timeline
stride of seven and the original all-turn technique domain; each is sliced
only after that domain is selected.

Actors, selected-event sampling, region ordering and every comparison inside
the original turn loop are unchanged. Array-identity and event-order checks
remain in place. The once-per-fixture provenance comparisons without a turn
cutoff, event-key lookups and missing-key assertion now have their own test,
between the timeline and technique ranges, preserving the old query order.
The five synthetic cases and three invalidation tests remain unchanged.

Fixtures are loaded/decoded once. Preparation and a `beforeAll` warmup keep
the same array objects and their lazy production indexes across ranges.
Every first query used to build a lazy index is also asserted against its
independent reference in setup, so warming cannot hide a wrong first return.
Expected results are never cached: every scheduled turn still runs the
original reference filters and assertions. Cold-index/invalidation coverage
continues to use fresh arrays in the unchanged synthetic and invalidation
cases.

Validation on the integration viewer runtime at `23f6136f`:

- Bounded index file: 168 tests passed with one worker and the unchanged
  five-second test timeout.
- With a generated 35-turn hybrid grain-reserve bundle supplied through
  `VIEWER_EQUIVALENCE_BUNDLES`: 173 tests passed, exercising the stride-seven
  timeline and all 37 technique turn points for that generated input.
- Full viewer: 621 tests passed across 60 files with one worker; lint and the
  TypeScript/Vite production build passed. All production viewer sources are
  unchanged from `23f6136f`.
