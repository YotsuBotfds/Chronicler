"""Pure contracts for the fixed historical audit: no network, native import or worlds."""
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ci_duration_audit.py"
spec = importlib.util.spec_from_file_location("duration_reader", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def fixture_xml():
    return b'''<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" tests="5" failures="0" errors="0" skipped="1" time="3.25"><testcase classname="tests.test_alpha.TestOne" name="test_a[x]" time="1.250"/><testcase classname="tests.test_alpha.TestOne" name="test_b" time="0.125"><skipped type="pytest.skip" message="no optional extension"/></testcase></testsuite></testsuites>'''


def fixture_summary():
    return dict(passed=1, skipped=1, subtests=3, seconds=3.2)


def fixture_zip(entries):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries:
            archive.writestr(name, payload)
    value = raw.getvalue()
    pin = dict(archive_bytes=len(value), archive_sha=audit.sha(value), members={name for name, _ in entries})
    return value, pin


def fixture_metadata():
    run = dict(id=audit.RUN, head_sha=audit.SOURCE, run_attempt=1, status="completed",
               conclusion="success", path=".github/workflows/tests.yml",
               repository=dict(full_name=audit.REPOSITORY))
    artifacts, jobs = [], []
    for lane, pin in audit.PINS.items():
        artifacts.append(dict(id=pin["artifact"], name=pin["artifact_name"],
            size_in_bytes=pin["archive_bytes"], digest="sha256:" + pin["archive_sha"], expired=False,
            expires_at="2099-11-11T22:55:12Z", workflow_run=dict(id=audit.RUN, head_sha=audit.SOURCE)))
        steps = [dict(name=pin["test_step"], conclusion="success", started_at="2026-10-28T22:50:00Z",
                      completed_at="2026-10-28T22:56:00Z")]
        if lane == "native":
            steps.append(dict(name="Build Rust extension wheel", conclusion="success",
                started_at="2026-10-28T22:49:00Z", completed_at="2026-10-28T22:50:00Z"))
        jobs.append(dict(id=pin["job"], name=pin["job_name"], run_id=audit.RUN, run_attempt=1,
            head_sha=audit.SOURCE, status="completed", conclusion="success", steps=steps,
            started_at="2026-10-28T22:48:00Z", completed_at="2026-10-28T22:57:00Z"))
    return run, dict(total_count=2, artifacts=artifacts), dict(total_count=2, jobs=jobs)


class JUnitContracts(unittest.TestCase):
    def parse(self, raw=None, summary=None):
        return audit.parse_junit(raw or fixture_xml(), summary or fixture_summary(),
                                 {"tests.test_alpha": "tests/test_alpha.py"})

    def test_successful_subtests_reconcile_without_fabricated_duration_rows(self):
        row = self.parse()
        self.assertEqual((row["serialized_testcases"], row["junit_declared_tests"],
                          row["successful_subtests_not_serialized"]), (2, 5, 3))
        self.assertEqual(row["testcase_seconds"], 1.375)
        self.assertEqual(row["modules"][0]["seconds"], 1.375)
        self.assertEqual(row["testcases"][0]["derived_node_id"],
                         "tests/test_alpha.py::TestOne::test_a[x]")
        self.assertEqual((row["passed"], row["skipped"]), (1, 1))

    def test_duplicate_case_identities_are_retained_with_ordinals(self):
        raw = fixture_xml().replace(b'name="test_b"', b'name="test_a[x]"')
        row = self.parse(raw)
        self.assertEqual(len(row["testcases"]), 2)
        self.assertEqual({r["xml_ordinal"] for r in row["testcases"]}, {0, 1})

    def test_exact_module_prefix_chooses_longest_and_unknown_stays_unattributed(self):
        self.assertEqual(audit.module_for("tests.test_alpha.TestOne",
            {"tests": "tests.py", "tests.test_alpha": "tests/test_alpha.py"}), "tests/test_alpha.py")
        self.assertIsNone(audit.module_for("tests.test_alphabet", {"tests.test_alpha": "tests/test_alpha.py"}))
        row = self.parse(fixture_xml().replace(b"tests.test_alpha", b"unknown.classname"))
        self.assertEqual(row["unattributed_testcases"], 2)
        self.assertIsNone(row["testcases"][0]["derived_node_id"])

    def test_malformed_and_unsafe_xml_refused(self):
        payloads = [b"", b"<", b"<x/>", fixture_xml().replace(b"tests=\"5\"", b"tests=\"-1\""),
            b'<!DOCTYPE testsuites [<!ENTITY stolen SYSTEM "file:///etc/passwd">]>' + fixture_xml(),
            b'<!ENTITY x "hello">' + fixture_xml(), fixture_xml().decode().encode("utf-16"),
            fixture_xml().replace(b"utf-8", b"iso-8859-1"), fixture_xml().replace(b"test_a[x]", b"bad\x00name"),
            fixture_xml().replace(b"time=\"1.250\"", b"time=\"NaN\""),
            fixture_xml().replace(b"time=\"1.250\"", b"time=\"1e9999\""),
            fixture_xml().replace(b"time=\"1.250\"", b"time=\"-1\""),
            fixture_xml().replace(b"time=\"1.250\"", b"time=\"7201\""),
            fixture_xml().replace(b"tests=\"5\"", b"tests=\"4\""),
            fixture_xml().replace(b"failures=\"0\"", b"failures=\"1\""),
            fixture_xml().replace(b"skipped=\"1\"", b"skipped=\"0\""),
            fixture_xml().replace(b"<skipped ", b"<failure "),
            fixture_xml().replace(b"classname=\"tests.test_alpha.TestOne\"", b""),
            fixture_xml().replace(b"<testcase ", b"<wrapper><testcase ", 1).replace(b"/>", b"/></wrapper>", 1)]
        for raw in payloads:
            with self.subTest(payload=raw[:70]), self.assertRaises(audit.Refusal):
                audit.parse_junit(raw, fixture_summary(), {})

    def test_structure_and_size_bounds(self):
        raw = b"<testsuites>" + b"<x>" * 13 + b"</x>" * 13 + b"</testsuites>"
        with self.assertRaises(audit.Refusal):
            self.parse(raw)
        with patch.object(audit, "XML_LIMIT", 32), self.assertRaises(audit.Refusal):
            self.parse()

    def test_terminal_summary_handles_original_timestamp_and_ansi(self):
        raw = b"2026-10-28T23:02:39.3585518Z \x1b[32m7800 passed, 6 skipped, 526 subtests passed in 655.82s (0:10:55)\x1b[0m\n2026-10-28T23:02:47Z cleanup\n"
        self.assertEqual(audit.terminal_summary(raw), dict(passed=7800, skipped=6, subtests=526, seconds=655.82))

    def test_terminal_summary_ignores_installation_timings_in_whole_job_log(self):
        noise = (b"2026-10-28T22:49:00.1234567Z Prepared 17 packages in 1.23s\n"
                 b"2026-10-28T22:49:01.1234567Z Installed 20 packages in 1.23s\n"
                 b"2026-10-28T22:49:02.1234567Z Resolved 20 packages in 2.12s\n")
        valid = b"2026-10-28T22:55:09.9881077Z 1 passed, 1 skipped, 3 subtests passed in 3.20s\n"
        self.assertEqual(audit.terminal_summary(noise + valid + noise), fixture_summary())
        for raw in (noise, noise + b"1 failed in 1.0s\n", noise + b"1 error in 1.0s\n",
                    noise + b"1 xfailed in 1.0s\n", noise + valid + valid):
            with self.subTest(raw=raw[-120:]), self.assertRaises(audit.Refusal):
                audit.terminal_summary(raw)

    def test_terminal_failures_duplicates_and_unverified_subtests_refused(self):
        good = b"1 passed, 1 skipped, 3 subtests passed in 3.20s\n"
        for raw in (b"no terminal summary\n", good + good, b"1 failed in 1.0s\n",
                    b"1 passed, 1 passed in 1.0s\n", b"1 passed, 1 xfailed in 1.0s\n", b"\xff"):
            with self.subTest(raw=raw), self.assertRaises(audit.Refusal):
                audit.terminal_summary(raw)
        for key in ("passed", "skipped", "subtests"):
            summary = fixture_summary()
            summary[key] += 1
            with self.subTest(key=key), self.assertRaises(audit.Refusal):
                self.parse(summary=summary)


class ZipAndTransportContracts(unittest.TestCase):
    def test_zip_exact_members_and_digest(self):
        raw, pin = fixture_zip([("native.xml", fixture_xml()), ("native-identity.json", b"{}")])
        self.assertEqual(set(audit.unpack(raw, pin)), pin["members"])
        for changed in ({**pin, "archive_sha": "0" * 64}, {**pin, "archive_bytes": len(raw) + 1},
                        {**pin, "members": {"native.xml"}}):
            with self.assertRaises(audit.Refusal):
                audit.unpack(raw, changed)

    def test_zip_alias_traversal_symlink_and_extra_members_refused(self):
        for entries in ([('native.xml', b'x'), ('NATIVE.XML', b'x')],
                        [('../native.xml', b'x')], [('nested/native.xml', b'x')],
                        [('native.xml', b'x'), ('other', b'x'), ('third', b'x')]):
            raw, pin = fixture_zip(entries)
            with self.subTest(entries=entries), self.assertRaises(audit.Refusal):
                audit.unpack(raw, pin)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            row = zipfile.ZipInfo("native.xml")
            row.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(row, b"/etc/passwd")
        raw = buffer.getvalue()
        with self.assertRaises(audit.Refusal):
            audit.unpack(raw, dict(archive_bytes=len(raw), archive_sha=audit.sha(raw), members={"native.xml"}))

    def test_stream_bounds(self):
        self.assertEqual(audit.bounded_read(io.BytesIO(b"abc"), 3), b"abc")
        with self.assertRaises(audit.Refusal):
            audit.bounded_read(io.BytesIO(b"abcd"), 3)

    def test_only_api_receives_authorization_in_redirect_chain(self):
        seen = []
        class Response(io.BytesIO):
            status = 200
        class Opener:
            def open(self, request, timeout):
                seen.append(request)
                if len(seen) == 1:
                    raise HTTPError(request.full_url, 302, "redirect", {"Location": "https://example.blob.core.windows.net/evidence?signature=private"}, None)
                if len(seen) == 2:
                    raise HTTPError(request.full_url, 307, "redirect", {"Location": "https://other.blob.core.windows.net/object?signature=private2"}, None)
                return Response(b"archive")
        with patch.object(audit, "build_opener", return_value=Opener()):
            self.assertEqual(audit.fetch_fixed("/actions/artifacts/12858492130/zip", "sentinel-token", 7, True), b"archive")
        self.assertEqual(seen[0].get_header("Authorization"), "Bearer sentinel-token")
        self.assertTrue(all(request.get_header("Authorization") is None for request in seen[1:]))

    def test_unsafe_redirect_and_exception_text_never_leak(self):
        for location in ("http://example.blob.core.windows.net/a", "https://evil.example/a",
                         "https://api.github.com/a", "https://u:p@example.blob.core.windows.net/a",
                         "https://example.blob.core.windows.net:444/a"):
            opener = unittest.mock.Mock()
            opener.open.side_effect = HTTPError("https://api.github.com/fixed", 302, "secret", {"Location": location}, None)
            with self.subTest(location=location), patch.object(audit, "build_opener", return_value=opener), self.assertRaises(audit.Refusal):
                audit.fetch_fixed("/actions/jobs/123148383504/logs", "sentinel-token", 10, True)
        opener = unittest.mock.Mock()
        opener.open.side_effect = RuntimeError("signed-url-and-sentinel-token")
        with patch.object(audit, "build_opener", return_value=opener), self.assertRaises(audit.Refusal) as error:
            audit.fetch_fixed(f"/actions/runs/{audit.RUN}", "sentinel-token", 10)
        self.assertNotIn("sentinel", str(error.exception))
        with self.assertRaises(audit.Refusal):
            audit.fetch_fixed("https://evil.example", "sentinel-token", 10)


class MetadataAndOutputContracts(unittest.TestCase):
    def test_exact_metadata_and_separate_wall_clocks(self):
        clocks = audit.validate_metadata(*fixture_metadata())
        self.assertEqual(clocks["native"], dict(job_seconds=540, test_step_seconds=360, build_step_seconds=60))
        self.assertEqual(clocks["no-rust"]["build_step_seconds"], 0)

    def test_wrong_source_missing_or_expired_evidence_and_failed_jobs_refused(self):
        mutations = [lambda r,a,j: r.update(head_sha="f" * 40),
            lambda r,a,j: r.update(run_attempt=2), lambda r,a,j: a.update(total_count=3),
            lambda r,a,j: a["artifacts"][0].update(expired=True),
            lambda r,a,j: a["artifacts"][0].update(expires_at="2020-01-01T00:00:00Z"),
            lambda r,a,j: a["artifacts"][0].update(digest="sha256:" + "0" * 64),
            lambda r,a,j: a["artifacts"][0]["workflow_run"].update(id=1),
            lambda r,a,j: j["jobs"][0].update(conclusion="failure"),
            lambda r,a,j: j["jobs"][0].update(run_attempt=2),
            lambda r,a,j: j["jobs"][0]["steps"][0].update(conclusion="failure")]
        for mutate in mutations:
            data = fixture_metadata()
            mutate(*data)
            with self.subTest(mutate=mutate), self.assertRaises(audit.Refusal):
                audit.validate_metadata(*data)

    def test_native_receipt_requires_actual_frozen_source_shape(self):
        receipt = dict(source_commit=audit.SOURCE, classes=["AgentSimulator", "EcologySimulator", "PoliticsSimulator"],
                       sha256="a" * 64, compiled_extension="/tmp/native.cpython-313-x86_64-linux-gnu.so", python="3.13.9 (main)")
        self.assertEqual(audit.native_identity(json.dumps(receipt).encode()), receipt)
        for key, value in (("source_commit", "b" * 40), ("compiled_extension", "stub.py"), ("classes", []), ("python", "3.12.0")):
            with self.subTest(key=key), self.assertRaises(audit.Refusal):
                audit.native_identity(json.dumps({**receipt, key:value}).encode())

    def test_partition_does_not_drop_files_or_predict_wall_speedup(self):
        rows = [dict(module="tests/a.py", seconds=10), dict(module="tests/b.py", seconds=6),
                dict(module="tests/c.py", seconds=5), dict(module=None, seconds=2)]
        bins = audit.shard_model(rows, 2)
        self.assertEqual([b["attributed_seconds"] for b in bins], [10, 11])
        self.assertEqual(sorted(m for b in bins for m in b["modules"]), ["tests/a.py", "tests/b.py", "tests/c.py"])

    def test_main_synthetic_success_keeps_original_inputs_and_distinct_clocks(self):
        pins = {key: dict(value, passed=1, skipped=1, subtests=3) for key, value in audit.PINS.items()}
        payloads = {}
        native = dict(source_commit=audit.SOURCE, classes=["AgentSimulator", "EcologySimulator", "PoliticsSimulator"],
                      sha256="a" * 64, compiled_extension="/tmp/native.cpython-313-x86_64-linux-gnu.so", python="3.13.9 (main)")
        for lane, pin in pins.items():
            entries = [(pin["xml"], fixture_xml())]
            if lane == "native":
                entries.append(("native-identity.json", json.dumps(native).encode()))
            archive, synthetic_pin = fixture_zip(entries)
            pin.update(synthetic_pin)
            payloads[f"/actions/artifacts/{pin['artifact']}/zip"] = archive
            payloads[f"/actions/jobs/{pin['job']}/logs"] = b"1 passed, 1 skipped, 3 subtests passed in 3.20s\n"
        with patch.object(audit, "PINS", pins):
            metadata = fixture_metadata()
            for key, value in zip(("", "/artifacts?per_page=100", "/jobs?per_page=100"), metadata):
                payloads[f"/actions/runs/{audit.RUN}" + key] = json.dumps(value).encode()
            with tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                source, output = base / "source", base / "output"
                source.mkdir()
                def fixed(suffix, token, limit, redirect=False):
                    self.assertEqual(token, "sentinel-token")
                    self.assertLessEqual(len(payloads[suffix]), limit)
                    return payloads[suffix]
                with patch.dict(os.environ, GH_ARTIFACT_READ_TOKEN="sentinel-token"), \
                     patch.object(audit, "source_modules", return_value={"tests.test_alpha": "tests/test_alpha.py"}), \
                     patch.object(audit, "fetch_fixed", side_effect=fixed):
                    self.assertEqual(audit.main(["--source-root", str(source), "--output", str(output)]), 0)
                report = json.loads((output / "duration-report.json").read_text())
                receipt = json.loads((output / "audit-result.json").read_text())
                self.assertIs(receipt["complete"], True)
                self.assertEqual(len(receipt["inputs"]), 7)
                self.assertEqual(report["lanes"]["native"]["testcase_seconds"], 1.375)
                self.assertEqual(report["lanes"]["native"]["terminal_seconds"], 3.2)
                self.assertEqual(report["lanes"]["native"]["test_step_seconds"], 360)
                for name, record in {**receipt["inputs"], **receipt["outputs"]}.items():
                    raw = (output / name).read_bytes()
                    self.assertEqual(record, dict(bytes=len(raw), sha256=audit.sha(raw)))
                self.assertNotIn("sentinel-token", (output / "audit-result.json").read_text())

    def test_main_failure_retains_negative_receipt_and_pops_token(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source, output = base / "source", base / "output"
            source.mkdir()
            with patch.dict(os.environ, GH_ARTIFACT_READ_TOKEN="sentinel-token"), \
                 patch.object(audit, "source_modules", return_value={}), \
                 patch.object(audit, "fetch_fixed", side_effect=audit.Refusal("fixed API request refused")):
                self.assertEqual(audit.main(["--source-root", str(source), "--output", str(output)]), 1)
                self.assertNotIn("GH_ARTIFACT_READ_TOKEN", os.environ)
            receipt = json.loads((output / "audit-result.json").read_text())
            self.assertIs(receipt["complete"], False)
            self.assertNotIn("sentinel", json.dumps(receipt))
            with self.assertRaises(audit.Refusal):
                audit.main(["--source-root", str(source), "--output", str(output)])


if __name__ == "__main__":
    unittest.main()
