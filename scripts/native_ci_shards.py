"""Whole-module native CI ownership and publication contracts.

The ordinary Tests workflow uses the reviewed current-source build, two native
module shards and their aggregate barrier. No product imports occur at module
initialization. The optional check-manifest --source-ref path reads only an
immutable Git manifest/default-module layout; it grants no collection, build or
runtime authority. Producer commands retain their existing admission checks."""
from __future__ import annotations

import argparse
from collections import Counter
import fnmatch
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'scripts/testing/native_shards_manifest.json'
MANIFEST_SELECTORS = ('scripts/testing/native_shards_manifest.json',
                      'scripts/testing/native_shards_manifest_v3.json')
PRIVATE_ENV = ('TMPDIR', 'PD_EVIDENCE_DIR', 'R007_EVIDENCE_DIR', 'Q009_EVIDENCE_DIR')
MAX_JSON = 16 * 1024**2
CONTEXT_MSG_CHARS = 256
CONTEXT_KWARGS_CHARS = 1024
CONTEXT_JSON_BYTES = 16 * 1024
CONTEXT_FORMAT = "pytest-saferepr-display-v1"


class Refused(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Refused(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path):
    require(Path(path).stat().st_size <= MAX_JSON, 'metadata exceeds fixed cap')
    return json.loads(Path(path).read_bytes())


def write_json(path, value):
    raw = canonical(value)
    require(len(raw) <= MAX_JSON, 'metadata exceeds fixed cap')
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open('xb') as stream:
        stream.write(raw)


def module_path(value):
    require(type(value) is str and '\\' not in value and '\x00' not in value, 'invalid module path')
    parts = value.split('/')
    require(len(parts) >= 2 and parts[0] == 'tests' and all(p not in ('', '.', '..') for p in parts), 'invalid module path')
    require(fnmatch.fnmatchcase(parts[-1], 'test_*.py') or fnmatch.fnmatchcase(parts[-1], '*_test.py'), 'nondefault test module')
    return value


def validate_assignment(manifest, actual_modules):
    require(type(manifest.get('schema_version')) is int and manifest['schema_version'] == 1, 'unknown manifest schema')
    shards = manifest.get('shards')
    require(type(shards) is dict and set(shards) == {'0', '1'}, 'expected exactly two shards')
    all_modules = []
    for names in shards.values():
        require(type(names) is list and names and names == sorted(names), 'module list must be nonempty and ordered')
        all_modules.extend(module_path(name) for name in names)
    require(len(set(all_modules)) == len(all_modules), 'duplicate module ownership')
    actual = [module_path(name) for name in actual_modules]
    require(len(actual) == len(set(actual)), 'duplicate source module')
    require(set(actual) == set(all_modules), 'missing or unknown source module')
    owners = {name: shard for shard, names in shards.items() for name in names}
    skips = manifest.get('expected_skips')
    require(type(skips) is list and len(skips) == len(set(skips)) and all(type(n) is str and '::' in n and n.split('::', 1)[0] in owners for n in skips), 'unowned expected skip')
    require(type(manifest.get('expected_successful_subtests')) is int and manifest['expected_successful_subtests'] >= 0, 'invalid expected subtest count')
    return owners


def selected_nodes(full, owners, shard):
    require(shard in ('0', '1'), 'unknown shard')
    require(type(full) is list and full and len(full) == len(set(full)), 'full collection must be unique and nonempty')
    for node in full:
        require(type(node) is str and '::' in node and node.split('::', 1)[0] in owners, 'unowned collection node')
    require({n.split('::', 1)[0] for n in full} == set(owners), 'assigned module absent from collection')
    return [node for node in full if owners[node.split('::', 1)[0]] == shard]


def validate_context_display(value):
    require(type(value) is dict and set(value) == {'representation', 'msg', 'kwargs'}, 'invalid diagnostic context display')
    require(value['representation'] == CONTEXT_FORMAT, 'unknown diagnostic context representation')
    require(type(value['msg']) is str and len(value['msg']) <= CONTEXT_MSG_CHARS, 'diagnostic message display exceeds bound')
    require(type(value['kwargs']) is str and len(value['kwargs']) <= CONTEXT_KWARGS_CHARS, 'diagnostic kwargs display exceeds bound')
    require(len(canonical(value)) <= CONTEXT_JSON_BYTES, 'diagnostic context JSON exceeds bound')
    return value


def context_display(context):
    """Bounded display labels only; never lossless inputs or authority values.

    Pytest 9.0.2 retains raw objects in SubtestContext. Its _to_json invokes
    dataclasses.asdict/deepcopy and is not a JSON-safety contract. Capture each
    label now with pytest's own safe display formatter; repeated reports remain
    separate even when their labels display identically or are truncated.
    """
    from _pytest._io.saferepr import saferepr
    value = {'representation': CONTEXT_FORMAT,
             'msg': saferepr(context.msg, maxsize=CONTEXT_MSG_CHARS),
             'kwargs': saferepr(context.kwargs, maxsize=CONTEXT_KWARGS_CHARS)}
    return validate_context_display(value)


def validate_execution(selected, parents, subtests):
    require(type(parents) is list and type(subtests) is list, 'missing execution reports')
    phases = {node: {} for node in selected}
    for report in parents:
        require(report['nodeid'] in phases and report['when'] in ('setup', 'call', 'teardown'), 'unowned parent report')
        require(report['when'] not in phases[report['nodeid']], 'duplicate parent phase')
        require(report['outcome'] in ('passed', 'skipped', 'failed'), 'unknown parent outcome')
        phases[report['nodeid']][report['when']] = report['outcome']
    require([r['nodeid'] for r in parents if r['when'] == 'setup'] == selected, 'parent execution order differs')
    require([r['nodeid'] for r in parents if r['when'] == 'teardown'] == selected, 'parent teardown order differs')
    result = Counter()
    for node in selected:
        state = phases[node]
        require(state.get('teardown') == 'passed' and state.get('setup') in ('passed', 'skipped'), 'missing or unsuccessful setup/teardown')
        if state['setup'] == 'skipped':
            require('call' not in state, 'call after skipped setup')
            result['skipped'] += 1
        else:
            require(state.get('call') in ('passed', 'skipped'), 'missing or unsuccessful parent call')
            result['passed' if state['call'] == 'passed' else 'skipped'] += 1
    # Context labels may repeat legitimately. Retain every ordered report and
    # validate ownership by the real parent, never by a unique label heuristic.
    for ordinal, report in enumerate(subtests):
        require(report['ordinal'] == ordinal and report['nodeid'] in phases, 'unowned or reordered subtest')
        validate_context_display(report['context'])
        require(report['when'] == 'call' and report['outcome'] == 'passed', 'unsuccessful subtest')
        require(phases[report['nodeid']].get('call') == 'passed', 'subtest has no successful parent')
    return {'passed': result['passed'], 'skipped': result['skipped'], 'successful_subtests': len(subtests)}


class ShardPlugin:
    """Full default collection first; stable filtering by whole-module owner."""
    def __init__(self, owners, shard):
        self.owners, self.shard = owners, shard
        self.full, self.selected, self.parents, self.subtests, self.collection_errors = [], [], [], [], []

    def pytest_collectreport(self, report):
        if report.failed or report.skipped:
            self.collection_errors.append({'nodeid': report.nodeid, 'outcome': report.outcome})

    def pytest_collection_modifyitems(self, session, config, items):
        self.full = [item.nodeid for item in items]
        self.selected = selected_nodes(self.full, self.owners, self.shard)
        keep = set(self.selected)
        dropped = [item for item in items if item.nodeid not in keep]
        items[:] = [item for item in items if item.nodeid in keep]
        config.hook.pytest_deselected(items=dropped)

    def pytest_collection_finish(self, session):
        require([item.nodeid for item in session.items] == self.selected, 'selection changed after ownership filter')
        require(not self.collection_errors, 'collection skip/error requires explicit new registration')

    def pytest_runtest_logreport(self, report):
        value = {'nodeid': report.nodeid, 'when': report.when, 'outcome': report.outcome}
        if hasattr(report, 'context'):
            value.update(ordinal=len(self.subtests), context=context_display(report.context))
            self.subtests.append(value)
        else:
            self.parents.append(value)


def skipped_nodes(parents):
    return [r['nodeid'] for r in parents if r['outcome'] == 'skipped']


def validate_junit(path, selected, counts, skips):
    require(Path(path).stat().st_size <= MAX_JSON, 'JUnit exceeds fixed cap')
    root = ET.parse(path).getroot()
    suites = list(root.iter('testsuite'))
    cases = list(root.iter('testcase'))
    require(len(cases) == len(selected), 'JUnit parent count mismatch')
    from _pytest.junitxml import bin_xml_escape, mangle_test_address
    expected = []
    for node in selected:
        names = mangle_test_address(node)
        expected.append(('.'.join(names[:-1]), bin_xml_escape(names[-1])))
    require([(c.get('classname'), c.get('name')) for c in cases] == expected, 'JUnit node ownership/order mismatch')
    require([node for node, case in zip(selected, cases) if case.find('skipped') is not None] == skips, 'JUnit skipped node mismatch')
    require(not any(list(root.iter(tag)) for tag in ('failure', 'error')), 'JUnit failure/error')
    require(sum(int(s.get('tests', '-1')) for s in suites) == len(selected) + counts['successful_subtests'], 'JUnit/subtest accounting mismatch')
    require(sum(int(s.get('skipped', '-1')) for s in suites) == counts['skipped'], 'JUnit skip accounting mismatch')


def validate_build_record(build, manifest):
    require(build.get('kind') == 'native-shard-current-build-v1' and build.get('producer_job_key') == 'python-native-build', 'wrong current build record')
    require(build.get('manifest_digest') == digest(manifest), 'build module manifest differs')
    identity = build['identity']
    require(type(identity.get('source_commit')) is str and re.fullmatch('[0-9a-f]{40}', identity['source_commit']), 'invalid build source')
    require(type(identity.get('source_tree_digest')) is str and re.fullmatch('[0-9a-f]{64}', identity['source_tree_digest']), 'missing source tree identity')
    require(all(type(identity.get(k)) is int and identity[k] > 0 for k in ('run_id', 'attempt')), 'missing numeric producer identity')
    require(identity.get('classes') == ['AgentSimulator', 'EcologySimulator', 'PoliticsSimulator'], 'missing compiled class checks')
    require(all(type(identity.get(k)) is str and identity[k] for k in ('python', 'implementation', 'machine', 'package_scope')), 'missing interpreter context')
    require(type(identity.get('packages')) is dict and identity['packages'] and all(type(k) is str and type(v) is str and k and v for k, v in identity['packages'].items()), 'missing package context')
    wheel = identity['wheel']
    require(type(wheel.get('schema_version')) is int and wheel['schema_version'] == 1 and wheel.get('source_commit') == identity['source_commit'], 'wheel source mismatch')
    native = wheel['installed_native']
    require(native['sha256'] == native['wheel_member_sha256'] and re.fullmatch('[0-9a-f]{64}', native['sha256']), 'native/wheel member mismatch')
    require(type(native['bytes']) is int and 0 < native['bytes'] <= 64 * 1024**2, 'invalid native size')
    require(type(wheel['wheel']['bytes']) is int and 0 < wheel['wheel']['bytes'] <= 32 * 1024**2, 'invalid wheel size')
    require(re.fullmatch('[0-9a-f]{64}', wheel['wheel']['sha256']), 'invalid wheel digest')
    require(Path(wheel['wheel']['filename']).name == wheel['wheel']['filename'] and wheel['wheel']['filename'].endswith('.whl'), 'invalid wheel name')
    return identity


def aggregate(build, receipts, junit_paths, manifest):
    require(len(receipts) == 2 and len(junit_paths) == 2, 'both shards required')
    require({r.get('shard') for r in receipts} == {'0', '1'}, 'duplicate or missing shard')
    owners = validate_assignment(manifest, [name for names in manifest['shards'].values() for name in names])
    validate_build_record(build, manifest)
    totals = Counter()
    expected_full = receipts[0]['full_collection']
    claimed = []
    observed_skips = []
    for receipt, junit in zip(receipts, junit_paths):
        require(receipt.get('state') == 'PASS' and type(receipt.get('exit_code')) is int and receipt['exit_code'] == 0, 'shard did not succeed')
        require(receipt.get('build_digest') == digest(build), 'different builder/wheel/source')
        require(receipt.get('identity') == build['identity'], 'different runtime/native/package identity')
        require(receipt.get('manifest_digest') == digest(manifest), 'different module manifest')
        require(receipt['full_collection'] == expected_full, 'full collection differs across shards')
        expected = selected_nodes(expected_full, owners, receipt['shard'])
        require(receipt['selected'] == expected, 'wrong selection/order')
        require(not receipt['collection_errors'], 'collection was incomplete')
        counts = validate_execution(expected, receipt['parents'], receipt['subtests'])
        require(type(receipt['counts']) is dict and all(type(v) is int and v >= 0 for v in receipt['counts'].values()) and counts == receipt['counts'], 'report totals mismatch')
        require(file_hash(junit) == receipt['junit_sha256'], 'JUnit bytes changed')
        skips = skipped_nodes(receipt['parents'])
        validate_junit(junit, expected, counts, skips)
        observed_skips.extend(skips)
        totals.update(counts)
        claimed.extend(expected)
    require(len(claimed) == len(set(claimed)) and set(claimed) == set(expected_full), 'not exact-once full selection')
    require(sorted(observed_skips) == sorted(manifest['expected_skips']), 'unexpected or missing registered skip')
    require(totals['successful_subtests'] == manifest['expected_successful_subtests'], 'lost or changed registered subtest count')
    return {'state': 'PASS', 'scope': 'Complete native shard execution ownership only; no serial trajectory/RNG parity or speed claim',
            'identity': build['identity'], 'full_collection_digest': digest(expected_full), 'counts': dict(totals),
            'modules': len(owners), 'shards': [r['shard'] for r in receipts], 'build_digest': digest(build)}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def source_modules():
    paths = git('ls-files', '-z', '--', 'tests').decode().split('\0')
    return sorted(name for name in paths if name and (fnmatch.fnmatchcase(Path(name).name, 'test_*.py') or fnmatch.fnmatchcase(Path(name).name, '*_test.py')))


def manifest_selector(value):
    """Two source-owned manifest paths only; never normalize caller paths."""
    require(type(value) is str and value in MANIFEST_SELECTORS, 'closed manifest selector required')
    return value


def check_ref_manifest(reference, *, manifest=None):
    """Read one immutable Git layout; never collect/import tests or admit a build."""
    require(type(reference) is str and re.fullmatch('[0-9a-f]{40}', reference) is not None,
            'source ref must be a full lowercase 40-hex commit')
    if manifest is not None:
        manifest = manifest_selector(manifest)
    # Replacement refs must not silently change the contents named by the SHA.
    def pinned_git(*args):
        try:
            return subprocess.check_output(['git', '--no-replace-objects', *args], cwd=ROOT,
                                           env={**os.environ, 'GIT_NO_LAZY_FETCH': '1'})
        except subprocess.CalledProcessError as exc:
            raise Refused('source ref Git metadata unavailable') from exc

    require(pinned_git('cat-file', '-t', reference).strip() == b'commit', 'source ref is not a commit')
    tree = pinned_git('rev-parse', '--verify', reference + '^{tree}').decode().strip()
    require(re.fullmatch('[0-9a-f]{40}', tree) is not None, 'invalid source tree')
    manifest_path = 'scripts/testing/native_shards_manifest.json'
    if manifest is not None:
        manifest_path = manifest
    listing = pinned_git('ls-tree', '-r', '-z', '--full-tree', tree, '--', manifest_path, 'tests')
    require(len(listing) <= MAX_JSON, 'source layout exceeds fixed metadata cap')
    manifest_blob, modules = None, []
    for entry in listing.split(b'\0'):
        if not entry:
            continue
        header, name = entry.decode().split('\t', 1)
        mode, kind, oid = header.split(' ')
        if name == manifest_path:
            require(manifest_blob is None and mode in ('100644', '100755') and kind == 'blob',
                    'source manifest must be one regular Git blob')
            manifest_blob = oid
        elif fnmatch.fnmatchcase(Path(name).name, 'test_*.py') or fnmatch.fnmatchcase(Path(name).name, '*_test.py'):
            require(mode in ('100644', '100755') and kind == 'blob', 'source module must be a regular Git blob')
            modules.append(name)
    require(manifest_blob is not None, 'source ref has no module manifest')
    require(re.fullmatch('[0-9a-f]{40}', manifest_blob) is not None, 'invalid source manifest blob')
    size = int(pinned_git('cat-file', '-s', manifest_blob))
    require(0 < size <= MAX_JSON, 'source manifest exceeds fixed metadata cap')
    raw = pinned_git('cat-file', 'blob', manifest_blob)
    require(len(raw) == size, 'source manifest Git size mismatch')
    manifest = json.loads(raw)
    owners = validate_assignment(manifest, sorted(modules))
    return {'state': 'PASS', 'source_ref': reference, 'source_commit': reference, 'source_tree': tree,
            'scope': 'Git manifest/default test-module layout only; no pytest collection, execution or producer/wheel admission',
            'manifest_path': manifest_path, 'manifest_blob': manifest_blob,
            'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'manifest_digest': digest(manifest),
            'modules': len(owners)}


def source_tree_digest():
    tracked = git('ls-files', '-z', '--', 'src', 'scripts', 'tests', 'chronicler-agents', 'pyproject.toml', 'uv.lock').decode().split('\0')
    return digest({name: file_hash(ROOT/name) for name in tracked if name})


def verify_transfer(build, wheel_dir, manifest):
    identity = validate_build_record(build, manifest)
    require(identity['source_commit'] == os.environ['GITHUB_SHA'] == git('rev-parse', 'HEAD').decode().strip(), 'transferred source mismatch')
    require(identity['run_id'] == positive_env('GITHUB_RUN_ID') and identity['attempt'] == positive_env('GITHUB_RUN_ATTEMPT'), 'historical/cross-run wheel refused')
    require(identity['source_tree_digest'] == source_tree_digest(), 'transferred source tree mismatch')
    wheels = sorted(Path(wheel_dir).glob('*.whl'))
    require(len(wheels) == 1, 'one current builder wheel required')
    pin = identity['wheel']['wheel']
    require(wheels[0].name == pin['filename'] and wheels[0].stat().st_size == pin['bytes'] and file_hash(wheels[0]) == pin['sha256'], 'wheel transfer bytes mismatch before install')
    return identity


def current_identity(wheel_dir):
    # Same actual compiled-module/class and wheel-member checks as the current
    # standard native lane, delegated to its unchanged receipt implementation.
    import importlib.util
    from importlib.machinery import EXTENSION_SUFFIXES
    import chronicler_agents as ca
    from native_wheel_receipt import wheel_receipt
    source = os.environ['GITHUB_SHA']
    require(re.fullmatch('[0-9a-f]{40}', source) is not None and git('rev-parse', 'HEAD').decode().strip() == source, 'source commit mismatch')
    require(not git('diff', '--name-only', 'HEAD', '--', 'src', 'scripts', 'tests', 'chronicler-agents', 'pyproject.toml', 'uv.lock').strip(), 'dirty qualified source')
    spec = importlib.util.find_spec('chronicler_agents.chronicler_agents')
    origin = spec.origin if spec else ''
    require(origin.endswith(tuple(EXTENSION_SUFFIXES)), 'not a compiled native submodule')
    classes = ['AgentSimulator', 'EcologySimulator', 'PoliticsSimulator']
    require(all(isinstance(getattr(ca, name, None), type) for name in classes), 'missing real compiled classes')
    wheel = wheel_receipt(Path(wheel_dir), Path(origin), source)
    return {'source_commit': source, 'source_tree_digest': source_tree_digest(), 'wheel': wheel,
            'python': sys.version, 'implementation': platform.python_implementation(), 'machine': platform.machine(),
            'packages': {d.metadata['Name'].lower().replace('_', '-'): d.version for d in metadata.distributions() if d.metadata['Name'].lower() != 'maturin'},
            'package_scope': 'all installed distributions except the explicit builder-only maturin tool', 'classes': classes,
            'run_id': positive_env('GITHUB_RUN_ID'), 'attempt': positive_env('GITHUB_RUN_ATTEMPT')}


def positive_env(name):
    value = os.environ[name]
    require(re.fullmatch('[1-9][0-9]*', value) is not None, 'invalid producer identity')
    return int(value)


def private_paths(output):
    output = Path(output).resolve()
    for name in PRIVATE_ENV:
        value = Path(os.environ[name])
        require(value.is_absolute() and value.resolve().is_relative_to(output) and value.resolve() != output, 'private output environment required before Python')
        value.mkdir(parents=True, exist_ok=True)
    require(len({str(Path(os.environ[n]).resolve()) for n in PRIVATE_ENV}) == len(PRIVATE_ENV), 'aliased private paths')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('check-manifest', 'record-build', 'verify-transfer', 'run', 'aggregate'))
    parser.add_argument('--execute', action='store_true', help='explicit dormant workflow opt-in')
    parser.add_argument('--source-ref', help='check-manifest only: immutable full 40-hex Git commit layout')
    parser.add_argument('--manifest', choices=MANIFEST_SELECTORS,
                        help='optional closed V2/V3 manifest; omission preserves the original V2 path')
    parser.add_argument('--wheel-dir', type=Path)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--shard', choices=('0', '1'))
    parser.add_argument('--receipts', nargs=2, type=Path)
    parser.add_argument('--junits', nargs=2, type=Path)
    args = parser.parse_args()
    require(args.execute, 'dormant prototype requires explicit execution registration')
    require(args.source_ref is None or args.command == 'check-manifest', 'source ref is only valid with check-manifest')
    if args.source_ref is not None:
        if args.manifest is None:
            write_json(args.output, check_ref_manifest(args.source_ref))
        else:
            write_json(args.output, check_ref_manifest(args.source_ref, manifest=args.manifest))
        return
    if args.manifest is None:
        manifest = read_json(MANIFEST)
    else:
        manifest = read_json(ROOT / manifest_selector(args.manifest))
    owners = validate_assignment(manifest, source_modules())
    if args.command == 'check-manifest':
        write_json(args.output, {'state': 'PASS', 'manifest_digest': digest(manifest), 'modules': len(owners)})
    elif args.command == 'record-build':
        require(os.environ.get('GITHUB_JOB') == 'python-native-build', 'wrong builder job')
        write_json(args.output, {'kind': 'native-shard-current-build-v1', 'identity': current_identity(args.wheel_dir),
                                 'manifest_digest': digest(manifest), 'producer_job_key': 'python-native-build'})
    elif args.command == 'verify-transfer':
        identity = verify_transfer(read_json(args.build), args.wheel_dir, manifest)
        write_json(args.output, {'state': 'PASS', 'identity': identity, 'scope': 'Current producer wheel content verified before install'})
    elif args.command == 'run':
        require(args.shard in ('0', '1'), 'shard required')
        private_paths(args.output)
        build = read_json(args.build)
        verify_transfer(build, args.wheel_dir, manifest)
        identity = current_identity(args.wheel_dir)
        require(build.get('kind') == 'native-shard-current-build-v1' and build['identity'] == identity and build['manifest_digest'] == digest(manifest), 'not the current-source producer wheel/context')
        require('PYTEST_ADDOPTS' not in os.environ and 'PYTEST_PLUGINS' not in os.environ and 'PYTEST_DISABLE_PLUGIN_AUTOLOAD' not in os.environ, 'altered full-suite plugin/filter context')
        require(Path.cwd().resolve() == ROOT, 'full default collection requires repository root')
        # The old inline native preloader starts with the working directory on
        # sys.path. Preserve that scope when this replacement is a script.
        sys.path.insert(0, str(ROOT))
        import pytest
        ShardPlugin.pytest_collection_modifyitems = pytest.hookimpl(trylast=True)(ShardPlugin.pytest_collection_modifyitems)
        plugin = ShardPlugin(owners, args.shard)
        args.output.mkdir(parents=True, exist_ok=True)
        junit = args.output/'native.xml'
        code = pytest.main(['-q', '-o', f'cache_dir={args.output}/cache', '--basetemp', str(args.output/'pytest'), '--junitxml', str(junit)], plugins=[plugin])
        result = {'state': 'FAIL', 'exit_code': int(code), 'shard': args.shard, 'identity': identity,
                  'build_digest': digest(build), 'manifest_digest': digest(manifest), 'full_collection': plugin.full,
                  'selected': plugin.selected, 'parents': plugin.parents, 'subtests': plugin.subtests,
                  'collection_errors': plugin.collection_errors}
        try:
            require(code == 0 and not plugin.collection_errors, 'pytest unsuccessful')
            result['counts'] = validate_execution(plugin.selected, plugin.parents, plugin.subtests)
            validate_junit(junit, plugin.selected, result['counts'], skipped_nodes(plugin.parents))
            require(current_identity(args.wheel_dir) == identity, 'source/runtime identity drift')
            result.update(state='PASS', junit_sha256=file_hash(junit))
        except Refused as exc:
            result['refusal'] = str(exc)
        write_json(args.output/'receipt.json', result)
        require(result['state'] == 'PASS', 'native shard failed; retained first result')
    else:
        require(os.environ.get('GITHUB_JOB') == 'python-native-shard-aggregate', 'wrong aggregate job')
        build = read_json(args.build)
        identity = validate_build_record(build, manifest)
        require(identity['source_commit'] == os.environ['GITHUB_SHA'] == git('rev-parse', 'HEAD').decode().strip(), 'aggregate source differs')
        require(identity['run_id'] == positive_env('GITHUB_RUN_ID') and identity['attempt'] == positive_env('GITHUB_RUN_ATTEMPT'), 'aggregate producer differs')
        require(identity['source_tree_digest'] == source_tree_digest(), 'aggregate source tree differs')
        result = aggregate(build, [read_json(p) for p in args.receipts], args.junits, manifest)
        write_json(args.output, result)


if __name__ == '__main__':
    main()
