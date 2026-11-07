"""Construct a labelled visibility demonstration; never rerun the simulation.

PYTHONPATH=src python reproduce.py --source RAW/chronicle_bundle.json --out OUT
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from chronicler.bundle_codec import dumps_bundle, load_bundle, same
from chronicler.narration_audit import audit_bundle
from chronicler.narration_provenance import livelihood_fact_id, resolve_record_pointer

EXPECTED = "f6cb5562a4aaec888b6f2a03b4c4b01bd1e8d49737aec22673034eba30ce0ee2"


def at(document, pointer):
    value = document
    for key in pointer.strip("/").split("/"):
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def put(document, pointer, value):
    parent, key = pointer.rsplit("/", 1)
    target = at(document, parent)
    target[int(key) if isinstance(target, list) else key] = value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    output = (args.out / "chronicle_bundle.json").resolve()
    if output == source:
        raise SystemExit("Refusing to overwrite the natural source")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if source_hash != EXPECTED:
        raise SystemExit("This demonstration requires the exact accepted natural bundle")
    bundle = load_bundle(source)
    if bundle.get("metadata", {}).get("constructed") is not None:
        raise SystemExit("The source must be the unchanged natural bundle")
    changes = [
        {"op": "replace", "path": "/history/26/livelihoods/recovery_crews/receipts/0/members/0/income_replaced",
         "before": 0.09490852802991867, "after": None},
        {"op": "replace", "path": "/history/26/livelihoods/adaptive_livelihoods/frame/work/0/withheld_milli",
         "before": 95, "after": None},
        {"op": "replace", "path": "/history/26/livelihoods/adaptive_livelihoods/frame/work/0/source",
         "before": "recovery_crews:individual wage + keyed paid-work receipt",
         "after": "constructed demonstration: actual saved wage retained; personal income-cost observation deliberately redacted"},
    ]
    assert at(bundle, "/history/26/turn") == 27
    assert at(bundle, "/history/26/livelihoods/recovery_crews/receipts/0/members/0/agent_id") == 13
    assert at(bundle, "/history/26/livelihoods/adaptive_livelihoods/frame/work/0/id") == 13
    assert at(bundle, "/history/26/livelihoods/adaptive_livelihoods/frame/work/0/net_milli") is None
    assert at(bundle, "/history/26/livelihoods/adaptive_livelihoods/frame/work/0/paid_milli") == 2000
    for change in changes:
        assert at(bundle, change["path"]) == change["before"], change["path"]
        put(bundle, change["path"], change["after"])
    marker = {"from": source_hash, "edits": [
        "Constructed visibility demonstration: at snapshot 27, person 13's PL3 income_replaced observation is redacted from 0.09490852802991867 to null. The saved 2.000-coin wage remains observed.",
        "The matching A6 work receipt's withheld_milli is redacted from 95 to null and source explicitly labels this edit. Its dependent net_milli remains null, never an invented zero or profit.",
        "No simulation was rerun. Cash, cargo, work, aggregate accounting and every other saved observation are unchanged. This copy demonstrates unknown personal cost, not natural activation or a policy effect.",
    ]}
    bundle["metadata"]["constructed"] = marker
    output.write_text(dumps_bundle(bundle), encoding="utf-8")
    decoded = load_bundle(output)
    assert decoded["metadata"]["constructed"] == marker
    for change in changes:
        assert at(decoded, change["path"]) == change["after"]
        put(decoded, change["path"], change["before"])
    del decoded["metadata"]["constructed"]
    assert same(decoded, load_bundle(source)), "Unexpected dependent-data changes"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    manifest = {"kind": "constructed_visibility_demonstration", "source": str(source),
        "source_sha256": source_hash, "source_unchanged": True,
        "derived": str(output), "derived_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "derived_bytes": output.stat().st_size, "edits": changes,
        "metadata_constructed": marker, "undo_exact_edits_matches_decoded_source": True,
        "coherence": "Only individual observation visibility is redacted in PL3 and matching A6; dependent A6 net stays unknown. Actual cash/work/cargo and aggregate observations are preserved.",
        "simulation_rerun": False, "paid_narration_calls": 0}
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    examples = []
    for package, fields in (("recovery_crews", ("receipts", 0, "members", 0)),
                            ("adaptive_livelihoods", ("frame", "work", 0))):
        fact = livelihood_fact_id(27, package, *fields)
        resolved = resolve_record_pointer(bundle, fact)
        assert resolved is not None and resolved.source_turn == 26
        text = "Constructed illustration at snapshot 27 records " + json.dumps(resolved.value, sort_keys=True) + "."
        entry = {"narrative": text, "provenance": {"v": 1, "narrator": "mechanical", "as_of": 26,
                 "facts": [fact], "names": [], "spans": [[0, len(text), [fact]]]}}
        examples.append({"fact_id": fact, "pointer": resolved.pointer, "source_turn": 26,
                         "values": resolved.value, "story_entry": entry})
    audit = audit_bundle({**bundle, "chronicle_entries": [e["story_entry"] for e in examples]}).to_dict()
    assert not audit["flags"]
    (args.out / "edited-provenance.json").write_text(json.dumps({"constructed": marker,
        "bundle_sha256": manifest["derived_sha256"], "examples": examples, "story_audit": audit}, indent=2) + "\n")
    print(json.dumps({k: manifest[k] for k in ("source_sha256", "derived_sha256", "derived_bytes", "source_unchanged")}))


if __name__ == "__main__":
    main()
