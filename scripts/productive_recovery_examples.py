#!/usr/bin/env python3
"""Find natural success and failure examples of the productive-recovery checkpoint-1 packages,
and (``--chain``) natural instances of the checkpoint-3 chain and its tradeoffs.

    python scripts/productive_recovery_examples.py BUNDLE [BUNDLE ...]
    python scripts/productive_recovery_examples.py --chain BUNDLE [BUNDLE ...]

Scans each run's dated livelihoods records (``history[i]["livelihoods"][<package>]``;
never the final world state) and prints, per package, the first natural instance of
each example kind with its snapshot turn and the stable ids involved, or "none
found". The packages are PL1 timber supply, PL2 (RS1 rules version 2 and
``--operating-wear``), PL3 recovery crews and the maintenance obligation, and RS2's
``no_people`` correction. A snapshot is dated by its ``turn``; every record in it
observes the completed turn before (``source_turn``).

``--chain`` follows each RS2 project that stalled ``no_timber`` through a PL1 expedition
from its region, the repair that used the delivered timber, the named workers paid
``repair_wage`` and the region's later food purchases (PL4 retail), and says for each link
whether the records join it by stable id or only by region; it also prints the chain's
natural tradeoffs (farm labour away, the forest stock drawn down, a family priced out
after its crew member's wages ended).

A bundle carries no CLI flags, so the reproducing command is the one that wrote it
(docs/superpowers/progress/productive-recovery-examples.md lists them). Constructed
examples are the unit and native tests named in that document, not this script.

The record keys read here are the packages' own model fields and declared reasons
(``*_state.py``); :func:`check_fields` checks them against this checkout's source,
as ``productive_recovery_screens.check_extractor`` checks the counters it reads.
"""
from __future__ import annotations

import json
import re
import sys
from itertools import pairwise
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Workshop condition below which a site stops operating until repaired, when the
#: record does not state it (``workshops.OPERATE_CONDITION``).
OPERATE_CONDITION = 0.5
#: Tolerance for comparing recorded conditions.
EPS = 1e-9

# --- Record access ---------------------------------------------------------------


def _liv(snap: dict, name: str):
    rec = (snap.get("livelihoods") or {}).get(name)
    return rec if isinstance(rec, dict) else None


def _records(hist, name):
    for snap in hist:
        rec = _liv(snap, name)
        if rec is not None:
            yield snap.get("turn"), rec


def _rows(rec, key) -> list:
    return (rec or {}).get(key) or []


def _first(hist, name, key, pred):
    for turn, rec in _records(hist, name):
        for row in _rows(rec, key):
            if pred(row, rec):
                return turn, row
    return None


def _has(hist, name) -> bool:
    return any(True for _ in _records(hist, name))


def _pick(row: dict, *keys) -> dict:
    return {k: row.get(k) for k in keys}


# --- PL1 timber supply --------------------------------------------------------------

#: The refusals that mean "no forest to cut" (``timber_supply_state.REFUSALS``).
FOREST_REFUSALS = ("no_forest", "too_far", "forest_depleted")
_EXPEDITION = ("eid", "civ", "home", "forest", "hops", "launched_turn", "ended_turn", "launched_crew", "crew")


def _timber_supply(hist):
    delivered: dict[int, tuple[int, dict]] = {}   # eid -> (snapshot, expedition), first seen delivered
    by_region: dict[int, list[tuple[int, dict]]] = {}
    pending: dict[int, tuple[int, dict]] = {}     # home -> a delivery not yet held by RS2 or released
    held: dict[int, list[tuple[int, float]]] = {}  # region -> (source turn, store timber RS2 held)
    used = completed = None
    seen_projects: set[int] = set()
    for snap in hist:
        turn = snap.get("turn")
        ts, rp = _liv(snap, "timber_supply"), _liv(snap, "repair_projects")
        if ts is None:
            continue
        for e in _rows(ts, "closed"):
            if e.get("status") == "delivered" and (e.get("delivered") or 0) > 0 and e["eid"] not in delivered:
                delivered[e["eid"]] = (turn, e)
                by_region.setdefault(e["home"], []).append((turn, e))
                pending.setdefault(e["home"], (turn, e))
        store = ts.get("store") or {}
        for row in _rows(ts, "stores"):
            if (row.get("held") or 0) > 0:
                held.setdefault(row["region"], []).append((ts.get("source_turn"), row["held"]))
            hit = pending.get(row["region"])
            if used is None and hit is not None and hit[0] < turn and (row.get("held") or 0) > 0:
                e = hit[1]
                used = (turn, {**_pick(e, *_EXPEDITION, "cut", "delivered"), "delivered_snapshot": hit[0],
                               "store_held": row["held"],
                               "rs2_projects": [_pick(r, "pid", "kind", "asset", "timber_used", "credited")
                                                for r in _rows(rp, "receipts")
                                                if r.get("region") == row["region"] and (r.get("timber_used") or 0) > 0]})
        for region in list(pending):
            # A store emptied without a hold: the delivery was released to the stockpile.
            if pending[region][0] < turn and str(region) not in store:
                del pending[region]
        for p in _rows(rp, "closed"):
            if completed is not None or p["pid"] in seen_projects:
                continue
            seen_projects.add(p["pid"])
            if p.get("kind") != "granary" or p.get("status") != "completed":
                continue
            before = [(t, e) for t, e in by_region.get(p["region"], [])
                      if p["opened_turn"] <= e["ended_turn"] < p["closed_turn"]]
            if before:
                completed =(turn, {**_pick(p, "pid", "asset", "region", "cause", "opened_turn", "closed_turn",
                                            "opened_condition", "scope", "delivered", "timber_used"),
                                    "deliveries": [_pick(x, "eid", "ended_turn", "delivered") for _t, x in before],
                                    "store_held_while_open": sum(a for s, a in held.get(p["region"], [])
                                                                 if p["opened_turn"] <= s <= p["closed_turn"])})
    out = {
        "success: an expedition delivers timber that RS2 then holds from the store": used,
        "success: a granary project completes after a delivery to its region": completed,
    }
    for reason in FOREST_REFUSALS:
        out[f"failure: a need refused for want of forest ({reason})"] = _first(
            hist, "timber_supply", "needs", lambda n, _r, reason=reason: n.get("status") == "refused"
            and n.get("reason") == reason)

    lost = None
    for turn, rec in _records(hist, "timber_supply"):
        for e in _rows(rec, "closed"):
            if e.get("status") == "abandoned" and e.get("end_reason") == "crew_lost" and (e.get("abandoned") or 0) > 0:
                deposits = [d for d in _rows(rec, "deposits") if len(d) == 4 and d[1] == e["eid"]]
                lost = (turn, {**_pick(e, *_EXPEDITION, "stage", "cut", "abandoned", "drops"),
                               "deposits": deposits})
                break
        if lost is not None:
            break
    out["failure: a crew lost and its cargo abandoned to the forest commons"] = lost

    recall = _first(hist, "timber_supply", "receipts", lambda r, _r: bool(r.get("recalled")))
    if recall is not None:
        turn, r = recall
        ended = next(((t, e) for t, rec in _records(hist, "timber_supply") if t >= turn
                      for e in _rows(rec, "closed") if e["eid"] == r["eid"]), None)
        recall = (turn, {**_pick(r, "eid", "civ", "home", "forest", "stage", "crew", "cut_end", "unpaid",
                                 "cargo_after", "wages_due_milli"),
                         "ended": None if ended is None else {"snapshot": ended[0],
                                                              **_pick(ended[1], "status", "delivered",
                                                                      "unpaid_turns", "recalled_turn")}})
    out["failure: a crew recalled for want of coins"] = recall
    return out


