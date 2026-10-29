"""Small external verifier tests; never import or run frozen project source."""

import copy
import hashlib
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import importlib.util

spec = importlib.util.spec_from_file_location("export_study_git_test", Path(__file__).resolve().parents[1] / "scripts/export_study_git.py")
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


CONTENT = b"# source fixture\n"
BLOB = hashlib.sha1(b"blob " + str(len(CONTENT)).encode() + b"\0" + CONTENT).hexdigest()
DIGEST = hashlib.sha256(CONTENT).hexdigest()
COMMIT = "1" * 40
CRATE = "2" * 40


def row(path="src/chronicler/__init__.py", *, mode="100644", kind="blob",
        blob=BLOB, size=len(CONTENT)):
    return f"{mode} {kind} {blob} {size}\t".encode() + path.encode() + b"\0"


def fixture():
    record = {"bytes": len(CONTENT), "sha256": DIGEST, "mode": 0o644, "blob": BLOB}
    return {"sha": COMMIT, "crate_tree": CRATE,
            "files": {"src/chronicler/__init__.py": record,
                      "src/chronicler/nested/part.py": dict(record),
                      "scripts/check.py": dict(record, mode=0o755),
                      "unselected.txt": dict(record)}}


class TreeParserTests(unittest.TestCase):
    def test_regular_modes_zero_bytes_and_path_with_spaces(self):
        parsed = subject._parse_tree(row() + row("scripts/with spaces.py", mode="100755", size=0))
        self.assertEqual(parsed["src/chronicler/__init__.py"]["mode"], 0o644)
        self.assertEqual(parsed["scripts/with spaces.py"]["mode"], 0o755)
        self.assertEqual(parsed["scripts/with spaces.py"]["bytes"], 0)

    def test_rejects_unsafe_or_unsupported_entries(self):
        bad = [row(mode="120000"), row(mode="160000", kind="commit"),
               row(kind="tree"), row(blob="a" * 39), row(size=-1), row(size="01x"),
               row("../escape.py"), row("/absolute.py"), row("a//b.py"),
               row("a/./b.py"), row("a/../b.py"), row("a\\b.py"), row("C:/a.py"),
               row("a\nb.py"), row()[:-1], row() + b"\0", row() + row(),
               row("a") + row("a/child.py"),
               row().replace(b"__init__", b"\xff"),
               row(size=subject.MAX_BLOB_BYTES + 1)]
        for raw in bad:
            with self.subTest(raw=raw[:100]), self.assertRaises(subject.SnapshotError):
                subject._parse_tree(raw)

    def test_rejects_complete_set_count_and_total_bytes_over_bounds(self):
        with patch.object(subject, "MAX_FILES", 1), self.assertRaises(subject.SnapshotError):
            subject._parse_tree(row("a") + row("b"))
        with patch.object(subject, "MAX_TOTAL_BYTES", len(CONTENT)), self.assertRaises(subject.SnapshotError):
            subject._parse_tree(row("a") + row("b"))


class FrozenIdentityTests(unittest.TestCase):
    def test_verification_requires_exact_complete_set_and_all_metadata(self):
        actual = fixture()
        with patch.object(subject, "snapshot", return_value=actual):
            self.assertEqual(subject.verify_snapshot(Path("unused"), copy.deepcopy(actual)), actual)
            bad = []
            missing = copy.deepcopy(actual)
            missing["files"].pop("unselected.txt")
            bad.append(missing)
            extra = copy.deepcopy(actual)
            extra["files"]["unrecorded.py"] = dict(extra["files"]["unselected.txt"])
            bad.append(extra)
            for field, value in (("sha256", "f" * 64), ("blob", "e" * 40),
                                 ("mode", 0o755), ("bytes", len(CONTENT) + 1)):
                changed = copy.deepcopy(actual)
                changed["files"]["unselected.txt"][field] = value
                bad.append(changed)
            changed_crate = copy.deepcopy(actual)
            changed_crate["crate_tree"] = "e" * 40
            bad.append(changed_crate)
            for expected in bad:
                with self.subTest(expected=expected), self.assertRaises(subject.SnapshotError):
                    subject.verify_snapshot(Path("unused"), expected)

    def test_package_digest_includes_nested_python_only_in_relative_order(self):
        source = fixture()
        expected = hashlib.sha256(
            b"__init__.py\0" + DIGEST.encode() + b"\n" +
            b"nested/part.py\0" + DIGEST.encode() + b"\n").hexdigest()
        self.assertEqual(subject.package_digest(source), expected)
        source["files"]["scripts/check.py"]["sha256"] = "f" * 64
        self.assertEqual(subject.package_digest(source), expected)
        source["files"]["src/chronicler/nested/part.py"]["sha256"] = "f" * 64
        self.assertNotEqual(subject.package_digest(source), expected)

    def test_rejects_boolean_size_or_mode_and_unknown_fields(self):
        for field, value in (("bytes", True), ("mode", True), ("extra", "value")):
            source = fixture()
            source["files"]["unselected.txt"][field] = value
            with self.subTest(field=field), self.assertRaises(subject.SnapshotError):
                subject.package_digest(source)


