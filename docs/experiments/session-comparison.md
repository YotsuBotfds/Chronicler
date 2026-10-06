# Compare two verified saved experiment histories

`scripts/compare_experiment_sessions.py` compares complete recorded experiments
after the accepted public loader validates both files, including all historical
replay. It reads each side once and writes nothing.

```sh
python scripts/compare_experiment_sessions.py --enable \
  --left checkpoint-a.json --right checkpoint-b.json \
  --transport transport.json --format json
```

`--format text` gives a deterministic text report. Without exact `--enable`, the
fixed off report precedes optional syntax/value parsing and all I/O. Explicit
`--help` or `-h` works before optional parsing. Enabled syntax, missing input,
transport, read, decode, replay and rendering errors produce one JSON error on
stderr, exit3 and no positive stdout. Every valid relationship exits0, including
conflicts and different genesis. Complete output is assembled before emission.

The public `compare_sessions(left=None, right=None, *, enabled=False,
transport=None)` requires an exact boolean and, when enabled, two explicit paths
and one exact public `TransportPolicy`. It returns a frozen `SessionComparison`.
`comparison_document`, `comparison_json` and `comparison_text` render fresh JSON
containers or deterministic text without exposing mutable report state. Both
files must declare exactly the supplied transport; differing transport policies
are outside this slice. No module exports or registries are changed.

| Relationship | Verified recorded-input comparison |
| --- | --- |
| `different_kernel` | Campaign versus memome; no shared-history/conflict claim |
| `different_recorded_genesis` | Complete genesis differs; differing top-level dimensions listed |
| `same_recorded_experiment` | Equal complete recorded genesis and full committed submissions |
| `left_history_prefix` | Equal genesis/overlap; only right continues |
| `right_history_prefix` | Equal genesis/overlap; only left continues |
| `conflicting_history` | Equal genesis; first unequal complete submission retained with exact turn |

Campaign genesis compares full policy, numeric topology and admission. Memome
genesis compares full policy, genesis turn and participant tuple. Same version IDs
or latest visible state do not override recorded-input differences. In particular,
distinct valid campaign admission tuple orders remain different recorded genesis,
even when their normalized current kernel state is equal. This checker performs
no new normalization or behavioral equivalence analysis.

With equal genesis, comparison uses the validated owners' canonical committed
campaign ticks or memome batches. All IDs, observations, draws, credits, rejected
proposals and empty batches count. A first conflict stops shared-prefix comparison;
later matching records cannot hide it. Conflict output includes both complete
submissions through their public dataclass fields with exact integer JSON values.

The accepted campaign demo through turn2 versus turn4 reports `left_history_prefix`,
shared count2, last shared turn2 and latest turns2/4. Swapping sides reverses the
prefix direction. March versus hold from the same ready turn1 conflicts at turn2
after one shared submission. The memome turn1 versus turn3 tables form a prefix;
different rejected proposals can leave equal participants but still conflict.
An empty committed batch is real history. Public proposal permutations that the
owner canonicalizes identically produce no false conflict.

Shared count/last turn are zero/null for equal genesis with no shared committed
submission: genesis is not a retained receipt. Different kernels or recorded
genesis report no shared-history claim (null count/turn). Per-side literal path,
generation, latest turn, kernel identity, source declarations and complete
file/session/genesis/history/latest digests are separate observations.
`file_digest_equal` and `generation_equal` do not determine the relationship.
Re-saving identical history with a different generation remains
`same_recorded_experiment`; generations are not ranked across independent files.
File hashes refer to observed bytes, not re-encoded canonical envelopes, and hash
equality alone is not asserted as byte equality or authentication.

Each public load uses descriptor regular-file validation and its accepted bounded
reader. CLI transport bootstrap uses the same public reader with 4096 bytes.
Read-symlink behavior is preserved; no path containment promise is added. Existing
per-file byte/history/record/integer domains apply, but do not bound combined
memory, output size or execution time. Runtime integer rendering limitations fail
before output; no global integer-digit-limit change is made.

The two reads are separate observations. Supplying the same path twice does not
coalesce them: a replacement between reads can correctly produce a prefix or
conflict. A descriptor-bound load remains about its observed bytes after a path
replacement. There is no simultaneous multi-file snapshot, reader/writer
coordination, lock acquisition, retry loop or mutation.

These relationships do not establish physical copying, chronological file lineage,
original capture identity, a shared session UUID, authentication, durability,
currentness or permission to overwrite. This tool supplies no recovery decision,
merge, rollback, history repair, fabricated electorate or receipt, scientific/native
qualification or production activation. Later actual-tree integration must confirm
the reviewed loader implementation and recheck replay/observations/nonmutation;
component test totals do not establish cumulative acceptance.
