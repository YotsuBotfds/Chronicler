"""Read back actual saved X1/C2 records; verify dated prior-frame diagnostics."""
import hashlib
import json
import math
import sys
from pathlib import Path

from chronicler.bundle_codec import load_bundle

source, output = map(Path, sys.argv[1:])
bundle = load_bundle(source)
frames = {s["livelihoods"]["residence_ledger"]["source_turn"]:
          s["livelihoods"]["residence_ledger"]["frame"] for s in bundle["history"]}
checked = 0
lag_witnesses = 0
selected = []
for snapshot in bundle["history"]:
    health = snapshot["livelihoods"]["public_health"]
    current = snapshot["livelihoods"]["residence_ledger"]
    assert health["source_turn"] == current["source_turn"] == snapshot["turn"] - 1
    for environment in health["environment"]:
        clock = environment["source_turn"]
        assert clock == health["source_turn"] - 1
        assert environment["crowding_source_turn"] == health["source_turn"]
        assert environment["crowding_basis"] == "density_only"
        assert environment["crowding_factor"] == 1
        prior = frames.get(clock)
        complete = prior["arrival_diagnostics"]["complete"] if prior else None
        region = next((r for r in (prior or {}).get("regions", [])
                       if r["region"] == environment["region"]), None)
        share = (region["recent_residence_arrivals"] / max(1, region["residents"])
                 if complete and region else 0 if complete else None)
        assert environment["arrival_diagnostics_complete"] is complete
        actual = environment["recent_arrival_share"]
        assert actual is None if share is None else actual is not None and math.isclose(actual, share, abs_tol=1e-12)
        assert environment["residence_observed"] == (prior is not None)
        now = next((r for r in current["frame"]["regions"]
                    if r["region"] == environment["region"]), None)
        same_turn_share = (now["recent_residence_arrivals"] / max(1, now["residents"])
                           if current["frame"]["arrival_diagnostics"]["complete"] and now else None)
        differs = (share is None) != (same_turn_share is None) or (
            share is not None and same_turn_share is not None and not math.isclose(share, same_turn_share, abs_tol=1e-12))
        lag_witnesses += bool(differs)
        checked += 1
    if snapshot["turn"] in (1, 22, 23, 120):
        selected.append({"snapshot": snapshot["turn"], "x1_source_turn": current["source_turn"],
                         "x1_arrival_diagnostics": current["frame"]["arrival_diagnostics"],
                         "x1_arrivals": current["frame"]["totals"]["recent_residence_arrivals"],
                         "x1_unknown_arrivals": current["frame"]["totals"]["recent_residence_arrivals_unknown_reason"],
                         "environment": health["environment"]})
report = {"bundle": str(source), "bundle_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
          "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          "decoder_source": str(Path(sys.modules["chronicler.bundle_codec"].__file__)),
          "decoder_source_sha256": hashlib.sha256(Path(sys.modules["chronicler.bundle_codec"].__file__).read_bytes()).hexdigest(),
          "snapshots": len(bundle["history"]), "regional_observations_checked": checked,
          "observations_different_from_same_turn_share": lag_witnesses,
          "all_prior_frame_shares_match": True, "all_density_multipliers_neutral_and_current": True,
          "selected": selected,
          "note": "Independent saved-record readback. Arrival shares are diagnostics, not housing pressure or a causal health effect. Same-turn counterfactual values only test source clocks; no alternate world is simulated."}
output.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({k: report[k] for k in ("snapshots", "regional_observations_checked", "observations_different_from_same_turn_share")}))
