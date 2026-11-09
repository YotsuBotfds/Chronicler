"""Read-only, policy-pinned experiment admission, independent of scientific gates.

The evidence manifest is frozen before review. Receipts form a separate acyclic
chain, hashing that manifest and preceding receipts; they never hash themselves.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import itertools
import os
import re
import subprocess
import sys
from decimal import Decimal, DecimalException, localcontext
from pathlib import Path, PurePosixPath
from typing import Any

from chronicler.artifact_io import strict_json_dumps, strict_json_loads


class AdmissionError(ValueError):
    """Invalid or inadmissible evidence. No repair is performed."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AdmissionError(message)


def _object(value: Any, keys: set[str], label: str) -> dict:
    _require(isinstance(value, dict), f"{label}: expected object")
    _require(set(value) == keys, f"{label}: expected keys {sorted(keys)}")
    return value


def _hash(value: Any, label: str, length: int = 64) -> str:
    _require(isinstance(value, str) and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None,
             f"{label}: expected full lowercase hash ({length} characters)")
    return value


def _name(value: Any, label: str) -> str:
    _require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value) is not None,
             f"{label}: expected nonempty identifier")
    return value


def _integers(value: Any, label: str) -> list[int]:
    _require(isinstance(value, list) and bool(value), f"{label}: expected nonempty list")
    _require(all(type(v) is int and v >= 0 for v in value), f"{label}: expected nonnegative integers")
    _require(len(set(value)) == len(value), f"{label}: duplicate values")
    return value


def _relative(value: Any) -> str:
    _require(isinstance(value, str) and bool(value), "path: expected nonempty relative path")
    path = PurePosixPath(value)
    _require(not path.is_absolute() and '..' not in path.parts and str(path) == value
             and '\\' not in value and ':' not in value and '\x00' not in value and value != '.',
             f"unsafe or noncanonical path: {value!r}")
    return value


def _member_path(root: Path, name: str) -> Path:
    path = root / _relative(name)
    cursor = root
    for part in PurePosixPath(name).parts:
        cursor = cursor / part
        _require(not cursor.is_symlink(), f"member symlink forbidden: {name}")
    _require(path.is_file(), f"missing member: {name}")
    _require(path.resolve().is_relative_to(root.resolve()), f"member escapes root: {name}")
    return path


def _json(raw: bytes, label: str) -> dict:
    try:
        value = strict_json_loads(raw.decode('utf-8'), label=label)
    except (UnicodeError, ValueError) as exc:
        raise AdmissionError(f"{label}: {exc}") from exc
    _require(isinstance(value, dict), f"{label}: expected JSON object")
    return value


def _decimal(value: Any, label: str) -> Decimal:
    _require(isinstance(value, str) and bool(value) and value.strip() == value,
             f"{label}: expected explicit numeric text")
    _require(len(value) <= 8192, f'{label}: unsupported numeric text size')
    # Decimal accepts underscores and noncanonical whitespace; CSV numbers do not.
    _require(re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value) is not None,
             f"{label}: undefined or invalid number {value!r}")
    try:
        number = Decimal(value)
    except DecimalException as exc:
        raise AdmissionError(f"{label}: invalid decimal") from exc
    _require(number.is_finite(), f"{label}: nonfinite number")
    _require(len(number.as_tuple().digits) <= 4096 and abs(number.as_tuple().exponent) <= 4096,
             f'{label}: unsupported numeric size (4096 digit/exponent limit)')
    return number


def _source_spec(source: Any, label: str) -> dict:
    source = _object(source, {'commit', 'tree', 'files', 'checkout'}, label)
    _hash(source['commit'], f'{label}.commit', 40)
    _hash(source['tree'], f'{label}.tree', 40)
    _require(source['checkout'] in ('live', 'frozen'), f'{label}.checkout: expected live or frozen')
    _require(isinstance(source['files'], dict) and bool(source['files']), f'{label}.files: expected nonempty hash map')
    for name, digest in source['files'].items():
        _relative(name)
        _hash(digest, f'{label}.files.{name}')
    return source