class FakeBatch:
    def __init__(self, _repo=None, _arguments=None, *, batch=False):
        self.finished = False
        self.sent = []
        self.raw = bytearray()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        pass

    def send(self, request):
        self.sent.append(request)
        self.raw.extend((BLOB + " blob " + str(len(CONTENT)) + "\n").encode() + CONTENT + b"\n")

    def exact(self, length):
        raw = bytes(self.raw[:length])
        del self.raw[:length]
        return raw

    def line(self):
        length = self.raw.index(10)
        return self.exact(length + 1)[:-1]

    def finish(self):
        if self.raw:
            raise subject.SnapshotError("fake trailing data")
        self.finished = True


class BlobAndViewTests(unittest.TestCase):
    def test_blob_content_hashes_and_corruption_fail_closed(self):
        process = FakeBatch()
        self.assertEqual(subject._blob(process, BLOB, len(CONTENT), collect=True), (DIGEST, CONTENT))
        self.assertEqual(process.sent, [BLOB.encode() + b"\n"])
        process = FakeBatch()
        with patch.object(process, "send", side_effect=lambda _: process.raw.extend(
                (BLOB + " blob " + str(len(CONTENT)) + "\n").encode() + b"x" * len(CONTENT) + b"\n")):
            with self.assertRaises(subject.SnapshotError):
                subject._blob(process, BLOB, len(CONTENT), collect=True)

    def test_snapshot_hashes_duplicate_blobs_once_and_keeps_complete_set(self):
        tree = subject._parse_tree(row() + row("scripts/check.py", mode="100755"))
        process = FakeBatch()
        with patch.object(subject, "_resolve_commit", return_value=COMMIT), \
                patch.object(subject, "_tree", return_value=tree), \
                patch.object(subject, "_output", side_effect=[(CRATE + "\n").encode(), b"tree\n"]), \
                patch.object(subject, "_GitIO", return_value=process):
            actual = subject.snapshot(Path("unused"), COMMIT)
        self.assertEqual(set(actual["files"]), {"src/chronicler/__init__.py", "scripts/check.py"})
        self.assertEqual(actual["files"]["scripts/check.py"]["sha256"], DIGEST)
        self.assertEqual(len(process.sent), 1)
        self.assertTrue(process.finished)

    def test_read_blob_rejects_wrong_path_and_size_before_content(self):
        tree = subject._parse_tree(row())
        with patch.object(subject, "_resolve_commit", return_value=COMMIT), \
                patch.object(subject, "_tree", return_value=tree), \
                patch.object(subject, "_GitIO", side_effect=AssertionError("must not read")):
            for path, limit in (("missing.py", len(CONTENT)), ("src/chronicler/__init__.py", 0)):
                with self.subTest(path=path), self.assertRaises(subject.SnapshotError):
                    subject.read_blob(Path("unused"), COMMIT, path, limit)

    def test_view_is_exact_readonly_and_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory(prefix="git-snapshot-test-") as temporary:
            destination = Path(temporary) / "derived"
            try:
                with patch.object(subject, "snapshot", return_value=fixture()), \
                        patch.object(subject, "_GitIO", FakeBatch):
                    written = subject.materialize_python_view(Path("unused"), COMMIT, destination,
                                                               ["scripts/check.py"])
                    self.assertEqual(set(written), {"src/chronicler/__init__.py",
                                                   "src/chronicler/nested/part.py", "scripts/check.py"})
                    actual = {path.relative_to(destination).as_posix() for path in destination.rglob("*")
                              if path.is_file()}
                    self.assertEqual(actual, set(written))
                    for path in destination.rglob("*"):
                        self.assertEqual(stat.S_IMODE(path.stat().st_mode),
                                         0o555 if path.is_dir() else 0o444)
                        if path.is_file():
                            self.assertEqual(path.read_bytes(), CONTENT)
                    self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o555)
                    with self.assertRaises(subject.SnapshotError):
                        subject.materialize_python_view(Path("unused"), COMMIT, destination, [])
            finally:
                if destination.exists():
                    for path in destination.rglob("*"):
                        path.chmod(0o700 if path.is_dir() else 0o600)
                    destination.chmod(0o700)


if __name__ == "__main__":
    unittest.main()
