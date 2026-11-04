# Recovery of seats of learning

This corrects institutional recovery in the opt-in scholarship layer, based on
`cb9fe70c` (2026-10-28). Scholarship remains **off by default**. It is a behavior
correction for scholarship-enabled worlds, not a new default or an optimization.

A destroyed seat used to disappear from the set of occupied learning sites
before the founding passes ran. A funded patron could therefore open another
institution in the same region in the very same turn. Only academies checked
the five-turn food-crisis cooldown; schools and libraries could open during a
continuing famine, and even an academy could open between its reports. The
review example was a fall at turn 183 followed by a founding at 185 while the
recorded famine did not end until 193.

## Shared site rules

Academies, temple schools and libraries now check the same site conditions
before a founding draw or payment:

- The region has a ruler and is not occupied by a hostile army.
- There is no actual famine: no current famine report, open famine episode,
  measured severe shortage lasting at least the ecology famine threshold, or
  famine cooldown in an aggregate/older save. An open dearth episode and a
  cooldown explicitly marked as dearth do not prevent founding. If a dearth
  deepens to the famine threshold between reports, it does prevent founding.
- The region has no current city sack or just-recorded conquest/occupation.
- At least `RECOVERY_TURNS = 10` turns have passed since the latest fall of
  **any** seat in that region. This is the existing strike/flight time scale;
  it is a minimum rebuilding interval, not ten consecutive healthy turns.

The old patron-specific requirements still apply: an academy needs its capital,
peace, treasury, culture and stability; a school needs an eligible temple of
the ruler's faith and prestige; a library needs a sufficiently rich, ranked
city. Founding remains probabilistic once all conditions hold. This change does
not automatically restore a seat, waive fees, or guarantee a founding date.

Recovery is regional. A new ruler, a different faith or a different institution
kind cannot bypass the interval. A further fall restarts it. An older fall in
another region does not delay a healthy site. The persisted `Seat.fallen_turn`
records already supply the recovery clock, so there are no new saved fields,
new counters or schema changes. The per-tick latest-fall index is rebuilt from
those records after loading.

Famine episodes close at the end of a turn, after scholarship has run. A famine
that ends at turn 193 therefore allows a founding from turn 194, provided the
regional interval and patron conditions also hold. This intentionally avoids a
founding before that turn's famine-ending event.

## History and causes

A reestablishment remains a `seat_founded` event and a `founded` entry in the
new seat's own history, preserving existing readers. Its text records that
learning returns after the preceding seat's fall, and its causes cite that
seat's `seat_fell` event when the saved history has an event ID. The fallen
seat is retained unchanged. Patron, institution and faith identities of the
new seat follow the normal founding rules.

## Verification

On Linux, using the project's locked Python 3.13 environment:

```sh
PYTHONPATH=src python -m pytest -q tests/test_scholarship.py tests/test_permanent_faiths.py -m 'not native'
```

The regression selection exercises all three institutions with every founding
draw forced to pass: an actual famine destroys a seat at 183, no replacement
opens in that turn or at 185, reports continue through 188, the episode ends
at 193, and learning may return at 194. A save at 185 followed by load produces
identical serialized worlds on every later tested turn, including the causal
founding record. Separate controls cover dearth, measured famine before its
next report, the aggregate/old-save cooldown, latest-fall ordering, cross-kind
replacement and an unpaid academy that cannot become a temple school in the
same turn. The original three famine regressions fail against the unchanged
base source.

Feature-off run comparisons use the same locked interpreter and Python-owned
ecology/politics, `PYTHONHASHSEED=0`, and identical arguments on the base and
changed source: template seeds 42 and 7 for 80 turns (default and explicit
`--no-scholarship`), and procedural seed 42, 32 regions / 10 civs, for 50 turns.
The existing scholarship identity comparator checks all run files, excluding
the source-specific manifest and log files and the bundle generation timestamp.

The focused selection passed **82 tests**, with **2 native tests deselected**.
The feature-off comparisons checked **33 files with zero differences** (9,
9 and 15 files respectively). The regression selection failed all three
institution cases against the unchanged base, then passed on this source.

No native, performance or full scientific template/procedural gate is claimed
by this document. Scholarship's earlier full-gate evidence describes its older
behavior; qualification of this opt-in correction is a separate step.