def _table_spec(spec: Any) -> dict:
    spec = _object(spec, {'columns', 'counts', 'ratios'}, 'table')
    columns = spec['columns']
    _require(isinstance(columns, list) and len(columns) >= 3, 'table.columns: expected seed, turn and metrics')
    for column in columns:
        _name(column, 'column')
    _require(columns[:2] == ['seed', 'turn'] and len(set(columns)) == len(columns),
             'table.columns: start with seed, turn; no duplicates')
    counts = spec['counts']
    _require(isinstance(counts, list) and all(isinstance(v, str) for v in counts) and len(set(counts)) == len(counts)
             and set(counts) <= set(columns[2:]), 'table.counts: expected unique metric columns')
    _require(isinstance(spec['ratios'], list), 'table.ratios: expected list')
    ratio_columns = []
    for ratio in spec['ratios']:
        _object(ratio, {'column', 'numerator', 'denominator', 'absolute_tolerance'}, 'ratio')
        _require(all(isinstance(ratio[key], str) and ratio[key] in columns[2:]
                     for key in ('column', 'numerator', 'denominator')), 'ratio: unknown metric column')
        _require(len({ratio['column'], ratio['numerator'], ratio['denominator']}) == 3,
                 'ratio: column and operands must differ')
        _require(_decimal(ratio['absolute_tolerance'], 'ratio.absolute_tolerance') >= 0,
                 'ratio: negative tolerance')
        ratio_columns.append(ratio['column'])
    _require(len(set(ratio_columns)) == len(ratio_columns), 'ratio: duplicate ratio column')
    return spec


def _review_tiers(tiers: Any) -> list[str]:
    _require(isinstance(tiers, list) and len(tiers) >= 2, 'review_tiers: at least two independent tiers required')
    for tier in tiers:
        _name(tier, 'review tier')
    _require(len(set(tiers)) == len(tiers), 'review_tiers: duplicate tiers')
    return tiers


def validate_policy(policy: dict) -> None:
    _object(policy, {'schema_version', 'lane', 'baseline_domain', 'runs', 'original_baseline', 'review_tiers'}, 'policy')
    _require(type(policy['schema_version']) is int and policy['schema_version'] == 1, 'policy: unsupported schema')
    _name(policy['lane'], 'lane')
    _name(policy['baseline_domain'], 'baseline_domain')
    runs = policy['runs']
    _require(isinstance(runs, dict) and bool(runs), 'policy.runs: expected nonempty object')
    for run_id, run in runs.items():
        _name(run_id, 'run_id')
        _object(run, {'source', 'native_sha256', 'config_sha256', 'seeds', 'checkpoints', 'table'}, f'policy.{run_id}')
        _source_spec(run['source'], f'{run_id}.source')
        _hash(run['native_sha256'], f'{run_id}.native_sha256')
        _hash(run['config_sha256'], f'{run_id}.config_sha256')
        _integers(run['seeds'], f'{run_id}.seeds')
        _integers(run['checkpoints'], f'{run_id}.checkpoints')
        _table_spec(run['table'])
    original = _object(policy['original_baseline'], {'run', 'sha256'}, 'original_baseline')
    _require(isinstance(original['run'], str) and original['run'] in runs, 'original_baseline: unknown run')
    _hash(original['sha256'], 'original_baseline.sha256')
    _review_tiers(policy['review_tiers'])