# --- PL2 RS1 rules version 2 -------------------------------------------------------------

_ARCHIVE = ("agent_id", "first_site", "site", "region", "started_turn", "ended_turn", "ended_reason", "attended",
            "transfers", "on_crew", "attached", "absent", "interruptions", "mentors", "granted")


def _apprenticeship(hist):
    def v2(rec):
        return rec.get("rules_version") == 2

    def archived(reason, extra=lambda a: True):
        return _first(hist, "apprenticeship", "archive", lambda a, r: v2(r) and a.get("ended_reason") == reason
                      and extra(a))

    graduate = _first(hist, "apprenticeship", "receipts", lambda s, r: v2(r) and s.get("operating")
                      and s.get("graduates_on_crew") and (s.get("offset_by_graduates") or 0) > 0)
    no_mentor = None
    for turn, rec in _records(hist, "apprenticeship"):
        if not v2(rec):
            continue
        for s in _rows(rec, "receipts"):
            seats = [x for x in _rows(s, "seats") if x.get("outcome") == "missed" and x.get("reason") == "no_mentor"]
            if seats and s.get("operating") and not s.get("qualified_on_crew"):
                no_mentor = (turn, {**_pick(s, "site", "region", "operating", "crew", "qualified_on_crew",
                                            "qualified_in_region"),
                                    "missed": [_pick(x, "agent_id", "reason") for x in seats]})
                break
        if no_mentor is not None:
            break
    site_region: dict[int, int] = {}       # workshop site -> region, from the dated records
    for _turn, rec in _records(hist, "apprenticeship"):
        for row in [*_rows(rec, "sites"), *_rows(rec, "receipts")]:
            site_region.setdefault(row["site"], row["region"])

    def pick(hit):
        if hit is None:
            return None
        return hit[0], {**_pick(hit[1], *_ARCHIVE), "first_region": site_region.get(hit[1].get("first_site"))}

    ungranted = pick(archived("completed", lambda a: a.get("granted") is False))
    if ungranted is None and all(rec.get("mode") == "train" for _t, rec in _records(hist, "apprenticeship")):
        ungranted = "not applicable (train mode grants every completion)"
    if not any(v2(rec) for _t, rec in _records(hist, "apprenticeship")):
        note = "not applicable (the run's RS1 records are rules version 1)"
        graduate = no_mentor = ungranted = note
        pick = (lambda _hit: note)
    return {
        "success: a graduate on an operating crew gives upkeep offset": graduate if not isinstance(graduate, tuple)
        else (graduate[0], _pick(graduate[1], "site", "region", "crew", "graduates_on_crew", "qualified_on_crew",
                               "offset_by_graduates", "offset_by_via", "upkeep_offset", "wear",
                               "condition_before", "condition_after")),
        "success: an apprentice who transferred regions completed":
            pick(archived("completed", lambda a: (a.get("transfers") or 0) > 0)),
        "failure: an apprenticeship ends long_absence": pick(archived("long_absence")),
        "failure: an apprenticeship ends stalled": pick(archived("stalled")),
        "failure: an apprentice misses teaching with no mentor aboard (no_mentor)": no_mentor,
        "control: a completion that grants no qualification (no_qualification)": ungranted,
    }


# --- PL2 operating wear ----------------------------------------------------------------------


def _operating_wear(hist):
    floor = OPERATE_CONDITION
    window: dict[int, list[dict]] = {}    # site -> wear receipts since its last repair
    worn: dict[int, list[dict]] = {}      # site -> every wear receipt, for RS2 projects
    done: dict[int, list[int]] = {}       # workshop site -> turns its RS2 projects completed
    lump = rebuilt = None
    rs2 = False
    seen: set[int] = set()

    def decline(rows):
        return {"worn_turns": len(rows), "first_turn": rows[0]["turn"], "last_turn": rows[-1]["turn"],
                "condition_before": rows[0]["condition_before"], "condition_after": rows[-1]["condition_after"],
                "wear": round(sum(r["wear"] for r in rows), 6),
                "upkeep_offset": round(sum(r.get("upkeep_offset") or 0 for r in rows), 6)}

    def by_operation(rows, below):
        """From full condition (built or repaired), operating turns with no qualified
        member and no upkeep offset, nothing else wearing the site between them, and
        the last one leaving it below ``below``."""
        return (bool(rows) and rows[0]["condition_before"] >= 1.0 - EPS and rows[-1]["condition_after"] < below
                and all(not (r.get("upkeep_offset") or 0) and not r.get("qualified_on_crew") for r in rows)
                and all(abs(a["condition_after"] - b["condition_before"]) < EPS for a, b in pairwise(rows)))

    for snap in hist:
        turn = snap.get("turn")
        ow, ws, rp = _liv(snap, "operating_wear"), _liv(snap, "workshops"), _liv(snap, "repair_projects")
        if ow is None:
            continue
        rs2 = rs2 or rp is not None
        floor = ((ws or {}).get("parameters") or {}).get("operate_condition", floor)
        for r in _rows(ws, "receipts"):
            if not (r.get("paid") or {}).get("repair"):
                continue
            rows = window.pop(r["site"], [])
            if lump is None and by_operation(rows, floor):
                lump = (turn, {"site": r["site"], "region": r["region"], "payer": r.get("payer"),
                               "repair_paid": r["paid"]["repair"], "condition_after_repair": r.get("condition_after"),
                               **decline(rows)})
        for p in _rows(rp, "closed"):
            if rebuilt is not None or p["pid"] in seen:
                continue
            seen.add(p["pid"])
            if p.get("kind") != "workshop" or p.get("status") != "completed":
                continue
            last = max((t for t in done.get(p["asset"], []) if t < p["opened_turn"]), default=None)
            done.setdefault(p["asset"], []).append(p["closed_turn"])
            if p.get("cause") != "wear":
                continue
            rows = [w for w in worn.get(p["asset"], [])
                    if w["turn"] <= p["opened_turn"] and (last is None or w["turn"] > last)]
            if by_operation(rows, p["opened_condition"] + EPS):
                rebuilt = (turn, {**_pick(p, "pid", "asset", "region", "opened_turn", "opened_condition", "closed_turn",
                                          "delivered", "timber_used", "last_crew"), **decline(rows)})
        for w in _rows(ow, "receipts"):
            window.setdefault(w["site"], []).append(w)
            worn.setdefault(w["site"], []).append(w)
    if lump is None and rs2:
        lump = "none found (RS2 owns workshop repair in this run, so no L1 lump repair is billed)"
    if rebuilt is None and not rs2:
        rebuilt = "not applicable (no repair_projects record)"
    return {
        "failure: a site worn below the operating floor for want of qualified upkeep, then an L1 lump repair": lump,
        "failure: a site worn to an RS2 project for want of qualified upkeep, then rebuilt by it": rebuilt,
    }


