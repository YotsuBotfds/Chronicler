"""Strict test-only projection of added, dormant experiment metadata.

Raw serialized artifacts gain fields. This projection checks their exact
defaults before removing only those fields; it does not normalize any existing
field, change order, round numbers, or change production serialization.
"""
import json
from pydantic_core import to_json

from chronicler.bundle_codec import decode_bundle

WORLD_DEFAULTS = {
    "fishery_experiment": {"enabled": False, "reserve_turns": 8.0, "recovery_rate": .04,
                           "harvest_fraction": .25, "reference_workers": 200},
    "mutual_aid_enabled": False,
    "mutual_aid_state": {},
    "mutual_aid_last_dispatch_turn": None,
    "mutual_aid_last_transfers": [],
    # M60 campaigns (default off): flag plus empty campaign state.
    "campaigns_enabled": False,
    "war_state": {"armies": [], "wars": [], "ended_wars": [], "occupations": [], "battles": [],
                  "treaties": [], "next_army_serial": 1, "raised_counts": {}, "last_raise_turn": {}},
}
REGION_DEFAULTS = {"fishery_stocks": [1., 1., 1.], "fishery_yield_ratios": [1., 1., 1.],
                   "fishery_catch_budgets": [None, None, None], "occupied_by": None}


def strip_dormant_fields(world, *, aid=True):
    for key, expected in WORLD_DEFAULTS.items():
        if not aid and key.startswith("mutual_aid"):
            continue
        if key in world:
            assert world.pop(key) == expected, (key, "experiment metadata changed")
    for region in world["regions"]:
        for key, expected in REGION_DEFAULTS.items():
            if key in region:
                assert region.pop(key) == expected, (region["name"], key, "experiment metadata changed")
    return world


# Causal provenance (docs/integration/causal-provenance.md) adds event and
# condition fields, the world's causal index and bundle version 4. Runs made
# with ``chronicler.provenance.LEGACY_TIMELINE`` keep the timeline itself
# exactly as a provenance-free run writes it, so removing only these
# additions recovers the pre-provenance bytes.
PROVENANCE_EVENT_FIELDS = ("event_id", "causes", "region", "civs", "episode", "duration")
PROVENANCE_CONDITION_FIELDS = ("condition_id", "cause_id", "onset_turn")


def strip_provenance_event(event: dict) -> dict:
    assert event.get("episode") != "end", "end events: run with provenance.LEGACY_TIMELINE"
    for key in PROVENANCE_EVENT_FIELDS:
        event.pop(key, None)
    return event


def legacy_event_dump(event) -> dict:
    """``event.model_dump(mode="json")`` without the provenance additions."""
    return strip_provenance_event(event.model_dump(mode="json"))


def strip_provenance(world: dict) -> dict:
    world.pop("provenance", None)
    for event in world.get("events_timeline", []):
        strip_provenance_event(event)
    for condition in world.get("active_conditions", []):
        for key in PROVENANCE_CONDITION_FIELDS:
            condition.pop(key, None)
    return world


def legacy_artifact_bytes(path, *, pre_pruning=False):
    """Artifact bytes without the dormant and provenance additions.

    Bundle version 4 (provenance) projects to version 3. A version-5 bundle
    (dead civs pruned from the history, docs/performance/dead-civ-pruning.md)
    keeps version 5 and its ``pruned_civ_stats``. With ``pre_pruning`` it
    projects to version 3 as well, which requires that no civ was pruned:
    then ``pruned_civ_stats`` is empty and the history is the version-4
    history byte for byte. A version-6 file (snapshot deltas,
    docs/performance/bundle-v6.md) is decoded and projects as version 5.
    """
    raw = path.read_bytes()
    if path.name not in ("state.json", "chronicle_bundle.json"):
        return raw
    data = json.loads(raw)
    if path.name == "chronicle_bundle.json" and data["metadata"]["bundle_version"] == 6:
        data = decode_bundle(data)
        data["metadata"]["bundle_version"] = 5
    strip_dormant_fields(data["world_state"] if path.name == "chronicle_bundle.json" else data)
    strip_provenance(data["world_state"] if path.name == "chronicle_bundle.json" else data)
    if path.name == "chronicle_bundle.json":
        for event in data.get("events_timeline", []):
            strip_provenance_event(event)
        for entry in data.get("chronicle_entries", []):
            assert "causal_chains" not in entry
            for event in entry.get("events", []):
                strip_provenance_event(event)
        version = data["metadata"]["bundle_version"]
        if version == 5 and pre_pruning:
            assert data.pop("pruned_civ_stats") == {}, "a civ was pruned from the history"
            version = 4
        if version == 4:
            data["metadata"]["bundle_version"] = 3
        else:
            assert version == 5, version
        return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    # Match WorldState.save's existing Pydantic formatting (including exponents).
    return to_json(data, indent=2)
