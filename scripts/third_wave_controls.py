"""Strict test-only projection of added, dormant experiment metadata.

Raw serialized artifacts gain fields. This projection checks their exact
defaults before removing only those fields; it does not normalize any existing
field, change order, round numbers, or change production serialization.
"""
import json
from pydantic_core import to_json

WORLD_DEFAULTS = {
    "fishery_experiment": {"enabled": False, "reserve_turns": 8.0, "recovery_rate": .04,
                           "harvest_fraction": .25, "reference_workers": 200},
    "mutual_aid_enabled": False,
    "mutual_aid_state": {},
    "mutual_aid_last_dispatch_turn": None,
    "mutual_aid_last_transfers": [],
}
REGION_DEFAULTS = {"fishery_stocks": [1., 1., 1.], "fishery_yield_ratios": [1., 1., 1.],
                   "fishery_catch_budgets": [None, None, None]}


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


def legacy_artifact_bytes(path):
    raw = path.read_bytes()
    if path.name not in ("state.json", "chronicle_bundle.json"):
        return raw
    data = json.loads(raw)
    strip_dormant_fields(data["world_state"] if path.name == "chronicle_bundle.json" else data)
    if path.name == "chronicle_bundle.json":
        return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    # Match WorldState.save's existing Pydantic formatting (including exponents).
    return to_json(data, indent=2)