# --- PL3 recovery crews, the maintenance obligation and RS2's no_people correction -------------


def _recovery_crews(hist):
    paid = _first(hist, "recovery_crews", "receipts", lambda r, _r: r.get("kind") == "granary"
                  and (r.get("wages_milli") or 0) > 0 and r.get("members"))
    veteran = _first(hist, "recovery_crews", "receipts", lambda r, _r: any(m.get("veteran") for m in _rows(r, "members")))
    short = None
    for snap in hist:
        rc = _liv(snap, "recovery_crews")
        for r in _rows(rc, "receipts"):
            if r.get("kind") == "granary" and r.get("short"):
                rs2 = [x for x in _rows(_liv(snap, "repair_projects"), "receipts") if x.get("pid") == r["pid"]]
                short = (snap.get("turn"), {**_pick(r, "pid", "region", "payer", "eligible", "planned", "capacity",
                                                    "requested", "delivered"),
                                            "members": [m["agent_id"] for m in _rows(r, "members")],
                                            "rs2": [_pick(x, "status", "reasons") for x in rs2]})
                break
        if short is not None:
            break

    def members(hit, keys):
        if hit is None:
            return None
        turn, r = hit
        return turn, {**_pick(r, "pid", "kind", "region", "payer", "delivered", "wages_milli", "sunk_milli"),
                      "members": [_pick(m, *keys) for m in _rows(r, "members")]}

    return {
        "success: wages paid to a named granary crew": members(paid, ("agent_id", "origin", "worked", "wage_milli")),
        "success: a veteran placed on a repair crew": members(veteran, ("agent_id", "origin", "veteran")),
        "failure: a granary crew short of farmers (short / no_labor)": short,
    }


def _maintenance_obligation(hist):
    return {
        "success: an obligation reservation used":
            _first(hist, "maintenance_obligation", "uses", lambda u, _r: (u.get("used") or 0) > 0),
        "failure: a reservation returned unspent":
            _first(hist, "maintenance_obligation", "uses", lambda u, _r: (u.get("returned") or 0) > 0),
    }


def _no_people(hist):
    suspended: dict[int, int] = {}   # pid -> first dated suspension
    resumed = None
    for turn, rec in _records(hist, "repair_projects"):
        for p in [*_rows(rec, "projects"), *_rows(rec, "closed")]:
            for t, event, *_rest in p.get("history") or []:
                if event == "suspended_no_people":
                    suspended.setdefault(p["pid"], t)
                elif event == "resumed" and resumed is None and p["pid"] in suspended and t > suspended[p["pid"]]:
                    resumed = (turn, {**_pick(p, "pid", "kind", "asset", "region", "opened_turn", "status"),
                                      "suspended_turn": suspended[p["pid"]], "resumed_turn": t})
        if resumed is not None:
            break
    return {
        "failure: a granary project suspended no_people and later resumed": resumed,
        "failure: a worn granary with no project for want of people (unmet no_people)":
            _first(hist, "repair_projects", "unmet", lambda u, _r: u.get("reason") == "no_people"),
    }


#: Group -> (the packages whose records it needs, finder).
FINDERS = {
    "PL1 timber_supply": (("timber_supply",), _timber_supply),
    "PL2 apprenticeship (rules version 2)": (("apprenticeship",), _apprenticeship),
    "PL2 operating_wear": (("operating_wear",), _operating_wear),
    "PL3 recovery_crews": (("recovery_crews",), _recovery_crews),
    "PL3 maintenance_obligation": (("maintenance_obligation",), _maintenance_obligation),
    "RS2 no_people correction (repair_projects)": (("repair_projects",), _no_people),
}

#: Record fields and declared values this script reads: (module, model) -> fields.
FIELDS_READ = {
    ("timber_supply_state", "Expedition"): {*_EXPEDITION, "status", "stage", "cut", "delivered", "abandoned", "drops",
                                            "end_reason", "unpaid_turns", "recalled_turn"},
    ("timber_supply_state", "ExpeditionReceipt"): {"eid", "civ", "home", "forest", "stage", "crew", "cut_end",
                                                   "unpaid", "recalled", "cargo_after", "wages_due_milli"},
    ("timber_supply_state", "StoreRow"): {"region", "held"},
    ("timber_supply_state", "NeedRow"): {"status", "reason"},
    ("repair_projects_state", "RepairProject"): {"pid", "kind", "asset", "region", "cause", "opened_turn",
                                                 "closed_turn", "opened_condition", "scope", "delivered",
                                                 "timber_used", "status", "history", "last_crew"},
    ("repair_projects_state", "RepairReceipt"): {"pid", "kind", "asset", "region", "status", "reasons",
                                                 "timber_used", "credited"},
    ("repair_projects_state", "UnmetNeed"): {"reason"},
    ("apprenticeship_state", "Apprenticeship"): set(_ARCHIVE),
    ("apprenticeship_state", "SiteReceipt"): {"site", "region", "operating", "crew", "qualified_on_crew",
                                              "qualified_in_region", "graduates_on_crew", "offset_by_graduates",
                                              "offset_by_via", "upkeep_offset", "wear", "condition_before",
                                              "condition_after", "seats"},
    ("apprenticeship_state", "Seat"): {"agent_id", "aboard", "reason", "outcome"},
    ("operating_wear_state", "WearReceipt"): {"turn", "site", "wear", "upkeep_offset", "condition_after",
                                              "qualified_on_crew"},
    ("workshops_state", "WorkshopReceipt"): {"site", "region", "payer", "paid", "condition_after"},
    ("recovery_crews_state", "CrewReceipt"): {"pid", "kind", "region", "payer", "eligible", "planned", "capacity",
                                              "requested", "delivered", "short", "members", "wages_milli",
                                              "sunk_milli"},
    ("recovery_crews_state", "CrewMember"): {"agent_id", "origin", "worked", "wage_milli", "veteran"},
    ("maintenance_obligation_state", "ReservationUse"): {"used", "returned"},
}
#: Declared values this script matches: (module, tuple name) -> values.
VALUES_READ = {
    ("timber_supply_state", "REFUSALS"): set(FOREST_REFUSALS),
    ("timber_supply_state", "STATUSES"): {"delivered", "abandoned"},
    ("timber_supply_state", "END_REASONS"): {"crew_lost"},
    ("repair_projects_state", "PROJECT_STATUSES"): {"completed"},
    ("repair_projects_state", "CAUSES"): {"wear"},
    ("repair_projects_state", "REASONS"): {"no_people"},
    ("repair_projects_state", "UNMET_REASONS"): {"no_people"},
    ("apprenticeship_state", "END_REASONS"): {"completed", "long_absence", "stalled"},
    ("apprenticeship_state", "MISS_REASONS"): {"no_mentor"},
}
#: Dated RS2 project history events (``repair_projects._note``) this script matches.
HISTORY_EVENTS = ("suspended_no_people", "resumed")


