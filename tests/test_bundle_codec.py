"""Bundle version 6: the history is written as changes between snapshots.

See src/chronicler/bundle_codec.py and docs/performance/bundle-v6.md.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import math
import gzip
import hashlib
from pathlib import Path

import pytest

from chronicler.bundle_codec import (
    BUNDLE_VERSION,
    BundleDecodeError,
    HISTORY_DELTA_KEY,
    decode_bundle,
    decode_history,
    dumps_bundle,
    encode_bundle,
    encode_history,
    is_encoded,
    load_bundle,
    same,
    archive_bundle,
)


class TestOptionalBundleArchive:
    @pytest.mark.parametrize("version", [1, 2, 3, 4, 5, 6])
    def test_old_layouts_and_number_types_survive_byte_exact_transport(self, tmp_path, version):
        bundle = {"metadata": {"bundle_version": version}, "history": [
            {"turn": 1, "values": {"integer": 0, "float": 0.0, "negative_zero": -0.0,
                                    "missing": None, "unicode": "水と木", "ordered": {"z": 1, "a": 2}}},
            {"turn": 2, "values": {"integer": 1, "float": 0.0, "negative_zero": -0.0,
                                    "missing": None, "unicode": "水と木", "ordered": {"a": 2, "z": 1}}},
        ]}
        raw = dumps_bundle(bundle) if version == 6 else json.dumps(bundle, ensure_ascii=False, indent=2)
        source, output = tmp_path / "source.json", tmp_path / "arbitrary-name.data"
        source.write_bytes((raw + "\r\n").encode())
        before = source.read_bytes()
        receipt = archive_bundle(source, output)
        assert source.read_bytes() == before
        assert gzip.decompress(output.read_bytes()) == before
        assert receipt["source_sha256"] == hashlib.sha256(before).hexdigest()
        assert receipt["archive_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
        assert receipt["source_unchanged"] and receipt["byte_exact_round_trip"]
        assert same(load_bundle(source), load_bundle(output))
        assert same(load_bundle(output), bundle)

    def test_archive_bytes_do_not_depend_on_destination_name_or_clock(self, tmp_path):
        source = tmp_path / "source.json"
        source.write_text('{"metadata":{},"history":[{"turn":0,"v":-0.0}]}')
        first, second = tmp_path / "first.json.gz", tmp_path / "different-name.gz"
        archive_bundle(source, first)
        archive_bundle(source, second)
        assert first.read_bytes() == second.read_bytes()
        assert first.read_bytes()[3] & 8 == 0  # no embedded filename
        assert first.read_bytes()[4:8] == b"\0" * 4

    def test_plain_json_does_not_need_a_json_suffix_and_is_not_reencoded(self, tmp_path):
        source = tmp_path / "misleading.json.gz"
        before = b'{ "history": [], "metadata": { "bundle_version": 5 } }\n'
        source.write_bytes(before)
        assert load_bundle(source) == {"history": [], "metadata": {"bundle_version": 5}}
        output = tmp_path / "copy.gz"
        archive_bundle(source, output)
        assert gzip.decompress(output.read_bytes()) == before

    @pytest.mark.parametrize("damage", ["truncated", "deflate", "crc"])
    def test_corrupt_archive_is_an_explicit_error_never_empty_history(self, tmp_path, damage):
        payload = gzip.compress(b'{"history":[],"metadata":{}}', mtime=0)
        if damage == "truncated":
            payload = payload[:-5]
        elif damage == "deflate":
            payload = payload[:10] + b"\xff" * 5 + payload[15:]
        else:
            payload = payload[:-8] + bytes([payload[-8] ^ 255]) + payload[-7:]
        source = tmp_path / "damaged.json"
        source.write_bytes(payload)
        with pytest.raises(BundleDecodeError, match="Could not decompress bundle"):
            load_bundle(source)

    def test_transport_preserves_existing_patch_validation_errors(self, tmp_path):
        source, output = tmp_path / "bad-patch.json", tmp_path / "bad-patch.json.gz"
        source.write_text('{"metadata":{"bundle_version":6},"history_delta":[{"turn":1},{"~l":[]}]}')
        archive_bundle(source, output)
        errors = []
        for path in (source, output):
            with pytest.raises(BundleDecodeError) as exc:
                load_bundle(path)
            errors.append(str(exc.value))
        assert errors[0] == errors[1]

    def test_existing_destination_and_original_are_never_overwritten(self, tmp_path):
        source, output = tmp_path / "source.json", tmp_path / "existing.gz"
        source.write_text('{"history":[]}')
        before = source.read_bytes()
        output.write_bytes(b"existing unrelated data")
        with pytest.raises(FileExistsError):
            archive_bundle(source, output)
        with pytest.raises(ValueError, match="different files"):
            archive_bundle(source, source)
        assert output.read_bytes() == b"existing unrelated data" and source.read_bytes() == before

    def test_archive_cli_emits_bound_receipt_and_refuses_existing_output(self, tmp_path, capsys):
        import importlib.util
        script = Path(__file__).resolve().parents[1] / "scripts" / "cw_bundle_archive.py"
        spec = importlib.util.spec_from_file_location("cw_bundle_archive_test", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        source, output = tmp_path / "source.json", tmp_path / "output.gz"
        source.write_text('{"metadata":{},"history":[]}')
        args = ["--source", str(source), "--output", str(output)]
        assert module.main(args) == 0
        receipt = json.loads(capsys.readouterr().out)
        assert receipt["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
        assert receipt["archive_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
        before = output.read_bytes()
        with pytest.raises(SystemExit) as exc:
            module.main(args)
        assert exc.value.code == 2 and "already exists" in capsys.readouterr().err
        assert output.read_bytes() == before

    def test_concurrent_destination_creation_is_refused_atomically(self, tmp_path, monkeypatch):
        import os
        source, output = tmp_path / "source.json", tmp_path / "output.gz"
        source.write_text('{"history":[]}')
        link = os.link
        def racing_link(src, dest, *args, **kwargs):
            Path(dest).write_bytes(b"concurrent owner")
            return link(src, dest, *args, **kwargs)
        monkeypatch.setattr(os, "link", racing_link)
        with pytest.raises(FileExistsError):
            archive_bundle(source, output)
        assert output.read_bytes() == b"concurrent owner"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["output.gz", "source.json"]

    def test_source_change_is_detected_without_undoing_the_other_writers_change(self, tmp_path, monkeypatch):
        source, output = tmp_path / "source.json", tmp_path / "output.gz"
        source.write_text('{"history":[]}')
        write = gzip.GzipFile.write
        changed = False
        def racing_write(self, data):
            nonlocal changed
            result = write(self, data)
            if data and not changed:
                changed = True
                source.write_bytes(b'{"history":[],"external_change":true}')
            return result
        monkeypatch.setattr(gzip.GzipFile, "write", racing_write)
        with pytest.raises(ValueError, match="source changed"):
            archive_bundle(source, output)
        assert not output.exists()
        assert source.read_bytes() == b'{"history":[],"external_change":true}'
        assert len(list(tmp_path.iterdir())) == 1

    def test_write_failure_leaves_no_partial_archive_or_source_change(self, tmp_path, monkeypatch):
        source, output = tmp_path / "source.json", tmp_path / "output.gz"
        source.write_text('{"history":[]}')
        before = source.read_bytes()
        def fail(*args, **kwargs):
            raise OSError("disk full")
        monkeypatch.setattr(gzip.GzipFile, "write", fail)
        with pytest.raises(OSError, match="disk full"):
            archive_bundle(source, output)
        assert source.read_bytes() == before and not output.exists()
        assert len(list(tmp_path.iterdir())) == 1

    @pytest.mark.parametrize("contents", [b"not JSON", b"[]", b"1"])
    def test_invalid_source_never_publishes_an_archive(self, tmp_path, contents):
        source, output = tmp_path / "source.json", tmp_path / "output.gz"
        source.write_bytes(contents)
        with pytest.raises(ValueError):
            archive_bundle(source, output)
        assert source.read_bytes() == contents and not output.exists()

    @pytest.mark.parametrize("level", [0, 10, True, 1.5])
    def test_invalid_levels_are_refused(self, tmp_path, level):
        source, output = tmp_path / "source.json", tmp_path / "output.gz"
        source.write_text('{}')
        with pytest.raises(ValueError, match="integer from 1 to 9"):
            archive_bundle(source, output, compresslevel=level)

    def test_archiving_an_archive_is_refused_without_nested_transport(self, tmp_path):
        source, output = tmp_path / "source.json.gz", tmp_path / "output.gz"
        source.write_bytes(gzip.compress(b'{}', mtime=0))
        with pytest.raises(ValueError, match="already compressed"):
            archive_bundle(source, output)
        assert not output.exists()
from chronicler.snapshot_pruning import restore_bundle

VIEWER_FIXTURES = Path(__file__).resolve().parents[1] / "viewer" / "src" / "__fixtures__"


def _text(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _round_trip(history):
    """Encode, write and read back as JSON, decode."""
    encoded = encode_history(history)
    assert encoded is not None
    return decode_history(json.loads(_text(encoded)))


def _assert_round_trip(history):
    decoded = _round_trip(history)
    assert _text(decoded) == _text(history)
    assert same(decoded, history)
    return decoded


class TestSame:
    def test_number_types_key_order_and_signed_zero(self):
        assert same({"a": 1, "b": [1.5, None]}, {"a": 1, "b": [1.5, None]})
        assert not same(1, 1.0)
        assert not same(1, True)
        assert not same({"a": 1, "b": 2}, {"b": 2, "a": 1})
        assert not same(0.0, -0.0)
        assert same(math.nan, math.nan)
        assert not same([1], (1,))


class TestPatches:
    def test_dict_changes_new_and_removed_keys(self):
        history = [
            {"turn": 1, "civ_stats": {"A": {"population": 5, "regions": ["r0"]}, "B": {"population": 3}}},
            {"turn": 2, "civ_stats": {"A": {"population": 6, "regions": ["r0"]}, "B": {"population": 3}}},
            {"turn": 3, "civ_stats": {"A": {"population": 6, "regions": ["r0"]}, "C": {"population": 1}}},
        ]
        encoded = encode_history(history)
        assert encoded[1] == {"turn": 2, "civ_stats": {"A": {"population": 6}}}
        assert encoded[2] == {"turn": 3, "civ_stats": {"C": {"population": 1}, "~d": ["B"]}}
        _assert_round_trip(history)

    def test_key_order_is_kept(self):
        history = [{"a": 1, "b": 2, "c": 3}, {"c": 3, "a": 1, "b": 2}, {"b": 2, "d": 4}, {"d": 4, "b": 2}]
        encoded = encode_history(history)
        assert encoded[1] == {"~o": ["c", "a", "b"]}
        decoded = _assert_round_trip(history)
        assert [list(s) for s in decoded] == [list(s) for s in history]

    def test_unchanged_snapshot_is_an_empty_patch(self):
        history = [{"turn": 1, "x": [1, 2]}, {"turn": 1, "x": [1, 2]}]
        assert encode_history(history)[1] == {}
        _assert_round_trip(history)

    def test_lists_grow_shrink_and_change_items(self):
        wars = [{"sponsor": "Ashkari Nomads", "target": "Vrashni Dominion", "turns_active": n} for n in range(6)]
        history = [
            {"proxy_wars": wars},
            {"proxy_wars": [dict(w, turns_active=w["turns_active"] + 1) for w in wars]},
            {"proxy_wars": [dict(w, turns_active=w["turns_active"] + 1) for w in wars[:3]]},
            {"proxy_wars": [dict(w, turns_active=w["turns_active"] + 1) for w in wars[:3]] + wars[3:]},
            {"proxy_wars": []},
        ]
        encoded = encode_history(history)
        assert encoded[1]["proxy_wars"]["~l"][0] == [0, {"turns_active": 1}]
        assert encoded[2]["proxy_wars"]["~n"] == 3
        assert "~t" in encoded[3]["proxy_wars"]
        assert encoded[4]["proxy_wars"] == []  # cheaper written whole
        _assert_round_trip(history)

    def test_type_changes(self):
        history = [
            {"a": [1, 2], "b": {"x": 1}, "c": None, "d": 1, "e": "s", "f": [3]},
            {"a": {"x": [1, 2]}, "b": [1], "c": {"y": 2}, "d": 1.0, "e": True, "f": {"~": 1}},
            {"a": [{"x": 1}], "b": None, "c": {"y": 2.0}, "d": -0.0, "e": 0.0, "f": 7},
            {"a": [{"x": 1}], "b": None, "c": {"y": 2.0}, "d": 0.0, "e": math.nan, "f": 7},
        ]
        encoded = encode_history(history)
        # A list replaced by an object is wrapped so it does not read as a list patch.
        assert encoded[1]["a"] == {"~r": {"x": [1, 2]}}
        assert encoded[1]["d"] == 1.0 and type(encoded[1]["d"]) is float
        decoded = _round_trip(history)
        assert _text(decoded) == _text(history)
        assert type(decoded[1]["d"]) is float and type(decoded[2]["c"]["y"]) is float
        assert str(decoded[2]["d"]) == "-0.0" and str(decoded[3]["d"]) == "0.0"

    def test_nested_patches_reach_the_changed_leaf(self):
        governance = {"institutions": ["a", "b"], "psi": 0.5, "legitimacy_sources": {"base": 0.5, "dynasty": 0.0}}
        history = [{"civ_stats": {"A": {"governance": copy.deepcopy(governance)}}}]
        governance["legitimacy_sources"]["dynasty"] = 0.1
        history.append({"civ_stats": {"A": {"governance": copy.deepcopy(governance)}}})
        assert encode_history(history)[1] == {"civ_stats": {"A": {"governance": {"legitimacy_sources": {"dynasty": 0.1}}}}}
        _assert_round_trip(history)

    def test_non_string_keys_are_written_as_json_keys(self):
        history = [{"m": {1: "a", 2: "b"}}, {"m": {2: "b", 3: "c"}}, {"m": {3: "c", 2: "b"}}]
        expected = json.loads(_text(history))
        decoded = decode_history(json.loads(_text(encode_history(history))))
        assert _text(decoded) == _text(expected)

    def test_proto_key_survives_json_round_trip_and_reordering(self):
        history = json.loads("""[
            {"safe": 0},
            {"safe": 1, "__proto__": {"polluted": true}},
            {"__proto__": {"polluted": false}, "safe": 1}
        ]""")

        decoded = _assert_round_trip(history)

        assert list(decoded[2]) == ["__proto__", "safe"]
        assert decoded[2]["__proto__"] == {"polluted": False}

    def test_reserved_keys_leave_the_history_whole(self):
        history = [{"turn": 1, "x": {"a": 1}}, {"turn": 2, "x": {"~d": 1}}]
        assert encode_history(history) is None
        bundle = {"world_state": {}, "history": history, "metadata": {"bundle_version": BUNDLE_VERSION}}
        written = json.loads(dumps_bundle(bundle))
        assert written["history"] == history and HISTORY_DELTA_KEY not in written
        assert decode_bundle(written) is written

    def test_empty_and_single_snapshot_histories(self):
        assert encode_history([]) == [] and decode_history([]) == []
        _assert_round_trip([{"turn": 0}])

    def test_decoded_snapshots_are_independent(self):
        history = [{"turn": t, "civ_stats": {"A": {"regions": ["r0"], "population": 5}}} for t in range(3)]
        decoded = _round_trip(history)
        decoded[1]["civ_stats"]["A"]["regions"].append("r1")
        assert decoded[0]["civ_stats"]["A"]["regions"] == ["r0"]
        assert decoded[2]["civ_stats"]["A"]["regions"] == ["r0"]


def _bundle(history, *, events=None):
    events = [{"turn": 1, "event_type": "war"}] if events is None else events
    return {
        "world_state": {"name": "W", "events_timeline": copy.deepcopy(events), "named_events": [], "turn": 3},
        "history": history,
        "pruned_civ_stats": {},
        "events_timeline": events,
        "named_events": [],
        "chronicle_entries": [],
        "era_reflections": {},
        "metadata": {"seed": 1, "generated_at": "x", "bundle_version": BUNDLE_VERSION},
    }


class TestBundle:
    HISTORY = [{"turn": t, "civ_stats": {"A": {"population": 5 + t // 2}}} for t in range(4)]

    def test_layout_and_round_trip(self):
        bundle = _bundle(copy.deepcopy(self.HISTORY))
        written = json.loads(dumps_bundle(bundle))
        assert list(written) == ["world_state", HISTORY_DELTA_KEY, *list(bundle)[2:]]
        assert written["world_state"]["events_timeline"] is None
        assert written["world_state"]["named_events"] is None
        assert is_encoded(written) and not is_encoded(bundle)
        decoded = decode_bundle(written)
        assert _text(decoded) == _text(bundle)
        # Re-encoding the decoded bundle writes the same bytes.
        assert dumps_bundle(decoded) == dumps_bundle(bundle)
        assert decode_bundle(decoded) is decoded
        # The two timelines are separate lists again.
        decoded["world_state"]["events_timeline"].append({})
        assert len(decoded["events_timeline"]) == 1

    def test_encode_does_not_change_its_input(self):
        bundle = _bundle(copy.deepcopy(self.HISTORY))
        before = _text(bundle)
        encode_bundle(bundle)
        assert _text(bundle) == before

    def test_world_state_lists_that_differ_are_kept(self):
        bundle = _bundle(copy.deepcopy(self.HISTORY))
        bundle["world_state"]["events_timeline"] = []
        written = json.loads(dumps_bundle(bundle))
        assert written["world_state"]["events_timeline"] == []
        assert written["world_state"]["named_events"] is None
        assert _text(decode_bundle(written)) == _text(bundle)

    def test_older_bundles_are_returned_as_they_are(self):
        v5 = _bundle(copy.deepcopy(self.HISTORY))
        v5["metadata"]["bundle_version"] = 5
        assert decode_bundle(v5) is v5
        assert decode_bundle([1]) == [1] and decode_bundle(None) is None

    def test_restore_bundle_decodes_first(self):
        history = [{"turn": 0, "civ_stats": {"A": {"regions": ["r"], "treasury": 1}, "B": {"regions": [], "treasury": 2}}},
                   {"turn": 1, "civ_stats": {"A": {"regions": ["r"], "treasury": 2}, "B": {"regions": [], "treasury": 2}}},
                   {"turn": 2, "civ_stats": {"A": {"regions": ["r"], "treasury": 3}}}]
        bundle = _bundle(history)
        bundle["pruned_civ_stats"] = {"B": [{"from_turn": 2, "snapshots": 1, "changes": {}}]}
        restored = restore_bundle(json.loads(dumps_bundle(bundle)))
        assert restored["history"][2]["civ_stats"]["B"] == {"regions": [], "treasury": 2}
        assert _text(restored) == _text(restore_bundle(copy.deepcopy(bundle)))

    def test_load_bundle_reads_both_layouts(self, tmp_path):
        bundle = _bundle(copy.deepcopy(self.HISTORY))
        (tmp_path / "v6.json").write_text(dumps_bundle(bundle), encoding="utf-8")
        (tmp_path / "v5.json").write_text(_text(bundle), encoding="utf-8")
        assert _text(load_bundle(tmp_path / "v6.json")) == _text(bundle)
        assert _text(load_bundle(tmp_path / "v5.json")) == _text(bundle)


# --- A real run (the bundle-size world, 60 turns, Python runtimes) -----------

def _real_run(tmp_path, monkeypatch):
    from chronicler import main as cli
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)
    assembled = {}
    write = cli.write_bundle

    def capture(bundle, path, world=None):
        # The assembled bundle as plain JSON, before the writer encodes it.
        assembled["bundle"] = json.loads(_text(bundle))
        write(bundle, path, world=world)

    monkeypatch.setattr("chronicler.main.write_bundle", capture)
    args = argparse.Namespace(seed=1, turns=60, civs=5, regions=10,
                              output=str(tmp_path / "chronicle.md"), state=str(tmp_path / "state.json"),
                              resume=None, reflection_interval=50, llm_actions=False, scenario=None,
                              pause_every=None, simulate_only=True, agents="off")
    with contextlib.redirect_stdout(io.StringIO()):
        cli.execute_run(args)
    return assembled["bundle"], tmp_path / "chronicle_bundle.json"


@pytest.fixture(scope="module")
def real_run(tmp_path_factory):
    with pytest.MonkeyPatch.context() as monkeypatch:
        return _real_run(tmp_path_factory.mktemp("delta_run"), monkeypatch)


class TestRealRun:
    def test_file_decodes_to_the_assembled_bundle(self, real_run):
        assembled, path = real_run
        text = path.read_text(encoding="utf-8")
        written = json.loads(text)
        assert written["metadata"]["bundle_version"] == BUNDLE_VERSION == 6
        assert HISTORY_DELTA_KEY in written and "history" not in written
        assert written["world_state"]["events_timeline"] is None
        decoded = decode_bundle(written)
        assert _text(decoded) == _text(assembled)
        assert dumps_bundle(decoded) == text
        assert len(text) < 0.6 * len(_text(assembled))

    def test_validation_oracles_read_identical_inputs(self, real_run, tmp_path):
        """Every bundle-reading oracle reports the same on the written file and the decoded bundle."""
        from chronicler.validate import run_oracles
        from chronicler.validation_io import load_seed_runs
        assembled, path = real_run
        reports, seed_runs = [], []
        for tag, text in (("v6", path.read_text(encoding="utf-8")), ("decoded", _text(assembled))):
            seed_dir = tmp_path / tag / "seed_1"
            seed_dir.mkdir(parents=True)
            (seed_dir / "chronicle_bundle.json").write_text(text, encoding="utf-8")
            report = run_oracles(tmp_path / tag, ["era", "arcs", "regression", "artifacts"], legacy_batch=True)
            report.pop("batch_dir")
            reports.append(report)
            seed_runs.append([{k: v for k, v in run.items() if k not in ("bundle_path", "seed_dir")}
                              for run in load_seed_runs(tmp_path / tag)])
        assert _text(seed_runs[0]) == _text(seed_runs[1])
        assert _text(reports[0]) == _text(reports[1])

    def test_live_mode_loads_the_file_decoded(self, real_run):
        from chronicler.live import _validate_legacy_live_bundle
        assembled, path = real_run
        loaded = _validate_legacy_live_bundle(json.loads(path.read_text(encoding="utf-8")))
        assert len(loaded["history"]) == len(assembled["history"])
        assert loaded["history"][-1]["turn"] == assembled["history"][-1]["turn"]
        assert loaded["world_state"]["events_timeline"] == assembled["events_timeline"]


class TestViewerFixture:
    def test_version_6_fixture_is_the_written_cities_fixture(self):
        """viewer/src/__fixtures__/cities_bundle_v6.json is what write_bundle
        writes for the cities fixture; the viewer decodes it to that fixture."""
        source = json.loads((VIEWER_FIXTURES / "cities_bundle.json").read_text(encoding="utf-8"))
        written = (VIEWER_FIXTURES / "cities_bundle_v6.json").read_text(encoding="utf-8")
        source["metadata"]["bundle_version"] = BUNDLE_VERSION
        assert dumps_bundle(source) == written
        assert _text(decode_bundle(json.loads(written))) == _text(source)


class TestScript:
    def test_convert_and_compare(self, tmp_path):
        from scripts.bundle_v6 import main
        bundle = _bundle(copy.deepcopy(TestBundle.HISTORY))
        bundle["metadata"]["bundle_version"] = 5
        base = tmp_path / "base" / "chronicle_bundle.json"
        new = tmp_path / "new" / "chronicle_bundle.json"
        for path in (base, new):
            path.parent.mkdir()
            path.write_text(_text(bundle), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            assert main(["convert", str(new.parent)]) == 0
            written = json.loads(new.read_text(encoding="utf-8"))
            assert is_encoded(written) and written["metadata"]["bundle_version"] == 6
            assert main(["compare", str(base.parent), str(new.parent)]) == 0
            written["events_timeline"][0]["turn"] = 2
            new.write_text(_text(written), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                assert main(["compare", str(base), str(new)]) == 1
        assert "/events_timeline[0]/turn" in out.getvalue()
