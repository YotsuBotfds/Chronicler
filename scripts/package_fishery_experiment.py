"""Create and verify a scoped local backup of the committed fishery branch.

Includes changed tracked source/evidence, a baseline patch, and an incremental
Git bundle requiring edf7299. Excludes workspaces, credentials, caches and binaries.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile

BASELINE = "edf72991cad58d6670b1f382c33d50d903a6054a"
BRANCH = "experiment/ecology-fishery-stock"
PREFIXES = ("src/chronicler/", "chronicler-agents/src/ffi/", "tests/", "scripts/", "docs/experiments/")
EXTENSIONS = {".py", ".rs", ".md", ".json", ".txt"}


def package(root: Path, output: Path) -> dict:
    root, output = root.resolve(), output.absolute()

    def git(*arguments):
        return subprocess.check_output(["git", "-C", str(root), *arguments])

    if git("branch", "--show-current").decode().strip() != BRANCH:
        raise ValueError(f"package only from {BRANCH}")
    if git("status", "--porcelain").strip():
        raise ValueError("commit and clean the worktree before creating the backup")
    subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", BASELINE, "HEAD"], check=True)
    head = git("rev-parse", "HEAD").decode().strip()
    changed = [name.decode() for name in git("diff", "--name-only", "-z", BASELINE, head).split(b"\0") if name]
    commits = git("rev-list", "--reverse", f"{BASELINE}..{head}").decode().splitlines()

    def safe_path(name):
        path = PurePosixPath(name)
        return (not path.is_absolute() and ".." not in path.parts and name.startswith(PREFIXES)
                and path.suffix in EXTENSIONS and not any(part.startswith(".") for part in path.parts))

    # The bundle carries intermediate commits too. Reject hidden/deleted paths
    # that are absent from the final reviewed delta, and reject nonregular modes.
    previous = BASELINE
    for commit in commits:
        parents = git("rev-list", "--parents", "-n", "1", commit).decode().split()[1:]
        if parents != [previous]:
            raise ValueError("backup history must be a linear isolated branch from the baseline")
        records = git("diff-tree", "--no-commit-id", "--no-renames", "--raw", "-z", "-r", commit).split(b"\0")
        for index in range(0, len(records) - 1, 2):
            header, name = records[index].decode(), records[index + 1].decode()
            old_mode, new_mode = header.lstrip(":").split()[:2]
            if (name not in changed or not safe_path(name)
                    or old_mode not in {"000000", "100644", "100755"}
                    or new_mode not in {"000000", "100644", "100755"}):
                raise ValueError(f"intermediate history outside reviewed regular-file scope: {name}")
        previous = commit
    payload = {}
    for name in changed:
        path = PurePosixPath(name)
        source = root / name
        if not safe_path(name) or source.is_symlink() or not source.is_file():
            raise ValueError(f"changed path outside safe fishery backup scope: {name}")
        payload[f"files/{name}"] = source.read_bytes()
    payload["patches/fishery-stock-from-edf7299.patch"] = git("diff", "--binary", BASELINE, head)
    with tempfile.TemporaryDirectory(prefix="fishery-bundle-") as directory:
        bundle = Path(directory) / "fishery-stock.bundle"
        subprocess.run(["git", "-C", str(root), "bundle", "create", str(bundle), "HEAD", f"^{BASELINE}"], check=True)
        subprocess.run(["git", "-C", str(root), "bundle", "verify", str(bundle)], check=True, capture_output=True)
        payload["commits/fishery-stock.bundle"] = bundle.read_bytes()
    payload["TRANSFER.md"] = (
        f"# Local fishery experiment backup\n\n"
        f"Branch: `{BRANCH}`\n\nCommit: `{head}`\n\nRequired public baseline: `{BASELINE}`\n\n"
        "This is an incremental experiment backup, not a full repository or runtime backup.\n"
        "It contains a manifest, changed tracked files, a Git patch, and an incremental commit bundle.\n"
        "Use a clean isolated checkout with the required baseline present. To inspect/import the\n"
        "commits without changing a default branch, verify the bundle and fetch its HEAD into a\n"
        "new local experiment ref. Alternatively review/apply the patch to an isolated baseline\n"
        "checkout. Copying the `files/` tree over that baseline also restores changed files.\n"
        "Keep the archived prior evidence unchanged. Rebuild the native extension in the receiving\n"
        "environment; compiled binaries and native runtime state are deliberately absent.\n"
        "Verify payload SHA-256 digests against MANIFEST.json before applying anything.\n"
        "No default promotion, public push, upload, or full hybrid continuation is authorized.\n"
        "\nExample from the receiving isolated checkout with edf7299 present:\n\n"
        "```bash\n"
        "git bundle verify /path/to/commits/fishery-stock.bundle\n"
        "git fetch /path/to/commits/fishery-stock.bundle HEAD:refs/heads/experiment/fishery-restored\n"
        "git switch experiment/fishery-restored\n"
        "```\n"
    ).encode()
    entries = [{"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
               for name, data in sorted(payload.items())]
    manifest = {
        "format": "chronicler-fishery-scoped-backup-v1", "branch": BRANCH, "commit": head,
        "required_baseline": BASELINE, "commits": commits,
        "changed_tracked_paths": changed, "incremental_bundle_verified": True,
        "intermediate_history_scope_verified": True, "payload": entries,
        "excluded": [".git directory/config", "untracked files", "credentials and security files", ".env",
                     ".venv", "compiled binaries", "toolchains", "caches", "unrelated branches/history"],
        "scope": "Committed fishery code, fixtures, interface and earlier/new validation evidence only; local archive, no upload",
        "continuation": "Python controlled-phase continuation tested; native agent/RNG/cargo/delivery continuation unvalidated",
    }
    payload["MANIFEST.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    archive_prefix = f"fishery-stock-{head[:12]}"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for name, data in sorted(payload.items()):
            entry = tarfile.TarInfo(f"{archive_prefix}/{name}")
            entry.size, entry.mode, entry.mtime = len(data), 0o644, 0
            entry.uid = entry.gid = 0
            archive.addfile(entry, io.BytesIO(data))
    checksum_path = output.with_suffix(output.suffix + ".sha256")
    manifest_path = output.with_suffix(".manifest.json")
    for path in (output, checksum_path, manifest_path):
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"refusing to overwrite existing backup output: {path}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            zipped.write(buffer.getvalue())

    # Inspect without extraction: regular entries only; no absolute/traversal names.
    with tarfile.open(output, "r:gz") as archive:
        expected = {f"{archive_prefix}/{name}": data for name, data in payload.items()}
        members = archive.getmembers()
        if {member.name for member in members} != expected.keys() or len(members) != len(expected):
            raise AssertionError("archive membership mismatch")
        for member in members:
            path = PurePosixPath(member.name)
            if not member.isfile() or path.is_absolute() or ".." in path.parts:
                raise AssertionError("unsafe archive member")
            if archive.extractfile(member).read() != expected[member.name]:
                raise AssertionError("archive payload mismatch")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    with checksum_path.open("x") as handle:
        handle.write(f"{digest}  {output.name}\n")
    with manifest_path.open("x") as handle:
        handle.write(json.dumps(manifest, indent=2) + "\n")
    return {"archive": str(output), "archive_sha256": digest, "manifest": str(manifest_path),
            "member_count": len(payload), "changed_file_count": len(changed),
            "archive_bytes": output.stat().st_size, "payload_verified": True,
            "incremental_bundle_verified": True, "intermediate_history_scope_verified": True, "commit": head}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(package(root, args.output), indent=2))


if __name__ == "__main__":
    main()
