"""D1b cross-border guild leagues (``--guild-leagues``): offline contract.

No native extension: guilds and cities are constructed directly on the
template seed 42 world (four cities in four regions under four lords), the
economy's recorded merchant deliveries are a stand-in ``inbound_sources``, and
the Phase 10 hook is called turn by turn. The real-native path is
``test_guild_leagues_native.py``.
"""
from __future__ import annotations

import argparse
import json
import pickle
from types import SimpleNamespace

import pytest

from chronicler import guild_leagues as GL
from chronicler.cities_state import City, CityState
from chronicler.guild_leagues_state import COUNTERS, GuildLeagueState
from chronicler.guilds_state import Guild, GuildState
from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES, LivelihoodsState
from chronicler.world_gen import generate_world

#: (region, lord) of the four cities; city ids 100 + region; guild index = position.
CITIES = ((0, 0), (1, 1), (2, 2), (3, 3))


def _world(mode="mutual", cities=CITIES, wealth=10.0):
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    world.turn = 10
    world.active_wars = []
    world.cities = CityState(cities=[City(settlement_id=100 + r, region=r, name=f"City{r}", founded_turn=0,
                                          founder=lord, lord=lord, wealth=20.0, commerce=1.0)
                                     for r, lord in cities])
    world.guilds = GuildState(guilds=[Guild(city=100 + r, region=r, name=f"Guild{r}", founded_turn=0,
                                            wealth=wealth, lord=lord) for r, lord in cities])
    world.livelihoods = LivelihoodsState()
    GL.set_guild_leagues_enabled(world, True, args=argparse.Namespace(guild_league_mode=mode))
    return world


def _econ(world, *pairs):
    """Recorded deliveries this turn: (from region, to region) pairs."""
    names = [r.name for r in world.regions]
    inbound: dict[str, list[str]] = {}
    for src, dst in pairs:
        inbound.setdefault(names[dst], []).append(names[src])
    return SimpleNamespace(inbound_sources=inbound)


def _turn(world, *pairs):
    GL.phase10(world, None, _econ(world, *pairs), None)
    world.turn += 1
    return GL._state(world).frame


def _league(world, n=3, *pairs):
    for _ in range(n):
        frame = _turn(world, *(pairs or ((0, 1),)))
    return frame


def _member_ids(world):
    return [[m.guild for m in league.members] for league in GL._state(world).leagues]


# --- registry and switch ------------------------------------------------------------

def test_switch_registry_cli_catalog_and_manifest():
    from chronicler import livelihoods as LV
    from chronicler.batch_manifest import SIMULATION_ARG_KEYS, simulation_config
    from chronicler.feature_catalog import REQUIREMENTS, SETTINGS
    from chronicler.main import _build_parser
    # Keep guild cooperation before X1 while the completed acting packages
    # consume the prior frame before the sole residence-ledger writer runs.
    assert LIVELIHOODS_SWITCHES[LIVELIHOODS_SWITCHES.index("guild_leagues"):
                               LIVELIHOODS_SWITCHES.index("residence_ledger") + 1] == (
        "guild_leagues", "war_requisition", "war_consequences", "adaptive_livelihoods",
        "public_health", "movement_branches", "residence_ledger")
    assert LV.LIVELIHOODS_CHOICES["guild_league_mode"] == ("mutual", "dues_only")
    keys = LV.LIVELIHOODS_ARG_KEYS
    assert keys[keys.index("guild_leagues") + 1] == "guild_league_mode"
    assert {"guild_leagues", "guild_league_mode"} <= set(SIMULATION_ARG_KEYS)
    assert REQUIREMENTS["guild_leagues"] == ({"agents": ["hybrid"]}, {"setting": "cities"}, {"setting": "guilds"})
    assert "guilds" in SETTINGS
    default = _build_parser().parse_args([])
    assert default.guild_leagues is None and default.guild_league_mode is None
    assert "guild_leagues" not in simulation_config(default)
    assert GuildLeagueState().mode == "mutual" and GuildLeagueState().next_league == 1


