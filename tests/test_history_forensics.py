"""Read-only forensics: historical knowledge, redaction and graph integrity."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from chronicler.bundle_codec import dumps_bundle
from chronicler.historical_context import AsOf
from chronicler.historiography import ACCOUNT_COLUMNS
from chronicler.history_forensics import (
    ForensicsError, HistoryForensics, Limits, inspect_bundle, inspect_path, main, render_markdown,
)


def event(turn, name, causes=(), description=None):
    return {"turn": turn, "event_id": f"{turn}:{name}:0", "event_type": name,
            "actors": ["A", "B"], "description": description or f"Recorded {name}", "causes": list(causes)}


def account(eid, cid, turn, text, *, lost=None, transforms=(), cited=()):
    return [eid, cid, turn, "claim", list(transforms), list(cited), text, lost, "sack" if lost else None]


@pytest.fixture
def bundle():
    declared = event(2, "war_declared")
    occupied = event(4, "occupation", [declared["event_id"]])
    famine = event(6, "famine", [occupied["event_id"], declared["event_id"]])
    return {
        "world_state": {"turn": 12}, "metadata": {"seed": 42, "bundle_version": 6},
        "history": [{"turn": 1, "civ_stats": {}}, {"turn": 12, "civ_stats": {}}],
        "events_timeline": [declared, occupied, famine],
        "historiography": {
            "chroniclers": [{"id": f"court:{i}", "name": f"Court {i}"} for i in range(4)],
            "archives": [], "account_columns": list(ACCOUNT_COLUMNS), "contested": [],
            "accounts": [
                account(famine["event_id"], "court:0", 6, "The enemy poisoned the fields.", lost=8,
                        transforms=[["blame", {"secret": "hidden bias detail"}]], cited=["SECRET-CITATION"]),
                account(famine["event_id"], "court:1", 6, "", transforms=[["omit", {}]]),
                account(famine["event_id"], "court:2", 6, "An honest surviving account."),
                account(famine["event_id"], "court:3", 10, "A later account."),
            ],
            "plain": {"seat:0": [declared["event_id"], famine["event_id"]]},
        },
    }


def by_chronicler(report):
    return {a["chronicler"]: a for a in report["selected"]["accounts"]}


def test_true_record_and_as_of_loss_and_silence_are_separate(bundle):
    before = inspect_bundle(bundle, "6:famine:0", as_of=AsOf.before(8))
    after = inspect_bundle(bundle, "6:famine:0", as_of=AsOf.after(8))
    assert before["as_of"]["completed_turn"] == 7
    assert before["selected"]["description"] == "Recorded famine"
    assert by_chronicler(before)["court:0"]["text"] == "The enemy poisoned the fields."
    assert by_chronicler(before)["court:0"]["status"] == "surviving"
    assert "lost_turn" not in by_chronicler(before)["court:0"]
    rows = by_chronicler(after)
    assert rows["court:0"]["status"] == "lost"
    assert rows["court:0"]["lost_turn"] == 8 and rows["court:0"]["text"] is None
    assert rows["court:1"]["status"] == "silent" and rows["court:1"]["text"] is None
    assert "bias_kinds" not in rows["court:0"] and "cited" not in rows["court:0"]
    assert "bias_kinds" not in rows["court:1"]
    assert "court:3" not in rows  # not yet written
    for text in (json.dumps(after), render_markdown(after)):
        for secret in ("poisoned", "hidden bias detail", "SECRET-CITATION", "later account"):
            assert secret not in text
    assert by_chronicler(inspect_bundle(bundle, "6:famine:0", as_of=AsOf.after(10)))["court:3"]["text"]


def test_plain_accounts_are_included_without_invented_quotes(bundle):
    report = inspect_bundle(bundle, "6:famine:0")
    plain = by_chronicler(report)["seat:0"]
    assert plain["status"] == "surviving" and plain["representation"] == "plain_reference"
    assert plain["text"] is None and plain["summary"] == "Recorded famine"
    assert "stance" not in plain and "cited" not in plain
    assert "wording" in plain
    assert report["ancestors"][0]["accounts"][0]["chronicler"] == "seat:0"


def test_dated_ancestry_uses_only_recorded_dependencies_not_account_claims(bundle):
    report = inspect_bundle(bundle, "6:famine:0", as_of=AsOf.after(7))
    assert [a["event_id"] for a in report["ancestors"]] == ["2:war_declared:0", "4:occupation:0"]
    assert [a["distance"] for a in report["ancestors"]] == [1, 1]  # shortest paths
    assert {(e["cause_id"], e["effect_id"]) for e in report["edges"]} == {
        ("2:war_declared:0", "4:occupation:0"), ("2:war_declared:0", "6:famine:0"),
        ("4:occupation:0", "6:famine:0"),
    }
    assert not report["diagnostics"] and not report["truncated_by"]
    assert "SECRET-CITATION" not in {e["cause_id"] for e in report["edges"]}
    assert "not a proven counterfactual" in report["interpretation"]


def test_cycles_dangling_duplicates_and_undated_causes_are_explicit():
    a, b, dupe, undated = event(1, "a"), event(2, "b"), event(1, "duplicate"), event(0, "undated")
    a["causes"] = [b["event_id"], a["event_id"], "not-found", dupe["event_id"], undated["event_id"]]
    b["causes"] = [a["event_id"]]
    undated.pop("turn")
    report = inspect_bundle({"events_timeline": [a, b, dupe, dupe.copy(), undated]}, a["event_id"])
    kinds = {d["kind"] for d in report["diagnostics"]}
    assert kinds == {"cycle", "dangling_id", "duplicate_event_id", "undated_cause", "future_cause"}
    assert len(report["ancestors"]) == 1
    assert sum(d["kind"] == "cycle" for d in report["diagnostics"]) == 2
    with pytest.raises(ForensicsError, match="ambiguous"):
        inspect_bundle({"events_timeline": [dupe, dupe.copy()]}, dupe["event_id"])


def test_selected_and_ancestral_future_content_never_leaks():
    a = event(2, "a", ["10:future:0"])
    future = event(10, "future", description="FUTURE SECRET")
    with pytest.raises(ForensicsError, match="not known"):
        inspect_bundle({"events_timeline": [a, future]}, future["event_id"], as_of=AsOf.before(10))
    report = inspect_bundle({"events_timeline": [a, future]}, a["event_id"], as_of=AsOf.after(2))
    assert report["edges"][0]["status"] == "after_as_of"
    assert report["diagnostics"][0]["kind"] == "cause_after_as_of"
    assert report["ancestors"] == [] and "FUTURE SECRET" not in json.dumps(report)


@pytest.mark.parametrize("limit,expected", [
    (Limits(max_depth=0), "max_depth"), (Limits(max_nodes=1), "max_nodes"),
    (Limits(max_edges=1), "max_edges"), (Limits(max_accounts=1), "max_accounts"),
])
def test_bounds_are_visible_and_reports_are_partial(bundle, limit, expected):
    report = inspect_bundle(bundle, "6:famine:0", limits=limit)
    assert expected in report["truncated_by"]
    assert len(report["ancestors"]) + 1 <= limit.max_nodes
    assert len(report["edges"]) <= limit.max_edges
    assert all(len(n["accounts"]) <= limit.max_accounts for n in [report["selected"], *report["ancestors"]])
    assert "report is partial" in render_markdown(report)


def test_deep_graph_traversal_is_iterative_and_bounded():
    events = [event(i, "step", [f"{i-1}:step:0"] if i else []) for i in range(3000)]
    report = inspect_bundle({"events_timeline": events}, "2999:step:0", limits=Limits(max_depth=256))
    assert len(report["ancestors"]) == 199
    assert report["truncated_by"] == ["max_nodes"]


def test_legacy_missing_ids_and_missing_historiography_are_not_silence():
    ev = event(1, "existing")
    bundle = {"events": [ev, {"turn": 2, "event_type": "old", "description": "Legacy"}]}
    report = inspect_bundle(bundle, ev["event_id"])
    assert report["bundle"]["events_without_ids"] == 1
    assert report["bundle"]["historiography"] == "unavailable"
    assert report["selected"]["accounts"] == []
    assert "absence is not recorded silence" in render_markdown(report)
    with pytest.raises(ForensicsError, match="legacy records cannot be selected"):
        inspect_bundle(bundle, "2:old:0")


def test_v6_and_legacy_file_roundtrip_preserves_input_and_stable_order(bundle, tmp_path):
    before = copy.deepcopy(bundle)
    reference = inspect_bundle(bundle, "6:famine:0")
    encoded = json.loads(dumps_bundle(bundle))
    assert "history_delta" in encoded
    assert inspect_bundle(encoded, "6:famine:0") == reference
    path = tmp_path / "chronicle_bundle.json"
    path.write_text(dumps_bundle(bundle), encoding="utf-8")
    raw = path.read_bytes()
    report = inspect_path(path, "6:famine:0")
    assert report["source"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert path.read_bytes() == raw and bundle == before
    # Account row ordering is not a source of arbitrary output ordering.
    reversed_bundle = copy.deepcopy(bundle)
    reversed_bundle["historiography"]["accounts"].reverse()
    assert inspect_bundle(reversed_bundle, "6:famine:0") == reference
    # Reports do not share account lists with the reader's source.
    report["selected"]["accounts"].clear()
    assert bundle == before


def test_reordered_account_columns_are_supported(bundle):
    baseline = inspect_bundle(bundle, "6:famine:0")
    hist = bundle["historiography"]
    hist["account_columns"] = list(reversed(ACCOUNT_COLUMNS))
    hist["accounts"] = [list(reversed(row)) for row in hist["accounts"]]
    assert inspect_bundle(bundle, "6:famine:0") == baseline


def test_source_digest_identifies_analyzed_bytes_if_file_is_replaced(bundle, tmp_path, monkeypatch):
    path = tmp_path / "input.json"
    raw = dumps_bundle(bundle).encode("utf-8")
    path.write_bytes(raw)
    replacement = copy.deepcopy(bundle)
    replacement["events_timeline"][2]["description"] = "A different source"
    changed = dumps_bundle(replacement).encode("utf-8")
    read_bytes, read_text = Path.read_bytes, Path.read_text

    def replacing_bytes(self, *args, **kwargs):
        data = read_bytes(self, *args, **kwargs)
        if self == path:
            path.write_bytes(changed)
        return data

    def replacing_text(self, *args, **kwargs):
        data = read_text(self, *args, **kwargs)
        if self == path:
            path.write_bytes(changed)
        return data

    monkeypatch.setattr(Path, "read_bytes", replacing_bytes)
    monkeypatch.setattr(Path, "read_text", replacing_text)
    report = inspect_path(path, "6:famine:0")
    assert report["selected"]["description"] == "Recorded famine"
    assert report["source"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert read_bytes(path) == changed


def test_unknown_account_dates_and_duplicate_identity_do_not_reveal_claims(bundle):
    hist = bundle["historiography"]
    hist["accounts"] += [account("6:famine:0", "court:4", None, "UNDATED SECRET"),
                         account("6:famine:0", "court:2", 6, "DUPLICATE SECRET")]
    report = inspect_bundle(bundle, "6:famine:0")
    assert by_chronicler(report)["court:4"]["status"] == "undated"
    assert by_chronicler(report)["court:2"]["status"] == "ambiguous"
    assert "UNDATED SECRET" not in json.dumps(report) and "DUPLICATE SECRET" not in json.dumps(report)
    assert "UNDATED SECRET" not in render_markdown(report)


def test_same_turn_emission_order_and_start_boundary_are_explicit():
    first, second = event(3, "first"), event(3, "second")
    first["causes"] = [second["event_id"]]
    with pytest.raises(ForensicsError, match="not known"):
        inspect_bundle({"events_timeline": [first, second]}, first["event_id"], as_of=AsOf.before(3))
    report = inspect_bundle({"events_timeline": [first, second]}, first["event_id"], as_of=AsOf.after(3))
    assert report["diagnostics"] == [{"kind": "future_cause", "event_id": first["event_id"],
                                     "cause_id": second["event_id"]}]


def test_markdown_quotes_records_as_text_not_html_or_links(bundle):
    bundle["events_timeline"][2]["description"] = "<script>x</script> [run](https://bad)\n# Heading"
    text = render_markdown(inspect_bundle(bundle, "6:famine:0"))
    assert "<script>" not in text and "&lt;script&gt;" in text
    assert "[run](https://bad)" not in text and "\n# Heading" not in text


@pytest.mark.parametrize("hist", [
    {"plain": ["court:0"]}, {"plain": []}, {"plain": {"court:0": "1:a:0"}},
    {"chroniclers": [{"id": "court:0"}]}, {"accounts": [{}]},
    {"account_columns": ["event_id", "event_id"]}, {"archives": [1]},
    {"archives": [{"owner": "court:0", "losses": [1]}]},
])
def test_malformed_optional_tables_fail_clearly(hist, tmp_path, capsys):
    bundle = {"events_timeline": [event(1, "a")], "historiography": hist}
    with pytest.raises(ForensicsError, match="historiography"):
        inspect_bundle(bundle, "1:a:0")
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    assert main([str(path), "1:a:0"]) == 2
    assert "history-forensics:" in capsys.readouterr().err


def test_cli_writes_forwardable_reports_and_protects_source(bundle, tmp_path, capsys):
    source = tmp_path / "input.json"
    source.write_text(dumps_bundle(bundle), encoding="utf-8")
    original = source.read_bytes()
    j, md = tmp_path / "reports" / "finding.json", tmp_path / "reports" / "finding.md"
    assert main([str(source), "6:famine:0", "--as-of", "8", "--phase", "start",
                 "--format", "json", "--json", str(j), "--markdown", str(md)]) == 0
    stdout = json.loads(capsys.readouterr().out)
    assert json.loads(j.read_text()) == stdout
    assert md.read_text() == render_markdown(stdout)
    assert source.read_bytes() == original
    assert main([str(source), "6:famine:0", "--json", str(source)]) == 2
    assert "must not overwrite" in capsys.readouterr().err and source.read_bytes() == original
    assert main([str(source), "missing"]) == 2
    assert "was not found" in capsys.readouterr().err


@pytest.mark.parametrize("kwargs", [{"max_depth": -1}, {"max_nodes": 0}, {"max_edges": 0},
                                    {"max_nodes": True}, {"max_accounts": 1001}])
def test_invalid_limits_fail_clearly(kwargs):
    with pytest.raises(ForensicsError):
        Limits(**kwargs)