# --- Checkpoint 3: the chain, traced by stable id (PL6d, ``--chain``) -------------------
#
# The phase's story: a community needs timber (an RS2 project stalls ``no_timber``), sends
# a named, paid crew to cut it (PL1), repairs the asset (RS2), pays named workers (PL3
# granary crews, RS2 workshop crews, the PL1 crew) and those households buy food (PL4
# retail, here at the ``paid_work`` boundary). Each link says whether the records join it
# to the previous one by stable id or only by region.

#: Retail person-sample statuses, native codes (``household_retail_state.SAMPLE_STATUSES``
#: plus the native withheld-dead status 3).
SAMPLE_STATUS_NAMES = ("fed", "priced_out", "offer_short", "withheld_dead")
PRICED_OUT = 1
#: The sample's columns when a record does not state them (``household_retail.snapshot_summary``).
SAMPLE_COLUMNS = ("agent_id", "region", "household", "ration", "fair_share", "status")
#: Native retail provisioning columns read (``RETAIL_REGION_COLUMNS`` in provisioning.rs).
PROVISIONING_READ = ("persons", "priced_out_persons", "sold_milli", "paid_milli")
#: The most sample hits and samples listed per instance.
MAX_HITS = 3


def _chain_index(hist) -> dict:
    """One pass over the dated records, keyed by snapshot turn ``T`` (each record
    observes the completed turn ``T - 1``)."""
    ix = {k: {} for k in ("stall", "rs2", "rs2_at", "closed", "open_at", "delivered", "launch", "ts_rx", "stores",
                          "crews", "frames", "sample", "opened", "food", "l3")}
    ix["ts_list"], ix["crew_list"], ix["rs2_list"] = [], [], []
    for snap in hist:
        T = snap.get("turn")
        rp, ts = _liv(snap, "repair_projects"), _liv(snap, "timber_supply")
        rc, hr = _liv(snap, "recovery_crews"), _liv(snap, "household_retail")
        for r in _rows(rp, "receipts"):
            ix["rs2"].setdefault(r["pid"], []).append((T, r))
            ix["rs2_at"].setdefault((T, r["region"]), []).append(r)
            ix["rs2_list"].append((T, r))
            if r.get("status") == "stalled" and "no_timber" in (r.get("reasons") or []):
                ix["stall"].setdefault(r["pid"], (T, r))
        for p in _rows(rp, "projects"):
            ix["open_at"].setdefault(T, {}).setdefault(p["region"], []).append(p["pid"])
        for p in _rows(rp, "closed"):
            ix["closed"].setdefault(p["pid"], (T, p))
        for e in _rows(ts, "closed"):
            if e.get("status") == "delivered" and (e.get("delivered") or 0) > 0:
                ix["delivered"].setdefault(e["eid"], (T, e))
        for n in _rows(ts, "needs"):
            if n.get("status") == "launched" and n.get("eid") is not None:
                ix["launch"].setdefault(n["eid"], (T, n))
        for r in _rows(ts, "receipts"):
            ix["ts_rx"].setdefault(r["eid"], []).append((T, r))
            ix["ts_list"].append((T, r))
        for row in _rows(ts, "stores"):
            ix["stores"][(T, row["region"])] = row
        for r in _rows(rc, "receipts"):
            ix["crews"].setdefault(r["pid"], []).append((T, r))
            ix["crew_list"].append((T, r))
        for f in _rows(hr, "regions"):
            ix["frames"][(T, f["region"])] = f
        if hr is not None and isinstance(hr.get("sample"), list):
            cols = hr.get("sample_columns") or SAMPLE_COLUMNS
            ix["sample"][T] = [dict(zip(cols, row)) for row in hr["sample"]]
        for rec in _rows(hr, "log"):
            if rec.get("kind") == "pilot_opened":
                ix["opened"].setdefault(rec["region"], rec)
        for row in (snap.get("food_accounting") or {}).get("regions") or []:
            ix["food"][(T, row.get("region_id"))] = row
        for row in _rows(_liv(snap, "timber_stock"), "regions"):
            ix["l3"][(T, row.get("region_id"), row.get("slot"))] = row
    return ix


def _l3(ix, T, r) -> dict | None:
    """The forest slot's L3 ledger row of snapshot ``T`` (what moved its stock)."""
    row = ix["l3"].get((T, r.get("forest"), r.get("slot")))
    return None if row is None else _pick(row, "opening", "cleared", "extraction", "regrowth", "stock", "capacity")


def _wage_snapshots(ix) -> dict[int, dict[int, list]]:
    """Stable id -> {snapshot: [repair_wage milli, [sources], [regions]]} for every named
    repair worker paid: PL3 crew members (``pl3_granary`` / ``pl3_workshop``, by member,
    in the project's region), RS2 workshop crews (``rs2_workshop``, the receipt's wages
    split evenly) and PL1 woodcutting crews (``pl1_woodcut``, likewise, in the home
    region; one rate per person-turn)."""
    paid: dict[int, dict[int, list]] = {}

    def add(aid, T, milli, source, region):
        if milli > 0:
            cell = paid.setdefault(aid, {}).setdefault(T, [0, [], []])
            cell[0] += milli
            cell[1].append(source)
            cell[2].append(region)

    pl3 = set()
    for T, r in ix["crew_list"]:
        for m in _rows(r, "members"):
            add(m["agent_id"], T, m.get("wage_milli") or 0, f"pl3_{r.get('kind')}", r.get("region"))
            pl3.add((T, r["pid"]))
    for T, r in ix["rs2_list"]:
        # PL3 lists the RS2 workshop crews it widened; count each wage once.
        if (T, r["pid"]) not in pl3 and r.get("crew") and (r.get("wages_milli") or 0) > 0:
            each, rest = divmod(r["wages_milli"], len(r["crew"]))
            for i, aid in enumerate(r["crew"]):
                add(aid, T, each + (1 if i < rest else 0), "rs2_workshop", r.get("region"))
    for T, r in ix["ts_list"]:
        if r.get("crew") and (r.get("wages_milli") or 0) > 0:
            each, rest = divmod(r["wages_milli"], len(r["crew"]))
            for i, aid in enumerate(r["crew"]):
                add(aid, T, each + (1 if i < rest else 0), "pl1_woodcut", r.get("home"))
    return paid