def test_never_enabled_world_notes_nothing():
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    assert GL._state(world) is None and not GL.guild_leagues_active(world)
    city = SimpleNamespace(settlement_id=1, lord=0)
    GL.note_city_dues(world, city, 5.0, 1.0, None)
    GL.note_city_sack(world, city, 3.0, "e1")


def _parse(*flags):
    from chronicler.main import _build_parser
    return _build_parser().parse_args(["--seed", "42", "--turns", "2", *flags])


@pytest.mark.parametrize("flags, drop", [
    (("--agents", "demographics-only", "--guild-leagues"), None),
    (("--agents", "hybrid", "--guild-leagues"), "guilds"),
    (("--agents", "hybrid", "--guild-leagues"), "cities"),
])
def test_refused_without_its_prerequisites(flags, drop):
    from chronicler.livelihoods import configure_livelihoods
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.cities, world.guilds = CityState(), GuildState()
    if drop:
        setattr(world, drop, None)
    args = _parse(*flags)
    with pytest.raises(ValueError, match="requires --agents hybrid, cities and guilds"):
        configure_livelihoods(world, args, agent_mode=args.agents)


def test_a_saved_switch_refuses_a_resume_without_guilds_until_ended():
    from chronicler.livelihoods import configure_livelihoods
    world = _world()
    world.guilds = None
    with pytest.raises(ValueError, match="pass --no-guild-leagues to end it"):
        configure_livelihoods(world, _parse("--agents", "hybrid"), agent_mode="hybrid")


# --- links and leagues ----------------------------------------------------------------

def test_three_turns_of_recorded_deliveries_across_a_border_found_a_league():
    world = _world()
    _turn(world, (0, 1))
    frame = _turn(world, (1, 0))                  # either direction counts
    assert frame.changes == [] and GL._state(world).links[0].turns == [10, 11]
    frame = _turn(world, (0, 1))
    assert [(c.kind, c.guild) for c in frame.changes] == [("founded", 0), ("joined", 1)]
    league = GL._state(world).leagues[0]
    assert league.league == 1 and [m.lord for m in league.members] == [0, 1] and league.founded_turn == 12


def test_no_league_without_enough_recent_deliveries_or_within_one_realm():
    world = _world()
    _turn(world, (0, 1))
    for _ in range(GL.LINK_WINDOW):
        _turn(world)                              # the first sighting falls out of the window
    _turn(world, (0, 1))
    _turn(world, (0, 1))
    assert GL._state(world).leagues == []
    same = _world(cities=((0, 0), (1, 0)))        # two cities of one realm
    _league(same, 3, (0, 1))
    assert GL._state(same).leagues == [] and GL._state(same).links == []


def test_joining_is_one_member_per_realm_and_war_blocks_it():
    world = _world(cities=((0, 0), (1, 1), (2, 2), (3, 1)))
    _league(world, 3, (0, 1))
    world.active_wars = [(world.civilizations[0].name, world.civilizations[2].name)]
    _league(world, 3, (0, 1), (2, 0), (3, 0))
    # Guild 2's realm is at war with member 0's; guild 3 shares member 1's realm.
    assert _member_ids(world) == [[0, 1]]
    world.active_wars = []
    _league(world, 3, (0, 1), (2, 0))
    assert _member_ids(world) == [[0, 1, 2]]


def test_dues_are_a_capped_purse_transfer_once_a_turn():
    world = _world(wealth=10.0)
    frame = _league(world)
    dues = {d.guild: d.milli for d in frame.dues}
    assert dues == {0: 200, 1: 200}               # 2% of 10 units
    g = world.guilds.guilds
    assert g[0].wealth == pytest.approx(9.8) and GL._state(world).leagues[0].fund_milli == 400
    rich = _world(wealth=100.0)
    frame = _league(rich)
    assert {d.milli for d in frame.dues} == {GL.DUES_CAP}
    # Until the fund holds its cap (3000 per member): then nothing more is taken.
    for _ in range(40):
        _turn(rich, (0, 1))
    assert GL._state(rich).leagues[0].fund_milli == 2 * GL.FUND_CAP_PER_MEMBER
    league = GL._state(world).leagues[0]
    with pytest.raises(RuntimeError, match="twice"):
        GL._dues(world, GL._state(world), GL.LeagueFrame(turn=league.dues_turn), {}, league.dues_turn)