def validate_table(raw: bytes, spec: dict, seeds: list[int], checkpoints: list[int], label: str) -> dict:
    """Validate an exact seed/checkpoint grid, finite metrics and defined ratios."""
    _table_spec(spec)
    _integers(seeds, 'table seeds')
    _integers(checkpoints, 'table checkpoints')
    try:
        rows = csv.reader(io.StringIO(raw.decode('utf-8'), newline=''), strict=True)
        _require(next(rows, None) == spec['columns'], f'{label}: altered or missing CSV header')
        result = {}
        for line, values in enumerate(rows, 2):
            _require(len(values) == len(spec['columns']), f'{label}:{line}: missing or extra columns')
            for value in values[:2]:
                _require(re.fullmatch(r'0|[1-9][0-9]*', value) is not None,
                         f'{label}:{line}: noncanonical seed/turn')
                _require(len(value) <= 4096, f'{label}:{line}: unsupported seed/turn size')
            try:
                key = (int(values[0]), int(values[1]))
            except ValueError as exc:
                raise AdmissionError(f'{label}:{line}: seed/turn exceeds interpreter integer limit') from exc
            _require(key not in result, f'{label}:{line}: duplicate seed/checkpoint {key}')
            numbers = {name: _decimal(value, f'{label}:{line}:{name}')
                       for name, value in zip(spec['columns'][2:], values[2:])}
            for name in spec['counts']:
                number = numbers[name]
                _require(number >= 0 and number == number.to_integral_value(), f'{label}:{line}:{name}: invalid count')
            for ratio in spec['ratios']:
                numerator = numbers[ratio['numerator']]
                denominator = numbers[ratio['denominator']]
                _require(denominator != 0, f'{label}:{line}:{ratio["column"]}: undefined ratio (zero denominator)')
                # Compare cross-products rather than rounding division, preserving
                # the trusted absolute tolerance including exact zero tolerance.
                digits = sum(len(n.as_tuple().digits) + abs(n.as_tuple().exponent)
                             for n in (numerator, denominator, numbers[ratio['column']]))
                tolerance = _decimal(ratio['absolute_tolerance'], 'ratio tolerance')
                with localcontext() as context:
                    context.prec = max(50, digits + len(tolerance.as_tuple().digits) + abs(tolerance.as_tuple().exponent) + 10)
                    context.Emax = 100000
                    context.Emin = -100000
                    error = abs(numbers[ratio['column']] * denominator - numerator)
                    _require(error <= tolerance * abs(denominator), f'{label}:{line}:{ratio["column"]}: ratio mismatch')
            result[key] = tuple(numbers[name] for name in spec['columns'][2:])
        expected = set(itertools.product(seeds, checkpoints))
        _require(set(result) == expected,
                 f'{label}: incomplete or unexpected rows; missing={sorted(expected - set(result))}, extra={sorted(set(result) - expected)}')
        return result
    except (UnicodeError, csv.Error, DecimalException) as exc:
        raise AdmissionError(f'{label}: malformed CSV: {exc}') from exc


def _git(repo: Path, *args: str) -> bytes:
    proc = subprocess.run(['git', '--no-replace-objects', '--no-optional-locks', '-c', 'core.fsmonitor=false',
                           '-C', str(repo), *args], capture_output=True, check=False)
    _require(proc.returncode == 0, f'source repository: git {args[0]} failed')
    return proc.stdout


def validate_source(source: dict, repo: Path, label: str) -> None:
    """Check immutable git objects; live runs also require an exact clean checkout."""
    _source_spec(source, f'{label}.source')
    commit = source['commit']
    _require(_git(repo, 'rev-parse', f'{commit}^{{commit}}').decode().strip() == commit,
             f'{label}: source commit mismatch')
    _require(_git(repo, 'rev-parse', f'{commit}^{{tree}}').decode().strip() == source['tree'],
             f'{label}: source tree mismatch')
    for name, digest in source['files'].items():
        _require(sha256(_git(repo, 'show', f'{commit}:{name}')) == digest, f'{label}: source file hash mismatch: {name}')
    if source['checkout'] == 'live':
        _require(_git(repo, 'rev-parse', 'HEAD').decode().strip() == commit, f'{label}: live source HEAD mismatch')
        _require(not _git(repo, 'status', '--porcelain', '--untracked-files=all'), f'{label}: live source checkout is dirty')
        flags = _git(repo, 'ls-files', '-v', '-z').split(b'\x00')
        _require(all(not entry or (entry[:1].isupper() and entry[:1] != b'S') for entry in flags),
                 f'{label}: hidden index flags (assume-unchanged/skip-worktree) forbidden')
        # Hash every tracked file, not just selected SHA-256 anchors. Compare to
        # immutable git blob objects so status caches cannot hide modifications.
        for entry in _git(repo, 'ls-tree', '-r', '-z', commit).split(b'\x00'):
            if not entry:
                continue
            metadata, raw_name = entry.split(b'\t', 1)
            mode, kind, object_id = metadata.split(b' ')
            _require(kind == b'blob', f'{label}: submodules require a separate pinned source contract')
            name = raw_name.decode('utf-8')
            _relative(name)
            path = repo / name
            if mode == b'120000':
                _require(path.is_symlink(), f'{label}: tracked symlink mismatch: {name}')
                for parent in path.parents:
                    if parent == repo:
                        break
                    _require(not parent.is_symlink(), f'{label}: symlink parent: {name}')
                content = os.fsencode(os.readlink(path))
            else:
                path = _member_path(repo, name)
                content = path.read_bytes()
                _require(bool(path.stat().st_mode & 0o111) == (mode == b'100755'), f'{label}: tracked file mode mismatch: {name}')
            blob_hash = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\x00' + content).hexdigest()
            _require(blob_hash == object_id.decode(), f'{label}: tracked source content mismatch: {name}')
        for name, digest in source['files'].items():
            _require(sha256(_member_path(repo, name).read_bytes()) == digest, f'{label}: live source file mismatch: {name}')