def _sample_hits(ix, people: dict[int, int], region=None) -> list[dict]:
    """Retail sample rows after each person's first wage (``people``: id -> snapshot of
    the first wage): the person themself, or a member of the household keyed by their
    id (a household's key is the smaller id of a co-resident couple, and a child takes
    a parent's key)."""
    hits = []
    for T in sorted(ix["sample"]):
        for row in ix["sample"][T]:
            for who, aid in (("self", row.get("agent_id")), ("household", row.get("household"))):
                if who == "household" and aid == row.get("agent_id"):
                    continue
                if aid in people and T > people[aid] and (region is None or row.get("region") == region):
                    status = row.get("status")
                    hits.append({"snapshot": T, "crew_member": aid, "who": who, "agent_id": row.get("agent_id"),
                                 "household": row.get("household"), "region": row.get("region"),
                                 "ration": row.get("ration"), "fair_share": row.get("fair_share"),
                                 "status": SAMPLE_STATUS_NAMES[status] if isinstance(status, int)
                                 and 0 <= status < len(SAMPLE_STATUS_NAMES) else status})
    return hits


def _trace(ix, pid: int) -> dict:
    """The chain from one project's first ``no_timber`` stall, link by link, until a
    link is not found (its reason stated)."""
    s1, r1 = ix["stall"][pid]
    R, t_stall = r1["region"], r1["turn"]
    closed = ix["closed"].get(pid)
    closed_turn = closed[1].get("closed_turn") if closed else None
    links = [{"link": 1, "what": "RS2 project stalled no_timber", "snapshot": s1, "by": "id (pid)",
              **_pick(r1, "pid", "kind", "asset", "region", "reasons", "condition_before"),
              "stalled_no_timber_snapshots": sum(1 for _T, r in ix["rs2"][pid]
                                                 if r.get("status") == "stalled"
                                                 and "no_timber" in (r.get("reasons") or []))}]
    out = {"pid": pid, "region": R, "links": links, "depth": 1, "id_to_food": False}
    # 2. A woodcutting expedition from the region, launched after the stall, delivered
    #    while the project was still open.
    exps = sorted((e["launched_turn"], eid) for eid, (_T, e) in ix["delivered"].items()
                  if e["home"] == R and e["launched_turn"] >= t_stall
                  and (closed_turn is None or e["ended_turn"] < closed_turn))
    if not exps:
        out["missing"] = "no expedition from the region delivered timber after the stall while the project was open"
        return out
    eid = exps[0][1]
    T_d, e = ix["delivered"][eid]
    launched = ix["launch"].get(eid)
    at_launch = ix["open_at"].get(e["launched_turn"] + 1, {}).get(R, [])
    links.append({"link": 2, "what": "PL1 expedition from that region launched, cut and delivered", "snapshot": T_d,
                  "by": "id (eid, crew); region for the project (PL1's need is per region)",
                  **_pick(e, "eid", "civ", "home", "forest", "hops", "launched_turn", "ended_turn", "launched_crew",
                          "crew", "cut", "delivered", "wages_milli", "away_delivered"),
                  "need_at_launch": None if launched is None else _pick(launched[1], "want", "free", "gap", "status"),
                  "open_projects_in_region_at_launch": at_launch,
                  "project_was_the_region_s_only_open_project": at_launch == [pid]})
    out["depth"] = 2
    # 3. The asset's repair used the delivered timber: the region's store held for RS2
    #    after the delivery, and the project's receipt used timber that turn.
    uses, others, released = [], set(), 0.0
    T = e["ended_turn"] + 2
    while True:
        row = ix["stores"].get((T, R))
        if row is None or (row.get("delivered") or 0) > 0 and uses:
            break
        released += row.get("released") or 0.0
        mine = [r for r in ix["rs2_at"].get((T, R), []) if r["pid"] == pid]
        holders = [r["pid"] for r in ix["rs2_at"].get((T, R), []) if (r.get("timber_held") or 0) > 0]
        if (row.get("held") or 0) > 0 and mine and (mine[0].get("timber_used") or 0) > 0:
            others.update(p for p in holders if p != pid)
            uses.append((T, row, mine[0]))
        if (row.get("closing") or 0) <= 0:
            break
        T += 1
    if not uses:
        out["missing"] = "the delivered timber was not used by this project (released, or held by another project)"
        return out
    completed = closed is not None and closed[1].get("status") == "completed"
    links.append({"link": 3, "what": "the asset's repair used the delivered timber", "snapshot": uses[0][0],
                  "by": "id (pid; the project was the only one in the region holding timber)" if not others
                  else "region (the store is per region; other projects held timber too)",
                  "snapshots": [u[0] for u in uses], "store_held": round(sum(u[1]["held"] for u in uses), 6),
                  "project_timber_used": round(sum(u[2]["timber_used"] for u in uses), 6),
                  "condition": [uses[0][2].get("condition_before"), uses[-1][2].get("condition_after")],
                  "other_projects_holding_timber": sorted(others),
                  "store_released_to_the_stockpile": round(released, 6),
                  "completed_snapshot": closed[0] if completed else None})
    out["depth"] = 3
    # 4. Named workers paid repair_wage: the project's crew in those turns, and the
    #    expedition's own crew.
    repair_turns = {u[0] for u in uses}
    crew = {}
    for T, r in ix["crews"].get(pid, []):
        if T in repair_turns:
            for m in _rows(r, "members"):
                if (m.get("wage_milli") or 0) > 0:
                    crew.setdefault(m["agent_id"], {"first_snapshot": T, "wage_milli": 0, "origin": m.get("origin")})
                    crew[m["agent_id"]]["wage_milli"] += m["wage_milli"]
    if not crew and r1["kind"] == "workshop":
        for T, r in ix["rs2"].get(pid, []):
            if T in repair_turns and r.get("crew") and (r.get("wages_milli") or 0) > 0:
                for aid in r["crew"]:
                    crew.setdefault(aid, {"first_snapshot": T, "wage_milli": 0, "origin": "rs2_workshop_crew"})
                    crew[aid]["wage_milli"] += r["wages_milli"] // len(r["crew"])
    woodcutters = {}
    for T, r in ix["ts_rx"].get(eid, []):
        if r.get("crew") and (r.get("wages_milli") or 0) > 0:
            for aid in r["crew"]:
                woodcutters.setdefault(aid, {"first_snapshot": T, "paid_turns": 0, "wage_milli": 0})
                woodcutters[aid]["paid_turns"] += 1
                woodcutters[aid]["wage_milli"] += r["wages_milli"] // len(r["crew"])
    if not crew and not woodcutters:
        out["missing"] = "no named worker was paid for this repair or expedition"
        return out
    # The repair crew's wages follow the delivery; the expedition's were paid on the way.
    paid_from = min(v["first_snapshot"] for v in (crew or woodcutters).values())
    links.append({"link": 4, "what": "named workers paid repair_wage", "by": "id (stable ids, per receipt)",
                  "snapshot": paid_from, "repair_crew": crew, "expedition_crew": woodcutters,
                  "expedition_crew_first_paid_snapshot": min((v["first_snapshot"] for v in woodcutters.values()),
                                                             default=None)})
    out["depth"] = 4
    # 5. Those households, or the region's pilot households, bought food later.
    people = {}
    for aid, v in (*woodcutters.items(), *crew.items()):
        people[aid] = min(people.get(aid, v["first_snapshot"]), v["first_snapshot"])
    bought = [(T, f) for (T, rid), f in sorted(ix["frames"].items())
              if rid == R and T > paid_from and ((f.get("provisioning") or {}).get("paid_milli") or 0) > 0]
    hits = sorted(_sample_hits(ix, people), key=lambda h: (h["region"] != R, h["who"] != "self", h["snapshot"]))
    here = [h for h in hits if h["region"] == R]
    # The repair crew in the chain's region after their repair wage (the strict reading
    # of "those households"; the expedition crew's wages came earlier).
    repairers = [h for h in _sample_hits(ix, {aid: v["first_snapshot"] for aid, v in crew.items()}, R)]
    opened = ix["opened"].get(R)
    if not bought and not hits:
        out["missing"] = "the region's households bought no food after the wages, and no crew member is in the sample"
        return out
    first = bought[0] if bought else None
    statuses = {}
    for h in hits:
        statuses[h["status"]] = statuses.get(h["status"], 0) + 1
    links.append({"link": 5, "what": "those households, or the region's pilot households, bought food later",
                  "by": ("region (purchases) and id (the person sample: ration and status, not purchases)" if hits
                         else "region only (purchases; no crew member or their household is in the person sample)"),
                  "snapshot": first[0] if first else hits[0]["snapshot"],
                  "region_pilot_opened": None if opened is None else _pick(opened, "turn", "note"),
                  "region_purchase_snapshots": len(bought),
                  "region_paid_milli": sum(f["provisioning"]["paid_milli"] for _T, f in bought),
                  "first_purchase": None if first is None else {
                      "snapshot": first[0], "price_milli": first[1].get("price_milli"),
                      **_pick(first[1]["provisioning"], *PROVISIONING_READ)},
                  "sample_hits": len(hits), "sample_hits_in_region": len(here), "sample_statuses": statuses,
                  "sample": hits[:MAX_HITS], "repair_crew_sample_hits_in_region": len(repairers),
                  "repair_crew_sample": repairers[:MAX_HITS]})
    out["depth"] = 5
    out["id_to_food"] = bool(hits)
    out["id_to_food_in_region"] = bool(here)
    out["repair_crew_to_food_in_region"] = bool(repairers)
    return out


