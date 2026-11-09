"""Read-only preflight: what pins or names a file you plan to change, move or delete.

Before a refactor, list the paths and read the report. The tool finds what it
knows how to find and states what it cannot:

  enforced    a known check fails if the file's bytes change or the path moves:
              a byte-identical workflow copy, native-shard and oracle-chunk
              ownership of a test module, the frozen witness snapshot
              (tests/fixtures/frozen_pin_sources/), or a source-witness fixture
              (tests/fixtures/*inverse*.json) in a checkout without that snapshot.
  digest      the file's current SHA-256 or Git blob id appears in test data
              (tests/, scripts/testing/). Usually a pin; find the test that
              reads it before deciding.
  reference   text that names the path, module or script (tests, test-only
              witnesses, workflows, importers, docs). A test may read, hash or
              import it; read each hit before deciding.
  historical  a recorded hash of an older version of the file (performance and
              reference-baseline provenance), or a source witness verified
              against the frozen copy. These do not pin the current file.
              Never rewrite them to match.

"No known pins" is not proof that a change is safe: see NOT_COVERED, and run
the lanes in docs/DEVELOPMENT.md. The tool never edits, regenerates or
re-hashes anything. Source-witness fixtures and their frozen copies are history:
never edit, re-hash or regenerate them. Each report also names the identity-gate
cases (tests/fixtures/identity/coverage.json) that execute a witnessed path.

    python scripts/refactor_preflight.py src/chronicler/agent_bridge.py
    python scripts/refactor_preflight.py --move scripts/a.py:scripts/tools/a.py
    python scripts/refactor_preflight.py --git-diff origin/main --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Directories whose tracked text can enforce or reference a pin.
TEST_DIRS = ("tests", "scripts/testing")
CODE_DIRS = ("src", "scripts", "tests")
WORKFLOW_DIRS = (".github/workflows", "docs/workflows")
DOC_DIRS = ("docs",)
DOC_FILES = ("README.md", "AGENTS.md", "viewer/README.md", "scripts/README.md")
TEXT_SUFFIXES = {".py", ".json", ".md", ".yml", ".yaml", ".in", ".toml", ".txt",
                 ".ts", ".tsx", ".mjs", ".js", ".rs", ".sh", ".bat", ".cfg", ".ini"}
SKIP_PARTS = {"__pycache__", "node_modules", ".git", "dist", "target", ".venv"}
SHARD_MANIFEST = "scripts/testing/native_shards_manifest.json"
ORACLE_RUNNER = "scripts/run_python_oracle_checks.py"
FROZEN_DIR = "tests/fixtures/frozen_pin_sources"
FROZEN_MANIFEST = f"{FROZEN_DIR}/MANIFEST.json"
IDENTITY_COVERAGE = "tests/fixtures/identity/coverage.json"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

NOT_COVERED = (
    "paths built at runtime (Path segments joined with '/', f-strings, globs, rglob, os.walk)",
    "source read through inspect.getsource, ast.parse of an imported module, or __file__ arithmetic",
    "whole-tree digests recomputed at run time (native wheel receipts, benchmark source identities)",
    "TypeScript and Rust module graphs beyond literal import specifiers and `mod` lines; tsc -b and cargo check them",
    "multi-line imports outside parentheses, aliases re-exported under another name, star imports",
    "behavioral pins: golden outputs, snapshot bytes, RNG streams and checkpoint identity",
    "private archives, other branches, external repositories and published receipts",
    "identity-gate cases run only their listed switches; code reached only through other flags or modes is not compared",
)


@dataclass
class Finding:
    level: str  # enforced | digest | reference | historical
    kind: str
    where: str
    detail: str = ""


@dataclass
class Report:
    path: str
    exists: bool
    sha256: str | None
    role: str
    findings: list[Finding] = field(default_factory=list)
    identity: str | None = None

    @property
    def verdict(self) -> str:
        levels = {f.level for f in self.findings}
        if "enforced" in levels:
            return "enforced pins found: do not edit or move without the matching reviewed update"
        if "digest" in levels:
            return "current digest recorded in test data: treat as pinned until you read the test"
        if "reference" in levels:
            return "references found: review each before changing (coverage incomplete)"
        return "no known pins or references (coverage incomplete; run the lanes)"


class Repo:
    """Read-only view over a checkout. Lists files by walking, never by Git."""

    def __init__(self, root: Path):
        self.root = root
        self._cache: dict[str, str | None] = {}
        self._lists: dict[tuple[str, ...], list[str]] = {}

    def files(self, *dirs: str, suffixes: set[str] | None = None) -> list[str]:
        key = (*dirs, *sorted(suffixes or ()))
        if key not in self._lists:
            out: list[str] = []
            for d in dirs:
                base = self.root / d
                if base.is_file():
                    out.append(d)
                    continue
                if not base.is_dir():
                    continue
                for p in base.rglob("*"):
                    rel = p.relative_to(self.root)
                    if SKIP_PARTS.intersection(rel.parts) or not p.is_file():
                        continue
                    if suffixes is not None and p.suffix not in suffixes:
                        continue
                    out.append(rel.as_posix())
            self._lists[key] = sorted(set(out))
        return self._lists[key]

    def text(self, rel: str) -> str | None:
        if rel not in self._cache:
            try:
                self._cache[rel] = (self.root / rel).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                self._cache[rel] = None
        return self._cache[rel]

    def grep(self, needle: str, files: list[str], exclude: str = "", bounded: bool = False) -> list[str]:
        """Lines containing needle; bounded=True requires it not to continue a longer path."""
        pat = re.compile(rf"(?<![\w./-]){re.escape(needle)}(?![\w-])") if bounded else None
        hits = []
        for rel in files:
            if rel == exclude:
                continue
            body = self.text(rel)
            if body is None or needle not in body:
                continue
            for n, line in enumerate(body.splitlines(), 1):
                if needle in line and (pat is None or pat.search(line)):
                    hits.append(f"{rel}:{n}")
        return hits


def digests(data: bytes) -> tuple[str, str]:
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    return hashlib.sha256(data).hexdigest(), blob


def role_of(path: str) -> str:
    p = Path(path)
    if path.startswith("tests/") and (p.name.startswith("test_") or p.name.endswith("_test.py")) and p.suffix == ".py":
        return "test module"
    if path.startswith(".github/workflows/") or path.startswith("docs/workflows/"):
        return "workflow"
    if path.startswith("scripts/testing/"):
        return "test-only helper"
    if path.startswith("src/") and p.suffix == ".py":
        return "python module"
    if path.startswith("scripts/") and p.suffix == ".py":
        return "script"
    if path.startswith("chronicler-agents/") and p.suffix == ".rs":
        return "rust module"
    if path.startswith("viewer/") and p.suffix in {".ts", ".tsx"}:
        return "viewer module"
    if p.suffix == ".md":
        return "document"
    return "file"


def module_name(path: str) -> str | None:
    p = Path(path)
    if p.suffix != ".py":
        return None
    parts = list(p.with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    elif not parts or parts[0] not in ("scripts", "tests"):
        return None
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts or not all(re.fullmatch(r"[A-Za-z_]\w*", s) for s in parts):
        return None
    return ".".join(parts)


def _hash_values(value) -> list[str]:
    """Hex digests attached to one fixture entry, in any of the shapes used."""
    if isinstance(value, str):
        return [value] if HEX64.match(value) else []
    if isinstance(value, dict):
        return [v for k, v in value.items() if k in ("sha256", "current_sha256") and isinstance(v, str) and HEX64.match(v)]
    return []


def _frozen_paths(repo: Repo) -> dict[str, str]:
    """Path -> SHA-256 of each frozen witness copy (empty without a snapshot)."""
    try:
        return dict(json.loads(repo.text(FROZEN_MANIFEST) or "{}").get("files") or {})
    except json.JSONDecodeError:
        return {}


def witness_findings(repo: Repo, path: str, sha: str | None) -> list[Finding]:
    out = []
    if path.startswith(f"{FROZEN_DIR}/"):
        what = "the snapshot manifest" if path == FROZEN_MANIFEST else "a frozen witness copy"
        out.append(Finding("enforced", "frozen snapshot", FROZEN_MANIFEST,
                           f"{what}: the integrity test in tests/test_refactor_preflight.py fails on any"
                           " change; never edit, re-hash or regenerate it"))
    frozen = path in _frozen_paths(repo)
    for rel in repo.files("tests/fixtures", suffixes={".json"}):
        if "inverse" not in Path(rel).name:
            continue
        try:
            data = json.loads(repo.text(rel) or "")
        except json.JSONDecodeError:
            continue
        for section in ("files", "new_files"):
            entries = data.get(section)
            listed = (isinstance(entries, list) and path in entries) or (isinstance(entries, dict) and path in entries)
            if listed and frozen:
                out.append(Finding("historical", "frozen source witness", rel,
                                   "verified against the frozen copy; editing this file does not break it"))
            elif isinstance(entries, list) and path in entries:
                out.append(Finding("enforced", "source witness", rel,
                                   f"listed in '{section}': a projection test reads this file's exact bytes"))
            elif isinstance(entries, dict) and path in entries:
                row = entries[path]
                current = row.get("current_sha256") if isinstance(row, dict) else row
                state = ("matches the current file" if current == sha else
                         "differs from the current file: an older chained layer, checked against the"
                         " source projected through newer layers; any edit still breaks the chain")
                key = "current_sha256" if isinstance(row, dict) else "sha256"
                out.append(Finding("enforced", "source witness", rel, f"'{section}' {key} {state}"))
    return out


def json_hash_records(repo: Repo, path: str, sha: str | None, skip: set[str]) -> list[Finding]:
    """Fixture JSON that records a hash for this path (not the witness fixtures)."""
    out = []

    def walk(node, rel, trail):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == path:
                    for h in _hash_values(v):
                        if h == sha:
                            out.append(Finding("digest", "recorded hash matches current", rel,
                                               f"{trail}/{k}: treat as pinned until the reading test is found"))
                        else:
                            out.append(Finding("historical", "provenance hash", rel,
                                               f"{trail}/{k}: older version, not enforced against current source"))
                walk(v, rel, f"{trail}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, rel, f"{trail}[{i}]")

    for rel in repo.files(*TEST_DIRS, suffixes={".json"}):
        if rel in skip:
            continue
        body = repo.text(rel)
        if body is None or path not in body:
            continue
        try:
            walk(json.loads(body), rel, "")
        except json.JSONDecodeError:
            continue
    return out


def identity_line(repo: Repo, path: str, role: str) -> str | None:
    """Identity-gate cases that execute this path, from the coverage map."""
    try:
        paths = json.loads(repo.text(IDENTITY_COVERAGE) or "{}").get("paths") or {}
    except json.JSONDecodeError:
        return None
    entry = paths.get(path)
    if entry is None:
        if role in ("python module", "rust module", "script") and paths:
            return f"not mapped ({IDENTITY_COVERAGE} lists the witnessed paths only)"
        return None
    cases = entry.get("identity")
    if isinstance(cases, list) and cases:
        return ", ".join(cases)
    if cases == "tests":
        return "NO IDENTITY CASE (guarded by tests only: " + ", ".join(entry.get("tests", [])) + ")"
    return "NO IDENTITY CASE"


def literal_digest_findings(repo: Repo, path: str, sha: str, blob: str, skip: set[str]) -> list[Finding]:
    out = []
    files = [f for f in repo.files(*TEST_DIRS, suffixes=TEXT_SUFFIXES) if f not in skip and f != path]
    unchanged_since_freeze = _frozen_paths(repo).get(path) == sha
    for label, value in (("SHA-256", sha), ("Git blob id", blob)):
        for hit in repo.grep(value, files):
            detail = f"current {label} of this file appears here"
            if unchanged_since_freeze:
                detail += "; the file still equals its frozen copy, so read whether the test hashes that copy"
            out.append(Finding("digest", "literal digest", hit, detail))
    return out


def workflow_findings(repo: Repo, path: str) -> list[Finding]:
    out = []
    name = Path(path).name
    if path.startswith(".github/workflows/"):
        twin = f"docs/workflows/{name}.in"
        if (repo.root / twin).is_file():
            out.append(Finding("enforced", "workflow copy", twin, "tests pin the .yml.in copy byte for byte"))
    elif path.startswith("docs/workflows/") and name.endswith(".in"):
        twin = f".github/workflows/{name[:-3]}"
        if (repo.root / twin).is_file():
            out.append(Finding("enforced", "workflow copy", twin, "tests pin this copy byte for byte"))
    wf = repo.files(*WORKFLOW_DIRS, suffixes={".yml", ".yaml", ".in"})
    hits = repo.grep(path, wf, exclude=path, bounded=True)
    mod = module_name(path)
    if mod and mod.startswith(("chronicler.", "scripts.")):
        hits += [h for h in repo.grep(mod, wf, exclude=path) if h not in hits]
    for hit in hits:
        out.append(Finding("reference", "workflow text", hit, "a workflow names this path or module"))
    return out


def test_text_findings(repo: Repo, path: str, skip: set[str]) -> list[Finding]:
    out = []
    files = [f for f in repo.files(*TEST_DIRS, suffixes={".py"}) if f not in skip]
    hits = repo.grep(path, files, exclude=path, bounded=True)
    for hit in hits:
        kind = "witness helper" if hit.startswith("scripts/testing/") else "test names path"
        out.append(Finding("reference", kind, hit, "reads, hashes, loads or checks this path"))
    name = Path(path).name
    seen = {h.split(":")[0] for h in hits}
    if name != path and len(name) > 6:
        for hit in repo.grep(f'"{name}"', files, exclude=path) + repo.grep(f"'{name}'", files, exclude=path):
            if hit.split(":")[0] not in seen:
                out.append(Finding("reference", "test names basename", hit,
                                   "path may be assembled from segments; confirm which file it means"))
    return out


def import_findings(repo: Repo, path: str) -> list[Finding]:
    out = []
    mod = module_name(path)
    if mod:
        parent, _, leaf = mod.rpartition(".")
        pats = [re.compile(rf"^\s*(?:import|from)\s+{re.escape(mod)}(?:\s|\.|$|,)", re.M),
                re.compile(rf"""["']{re.escape(mod)}(?:\.[A-Za-z_]\w*)*["']""")]
        if parent:
            pats.append(re.compile(rf"^\s*from\s+{re.escape(parent)}\s+import\s+(?:\([^)]*\b{re.escape(leaf)}\b[^)]*\)|[^\n]*\b{re.escape(leaf)}\b)", re.M))
        for rel in repo.files(*CODE_DIRS, suffixes={".py"}):
            if rel == path:
                continue
            body = repo.text(rel)
            if body is None or leaf not in body:
                continue
            for pat in pats:
                m = pat.search(body)
                if m:
                    line = body.count("\n", 0, m.start()) + 1
                    kind = "string target" if m.group(0).lstrip()[:1] in "\"'" else "importer"
                    out.append(Finding("reference", kind, f"{rel}:{line}", f"uses {mod}"))
                    break
    p = Path(path)
    if path.startswith("chronicler-agents/src/") and p.suffix == ".rs":
        stem = p.stem if p.stem != "mod" else p.parent.name
        for rel in repo.files("chronicler-agents/src", suffixes={".rs"}):
            for hit in repo.grep(f"mod {stem};", [rel], exclude=path):
                out.append(Finding("reference", "rust mod", hit, f"declares module {stem}"))
    if path.startswith("viewer/src/") and p.suffix in {".ts", ".tsx"}:
        pat = re.compile(rf"""from\s+['"][^'"]*/{re.escape(p.stem)}(?:\.tsx?)?['"]|import\(\s*['"][^'"]*/{re.escape(p.stem)}(?:\.tsx?)?['"]""")
        for rel in repo.files("viewer/src", suffixes={".ts", ".tsx"}):
            if rel == path:
                continue
            body = repo.text(rel) or ""
            m = pat.search(body)
            if m:
                out.append(Finding("reference", "viewer import", f"{rel}:{body.count(chr(10), 0, m.start()) + 1}",
                                   f"imports a module named {p.stem}; confirm it resolves here"))
    return out


def manifest_findings(repo: Repo, path: str) -> list[Finding]:
    out = []
    if role_of(path) != "test module":
        return out
    try:
        manifest = json.loads(repo.text(SHARD_MANIFEST) or "{}")
    except json.JSONDecodeError:
        manifest = {}
    owner = next((s for s, names in (manifest.get("shards") or {}).items() if path in names), None)
    if owner is not None:
        out.append(Finding("enforced", "native shard owner", SHARD_MANIFEST,
                           f"assigned to shard {owner}; moving or deleting it must update the manifest"))
    elif (repo.root / path).exists():
        out.append(Finding("enforced", "native shard owner", SHARD_MANIFEST,
                           "not assigned: test_native_ci_shards requires every test module in exactly one shard"))
    skips = [n for n in manifest.get("expected_skips", []) if n.split("::", 1)[0] == path]
    if skips:
        out.append(Finding("enforced", "expected skips", SHARD_MANIFEST,
                           f"{len(skips)} expected skip node IDs name this module"))
    for hit in repo.grep(f'"{path}', [ORACLE_RUNNER]):
        out.append(Finding("enforced", "oracle chunk", hit, "the bounded offline lane selects this module"))
    return out


def doc_findings(repo: Repo, path: str) -> list[Finding]:
    docs = repo.files(*DOC_DIRS, suffixes={".md"}) + [d for d in DOC_FILES if (repo.root / d).is_file()]
    hits = repo.grep(path, sorted(set(docs)), exclude=path, bounded=True)
    if not hits:
        return []
    files = sorted({h.split(":")[0] for h in hits})
    return [Finding("reference", "docs", f"{len(files)} documents",
                    f"name the path ({len(hits)} lines), e.g. {', '.join(files[:3])}; dated records keep old paths, current guides need updates")]


def analyse(repo: Repo, path: str) -> Report:
    path = Path(path).as_posix()
    while path.startswith("./"):
        path = path[2:]
    target = repo.root / path
    exists = target.is_file()
    sha = blob = None
    if exists:
        sha, blob = digests(target.read_bytes())
    report = Report(path=path, exists=exists, sha256=sha, role=role_of(path))
    witness_files = {f for f in repo.files("tests/fixtures", suffixes={".json"}) if "inverse" in Path(f).name}
    witness_files |= set(repo.files(FROZEN_DIR))  # the manifest and copies record frozen bytes, not current pins
    report.findings += witness_findings(repo, path, sha)
    report.findings += manifest_findings(repo, path)
    report.findings += workflow_findings(repo, path)
    if exists:
        report.findings += literal_digest_findings(repo, path, sha, blob, witness_files)
    records = json_hash_records(repo, path, sha, witness_files)
    recorded = {f.where for f in records if f.level == "digest"}
    report.findings = [f for f in report.findings
                       if not (f.kind == "literal digest" and f.where.split(":")[0] in recorded)]
    report.findings += records
    report.findings += test_text_findings(repo, path, {SHARD_MANIFEST})
    report.findings += import_findings(repo, path)
    report.findings += doc_findings(repo, path)
    report.identity = identity_line(repo, path, report.role)
    return report


def paths_from_git_diff(root: Path, base: str) -> list[tuple[str, str | None]]:
    """(path, moved_to) pairs from `git diff --name-status -M base`."""
    out = subprocess.run(["git", "-C", str(root), "diff", "--name-status", "-M", base],
                         check=True, capture_output=True, text=True).stdout
    pairs = []
    for line in out.splitlines():
        cols = line.split("\t")
        if cols[0].startswith("R") and len(cols) == 3:
            pairs.append((cols[1], cols[2]))
        elif len(cols) >= 2:
            pairs.append((cols[-1], None))
    return pairs


def render(reports: list[Report], moves: dict[str, str]) -> str:
    lines = []
    for r in reports:
        state = "" if r.exists else " (absent in this checkout)"
        lines.append(f"{r.path}  [{r.role}]{state}")
        if r.path in moves:
            lines.append(f"  move to {moves[r.path]}: keep every importer, test and workflow path below working")
        order = {"enforced": 0, "digest": 1, "reference": 2, "historical": 3}
        for f in sorted(r.findings, key=lambda f: (order[f.level], f.kind, f.where)):
            lines.append(f"  {f.level.upper():<10} {f.kind}: {f.where}" + (f"  ({f.detail})" if f.detail else ""))
        if r.identity is not None:
            lines.append(f"  identity gate: {r.identity}")
        lines.append(f"  verdict: {r.verdict}")
        lines.append("")
    lines.append("Not covered by this tool (check these by reading and by running the lanes):")
    lines += [f"  - {item}" for item in NOT_COVERED]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="Levels: enforced, reference, historical. See docs/DEVELOPMENT.md.")
    parser.add_argument("paths", nargs="*", help="repository-relative paths you plan to change or delete")
    parser.add_argument("--move", action="append", default=[], metavar="OLD:NEW",
                        help="a planned move; reports on OLD (what must keep working) and NEW")
    parser.add_argument("--git-diff", metavar="BASE", help="also check every path changed since BASE (renames included)")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--fail-on-enforced", action="store_true",
                        help="exit 1 when any path has an enforced pin or a recorded current digest")
    args = parser.parse_args(argv)

    moves: dict[str, str] = {}
    targets: list[str] = list(args.paths)
    for spec in args.move:
        old, sep, new = spec.partition(":")
        if not sep or not old or not new:
            parser.error(f"--move expects OLD:NEW, got {spec!r}")
        moves[old] = new
        targets += [old, new]
    if args.git_diff:
        for old, new in paths_from_git_diff(args.root, args.git_diff):
            targets.append(old)
            if new:
                moves[old] = new
                targets.append(new)
    if not targets:
        parser.error("name at least one path, --move or --git-diff")
    repo = Repo(args.root.resolve())
    seen: set[str] = set()
    reports = []
    for t in targets:
        if t not in seen:
            seen.add(t)
            reports.append(analyse(repo, t))
    if args.json:
        print(json.dumps({"root": str(repo.root), "moves": moves, "not_covered": list(NOT_COVERED),
                          "reports": [{**asdict(r), "verdict": r.verdict} for r in reports]}, indent=2))
    else:
        print(render(reports, moves))
    enforced = any(f.level in ("enforced", "digest") for r in reports for f in r.findings)
    return 1 if args.fail_on_enforced and enforced else 0


if __name__ == "__main__":
    sys.exit(main())
