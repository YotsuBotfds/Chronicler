# Cross-border guild leagues (D1b, `--guild-leagues`)

Default off. Connected-world program D1 ("bounded cross-border branches or guild cooperation, actual
costs and transfers, grievances grounded in recorded taxes, dues or service failures"); design from
AUDIT-D section 7.4(b)
([audit](../superpowers/audits/connected-world/audit-d-institutions-war-owned-stock.md)). Module
`chronicler.guild_leagues` (state `guild_leagues_state.py`); event notes from `cities._commerce` and
`cities._sack` (behind the existing livelihoods guard, beside D2's notes).

## Why

Guilds (`guilds.py`) stay inside their city's realm: a levy, a sack or an occupation falls on one city's
purse alone, and no institution crosses a border (AUDIT-D section 5). A league lets guilds of cities in
different realms pool part of their purses in a bounded mutual fund that pays a member's recorded
losses.

## The switch

`--guild-leagues` (mode `mutual`, default) or `--guild-league-mode dues_only` (the cost control: the same
links, leagues, dues and dissolutions; no claim is paid). Requires `--agents hybrid` (the links are
native merchant agents' recorded deliveries), cities and guilds (both on by default; feature catalog
settings `cities` and `guilds`). A saved switch is checked on every resume and refused, with a hint to
pass `--no-guild-leagues`, when one of these is gone; `--no-guild-leagues` dissolves every living league
(`switched_off`) and returns its fund to its members' purses. A livelihoods switch, as the closest
precedent (D2's attribution records), declared after C2 and before D2's observer.

## Mechanism (Phase 10, after the cities and guilds ticks)

1. **Departures.** A member leaves when its guild dissolved, its city fell, or its city's lord is no
   longer the lord it joined under (a conquest or cession: it joined across that border). A member that
   leaves keeps no claim on the fund.
2. **Dissolution** when two members' realms are at war, fewer than two members remain, all remaining
   members share one realm, or (step 4) no recorded delivery passed between two members' regions for
   `DORMANT_TURNS` = 20. The fund returns to the remaining members' guild purses pro rata to the dues each
   paid (largest remainder, ties by guild index; equally when none paid); with no member left it is
   recorded as unclaimed (lost).
3. **Links.** The economy's recorded merchant deliveries of this turn (`EconomyResult.inbound_sources`:
   in hybrid, the native merchants' delivery provenance) mark every pair of living guilds in different
   regions of different realms whose regions traded either way. A guild knows the goods that reach its own
   market and where its merchants go; nothing else is read (no other market, no provenance, no attribution
   record). Records are bounded (`MAX_LINKS` = 512) and pruned after `LINK_WINDOW` = 10 turns.
4. **Dormancy** (above).
5. **Claims** (mode `mutual`). The fund pays a member city's civic purse only for that member's recorded
   loss of this turn, noted at the event and matched to the city's history:
   - the levy's share of this turn's dues (`commerce x guilds.LEVY_SHARE`, noted in `cities._commerce`
     while a levy runs) when a `levy` entry of an earlier turn within `guilds.LEVY_TURNS` is in the city's
     history;
   - the plunder of a sack (the loot, noted in `cities._sack`, an occupation's sack included) when that
     turn's `sacked` entry with the same event id is in the city's history.

   Each claim is paid at most `min(loss, PAYOUT_CAP = 2 units, fund)`, once; the record keeps the event id.
   A noted loss without its history entry is refused and logged (`claim_unverified`).
6. **Foundings and joins.** A pair linked on `LINK_TURNS` = 3 turns within the window, of realms not at
   war, founds a league when neither guild belongs to one (id from `next_league`, never reused,
   checkpointed); a guild linked to a member joins that member's league when it has fewer than
   `MAX_MEMBERS` = 4 members, none of its realm (one member per realm) and none at war with it. Leagues
   never merge. A league dissolved by a war can be re-founded by members whose realms are not at war, under
   a new id.
7. **Dues**, once a turn per league: each member pays `DUES_SHARE` = 2% of its guild purse, at most
   0.25 units, while the fund holds less than `FUND_CAP_PER_MEMBER` = 3 units per member: a real purse
   transfer (the purse falls by exactly what the fund gains, to the purses' 1e-4 rounding, checked).

No random draws; every order is by league id, guild index or settlement id. No event is emitted
(records only).

## Duplicate influence (AUDIT-D section 4.3)

`city.grievance` and every proxy that feeds it (the levy's and the sack's grievance) are untouched: no
recorded quantity replaces a proxy here, so nothing stacks. The lord still receives the dues and the sacker
the plunder; the fund restores the civic purse and does not pay walls, so guild wall help is unchanged and a
league payout never also flows through city dues or wall help for the same event. Purses do reach
existing consumers: lower guild purses lower a guild movement's appeal (`guilds.movement_appeal`) and its
wall help capacity; a restored civic purse is plunderable again and funds walls.

## Conservation

Dues move purse to fund, claims fund to purse, dissolution fund to purses (or an unclaimed loss, counted).
Each league row closes `open + dues - claims - returned - unclaimed = close` every turn (checked; a failure
raises).

## Record (`snapshot.livelihoods.guild_leagues`, schema 1, stage `D1b`)

`mode`, `source_turn`, `frame` (null: not observed) with `leagues` (members with realm and join turn,
fund open/close, dues, claims, returned, unclaimed, cap, dissolution), `dues`, `payouts` (kind, recorded
loss, paid, event id), `changes` (founded, joined, left with reason, dissolved with reason and money),
`links`, `candidates`; `next_league`, the last dissolved leagues, `counters`, a bounded `log`,
`parameters`. Python reader `guild_leagues.record_status`; viewer `viewer/src/lib/guildLeagues.ts` (through
`recordReading.ts`) and the Livelihoods tab panel `GuildLeagues.tsx`.

## Boundaries

- Occupation without a sack pays nothing (no recorded loss); a member whose city changed lord this turn
  leaves before claims, so a conquest's sack is not paid.
- Links need hybrid merchants; aggregate modes are refused.
- Parameters are declared modeling choices, not calibrated.

## Tests

`tests/test_guild_leagues.py` (offline: registry, refusals, links and foundings, one per realm and war,
dues caps and once a turn, claims and their verification, dues-only, departures and pro-rata returns, war
dissolution and id reuse, dormancy, unclaimed funds, switch-off, record states, the cities notes) in oracle
chunk `connected-world-d1`; `tests/test_guild_leagues_native.py` (identity before the first league, natural
foundings, dues and levy claims against the dues-only control, exact resume with leagues holding funds);
viewer `guildLeagues.test.ts`, `GuildLeagues.test.tsx`.