def validate_identity(raw: bytes, expected_digest: str, label: str) -> None:
    """Reusable binary/config identity check against an independently pinned hash."""
    _hash(expected_digest, f'{label} expected digest')
    _require(sha256(raw) == expected_digest, f'{label} identity mismatch')


def validate_evidence(manifest: dict, policy: dict, policy_digest: str, root: Path,
                      source_repos: dict[str, Path], excluded: list[Path] | None = None) -> dict:
    """Validate all declared evidence and original-baseline exact numeric equality."""
    validate_policy(policy)
    _hash(policy_digest, 'trusted policy hash')
    _object(manifest, {'schema_version', 'lane', 'baseline_domain', 'policy_sha256', 'members', 'runs', 'original_baseline'}, 'manifest')
    _require(type(manifest['schema_version']) is int and manifest['schema_version'] == 1, 'manifest: unsupported schema')
    for key in ('lane', 'baseline_domain'):
        _require(manifest[key] == policy[key], f'manifest: {key} mismatch (cross-baseline admission forbidden)')
    _require(manifest['policy_sha256'] == policy_digest, 'manifest: stale policy hash')
    _require(isinstance(manifest['runs'], dict) and set(manifest['runs']) == set(policy['runs']), 'manifest: incomplete or unexpected runs')
    _require(set(source_repos) == set(policy['runs']), 'source repositories: provide exactly one per run')
    paths = []
    for run_id, run in manifest['runs'].items():
        _object(run, {'source', 'native', 'config', 'process', 'table'}, f'manifest.{run_id}')
        _require(run['source'] == policy['runs'][run_id]['source'], f'{run_id}: source identity mismatch')
        paths.extend(_relative(run[key]) for key in ('native', 'config', 'process', 'table'))
    original_path = _relative(manifest['original_baseline'])
    paths.append(original_path)
    members = manifest['members']
    _require(isinstance(members, dict) and set(members) == set(paths), 'manifest: members must exactly cover evidence roles; receipts/self are forbidden')
    # Multiple runs may use the same native/config bytes. Tables, process records
    # and the preserved original are independent roles and cannot alias.
    independent = [manifest['original_baseline']]
    for run in manifest['runs'].values():
        independent.extend([run['process'], run['table']])
    _require(len(set(independent)) == len(independent), 'manifest: table/process/original roles alias')
    _require(not set(independent) & {run[role] for run in manifest['runs'].values() for role in ('native', 'config')},
             'manifest: independent evidence aliases native/config')
    data = {}
    resolved = []
    for name, digest in members.items():
        _hash(digest, f'member.{name}')
        path = _member_path(root, name)
        _require(all(not path.samefile(other) for other in excluded or [] if other.exists()),
                 f'manifest: member aliases policy, manifest or receipt: {name}')
        _require(all(not path.samefile(other) for other in resolved), f'manifest: hard-linked members: {name}')
        resolved.append(path)
        data[name] = path.read_bytes()
        _require(sha256(data[name]) == digest, f'manifest: stale member hash: {name}')
    tables = {}
    for run_id, run in manifest['runs'].items():
        expected = policy['runs'][run_id]
        validate_source(run['source'], source_repos[run_id], run_id)
        for role in ('native', 'config'):
            validate_identity(data[run[role]], expected[f'{role}_sha256'], f'{run_id}: {role}')
        process = _object(_json(data[run['process']], f'{run_id}.process'),
                          {'run_id', 'status', 'returncode', 'seeds', 'turns', 'source', 'native_sha256', 'config_sha256', 'executions'}, f'{run_id}.process')
        _require(process['run_id'] == run_id, f'{run_id}: process run identity mismatch')
        _require(process['status'] == 'complete' and type(process['returncode']) is int and process['returncode'] == 0,
                 f'{run_id}: process failed or incomplete')
        _integers(process['seeds'], f'{run_id}.process.seeds')
        _require(set(process['seeds']) == set(expected['seeds']), f'{run_id}: incomplete process seeds')
        _require(type(process['turns']) is int and process['turns'] == max(expected['checkpoints']), f'{run_id}: incomplete process turns')
        for key in ('source', 'native_sha256', 'config_sha256'):
            _require(process[key] == expected[key], f'{run_id}: process {key} identity mismatch')
        _require(isinstance(process['executions'], list), f'{run_id}: expected per-seed execution records')
        executed = set()
        for execution in process['executions']:
            _object(execution, {'seed', 'status', 'returncode', 'terminal_turn'}, f'{run_id}.execution')
            seed = execution['seed']
            _require(type(seed) is int and seed in expected['seeds'] and seed not in executed,
                     f'{run_id}: duplicate or unexpected execution seed')
            _require(execution['status'] == 'complete' and type(execution['returncode']) is int
                     and execution['returncode'] == 0, f'{run_id}: seed {seed} process failed or incomplete')
            _require(type(execution['terminal_turn']) is int and execution['terminal_turn'] == process['turns'],
                     f'{run_id}: seed {seed} incomplete terminal turn')
            executed.add(seed)
        _require(executed == set(expected['seeds']), f'{run_id}: missing seed execution records')
        tables[run_id] = validate_table(data[run['table']], expected['table'], expected['seeds'], expected['checkpoints'], run_id)
    original = policy['original_baseline']
    _require(members[original_path] == original['sha256'], 'original baseline: pinned member hash mismatch')
    baseline = policy['runs'][original['run']]
    original_rows = validate_table(data[original_path], baseline['table'], baseline['seeds'], baseline['checkpoints'], 'original baseline')
    _require(tables[original['run']] == original_rows, 'original baseline: exact numeric equivalence failed')
    return {'run_rows': {name: len(table) for name, table in tables.items()},
            'member_count': len(data), 'original_baseline_equivalent': True}


