"""CW6-D1 bounded held screen; see its preregistration, no qualification gate.

python scripts/cw_d1_screen.py run OUT --screen CW6D1 --cohort pilot --jobs 1
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import screen_runner as SR


def _rate(total, count):
    return total / count if count else None


def extract(bundle, flags):
    from chronicler.reform_services import record_status as relief_status
    from chronicler.guild_leagues import record_status as league_status
    relief_on, leagues_on = "--reform-services" in flags, "--guild-leagues" in flags
    names = [c["name"] for c in bundle["world_state"]["civilizations"]]
    regions = [r["name"] for r in bundle["world_state"]["regions"]]
    m = dict(relief_civ_turns=0, purchases=0, food_bought_milli=0, credited_milli=0,
             residual_milli=0, refunded_milli=0, paid_in_milli=0, sunk_units=0,
             delivered_lower=None, delivered_upper=0.0, lower_unknown=0,
             historical_lower_unverified=0.0,
             league_member_turns=0, league_turns=0, claims=0, dues_milli=0, payouts_milli=0,
             returned_milli=0, unclaimed_milli=0, foundings=0)
    problems, relief_short, relief_regions, commons, population, city_purses = [], 0, 0, 0, 0, 0
    for snap in bundle.get("history", []):
        turn = snap["turn"] - 1
        mov = snap.get("agent_movements") or {}
        relief_civs = {r["civ"] for r in mov.get("reforms", []) if r["kind"] == "poor relief"}
        # REFORM_NAMES uses relief; accept the descriptive historical spelling too.
        relief_civs |= {r["civ"] for r in mov.get("reforms", []) if r["kind"] == "relief"}
        m["relief_civ_turns"] += len(relief_civs)
        names_relief = {names[i] for i in relief_civs}
        for row in mov.get("living", []):
            if row["creed"] == "commons" and row["target"] in relief_civs:
                commons += row["members"]
        for name in names_relief:
            stats = snap.get("civ_stats", {}).get(name)
            if stats is None:
                problems.append(f"missing civ_stats {name} at {turn}")
            else:
                population += stats["population"]
        retail = (snap.get("livelihoods") or {}).get("household_retail") or {}
        for row in retail.get("regions") or []:
            if snap["region_control"].get(regions[row["region"]]) in names_relief:
                provisioning = row.get("provisioning")
                if provisioning is None:
                    problems.append(f"unobserved relief-region provisioning at {turn}")
                else:
                    relief_regions += 1
                    relief_short += provisioning["priced_out_persons"] + provisioning["offer_short_persons"]
        if relief_on:
            status, frame = relief_status(snap)
            if status not in ("recorded", "recorded_zero"):
                problems.append(f"relief {status} at {turn}")
                continue
            for c in frame["civs"]:
                if c["fund_open_milli"] + c["to_fund_milli"] - c["spent_milli"] - c["refunded_milli"] != c["fund_close_milli"]:
                    problems.append(f"fund does not close at {turn}")
                m["paid_in_milli"] += c["to_fund_milli"]
                m["refunded_milli"] += c["refunded_milli"]
                m["sunk_units"] += c["sunk_units"]
            for p in frame["purchases"]:
                if p["credited_milli"] + p["residual_milli"] != p["cost_milli"]:
                    problems.append(f"purchase does not close at {turn}")
                m["purchases"] += 1
                for key in ("food_bought_milli", "credited_milli", "residual_milli"):
                    m[key] += p["food_milli" if key == "food_bought_milli" else key]
            for d in frame["deliveries"]:
                # Historical records estimated a positive lower bound without
                # observing gross exports. Keep that raw diagnostic separate;
                # it is not established delivery and never a primary outcome.
                m["lower_unknown"] += 1
                if d["delivered_at_least"] is not None:
                    m["historical_lower_unverified"] += d["delivered_at_least"]
                if d["delivered_at_most"] is not None:
                    if not 0 <= d["delivered_at_most"] <= min(d["rations_bought"], d["free_given"]) + 1e-6:
                        problems.append(f"delivery exceeds bound at {turn}")
                    m["delivered_upper"] += d["delivered_at_most"]
        if leagues_on:
            status, frame = league_status(snap)
            if status not in ("recorded", "recorded_zero"):
                problems.append(f"leagues {status} at {turn}")
                continue
            cities = {c["id"]: c for c in (snap.get("cities") or {}).get("cities", [])}
            m["league_turns"] += any(row["members"] for row in frame["leagues"])
            for row in frame["leagues"]:
                if (row["fund_open_milli"] + row["dues_milli"] - row["payouts_milli"]
                        - row["returned_milli"] - row["unclaimed_milli"] != row["fund_close_milli"]):
                    problems.append(f"league does not close at {turn}")
                members = row["members"]
                if len({x["lord"] for x in members}) != len(members) or len(members) > 4:
                    problems.append(f"invalid membership at {turn}")
                for member in members:
                    city = cities.get(member["city"])
                    if city is None:
                        problems.append(f"member city absent at {turn}")
                    else:
                        city_purses += city["wealth"]
                        m["league_member_turns"] += 1
                for key in ("dues_milli", "payouts_milli", "returned_milli", "unclaimed_milli"):
                    m[key] += row[key]
            for p in frame["payouts"]:
                if not p["event_id"] or not 0 <= p["paid_milli"] <= min(2000, p["loss_milli"]):
                    problems.append(f"invalid claim at {turn}")
                m["claims"] += p["paid_milli"] > 0
            m["foundings"] += sum(x["kind"] == "founded" for x in frame["changes"])
    m.update(priced_out=_rate(relief_short, relief_regions),
             commons_members_per_1000_residents=_rate(1000 * commons, population),
             member_purse=_rate(city_purses, m["league_member_turns"]),
             relief_active=m["relief_civ_turns"] >= 10 and m["purchases"] > 0,
             league_active=m["league_turns"] >= 20 and m["claims"] > 0)
    return m, problems


def activation(bundle, flags):
    m, problems = extract(bundle, flags)
    if problems:
        return None, "; ".join(problems)
    if "--reform-services" in flags:
        return m["relief_active"], f'{m["relief_civ_turns"]} relief civ-turns; {m["purchases"]} purchases'
    return m["league_active"], f'{m["league_member_turns"]} member city-turns; {m["claims"]} paid claims'


def pair(key, active):
    def values(a, b):
        if not a["m"][active]:
            return "not activated"
        if a["m"][key] is None or b["m"][key] is None:
            return "no observed denominator in one arm"
        return a["m"][key], b["m"][key]
    return values


def read(key):
    return lambda row: row["m"][key]


outcomes = [
    SR.Outcome("cw6d1_priced_out", "Short person-turns per relief-region-turn (RS - RC)", "RS", "RC", read("priced_out"), True,
               pair=pair("priced_out", "relief_active")),
    SR.Outcome("cw6d1_commons_grievance", "Commons members per 1,000 relief-realm residents (RS - R0)", "RS", "R0",
               read("commons_members_per_1000_residents"), True, pair=pair("commons_members_per_1000_residents", "relief_active")),
    SR.Outcome("cw6d1_member_purse", "Mean civic purse while a league member (GM - GD)", "GM", "GD", read("member_purse"), True,
               pair=pair("member_purse", "league_active")),
]
for key in ("paid_in_milli", "food_bought_milli", "credited_milli", "refunded_milli", "delivered_upper", "lower_unknown"):
    outcomes.append(SR.Outcome(f"cw6d1_{key}", key, "RS", None, read(key)))
for key in ("foundings", "claims", "dues_milli", "payouts_milli", "returned_milli", "unclaimed_milli"):
    outcomes.append(SR.Outcome(f"cw6d1_{key}", key, "GM", None, read(key)))
SCREEN = SR.Screen(
    name="CW6D1", title="D1 relief services and guild leagues", module=Path(__file__).resolve(),
    preregistration=SR.REPO / "docs/superpowers/progress/connected-world-screens-cw6d1.md",
    base=("--turns", "200", "--agents", "hybrid", "--simulate-only", "--food-allocation", "--household-retail",
          "--household-retail-boundary", "all", "--grain-reserves"),
    arms={"R0": ((), None), "RC": (("--reform-services", "--reform-services-mode", "cost_only"), "R0"),
          "RS": (("--reform-services",), "RC"), "GD": (("--guild-leagues", "--guild-league-mode", "dues_only"), "R0"),
          "GM": (("--guild-leagues",), "GD")},
    root="R0", pilot={"template": (5,), "procedural": (19,)},
    held={"template": tuple(range(3701, 3707)), "procedural": tuple(range(3801, 3807))},
    packages=(SR.Package("--reform-services", ("livelihoods", "reform_services"), mode_flag="--reform-services-mode", default_mode="service"),
              SR.Package("--guild-leagues", ("livelihoods", "guild_leagues"), mode_flag="--guild-league-mode", default_mode="mutual")),
    outcomes=tuple(outcomes), activation=activation, extract=extract, ready=True)

if __name__ == "__main__":
    raise SystemExit(SR.main(None, {"CW6D1": SCREEN}, prog="cw_d1_screen.py"))