def _id_links(t: dict) -> int:
    """How many of the links that can be joined by id were: the store link (the project
    was the region's only holder), a paid worker in the sample in the chain's region, and
    the repair crew there after its repair wage."""
    by3 = len(t["links"]) >= 3 and t["links"][2]["by"].startswith("id")
    return int(by3) + int(t.get("id_to_food_in_region", False)) + int(t.get("repair_crew_to_food_in_region", False))


def _chain(hist) -> dict:
    """The best natural chain instance (the deepest, then traced to food by id, then the
    earliest stall), and a funnel over every project that stalled ``no_timber``."""
    ix = _chain_index(hist)
    traces = [_trace(ix, pid) for pid in sorted(ix["stall"], key=lambda p: (ix["stall"][p][0], p))]
    funnel = {"projects stalled no_timber": len(traces)}
    for depth, label in ((2, "an expedition from the region delivered after the stall"),
                         (3, "the repair used the delivered timber"), (4, "named workers paid"),
                         (5, "the region's households bought food later")):
        funnel[label] = sum(1 for t in traces if t["depth"] >= depth)
    funnel["a paid crew member or their household in the retail sample later"] = sum(1 for t in traces
                                                                                     if t["id_to_food"])
    funnel["... in the chain's region"] = sum(1 for t in traces if t.get("id_to_food_in_region"))
    funnel["... the repair crew there after its repair wage"] = sum(1 for t in traces
                                                                  if t.get("repair_crew_to_food_in_region"))
    funnel["the store link joined by id (the project the region's only holder)"] = sum(
        1 for t in traces if len(t["links"]) >= 3 and t["links"][2]["by"].startswith("id"))
    best = max(traces, key=lambda t: (t["depth"], _id_links(t), t["id_to_food"]), default=None)
    return {"instance": best, "funnel": funnel}


