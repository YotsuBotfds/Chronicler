"""Pure reader contracts: synthetic files only, no worlds or native pools."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
from urllib.error import HTTPError
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/default_output_identity_reader.py"
SPEC = importlib.util.spec_from_file_location("identity_reader_contract", SCRIPT)
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def json_file(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class ReaderContracts(unittest.TestCase):
    def test_strict_json_refuses_duplicates_nonfinite_and_overflow(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":1e9999}'):
            with self.subTest(raw=raw), self.assertRaises(reader.Refusal):
                reader.strict_json(raw)

    def test_archive_roundtrip_is_exclusive_and_preserves_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / "original.zip", root / "restored"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("folder/data.json", b'{"hello":"world"}')
            raw = source.read_bytes()
            with mock.patch.multiple(reader, ARCHIVE_BYTES=len(raw), ARCHIVE_SHA=sha(raw)):
                reader.extract_archive(source, output)
                with self.assertRaises(FileExistsError):
                    reader.extract_archive(source, output)
            self.assertEqual((output / "folder/data.json").read_bytes(), b'{"hello":"world"}')
            self.assertEqual(source.read_bytes(), raw)

    def test_outer_digest_and_size_are_required_before_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "original.zip"
            source.write_bytes(b"not the registered ZIP")
            with self.assertRaises(reader.Refusal):
                reader.extract_archive(source, root / "restored")
            self.assertFalse((root / "restored").exists())

    def test_unsafe_archive_names_aliases_and_types_are_refused(self):
        names = [
            ["../escape"], ["/absolute"], ["C:/escape"], ["a\\escape"],
            ["a/./b"], ["a//b"], ["a/../b"], ["same", "same"],
            ["Same", "same"], ["file", "file/child"],
            ["File", "file/child"], ["Upper/a", "upper/b"],
        ]
        for members in names:
            with self.subTest(members=members), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "bad.zip"
                with zipfile.ZipFile(path, "w") as archive:
                    for name in members:
                        archive.writestr(name, b"x")
                with zipfile.ZipFile(path) as archive, self.assertRaises(reader.Refusal):
                    reader.archive_members(archive)
        link = zipfile.ZipInfo("link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        fake = mock.Mock()
        fake.infolist.return_value = [link]
        with self.assertRaises(reader.Refusal):
            reader.archive_members(fake)

    def test_zip_nul_truncation_is_refused_using_original_filename(self):
        item = zipfile.ZipInfo("safe\x00hidden")
        self.assertEqual(item.filename, "safe")
        fake = mock.Mock()
        fake.infolist.return_value = [item]
        with self.assertRaises(reader.Refusal):
            reader.archive_members(fake)

    def test_actions_token_is_removed_before_any_source_inspection_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = mock.Mock(control_root=str(root / "control"),
                baseline_root=str(root / "baseline"), candidate_root=str(root / "candidate"),
                archive=str(root / "original.zip"), download=False)

            def stop_before_read(*args):
                self.assertNotIn("GITHUB_TOKEN", reader.os.environ)
                raise reader.Refusal("fixture stop")

            with mock.patch.dict(reader.os.environ, {"GITHUB_TOKEN": "fixture-read-token"}), \
                 mock.patch.object(reader.sys, "version_info", (3, 13, 0)), \
                 mock.patch.object(reader.importlib.util, "find_spec", return_value=None), \
                 mock.patch.object(reader, "extract_archive", side_effect=stop_before_read):
                with self.assertRaisesRegex(reader.Refusal, "fixture stop"):
                    reader.inspect(args, root / "output")

    def test_archive_member_total_and_file_count_caps_are_independent(self):
        item = zipfile.ZipInfo("a")
        item.file_size = 3
        fake = mock.Mock()
        fake.infolist.return_value = [item]
        with mock.patch.object(reader, "MEMBER_LIMIT", 2), self.assertRaises(reader.Refusal):
            reader.archive_members(fake)
        other = zipfile.ZipInfo("b")
        other.file_size = 3
        fake.infolist.return_value = [item, other]
        with mock.patch.object(reader, "TOTAL_LIMIT", 5), self.assertRaises(reader.Refusal):
            reader.archive_members(fake)
        with mock.patch.object(reader, "FILE_LIMIT", 1), self.assertRaises(reader.Refusal):
            reader.archive_members(fake)

    def test_inventory_requires_exact_file_set_sizes_and_hashes(self):
        for mutation in ("none", "extra", "missing", "tampered"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                payload = b"original"
                (root / "data").write_bytes(payload)
                json_file(root / "result.json", {"qualified": True})
                json_file(root / "inventory.json", {"data": {"bytes": len(payload), "sha256": sha(payload)}})
                pin = sha((root / "inventory.json").read_bytes())
                if mutation == "extra":
                    (root / "extra").write_bytes(b"extra")
                elif mutation == "missing":
                    (root / "data").unlink()
                elif mutation == "tampered":
                    (root / "data").write_bytes(b"tampered")
                with mock.patch.object(reader, "INVENTORY_SHA", pin):
                    if mutation == "none":
                        self.assertEqual(set(reader.verify_inventory(root)), {"data", "inventory.json", "result.json"})
                    else:
                        with self.assertRaises(reader.Refusal):
                            reader.verify_inventory(root)

    def test_inventory_self_reference_and_invalid_records_are_refused(self):
        bad = [
            {"../escape": {"bytes": 0, "sha256": "0" * 64}},
            {"x": {"bytes": True, "sha256": "0" * 64}},
            {"x": {"bytes": 0, "sha256": "not-a-digest"}},
            {"x": {"bytes": 0, "sha256": "0" * 64, "unknown": 1}},
            {"X": {"bytes": 0, "sha256": "0" * 64}, "x": {"bytes": 0, "sha256": "0" * 64}},
        ]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(reader.Refusal):
                reader.validate_file_map(value)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            json_file(root / "inventory.json", {"result.json": {"bytes": 0, "sha256": "0" * 64}})
            with mock.patch.object(reader, "INVENTORY_SHA", sha((root / "inventory.json").read_bytes())):
                with self.assertRaises(reader.Refusal):
                    reader.verify_inventory(root)

    def result_fixture(self):
        cases = {f"case_{index}": None for index in range(9)}
        return cases, {
            "qualified": True, "baseline": reader.BASELINE, "candidate": reader.CANDIDATE,
            "inventory_sha256": reader.INVENTORY_SHA, "wheel_sha256": reader.WHEEL_SHA,
            "native_sha256": reader.NATIVE_SHA, "normalization": reader.NORMALIZATION,
            "cases": [{"arm": arm, "case": case, "status": "complete", "audit_sha256": "0" * 64}
                      for arm in ("baseline", "candidate") for case in cases],
        }

    def test_only_complete_unique_exact_eighteen_case_result_is_accepted(self):
        cases, value = self.result_fixture()
        self.assertEqual(len(reader.validate_result(value, cases)), 18)
        for mutation in ("unqualified", "boolean_alias", "source", "native", "wheel",
                         "normalization", "missing", "extra", "duplicate", "failed", "no_audit", "error"):
            changed = deepcopy(value)
            if mutation == "unqualified":
                changed["qualified"] = False
            elif mutation == "boolean_alias":
                changed["qualified"] = 1
            elif mutation in ("source", "native", "wheel", "normalization"):
                key = {"source": "candidate", "native": "native_sha256", "wheel": "wheel_sha256",
                       "normalization": "normalization"}[mutation]
                changed[key] = "wrong"
            elif mutation == "missing":
                changed["cases"].pop()
            elif mutation == "extra":
                changed["cases"].append(deepcopy(changed["cases"][0]))
            elif mutation == "duplicate":
                changed["cases"][-1] = deepcopy(changed["cases"][0])
            elif mutation == "failed":
                changed["cases"][0]["status"] = "failed"
            elif mutation == "no_audit":
                del changed["cases"][0]["audit_sha256"]
            elif mutation == "error":
                changed["error"] = "earlier failure"
            with self.subTest(mutation=mutation), self.assertRaises(reader.Refusal):
                reader.validate_result(changed, cases)

    def test_raw_case_audit_maps_cannot_ignore_extra_missing_or_changed_files(self):
        record = {"bytes": 1, "sha256": sha(b"a")}
        inventory = {"raw/baseline/case/a": record}
        self.assertEqual(reader.verify_case_file_map(inventory, {"a": record}, "baseline", "case"), {"a": record})
        for actual, audit in (
            ({**inventory, "raw/baseline/case/extra": record}, {"a": record}),
            ({}, {"a": record}),
            (inventory, {"a": {"bytes": 1, "sha256": sha(b"b")}}),
        ):
            with self.assertRaises(reader.Refusal):
                reader.verify_case_file_map(actual, audit, "baseline", "case")

    def test_comparison_requires_exact_names_counts_and_aggregate_zero(self):
        counts = {f"case_{index}": index + 1 for index in range(9)}
        good = "\n".join([f"{name}: {count} files, 0 differences" for name, count in counts.items()]
                         + ["9 cases, 45 files compared, 0 differences"]) + "\n"
        self.assertEqual(reader.parse_comparison(good, counts)["files_compared"], 45)
        for text in (
            good.replace("case_0", "unknown"), good.replace("1 files", "2 files", 1),
            good.replace("0 differences", "1 differences", 1),
            good.replace("45 files compared", "44 files compared"),
            "\n".join(good.splitlines()[1:]), good + "extra\n",
            good + "faith table: projected\n",
        ):
            with self.subTest(text=text[:80]), self.assertRaises(reader.Refusal):
                reader.parse_comparison(text, counts)

    def test_only_sole_metadata_timestamp_rule_is_accepted_by_original_helper(self):
        control = Path(__file__).resolve().parents[1]
        helper_path = control / "scripts/default_output_identity_qualification.py"
        helper, _ = reader.load_original_helper(control, reader.digest(helper_path)["sha256"])
        helper.require_stamp(b'{"metadata":{"generated_at":"now"}}')
        for raw in (
            b'{"metadata":{"generated_at":"now"},"generated_at":"other"}',
            b'{"metadata":{"generated_at":"now"},"nested":{"generated_at":"other"}}',
            b'{"metadata":{"generated_at":1}}', b'{"metadata":{}}',
        ):
            with self.subTest(raw=raw), self.assertRaises(Exception):
                helper.require_stamp(raw)
        with self.assertRaises(reader.Refusal):
            reader.load_original_helper(control, "0" * 64)

    def test_imports_do_not_write_bytecode_inside_original_source(self):
        self.assertTrue(reader.sys.dont_write_bytecode)
        with tempfile.TemporaryDirectory() as temporary:
            control = Path(temporary)
            path = control / "scripts/default_output_identity_qualification.py"
            path.parent.mkdir()
            path.write_text("VALUE = 1\n", encoding="utf-8")
            helper, _ = reader.load_original_helper(control, reader.digest(path)["sha256"])
            self.assertEqual(helper.VALUE, 1)
            self.assertFalse((path.parent / "__pycache__").exists())

    def test_download_never_forwards_api_authorization_to_storage_redirects(self):
        with tempfile.TemporaryDirectory() as temporary:
            payload = b"download fixture"
            requests = []
            opener = mock.Mock()

            def open_request(request, timeout):
                requests.append(request)
                if len(requests) == 1:
                    raise HTTPError(reader.API_URL, 302, "redirect",
                        {"Location": "https://fixture.blob.core.windows.net/object?sig=fixture"}, io.BytesIO())
                if len(requests) == 2:
                    raise HTTPError(request.full_url, 302, "redirect",
                        {"Location": "https://fixture.githubusercontent.com/object?sig=fixture"}, io.BytesIO())
                return io.BytesIO(payload)

            opener.open.side_effect = open_request
            with mock.patch.object(reader, "build_opener", return_value=opener), \
                 mock.patch.multiple(reader, ARCHIVE_BYTES=len(payload), ARCHIVE_SHA=sha(payload)):
                target = Path(temporary) / "original.zip"
                reader.download_archive(target, "fixture-read-token")
            self.assertEqual(target.read_bytes(), payload)
            self.assertEqual(requests[0].get_header("Authorization"), "Bearer fixture-read-token")
            self.assertEqual(len(requests), 3)
            self.assertTrue(all(request.get_header("Authorization") is None for request in requests[1:]))

    def test_redirect_and_network_failures_do_not_reveal_urls_or_tokens(self):
        for target in ("http://fixture.blob.core.windows.net/object", "https://example.com/object",
                       "https://token@fixture.blob.core.windows.net/object"):
            with self.subTest(target=target), self.assertRaises(reader.Refusal):
                reader._public_location(target)
        opener = mock.Mock()
        opener.open.side_effect = OSError("SECRET signed URL and token")
        with mock.patch.object(reader, "build_opener", return_value=opener), \
             tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(reader.Refusal, "^artifact download failed$"):
                reader.download_archive(Path(temporary) / "original.zip", "fixture-read-token")

    def test_compare_command_is_read_only_and_has_no_faith_projection_or_token(self):
        counts = {f"case_{index}": 1 for index in range(9)}
        text = "\n".join([f"{name}: 1 files, 0 differences" for name in counts]
                         + ["9 cases, 9 files compared, 0 differences"]) + "\n"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            candidate = output / "candidate"
            payload = output / "payload"

            def child(command, **kwargs):
                self.assertEqual(command[2], "compare")
                self.assertEqual(len(command), 5)
                self.assertNotIn("--faith-ids", command)
                self.assertNotIn("GITHUB_TOKEN", kwargs["env"])
                self.assertEqual(kwargs["env"]["LD_LIBRARY_PATH"], "/fixture/runtime/lib")
                kwargs["stdout"].write(text.encode())
                return mock.Mock(returncode=0)

            with mock.patch.object(reader.subprocess, "run", side_effect=child), \
                 mock.patch.dict(reader.os.environ, {"GITHUB_TOKEN": "fixture-read-token",
                                                       "LD_LIBRARY_PATH": "/fixture/runtime/lib"}):
                result = reader.run_compare(payload, candidate, output, counts)
            self.assertEqual(result["files_compared"], 9)

    def test_existing_output_is_refused_without_rewriting_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            marker = output / "marker"
            marker.write_bytes(b"preserve")
            with self.assertRaises(reader.Refusal):
                reader.main(["--control-root", str(output / "control"),
                             "--baseline-root", str(output / "baseline"),
                             "--candidate-root", str(output / "candidate"),
                             "--archive", str(output / "original.zip"), "--output", str(output)])
            self.assertEqual(marker.read_bytes(), b"preserve")


if __name__ == "__main__":
    unittest.main()