def validate_receipts(receipts: list[bytes], tiers: list[str], evidence_digest: str, policy_digest: str) -> dict:
    """Bind every final independent tier to frozen evidence and all prior tiers."""
    _review_tiers(tiers)
    _hash(evidence_digest, 'receipt evidence digest')
    _hash(policy_digest, 'receipt policy digest')
    _require(len(receipts) == len(tiers), 'reviews: require exactly one final receipt per tier')
    by_tier = {}
    reviewers = set()
    for raw in receipts:
        receipt = _object(_json(raw, 'review receipt'),
                          {'schema_version', 'tier', 'reviewer', 'status', 'evidence_sha256', 'policy_sha256', 'dependencies'}, 'receipt')
        _require(type(receipt['schema_version']) is int and receipt['schema_version'] == 1, 'receipt: unsupported schema')
        tier = _name(receipt['tier'], 'receipt.tier')
        reviewer = _name(receipt['reviewer'], 'receipt.reviewer')
        _require(tier in tiers and tier not in by_tier, 'receipt: unknown or duplicate tier')
        _require(reviewer not in reviewers, 'receipt: reviewers must be independent')
        _require(receipt['status'] == 'approved', 'receipt: provisional, rejected or incomplete review')
        _require(receipt['evidence_sha256'] == evidence_digest, 'receipt: stale evidence hash')
        _require(receipt['policy_sha256'] == policy_digest, 'receipt: stale policy hash')
        _require(isinstance(receipt['dependencies'], dict), 'receipt.dependencies: expected hash map')
        by_tier[tier] = (receipt, sha256(raw))
        reviewers.add(reviewer)
    prior = {}
    for tier in tiers:
        receipt, digest = by_tier[tier]
        _require(receipt['dependencies'] == prior, f'receipt.{tier}: stale, missing, cyclic or unexpected dependencies')
        prior = {**prior, tier: digest}
    return prior