def _tradeoffs(hist, ix=None) -> dict:
    """Natural tradeoff instances: a crew's farm labour away while its home region was
    short of food; the forest stand drawn down by a cut (and the guard ending one); a
    family priced out after its crew member's wages ended."""
    ix = ix or _chain_index(hist)
    away = short = None
    cells = shorts = 0
    for T, r in ix["ts_list"]:
        if (r.get("away_delivered") or 0) <= 0:
            continue
        cells += 1
        food = ix["food"].get((T, r["home"]))
        s = (food or {}).get("sufficiency_after_relief")
        if s is None or s >= 1.0:
            continue
        shorts += 1
        demand = (food.get("native") or {}).get("demand") or 0.0
        prov = (ix["frames"].get((T, r["home"])) or {}).get("provisioning") or {}
        hit = (T, {**_pick(r, "eid", "home", "forest", "stage", "crew", "away_delivered"),
                   "home_demand": demand, "home_sufficiency_after_relief": s,
                   "home_shortfall": round(demand * (1 - s), 6),
                   "home_priced_out_persons": prov.get("priced_out_persons"),
                   "home_pilot_persons": prov.get("persons")})
        short = short or hit
        if away is None and (prov.get("priced_out_persons") or 0) > 0:
            away = hit
    cut = guard = None
    cutting = falls = 0
    for T, r in ix["ts_list"]:
        if r.get("stage") == "cutting" and isinstance(r.get("capacity"), (int, float)) and r["capacity"] > 0 \
                and isinstance(r.get("stock_after"), (int, float)) and isinstance(r.get("stock_before"), (int, float)):
            cutting += 1
            fall = r["stock_before"] - r["stock_after"]
            falls += fall > 0
            if fall > 0 and (cut is None or fall > cut[1]["stock_fall"]):
                cut = (T, {**_pick(r, "eid", "home", "forest", "slot", "crew", "cut", "stock_before", "stock_after",
                                   "capacity"),
                           "stock_fall": round(fall, 6), "share_before": round(r["stock_before"] / r["capacity"], 6),
                           "share_after": round(r["stock_after"] / r["capacity"], 6), "l3_row": _l3(ix, T, r)})
        if guard is None and r.get("cut_end") == "forest_depleted":
            worked = [(t, x) for t, x in ix["ts_rx"].get(r["eid"], []) if t < T and x.get("stage") == "cutting"]
            last = [(t, x) for t, x in worked
                    if isinstance(x.get("stock_after"), (int, float)) and (x.get("capacity") or 0) > 0]
            span = range(worked[0][0], T + 1) if worked else range(T, T + 1)
            rows = [_l3(ix, t, r) for t in span]
            rows = [x for x in rows if x is not None]
            guard = (T, {**_pick(r, "eid", "home", "forest", "slot", "stage", "cut_end", "cargo_after"),
                         "crew_cut": round(sum(x.get("cut") or 0 for _t, x in worked), 6),
                         "last_cutting_snapshot": last[-1][0] if last else None,
                         "last_cutting_share_after": round(last[-1][1]["stock_after"] / last[-1][1]["capacity"], 6)
                         if last else None,
                         "l3_snapshots": [span[0], span[-1]],
                         "l3_cleared": round(sum(x.get("cleared") or 0 for x in rows), 6),
                         "l3_extraction": round(sum(x.get("extraction") or 0 for x in rows), 6),
                         "l3_capacity_after": rows[-1].get("capacity") if rows else None})
    family = None
    hits = 0
    if not ix["sample"]:
        family = "not applicable (no household_retail person sample)"
    else:
        paid = _wage_snapshots(ix)
        for T in sorted(ix["sample"]):
            for row in ix["sample"][T]:
                if row.get("status") != PRICED_OUT:
                    continue
                for who, aid in (("self", row.get("agent_id")), ("household", row.get("household"))):
                    if who == "household" and aid == row.get("agent_id"):
                        continue
                    wages = paid.get(aid) or {}
                    prior = [w for w in wages if w < T]
                    if prior and T not in wages:
                        hits += 1
                        if family is None:
                            last = max(prior)
                            family = (T, {"crew_member": aid, "who": who, "priced_out_person": row.get("agent_id"),
                                          "household": row.get("household"), "region": row.get("region"),
                                          "ration": row.get("ration"), "fair_share": row.get("fair_share"),
                                          "wage_snapshots": sorted(prior),
                                          "wage_sources": sorted({x for w in prior for x in wages[w][1]}),
                                          "wage_regions": sorted({x for w in prior for x in wages[w][2]}),
                                          "wages_milli": sum(wages[w][0] for w in prior),
                                          "last_wage_snapshot": last, "turns_since_last_wage": T - last,
                                          "paid_again_later": any(w > T for w in wages)})
    return {
        "tradeoff: crew farm labour away while the home region was short of food (first with home pilot persons "
        "priced out that turn, else the first short)": away or short,
        "tradeoff: the forest stand drawn down by a cut (the largest one-turn fall of the L3 stock while cutting)": cut,
        "tradeoff: the guard ended a cutting stage (forest_depleted)": guard,
        "tradeoff: a family priced out after its crew member's wages ended": family,
        "counts": {"away crew-turns": cells, "away crew-turns with the home region short": shorts,
                   "cutting turns": cutting, "cutting turns whose L3 stock fell": falls,
                   "priced-out sample rows after a crew member's wages ended": hits},
    }


#: Record fields the chain mode reads: (module, model) -> fields.
CHAIN_FIELDS_READ = {
    ("repair_projects_state", "RepairReceipt"): {"turn", "pid", "kind", "asset", "region", "status", "reasons",
                                                 "condition_before", "condition_after", "timber_held", "timber_used",
                                                 "crew", "wages_milli"},
    ("repair_projects_state", "RepairProject"): {"pid", "region", "status", "closed_turn"},
    ("timber_supply_state", "Expedition"): {"eid", "civ", "home", "forest", "hops", "launched_turn", "ended_turn",
                                            "launched_crew", "crew", "cut", "delivered", "wages_milli",
                                            "away_delivered", "status"},
    ("timber_supply_state", "ExpeditionReceipt"): {"eid", "home", "forest", "slot", "stage", "crew", "wages_milli",
                                                   "away_delivered", "cut", "stock_before", "stock_after",
                                                   "capacity", "cut_end", "cargo_after"},
    ("timber_stock_state", "TimberLedgerRow"): {"region_id", "slot", "opening", "cleared", "extraction", "regrowth",
                                                "stock", "capacity"},
    ("timber_supply_state", "StoreRow"): {"region", "held", "delivered", "closing"},
    ("timber_supply_state", "NeedRow"): {"want", "free", "gap", "status", "eid"},
    ("recovery_crews_state", "CrewReceipt"): {"pid", "members"},
    ("recovery_crews_state", "CrewMember"): {"agent_id", "origin", "wage_milli"},
    ("household_retail_state", "RegionFrame"): {"region", "provisioning", "price_milli"},
    ("household_retail_state", "RetailRecord"): {"turn", "region", "kind", "note"},
}
CHAIN_VALUES_READ = {
    ("repair_projects_state", "REASONS"): {"no_timber"},
    ("repair_projects_state", "PROJECT_STATUSES"): {"completed"},
    ("timber_supply_state", "STATUSES"): {"delivered"},
    ("timber_supply_state", "NEED_STATUSES"): {"launched"},
    ("timber_supply_state", "STAGES"): {"cutting"},
    ("timber_supply_state", "CUT_ENDS"): {"forest_depleted"},
    ("household_retail_state", "RECORD_KINDS"): {"pilot_opened"},
}


def _chain_problems(import_module) -> list[str]:
    problems = []
    for (module, model), fields in CHAIN_FIELDS_READ.items():
        declared = set(getattr(import_module(f"chronicler.{module}"), model).model_fields)
        problems += [f"{model}.{f} is not a field" for f in sorted(fields - declared)]
    for (module, name), values in CHAIN_VALUES_READ.items():
        declared = set(getattr(import_module(f"chronicler.{module}"), name))
        problems += [f"{module}.{name} does not declare {v!r}" for v in sorted(values - declared)]
    statuses = tuple(import_module("chronicler.household_retail_state").SAMPLE_STATUSES)
    if statuses != SAMPLE_STATUS_NAMES[:len(statuses)] or SAMPLE_STATUS_NAMES[PRICED_OUT] != "priced_out":
        problems.append(f"SAMPLE_STATUSES {statuses} do not lead SAMPLE_STATUS_NAMES {SAMPLE_STATUS_NAMES}")
    retail = (REPO / "src" / "chronicler" / "household_retail.py").read_text(encoding="utf-8")
    if f'"sample_columns": {json.dumps(list(SAMPLE_COLUMNS))}' not in retail:
        problems.append("household_retail.snapshot_summary declares other sample_columns")
    rust = (REPO / "chronicler-agents" / "src" / "provisioning.rs").read_text(encoding="utf-8")
    m = re.search(r"pub const RETAIL_REGION_COLUMNS: \[&str; \d+\] = \[(.*?)\];", rust, re.S)
    declared = set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()
    problems += [f"provisioning column {c} is not in RETAIL_REGION_COLUMNS" for c in PROVISIONING_READ
                 if c not in declared]
    return problems


