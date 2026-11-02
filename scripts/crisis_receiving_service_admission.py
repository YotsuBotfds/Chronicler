"""Manual pytest admission probe; this fixed development case currently fails.

Run explicitly with pytest and the matching native environment. Failure to meet
post-arrival service preconditions is a recorded result, not a CI passing test.
"""
import json
import random

import pytest

pytestmark = pytest.mark.native


def run_receiving_service_admission(tmp_path, monkeypatch, require_positive=True):
    pytest.importorskip("chronicler_agents")
    from chronicler import scholarship
    from chronicler.agent_bridge import AgentBridge
    from chronicler.cities import set_cities_enabled
    from chronicler.learning_services import set_learning_services_enabled
    from chronicler.run_checkpoint import RunState, read_checkpoint, write_checkpoint
    from chronicler.scholarship_state import ACADEMY, ScholarshipState, Seat
    from chronicler.techniques import set_techniques_enabled
    from chronicler.world_gen import generate_world
    from scripts.crisis_migration_example import _advance, _agents

    random.seed(42)
    world = generate_world(seed=42, num_regions=5, num_civs=2)
    world.agent_mode = "hybrid"
    set_cities_enabled(world, True)
    set_techniques_enabled(world, True)
    for i, r in enumerate(world.regions):
        r.stockpile.goods = {"grain": 100.0 if i == 0 else 0.0}
    receiver = world.regions[2]
    receiver.resource_base_yields = [0.25 * v for v in receiver.resource_base_yields]
    receiver.stockpile.goods["crafts"] = 8.0
    world.household_mobility_liquid_requirement = 1.0
    assert receiver.controller is not None, "admission: receiver has no controller"
    owner = world.civ_index_map[receiver.controller]
    world.civilizations[owner].treasury = 500
    world.scholarship = ScholarshipState(seats=[Seat(region=2, kind=ACADEMY,
        name="Constructed receiving academy", founded_turn=0, founder=owner, lord=owner)])
    set_learning_services_enabled(world, True)
    bridge = AgentBridge(world, mode="hybrid")
    owners = [bridge]
    traces = {"active": [], "paused": []}
    effects = []
    original_factors = scholarship.learning_factors
    def capture_factors(w):
        result = original_factors(w)
        if any(w is item for item in worlds.values()):
            label = next(k for k, v in worlds.items() if v is w)
            effects.append({"arm": label, "source": w.turn,
                "hazard": result[0].get(2), "seat_level": w.scholarship.seats[0].level})
        return result
    monkeypatch.setattr(scholarship, "learning_factors", capture_factors)
    def checkpoint(w, b, path):
        write_checkpoint(path, RunState(world=w, agent_bridge=b, memories={}, history=[],
            chronicle_entries=[], era_reflections={}, pending_injections=[], start_turn=0,
            seed=42, num_turns=8))
    def verify_checkpoint(w, sim, path):
        checkpoint(w, sim, path)
        left, right = read_checkpoint(path), read_checkpoint(path)
        assert left.exact and right.exact
        assert left.state.world.model_dump_json() == w.model_dump_json()
        assert left.state.agent_bridge._sim.checkpoint_state() == sim._sim.checkpoint_state()
        before_rng = random.getstate()
        try:
            one = _advance(left.state.world, left.state.agent_bridge)
            after_rng = random.getstate()
            random.setstate(before_rng)
            two = _advance(right.state.world, right.state.agent_bridge)
            assert random.getstate() == after_rng and one == two
            assert left.state.world.model_dump_json() == right.state.world.model_dump_json()
            assert left.state.agent_bridge._sim.checkpoint_state() == right.state.agent_bridge._sim.checkpoint_state()
        finally:
            random.setstate(before_rng)
            left.state.agent_bridge.close()
            right.state.agent_bridge.close()
    try:
        people = _agents(bridge)
        print("OPENING=" + json.dumps({"receiver": 2, "owner": owner,
             "scholars": [aid for aid, row in people.items() if row["region"] == 2 and row["occupation"] == 3],
             "receiver_count": sum(r["region"] == 2 for r in people.values())}))
        assert any(row["region"] == 2 and row["occupation"] == 3 and row["age"] >= 20 for row in people.values()), "admission: no adult native Scholar at receiving academy"
        checkpoint(world, bridge, tmp_path / "start.ckpt")
        a, b = read_checkpoint(tmp_path / "start.ckpt").state, read_checkpoint(tmp_path / "start.ckpt").state
        owners.extend([a.agent_bridge, b.agent_bridge])
        assert a.agent_bridge._sim.checkpoint_state() == b.agent_bridge._sim.checkpoint_state()
        set_learning_services_enabled(b.world, False)
        worlds = {"active": a.world, "paused": b.world}
        bridges = {"active": a.agent_bridge, "paused": b.agent_bridge}
        first_arrival, first_paid = None, None
        for _ in range(8):
            state = random.getstate()
            for label in ("active", "paused"):
                if label == "paused":
                    random.setstate(state)
                w, sim = worlds[label], bridges[label]
                pre = _agents(sim)
                observation = _advance(w, sim)
                post = _agents(sim)
                for event in observation["migration_events"]:
                    aid = event["agent_id"]
                    event["pre_occupation"] = pre.get(aid, {}).get("occupation")
                    event["post_occupation"] = post.get(aid, {}).get("occupation")
                services = w.scholarship.learning_services
                procurement = [r.model_dump(mode="json") for r in (services.procurement_receipts or [])]
                teaching = [r.model_dump(mode="json") for r in (services.teaching_receipts or [])]
                observation.update(pre_non_scholar=sum(r["region"] == 2 and r["occupation"] != 3 for r in pre.values()),
                    post_non_scholar=sum(r["region"] == 2 and r["occupation"] != 3 for r in post.values()),
                    procurement=procurement, teaching=teaching,
                    balance=services.material_balance,
                    seat=w.scholarship.seats[0].model_dump(mode="json"),
                    receiver_controller=w.regions[2].controller,
                    owner_treasury=w.civilizations[owner].treasury,
                    receiver_crafts=w.regions[2].stockpile.goods.get("crafts", 0.0))
                traces[label].append(observation)
                if label == "active":
                    after = random.getstate()
                    if first_arrival is None and any(e["region"] == 1 and e["target_region"] == 2 and e["pre_region"] == 1 and e["post_region"] == 2 for e in observation["migration_events"]):
                        first_arrival = observation["source_turn"]
                        verify_checkpoint(w, sim, tmp_path / "arrival.ckpt")
                    if first_paid is None and any(p["purchased"] > 0 and p["paid"] > 0 for p in procurement):
                        first_paid = observation["source_turn"]
                        verify_checkpoint(w, sim, tmp_path / "paid.ckpt")
                else:
                    assert random.getstate() == after
        print("CASE_TRACE=" + json.dumps({"arms": traces, "effects": effects}, default=str))
        assert first_arrival is not None, "admission: no actual 1→2 arrival"
        row = traces["active"][first_arrival]
        samples = {s["group_id"]: s for s in row["mobility"]["samples"]}
        matched = [e for e in row["migration_events"] if e["region"] == 1 and e["target_region"] == 2
                   and e["pre_region"] == 1 and e["post_region"] == 2 and e["agent_id"] in samples
                   and samples[e["agent_id"]]["local_food_sufficiency"] < 1
                   and e["driver_name"] in {"famine_memory", "material_need", "low_satisfaction", "opp_food"}]
        assert matched, "admission: no matched food-distress move"
        assert row["food"]["regions"][2]["native"]["sufficiency"] < 1, "admission: receiving food unconstrained"
        assert first_arrival < 7 and row["post_non_scholar"] > row["pre_non_scholar"], "admission: no increased receiver non-Scholar bound"
        assert traces["active"][first_arrival + 1]["pre_non_scholar"] == row["post_non_scholar"]
        native_food = row["food"]["regions"][2]["native"]
        assert abs(native_food["balance_residual"]) <= native_food["balance_tolerance"]
        assert row["procurement"][0]["learner_upper_bound"] == row["post_non_scholar"]
        assert traces["active"][first_arrival + 1]["teaching"][0]["learner_upper_bound"] == row["post_non_scholar"]
        assert first_paid is not None, "admission: no paid academy supplies"
        positive = [(r["source_turn"], t) for r in traces["active"] for t in r["teaching"]
                    if r["source_turn"] > first_arrival and (t["work_delivered"] or 0) > 0 and (t["crafts_used"] or 0) > 0
                    and t["learner_upper_bound"] > t["learners_delivered"]]
        if require_positive:
            assert positive, "admission: no post-arrival actual work with positive potential-capacity gap"
        else:
            # A negative case: zero requested with no native result means unknown
            # actual work, not a measured zero worker delivery.
            assert not positive
            for frame in traces["active"][first_arrival:]:
                receipt = frame["teaching"][0]
                purchase = frame["procurement"][0]
                assert frame["seat"]["fallen_turn"] is None
                assert frame["receiver_controller"] == worlds["active"].civilizations[owner].name
                assert receipt["held_before"] == 0 and receipt["work_requested"] == 0
                assert receipt["work_delivered"] is None and receipt["learners_delivered"] is None
                assert purchase["market_stock"] == 0 and purchase["purchased"] == 0 and purchase["paid"] == 0
                assert purchase["upkeep_satisfied"] is True
                assert abs(frame["balance"]["residual"]) <= frame["balance"]["absolute_tolerance"]
            assert traces["active"][3]["procurement"][0]["upkeep_amount_paid"] > 0
        for source, t in positive:
            later = [e for e in effects if e["arm"] == "active" and e["source"] == source + 1]
            if later:
                assert later[0]["hazard"] == pytest.approx(1 + scholarship.LEARN_HAZARD * later[0]["seat_level"] * t["learners_delivered"] / t["learner_upper_bound"])
        for stage in ("arrival", "paid"):
            loaded = read_checkpoint(tmp_path / f"{stage}.ckpt")
            assert loaded.exact
            # Checkpoint materializes complete same-boundary native/world state.
            loaded.state.agent_bridge.close()
    finally:
        for b in owners:
            b.close()


def test_distress_arrival_receiving_academy_capacity_and_exact_resume(tmp_path, monkeypatch):
    run_receiving_service_admission(tmp_path, monkeypatch, require_positive=True)
