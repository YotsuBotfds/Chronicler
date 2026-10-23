"""Read-only historical explanations from publicly validated saved sessions.

The session loader owns complete replay validation. This module selects existing
receipts; it never submits a tick/batch or substitutes the latest for a missing
turn. No per-receipt memome digest or individual vote list is invented.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
import json
from pathlib import Path

from chronicler import experiment_sessions as es
from chronicler.campaign_logistics import Receipt as CampaignReceipt
from chronicler.memome_experiment import Tick as MemomeTick

CONTRACT = "chronicler-experiment-receipt-inspector-v1"


@dataclass(frozen=True, slots=True)
class HistoricalTurn:
    turn: int
    campaign: CampaignReceipt | None = None
    campaign_receipt_digest: str | None = None
    memome: MemomeTick | None = None


@dataclass(frozen=True, slots=True)
class ReceiptInspection:
    kernel: str
    kernel_contract: str
    generation: int
    latest_turn: int
    genesis_turn: int
    file_digest: str
    session_digest: str
    genesis_digest: str
    history_digest: str
    latest_digest: str
    source_head: str
    source_tree: str
    transport: es.TransportPolicy
    selection: str
    start_turn: int
    end_turn: int
    max_turns: int | None
    initial_state_digest: str | None
    turns: tuple[HistoricalTurn, ...]


def disabled_receipt() -> dict:
    return {"contract": CONTRACT, "enabled": False, "reads_files": False,
            "writes_files": False, "calls_kernels": False,
            "reason": "explicit --enable, session path, transport and historical selection required"}


def _turn(value: object, name: str, transport: es.TransportPolicy) -> int:
    if type(value) is not int or value < 0:
        raise es.SessionError(f"{name} must be a nonnegative exact integer")
    if value.bit_length() > transport.max_int_bits:
        raise es.TransportDomainError(f"{name} exceeds the transport integer domain")
    return value


def _selection(*, transport, turn, start_turn, end_turn, max_turns):
    if turn is not None:
        if any(value is not None for value in (start_turn, end_turn, max_turns)):
            raise es.SessionError("exact turn and interval arguments are mutually exclusive")
        exact = _turn(turn, "turn", transport)
        return "exact", exact, exact
    if start_turn is None or end_turn is None or max_turns is None:
        raise es.SessionError("an interval requires explicit start_turn, end_turn and max_turns")
    start = _turn(start_turn, "start_turn", transport)
    end = _turn(end_turn, "end_turn", transport)
    if type(max_turns) is not int or not 1 <= max_turns <= es.MAX_TRANSPORT_HISTORY:
        raise es.SessionError(f"max_turns must be an exact integer in 1..{es.MAX_TRANSPORT_HISTORY}")
    if end < start:
        raise es.SessionError("end_turn must not precede start_turn")
    if end - start + 1 > max_turns:
        raise es.TransportDomainError("requested inclusive interval exceeds explicit max_turns")
    return "interval", start, end


def inspect_receipts(path: str | Path | None = None, *, enabled: bool = False,
                     transport: es.TransportPolicy | None = None,
                     turn: int | None = None, start_turn: int | None = None,
                     end_turn: int | None = None,
                     max_turns: int | None = None) -> ReceiptInspection | dict:
    """Select an exact turn or an explicitly bounded inclusive interval.

    Disabled returns before examining any input. Enabled validates the selection
    before opening the session. A valid but uncommitted turn is unavailable,
    including genesis and future turns. Negative, noninteger and over-wide turns
    are errors. Full history replay by load_session verifies the saved receipts;
    no new experimental decision or persistence occurs here.
    """
    if type(enabled) is not bool:
        raise es.SessionError("enabled must be an exact boolean")
    if not enabled:
        return disabled_receipt()
    if path is None:
        raise es.SessionError("an explicit session path is required")
    if type(transport) is not es.TransportPolicy:
        raise es.SessionError("an exact explicit TransportPolicy is required")
    es.transport_policy_from_payload(transport.as_payload())
    mode, start, end = _selection(transport=transport, turn=turn,
                                start_turn=start_turn, end_turn=end_turn, max_turns=max_turns)
    loaded = es.load_session(path, transport=transport)
    session, envelope = loaded.session, loaded.envelope
    if type(session) is es.CampaignSession:
        cursor = session.session.cursor
        historical = {receipt.turn: HistoricalTurn(receipt.turn, receipt, digest)
                      for receipt, digest in zip(cursor.receipts, cursor.receipt_digests)}
        genesis_turn = session.admission.turn
        initial_digest = cursor.initial_state_digest
    elif type(session) is es.MemomeSession:
        historical = {tick.batch.turn: HistoricalTurn(tick.batch.turn, memome=tick)
                      for tick in session.ledger.history}
        genesis_turn, initial_digest = session.genesis_turn, None
    else:
        raise es.SessionError("unsupported validated session record")
    selected = tuple(historical.get(number, HistoricalTurn(number))
                     for number in range(start, end + 1))
    return ReceiptInspection(
        envelope.kernel, envelope.kernel_contract, loaded.generation, loaded.turn,
        genesis_turn, loaded.digest, envelope.session_digest, envelope.genesis_digest,
        envelope.history_digest, envelope.latest_digest, envelope.source_head,
        envelope.source_tree, transport, mode, start, end, max_turns, initial_digest, selected)


def _plain(value):
    if is_dataclass(value):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    if type(value) is tuple:
        return [_plain(item) for item in value]
    return value


def inspection_document(inspection: ReceiptInspection) -> dict:
    """All authoritative receipt fields, with explicitly labeled arithmetic summaries."""
    if type(inspection) is not ReceiptInspection:
        raise es.SessionError("an exact ReceiptInspection is required")
    turns = []
    for entry in inspection.turns:
        row = {"turn": entry.turn, "available": entry.campaign is not None or entry.memome is not None}
        if entry.campaign is not None:
            receipt = entry.campaign
            row["campaign"] = {
                "receipt": _plain(receipt), "receipt_digest": entry.campaign_receipt_digest,
                "derived_member_changes": [
                    {"agent_id": member.agent_id,
                     "morale_delta": member.morale_after - member.morale_before,
                     "deserted_rations": member.released if member.deserted else 0,
                     "returned_rations": member.released if member.status_after == "returned"
                                           and member.status_before != "returned" else 0}
                    for member in receipt.members],
            }
        elif entry.memome is not None:
            row["memome"] = {
                "batch": _plain(entry.memome.batch),
                "receipts": _plain(entry.memome.receipts),
                "participants_after": _plain(entry.memome.participants),
                "individual_electorate_votes": "unavailable: not retained in receipts",
                "receipt_digest_chain": "unavailable: not retained by this kernel",
            }
        else:
            row["reason"] = "unavailable: no committed receipt at this turn"
        turns.append(row)
    document = {
        "contract": CONTRACT, "enabled": True, "writes_files": False,
        "kernel": inspection.kernel, "kernel_contract": inspection.kernel_contract,
        "generation": inspection.generation, "latest_turn": inspection.latest_turn,
        "genesis_turn": inspection.genesis_turn,
        "file_digest": inspection.file_digest, "session_digest": inspection.session_digest,
        "genesis_digest": inspection.genesis_digest, "history_digest": inspection.history_digest,
        "latest_digest": inspection.latest_digest,
        "source_head": inspection.source_head, "source_tree": inspection.source_tree,
        "transport": inspection.transport.as_payload(),
        "selection": {"mode": inspection.selection, "start_turn": inspection.start_turn,
                      "end_turn": inspection.end_turn, "max_turns": inspection.max_turns},
        "turns": turns,
    }
    if inspection.kernel == "m60a":
        document["campaign_initial_state_digest"] = inspection.initial_state_digest
    return document


def inspection_json(inspection: ReceiptInspection) -> str:
    return json.dumps(inspection_document(inspection), sort_keys=True,
                      separators=(",", ":"), allow_nan=False) + "\n"


def inspection_text(inspection: ReceiptInspection) -> str:
    """Deterministic tab-separated receipt tables; exact integer rendering only."""
    document = inspection_document(inspection)
    lines = [f"{inspection.kernel} generation={inspection.generation} latest_turn={inspection.latest_turn}",
             f"file_digest={inspection.file_digest}", f"session_digest={inspection.session_digest}"]
    if inspection.kernel == "m60a":
        lines.append("turn\tagent\tregion\tstatus\tconsumed\treplenished\tdeserted_rations\treturned_rations\tmorale\tdelta\tpath\tsupply_distance\tdraw\treasons")
        for row in document["turns"]:
            if not row["available"]:
                lines.append(f"{row['turn']}\tunavailable: no committed receipt")
                continue
            campaign = row["campaign"]
            receipt = campaign["receipt"]
            lines.append(f"turn={row['turn']} receipt_digest={campaign['receipt_digest']} "
                         f"state_before_digest={receipt['state_before_digest']} "
                         f"state_after_digest={receipt['state_after_digest']} "
                         f"phase={receipt['phase_before']}->{receipt['phase_after']}")
            changes = {change["agent_id"]: change for change in campaign["derived_member_changes"]}
            for member in receipt["members"]:
                change = changes[member["agent_id"]]
                values = [row["turn"], member["agent_id"],
                          f"{member['region_before']}->{member['region_after']}",
                          f"{member['status_before']}->{member['status_after']}",
                          member["consumed"], member["replenished"], change["deserted_rations"],
                          change["returned_rations"], f"{member['morale_before']}->{member['morale_after']}",
                          change["morale_delta"], json.dumps(member["path"], separators=(",", ":")),
                          member["supply_distance"], member["draw"], ",".join(member["reasons"])]
                lines.append("\t".join(_cell(value) for value in values))
    else:
        lines.append("turn\tproposal\trecipient\tslot\tprevious\tcandidate\tdraw\tcandidate_weight\telectorate_weight\tthreshold\treason")
        for row in document["turns"]:
            if not row["available"]:
                lines.append(f"{row['turn']}\tunavailable: no committed receipt")
                continue
            receipts = row["memome"]["receipts"]
            if not receipts:
                lines.append(f"{row['turn']}\tavailable: committed batch contains no proposals")
            for receipt in receipts:
                lines.append("\t".join(_cell(value) for value in [row["turn"], *(
                    receipt[name] for name in ("proposal_id", "recipient", "slot", "previous", "candidate",
                                              "draw", "candidate_weight", "electorate_weight", "threshold", "reason"))]))
        lines.append("Individual electorate votes and per-receipt digest chain: unavailable (not retained).")
    return "\n".join(lines) + "\n"


def _cell(value) -> str:
    return str(value).replace("\\", "\\\\").replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n")