def _noted(world, city_id, **note):
    t = GL._turn(GL._state(world), world)
    t.notes[city_id] = note


def test_claims_pay_recorded_levy_and_sack_losses_up_to_the_caps():
    world = _world(wealth=100.0)
    _league(world, 12)                            # the fund holds 12 x 2 x 250 = 6000 (its cap)
    city = world.cities.cities[0]
    city.history.append((world.turn - 3, "levy", "ev-levy"))
    city.history.append((world.turn, "sacked", "ev-sack"))
    _noted(world, 100, levy=150, sack=(9000, "ev-sack"))
    before = city.wealth
    frame = _turn(world, (0, 1))
    paid = {(p.kind, p.event_id): (p.loss_milli, p.paid_milli) for p in frame.payouts}
    assert paid == {("levy", "ev-levy"): (150, 150), ("sack", "ev-sack"): (9000, GL.PAYOUT_CAP)}
    assert city.wealth == pytest.approx(before + 2.15)
    row = frame.leagues[0]
    assert row.payouts_milli == 2150 and row.fund_open_milli + row.dues_milli - 2150 == row.fund_close_milli


def test_unrecorded_claims_are_refused_and_dues_only_pays_nothing():
    world = _world(wealth=100.0)
    _league(world, 6)
    _noted(world, 100, levy=150, sack=(900, "ev-none"))       # no levy and no sack in the city's history
    frame = _turn(world, (0, 1))
    assert frame.payouts == [] and [r.kind for r in GL._state(world).log][-2:] == ["claim_unverified"] * 2
    control = _world("dues_only", wealth=100.0)
    _league(control, 6)
    control.cities.cities[0].history.append((control.turn, "sacked", "ev-sack"))
    _noted(control, 100, sack=(900, "ev-sack"))
    frame = _turn(control, (0, 1))
    assert [(p.loss_milli, p.paid_milli) for p in frame.payouts] == [(900, 0)]
    assert GL._state(control).counters["claims_unpaid_milli"] == 900


def test_departures_and_too_few_members_dissolve_and_return_the_fund_pro_rata():
    world = _world(cities=((0, 0), (1, 1), (2, 2)), wealth=50.0)
    _league(world, 3, (0, 1), (2, 0))
    assert _member_ids(world) == [[0, 1, 2]]
    _league(world, 4, (0, 1), (2, 0))
    world.cities.cities[2].lord = 0               # guild 2's city changes lord: it leaves
    frame = _turn(world, (0, 1))
    assert [(c.kind, c.guild, c.reason) for c in frame.changes] == [("left", 2, "lord_changed")]
    world.guilds.guilds[1].dissolved_turn = world.turn
    fund = GL._state(world).leagues[0].fund_milli
    purse = world.guilds.guilds[0].wealth
    frame = _turn(world, (0, 1))
    kinds = [(c.kind, c.reason) for c in frame.changes]
    assert kinds == [("left", "guild_dissolved"), ("dissolved", "too_few_members")]
    assert frame.changes[-1].returned_milli == fund and GL._state(world).leagues == []
    assert world.guilds.guilds[0].wealth == pytest.approx(purse + fund / 1000)
    assert GL._state(world).dissolved[0].dissolved_reason == "too_few_members"


def test_war_between_members_dissolves_and_ids_are_never_reused():
    world = _world(wealth=50.0)
    _league(world, 3, (0, 1))
    world.active_wars = [(world.civilizations[1].name, world.civilizations[0].name)]
    frame = _turn(world, (0, 1))
    assert [(c.kind, c.reason) for c in frame.changes] == [("dissolved", "war_between_members")]
    world.active_wars = []
    _league(world, 3, (0, 1))
    assert [x.league for x in GL._state(world).leagues] == [2] and GL._state(world).next_league == 3