def _repo_arguments(values: list[str]) -> dict[str, Path]:
    repos = {}
    for value in values:
        key, separator, path = value.partition('=')
        _require(bool(separator) and bool(path) and key not in repos, 'source-repo: expected unique RUN=PATH')
        repos[key] = Path(path)
    return repos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('seal', 'validate'))
    parser.add_argument('--root', type=Path, required=True, help='Read-only evidence member root')
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--policy-sha256', required=True, help='Independent trusted policy digest, never inferred')
    parser.add_argument('--source-repo', action='append', default=[], metavar='RUN=PATH')
    parser.add_argument('--manifest', type=Path, required=True, help='Existing manifest for validate; new exclusive path for seal')
    parser.add_argument('--plan', type=Path, help='Seal: manifest skeleton with members set to {}')
    parser.add_argument('--receipt', type=Path, action='append', default=[])
    parser.add_argument('--evidence-only', action='store_true', help='Validate evidence readiness without admitting it')
    args = parser.parse_args(argv)
    try:
        _hash(args.policy_sha256, 'trusted policy hash')
        raw_policy = args.policy.read_bytes()
        _require(sha256(raw_policy) == args.policy_sha256, 'policy: independently pinned digest mismatch')
        policy = _json(raw_policy, 'policy')
        validate_policy(policy)
        repos = _repo_arguments(args.source_repo)
        excluded = [args.policy, args.manifest, *args.receipt]
        if args.command == 'seal':
            _require(args.plan is not None and not args.receipt and not args.evidence_only,
                     'seal: requires --plan; receipt/evidence-only options are invalid')
            _require(not args.manifest.exists() and not args.manifest.is_symlink(), 'seal: refuses to overwrite existing manifest')
            manifest = _json(args.plan.read_bytes(), 'plan')
            _object(manifest, {'schema_version', 'lane', 'baseline_domain', 'policy_sha256', 'members', 'runs', 'original_baseline'}, 'plan')
            _require(manifest['members'] == {}, 'seal: plan members must be empty')
            _require(isinstance(manifest['runs'], dict), 'plan.runs: expected object')
            names = [_relative(manifest['original_baseline'])]
            for run in manifest['runs'].values():
                _object(run, {'source', 'native', 'config', 'process', 'table'}, 'plan.run')
                names.extend(_relative(run[role]) for role in ('native', 'config', 'process', 'table'))
            manifest['members'] = {name: sha256(_member_path(args.root, name).read_bytes()) for name in sorted(set(names))}
            excluded.append(args.plan)
            details = validate_evidence(manifest, policy, args.policy_sha256, args.root, repos, excluded)
            raw_manifest = strict_json_dumps(manifest).encode()
            # Exclusive creation is deliberate: sealed evidence is immutable.
            with args.manifest.open('xb') as output:
                output.write(raw_manifest)
            status = 'READY_FOR_REVIEW'
            exit_code = 0
            reviews = {}
        else:
            _require(args.plan is None and not (args.evidence_only and args.receipt), 'validate: incompatible options')
            raw_manifest = args.manifest.read_bytes()
            manifest = _json(raw_manifest, 'manifest')
            details = validate_evidence(manifest, policy, args.policy_sha256, args.root, repos, excluded)
            if args.evidence_only:
                reviews, status, exit_code = {}, 'READY_FOR_REVIEW', 0
            elif not args.receipt:
                reviews, status, exit_code = {}, 'REVIEW_REQUIRED', 3
            else:
                reviews = validate_receipts([path.read_bytes() for path in args.receipt], policy['review_tiers'],
                                            sha256(raw_manifest), args.policy_sha256)
                status, exit_code = 'ADMITTED', 0
        print(strict_json_dumps({'schema_version': 1, 'status': status, 'lane': policy['lane'],
                                 'baseline_domain': policy['baseline_domain'], 'policy_sha256': args.policy_sha256,
                                 'evidence_sha256': sha256(raw_manifest), 'reviews': reviews, **details}), end='')
        return exit_code
    except (AdmissionError, OSError, ValueError, DecimalException) as exc:
        print(strict_json_dumps({'schema_version': 1, 'status': 'REJECTED', 'reason': str(exc)}), end='')
        return 2


if __name__ == '__main__':
    sys.exit(main())
