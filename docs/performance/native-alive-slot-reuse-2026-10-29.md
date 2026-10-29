# Shared live-slot membership — source candidate, October 29

This isolated candidate starts at qualified Python source
`cbf6e368ebd218c1f54179bee4accffc1ab2a4c0`, whose native crate
`912a1a2489f8f8c548df19302bb2c0a4365fc32e` is byte-identical to the crate
at `95f73a74f809d7e10f09a1241c98014864350ffb`. The producing C76/95,
reader/audit and prior index-reuse sources, refs and evidence remain intact.
This candidate has not been built, tested or timed. The earlier C76-to95
default-export qualification does not qualify this new native source.

The tick already collects all live slots in ascending slot order immediately
after catastrophe/targeted deaths and before memory decay. That vector remains
available for the existing famine/prosperity intent loop. Skill growth, wealth,
settlement assignment, needs, relationship drift and merchant mobility change
no IDs or liveness before knowledge. The candidate passes that same membership
slice into the crate-private needs entry and a crate-private knowledge entry,
and traverses it for skill growth. It carries no region, wealth, relationship,
packet or other field value between phases: each phase reads current fields.

Public standalone needs/knowledge APIs still collect their own live sets.
Needs still decays before constructing its bond-count lookup, and the sparse
lookup still drops at the original counting boundary. Knowledge retains its
empty return before lookup construction and its decay/observation/lookup/
propagation/commit/statistics/arrival-clear order. Dense lookup reuse, sparse
`RandomState` constructor placement and all per-phase read/accumulation orders
remain as before. No runtime membership revalidation pass was added.

Demographic death/birth/slot reuse invalidates this membership. No new use
extends beyond knowledge; parent-needs/trait inheritance, death application,
births, newborn skills and the fresh post-demographic partition are unchanged.
The separate satisfaction-partition and drift scratch-cache suggestions are
not part of this patch. There are no new persisted fields, schemas, enums,
public APIs, RNG draws or checkpoint formats.

Let C be pool capacity and A the post-catastrophe alive count. The production
needs/knowledge calls remove two C-slot filtering passes and two temporary
live-index vector materializations (2A index writes and their capacity growth/
deallocation work). Empty vectors need not allocate. Skill growth replaces
the C-slot scan/liveness checks with traversal of the same A live entries;
every skill/progress operation still runs once, in ascending slot order.
These are structural work counts, not measured CPU, wall-time or RSS savings.
Allocator behavior, helper overhead and all other tick work still require
whole-workload measurement, including peak RSS on larger worlds.

Two ordinary Rust regressions are authored and unrun:

* `test_shared_alive_slots_match_fresh_phase_collection` restores identical
  persisted pool clones and compares complete persisted needs/drift/knowledge
  state plus knowledge statistics against fresh standalone APIs. Dense and
  sparse IDs, live ID zero, dead holes, all-dead and truly empty pools are
  covered. Location/arrival values change between phases; a later tick kills,
  spawns into old holes and refreshes both membership and identity lookup.
* `test_shared_alive_skills_use_post_catastrophe_set` calls the real complete
  tick with an existing dead hole and an explicit targeted death. It checks
  all skill bits against the original per-live-occupation growth, including
  threshold crossing/max clamping and progress saturation/reset. Age13 rules
  out births; later occupation switches start above the skill-reset floor.

The existing dense/sparse lookup differential receives only the new private
needs slice argument and retains its assertions. A bounded source-token check
reconstructs the exact allowed production transforms in all three files and
checks all public function signatures, the empty-knowledge ordering and both
test annotations. This is lexical source validation, not a Rust AST/type/
borrow check. `rustfmt`, `rustc`, `cargo` and `rust-analyzer` are unavailable
locally; no formatter, compiler, test, native import, World or benchmark ran.
Fresh compiled Rust/native/full CI, exact default-output comparison and any
scientific/performance qualification remain separate required work.
