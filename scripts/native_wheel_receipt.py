"""Link a CI-built wheel to the installed native bytes; never import the runtime."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import zipfile


def _sha256(stream) -> str:
    return hashlib.file_digest(stream, "sha256").hexdigest()


def wheel_receipt(wheel_dir: Path, native_path: Path, source_commit: str) -> dict:
    """Require one wheel containing exactly the installed extension's bytes.

    The caller separately verifies the loaded compiled module and class exports.
    Inputs are the completed build's private files, not untrusted archives.
    This receipt does not certify reproducible builds or scientific reuse.
    """
    if type(source_commit) is not str or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ValueError("an exact source commit is required")
    wheels = sorted(wheel_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("expected exactly one freshly built native wheel")
    wheel = wheels[0]
    with native_path.open("rb") as stream:
        native_sha = _sha256(stream)
    with wheel.open("rb") as stream:
        wheel_sha = _sha256(stream)
    with zipfile.ZipFile(wheel) as archive:
        members = [item for item in archive.infolist()
                   if Path(item.filename).name == native_path.name]
        if len(members) != 1 or members[0].is_dir():
            raise ValueError("wheel must contain exactly one matching native member")
        member = members[0]
        with archive.open(member) as stream:
            member_sha = _sha256(stream)
        if member.file_size != native_path.stat().st_size or member_sha != native_sha:
            raise ValueError("wheel member differs from installed compiled extension")
    return {
        "schema_version": 1,
        "source_commit": source_commit,
        "wheel": {"filename": wheel.name, "bytes": wheel.stat().st_size,
                  "sha256": wheel_sha, "native_member": member.filename},
        "installed_native": {"filename": native_path.name, "bytes": member.file_size,
                             "sha256": native_sha, "wheel_member_sha256": member_sha},
        "scope": "Completed CI build identity only; no reproducibility, performance or scientific qualification",
    }