def check_fields() -> None:
    """Every record field and declared value this script reads exists in this
    checkout's source (its models, reason tuples, RS2's dated notes, the retail sample
    columns and the native provisioning columns), and the fallback operating floor is
    the workshops' own. Raises SystemExit naming each problem."""
    if str(REPO / "src") not in sys.path:
        sys.path.insert(0, str(REPO / "src"))
    from importlib import import_module
    problems = []
    for (module, model), fields in FIELDS_READ.items():
        declared = set(getattr(import_module(f"chronicler.{module}"), model).model_fields)
        problems += [f"{model}.{f} is not a field" for f in sorted(fields - declared)]
    for (module, name), values in VALUES_READ.items():
        declared = set(getattr(import_module(f"chronicler.{module}"), name))
        problems += [f"{module}.{name} does not declare {v!r}" for v in sorted(values - declared)]
    source = (REPO / "src" / "chronicler" / "repair_projects.py").read_text(encoding="utf-8")
    problems += [f"repair_projects.py notes no {e!r} event" for e in HISTORY_EVENTS if f'"{e}"' not in source]
    if import_module("chronicler.workshops").OPERATE_CONDITION != OPERATE_CONDITION:
        problems.append("OPERATE_CONDITION differs from workshops.OPERATE_CONDITION")
    problems += _chain_problems(import_module)
    if problems:
        raise SystemExit("productive-recovery examples do not match the source: " + "; ".join(problems))


#: The packages the chain mode needs, and the tradeoffs.
CHAIN_NEEDS = ("repair_projects", "timber_supply", "household_retail")


def find_chain(bundle: dict) -> dict:
    """{"chain": {...} | note, "tradeoffs": {...} | note} for one run (dated records only)."""
    hist = bundle.get("history") or []
    missing = [name for name in CHAIN_NEEDS if not _has(hist, name)]
    ix = _chain_index(hist)
    out = {"chain": f"not recorded in this run (no {', '.join(missing)} record)" if missing else _chain(hist)}
    out["tradeoffs"] = (_tradeoffs(hist, ix) if _has(hist, "timber_supply")
                        else "not recorded in this run (no timber_supply record)")
    return out


def chain_main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    sys.path.insert(0, str(REPO / "src"))
    from chronicler.bundle_codec import load_bundle
    for path in argv:
        b = load_bundle(Path(path))
        hist = b.get("history") or []
        modes = {}
        for name in ("timber_supply", "recovery_crews", "repair_projects", "household_retail", "remittances"):
            first = next(_records(hist, name), None)
            if first is not None:
                modes[name] = first[1].get("mode")
                if name == "household_retail":
                    modes["household_retail_boundary"] = first[1].get("boundary")
        print(f"== {path} (seed {(b.get('metadata') or {}).get('seed')}, {len(hist)} snapshots; natural; "
              f"modes {json.dumps(modes, sort_keys=True)})")
        found = find_chain(b)
        chain = found["chain"]
        if isinstance(chain, str):
            print(f"  chain: {chain}")
        else:
            inst = chain["instance"]
            if inst is None:
                print("  chain: none found (no project stalled no_timber)")
            else:
                print(f"  chain: project {inst['pid']} (region {inst['region']}), {inst['depth']} of 5 links"
                      + (f"; link {inst['depth'] + 1} not found: {inst['missing']}" if inst.get("missing") else ""))
                for link in inst["links"]:
                    print(f"    link {link['link']} ({link['by']}): snapshot {link['snapshot']}: "
                          f"{json.dumps(link, sort_keys=True)}")
            print(f"  chain funnel: {json.dumps(chain['funnel'])}")
        trade = found["tradeoffs"]
        if isinstance(trade, str):
            print(f"  tradeoffs: {trade}")
            continue
        print("  tradeoffs")
        for kind, hit in trade.items():
            if kind == "counts":
                print(f"    counts: {json.dumps(hit)}")
            elif hit is None:
                print(f"    {kind}: none found")
            elif isinstance(hit, str):
                print(f"    {kind}: {hit}")
            else:
                print(f"    {kind}: snapshot {hit[0]}: {json.dumps(hit[1], sort_keys=True)}")
    return 0


def find(bundle: dict) -> dict:
    """{group: {kind: (snapshot turn, row) | None | note}} for the groups whose
    packages the run recorded (a group whose records are absent is left out)."""
    hist = bundle.get("history") or []
    out = {}
    for group, (needs, finder) in FINDERS.items():
        if all(_has(hist, name) for name in needs):
            out[group] = finder(hist)
    return out


def rules_version(bundle: dict):
    """The apprenticeship rules version the run's records state (None: no RS1 record)."""
    for _turn, rec in _records(bundle.get("history") or [], "apprenticeship"):
        return rec.get("rules_version", rec.get("schema_version"))
    return None


def main(argv: list[str]) -> int:
    if argv[:1] == ["--chain"]:
        return chain_main(argv[1:])
    if not argv:
        print(__doc__)
        return 2
    sys.path.insert(0, str(REPO / "src"))
    from chronicler.bundle_codec import load_bundle
    for path in argv:
        b = load_bundle(Path(path))
        seed = (b.get("metadata") or {}).get("seed")
        hist = b.get("history") or []
        modes = {}
        for name in ("apprenticeship", "timber_supply", "recovery_crews", "maintenance_obligation", "repair_projects"):
            first = next(_records(hist, name), None)
            if first is not None:
                modes[name] = first[1].get("mode")
        print(f"== {path} (seed {seed}, {len(hist)} snapshots; natural; modes {json.dumps(modes, sort_keys=True)}; "
              f"RS1 rules {rules_version(b)})")
        found = find(b)
        for group in FINDERS:
            if group not in found:
                print(f"  {group}: not recorded in this run")
                continue
            print(f"  {group}")
            for kind, hit in found[group].items():
                if hit is None:
                    print(f"    {kind}: none found")
                elif isinstance(hit, str):
                    print(f"    {kind}: {hit}")
                else:
                    turn, row = hit
                    print(f"    {kind}: snapshot {turn}: {json.dumps(row, sort_keys=True)[:600]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