def test_a_league_without_trade_goes_dormant_and_an_empty_one_is_unclaimed():
    world = _world(wealth=50.0)
    _league(world, 3, (0, 1))
    for _ in range(GL.DORMANT_TURNS - 1):
        assert _turn(world).changes == []
    frame = _turn(world)
    assert [(c.kind, c.reason) for c in frame.changes] == [("dissolved", "dormant")]
    lone = _world(wealth=50.0)
    _league(lone, 3, (0, 1))
    state = GL._state(lone)
    frame = GL.LeagueFrame(turn=lone.turn)
    for g in lone.guilds.guilds:
        g.dissolved_turn = lone.turn
    fund = state.leagues[0].fund_milli
    GL._dissolve(lone, state, state.leagues[0], "too_few_members", frame, {}, lone.turn)
    assert frame.changes[0].unclaimed_milli == fund and state.counters["unclaimed_milli"] == fund


def test_switching_off_dissolves_every_league_with_its_fund_returned():
    world = _world(wealth=50.0)
    _league(world, 3, (0, 1))
    fund = GL._state(world).leagues[0].fund_milli
    purses = sum(g.wealth for g in world.guilds.guilds)
    GL.set_guild_leagues_enabled(world, False)
    state = GL._state(world)
    assert state.leagues == [] and state.dissolved[0].dissolved_reason == "switched_off" and not state.enabled
    assert sum(g.wealth for g in world.guilds.guilds) == pytest.approx(purses + fund / 1000)


def test_pickle_json_record_states_and_double_commit():
    world = _world()
    _league(world)
    GL.note_city_sack(world, world.cities.cities[0], 1.0, "e")
    state = GL._state(world)
    assert pickle.loads(pickle.dumps(state))._turn is None
    assert GuildLeagueState.model_validate_json(state.model_dump_json()).leagues == state.leagues
    snap = {"livelihoods": {"schema_version": 1, "guild_leagues": GL.snapshot_summary(world)}}
    json.dumps(snap)
    assert GL.record_status(snap)[0] == "recorded"
    world.turn += 1
    assert GL.record_status({"livelihoods": {"guild_leagues": GL.snapshot_summary(world)}})[0] == "unobserved"
    assert GL.record_status({"livelihoods": {"guild_leagues": {"schema_version": 1}}})[0] == "malformed"
    assert GL.record_status({"livelihoods": {}})[0] == "absent"
    quiet = _world()
    _turn(quiet)
    assert GL.record_status({"livelihoods": {"guild_leagues": GL.snapshot_summary(quiet)}})[0] == "recorded_zero"
    world.turn = state.frame_turn                 # the turn already committed
    with pytest.raises(RuntimeError, match="twice"):
        GL.phase10(world, None, _econ(world), None)
    with pytest.raises(KeyError):
        GL._bump(state, "nope")
    assert set(state.counters) <= set(COUNTERS)


def test_notes_come_from_the_cities_seams_for_members_only():
    world = _world(wealth=50.0)
    _league(world, 3, (0, 1))
    guild = world.guilds.guilds[0]
    guild.levy_turn = world.turn - 2
    city = world.cities.cities[0]
    GL.note_city_dues(world, city, 3.0, 1.0, guild)
    GL.note_city_dues(world, world.cities.cities[2], 3.0, 1.0, world.guilds.guilds[2])   # not a member
    GL.note_city_sack(world, city, 4.5678, "ev")
    notes = GL._state(world)._turn.notes
    assert notes == {100: {"levy": 300, "sack": (4567, "ev")}}


def test_nested_malformed_record_is_rejected():
    record = {"schema_version": 1, "stage": "D1b", "mode": "mutual", "source_turn": 1,
              "frame": {"turn": 1, "leagues": [None], "dues": [], "payouts": [], "changes": [],
                        "links": 0, "candidates": 0}}
    assert GL.record_status({"livelihoods": {"guild_leagues": record}}) == ("malformed", None)
