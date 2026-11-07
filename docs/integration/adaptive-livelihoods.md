# Corrected controls in rules3

Corrected A6 is explicitly selected with `--adaptive-livelihoods-rules 3`.
The existing new-run default remains2; saved rules1/2 retain historical behavior. The
persisted default for missing old JSON/pickle fields remains2. Rules3 keeps
rules2 personal work, learning, information and trade policies, but its
`record_only` and `shuffled` controls cannot erase or redirect D3 war/home
inputs. Shuffle applies only to personal migration penalties, then unmodified
D3 contributions join them under the existing ±0.30 cap. D3 movement still
requires the enabled A6 dispatcher; this is independence from personal modes
and channels, not from the dispatcher feature itself.

`--adaptive-livelihoods-decision-channels` requires rules3: `all`,
`no_migration_experience`, `no_information` (migration-destination knowledge),
`no_work` (work/training choices), or `no_trade` (packet/failure trade filters).
These are saved marginal deletion controls, not additive causal effects.
Experience and would-decline observations remain recorded. Actual merged
native inputs are `frame.rows`; `a6_rows` and `d3_rows` expose the contributing
inputs before summation/capping, not individually caused outcomes.
`migration_rows_would` records personal penalties before controls, and native
receipts describe only combined realized gates/moves. Historical rules2
record-only/shuffle behavior remains available without rewriting old evidence.

# Adaptive personal work and training choices (A6 rules 2)

`--adaptive-livelihoods` remains opt-in. Rules 1 records experience and uses
the migration penalty. Rules 2 additionally applies dated personal experience
to new workshop, apprenticeship and academy offers. `record_only` records
the same decision inputs while accepting offers. Existing finite training
commitments continue; a new offer decision does not end an accepted course.

Workshop payroll supplies the exact individual's untruncated wage transfers,
including arrears actually paid this turn. This is a cash receipt, not an
estimate of the marginal wage for today's hours. The shared native paid-work
receipt supplies withheld income only when its work share matches that job's
share. A combined share that cannot be attributed is null. A household retail
pilot's regional harvest does not establish a person's counterfactual forgone
title: that cost is null. A non-farmer or a person outside the title pilot has
zero title cost. Null components never become an invented zero or cause a
monetary refusal. Known workshop net cash at most zero over the preceding ten
turns excludes the person from a later workshop crew plan. The planner keeps
its intrinsic eligible count; a choice exclusion is not an army exclusion or
a booked worker.

Academy attendance and apprentice seat/stipend records provide personal
training observations. Attending is real skill/qualification progress and
does not have a fabricated zero monetary benefit. A person declines a new
offer of the same training kind after two failed-progress observations in
the preceding ten turns and no successful progress in that window. Exact
stipends and observed withheld income remain separately visible. Training
attached to an already paid workshop crew has no additional foregone time;
the workshop's wage is not booked a second time.

Offer decisions are deduplicated per person, kind and turn; current-turn work
is never used to choose a current-turn offer. Pool replacement clears all
personal memory and transient indexes. Native-pool identity is never guessed.
Work memory is capped at 16,384 newest deterministic keys, with explicit
dropped counts. Current work, offers, migration refusals and quick departures
have bounded 256-row frame samples with totals. Individual history points to
these observations, not a regional total assigned to that person.

Rules 2 also gates migration information through each person's own prior
residence history, live bonded people's residences and positive, unexpired
native packets issued before the decision turn. The Python dispatcher reads
only bound X1 `OwnRow` accessors for T−1; native bonds and packets retain their
existing authorities. The native setter returns source masks: 1 own prior
residence, 2 a living bond formed before T, 4 a recognized packet issued
before T. Unknown destinations use an empty-land prior with the person's
home food/satisfaction observation, without reading foreign population,
capacity, food or voluntary pulls. They remain possible destinations.

Titled-trade planners in rules 2 use only the carrier's own dated trade
packets. A closed shipment is dated personal experience. A returned, released
or seized shipment excludes its destination for the following ten turns;
another merchant's failure and a same-turn return do not inform the choice.
Successful delivery is separately recorded. The packet substrate's existing
positive-intensity decay/expiry authority is used; no second packet TTL is
invented. Rules 1 and `record_only` keep the existing trade planner choices.

D3 local war and return signals join the same bounded signed migration score,
clamped in aggregate to ±0.30 per person/destination. Neither package moves
people in Python or bypasses closure, liquidity or household movement rules.
See [war consequences](war-consequences.md) for their dated sources.

Focused Python tests cover real payroll receipt intake and later unpaid-work
refusal, new academy offers after personal failed attendance, successful
training progress, null title costs, deduplicated probes, bounded frames,
pickle restoration and pool reset. The integration owner must still record
native crew-decline validation, feature-off identity, enabled exact resume,
fresh held evidence and integrated browser results. No qualification result
is claimed here. Repair, granary, woodcutting and care planners use separately
reviewed adapters; the existence of this API does not establish their intake.
