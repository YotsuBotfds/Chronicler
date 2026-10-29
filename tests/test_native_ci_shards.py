"""Pure fake-collection/report contracts; no real suite collection or native."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import json
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/native_ci_shards.py'
SPEC = importlib.util.spec_from_file_location('native_shards_under_test', SCRIPT)
S = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = S
SPEC.loader.exec_module(S)


@pytest.fixture
def manifest():
    return {'schema_version': 1, 'shards': {'0': ['tests/test_a.py'], '1': ['tests/test_b.py']}, 'expected_skips': ['tests/test_b.py::test_x'], 'expected_successful_subtests': 2}


@pytest.fixture
def full():
    return ['tests/test_a.py::test_z', 'tests/test_a.py::TestC::test_a[p]', 'tests/test_b.py::test_x']


def parents(nodes, skipped=()):
    result = []
    for node in nodes:
        skip = node in skipped
        result.append({'nodeid': node, 'when': 'setup', 'outcome': 'skipped' if skip else 'passed'})
        if not skip:
            result.append({'nodeid': node, 'when': 'call', 'outcome': 'passed'})
        result.append({'nodeid': node, 'when': 'teardown', 'outcome': 'passed'})
    return result


def build_record(manifest):
    native = {'filename': 'native.so', 'bytes': 10, 'sha256': 'b'*64, 'wheel_member_sha256': 'b'*64}
    return {'kind': 'native-shard-current-build-v1', 'producer_job_key': 'python-native-build', 'manifest_digest': S.digest(manifest),
            'identity': {'source_commit': 'a'*40, 'source_tree_digest': 'c'*64, 'run_id': 10, 'attempt': 1,
                         'classes': ['AgentSimulator', 'EcologySimulator', 'PoliticsSimulator'], 'python': 'test-python',
                         'implementation': 'CPython', 'machine': 'fixture', 'package_scope': 'fixture packages', 'packages': {'pytest': '9'},
                         'wheel': {'schema_version': 1, 'source_commit': 'a'*40, 'installed_native': native,
                                   'wheel': {'filename': 'test.whl', 'bytes': 5, 'sha256': S.hashlib.sha256(b'wheel').hexdigest(), 'native_member': 'package/native.so'}}}}


def subtests(node, n=2):
    # Identical labels are legitimate, and must retain multiplicity/order.
    return [{'nodeid': node, 'when': 'call', 'outcome': 'passed', 'ordinal': i,
             'context': {'msg': 'same', 'kwargs': {'x': '1'}}} for i in range(n)]


def test_manifest_assigns_all_modules_once_and_preserves_collection_order(manifest, full):
    owners = S.validate_assignment(manifest, ['tests/test_b.py', 'tests/test_a.py'])
    assert S.selected_nodes(full, owners, '0') == full[:2]
    assert S.selected_nodes(full, owners, '1') == full[2:]


@pytest.mark.parametrize('change', ['new', 'missing', 'duplicate', 'empty', 'third', 'unsorted', 'bool_schema'])
def test_unknown_missing_duplicate_and_malformed_modules_refuse(manifest, change):
    actual = ['tests/test_a.py', 'tests/test_b.py']
    if change == 'new': actual.append('tests/test_new.py')
    elif change == 'missing': actual.pop()
    elif change == 'duplicate': manifest['shards']['1'].append('tests/test_a.py'); manifest['shards']['1'].sort()
    elif change == 'empty': manifest['shards']['0'] = []
    elif change == 'third': manifest['shards']['2'] = ['tests/test_c.py']
    elif change == 'unsorted': manifest['shards']['0'] = ['tests/test_z.py', 'tests/test_a.py']
    else: manifest['schema_version'] = True
    with pytest.raises(S.Refused): S.validate_assignment(manifest, actual)


@pytest.mark.parametrize('bad', ['../test_a.py', '/tests/test_a.py', 'tests/../test_a.py', 'tests//test_a.py', 'tests/./test_a.py', 'tests\\test_a.py', 'tests/test_\x00.py', 'tests/helper.py'])
def test_only_canonical_default_test_modules(bad):
    with pytest.raises(S.Refused): S.module_path(bad)


@pytest.mark.parametrize('change', ['duplicate', 'unknown', 'missing_module', 'empty'])
def test_bad_full_collection_refuses(manifest, full, change):
    owners = S.validate_assignment(manifest, ['tests/test_a.py', 'tests/test_b.py'])
    if change == 'duplicate': full.append(full[0])
    elif change == 'unknown': full.append('tests/test_new.py::test_x')
    elif change == 'missing_module': full = full[:2]
    else: full = []
    with pytest.raises(S.Refused): S.selected_nodes(full, owners, '0')


def test_real_parent_owns_repeated_subtest_contexts(full):
    reports = parents(full, skipped=full[2:])
    subs = subtests(full[0])
    assert S.validate_execution(full, reports, subs) == {'passed': 2, 'skipped': 1, 'successful_subtests': 2}
    assert len(subs) == 2 and subs[0]['context'] == subs[1]['context']


@pytest.mark.parametrize('change', ['missing_parent', 'duplicate_phase', 'unowned', 'reordered', 'failed_call', 'failed_teardown', 'call_after_skip', 'subtest_unowned', 'subtest_failed', 'subtest_lost_order'])
def test_incomplete_or_wrong_parent_subtest_execution_refuses(full, change):
    selected = full[:2]; reports = parents(selected); subs = subtests(selected[0])
    if change == 'missing_parent': reports = reports[:3]
    elif change == 'duplicate_phase': reports.append(deepcopy(reports[0]))
    elif change == 'unowned': reports[0]['nodeid'] = full[2]
    elif change == 'reordered': reports = reports[3:] + reports[:3]
    elif change == 'failed_call': reports[1]['outcome'] = 'failed'
    elif change == 'failed_teardown': reports[2]['outcome'] = 'failed'
    elif change == 'call_after_skip': reports[0]['outcome'] = 'skipped'
    elif change == 'subtest_unowned': subs[0]['nodeid'] = full[2]
    elif change == 'subtest_failed': subs[0]['outcome'] = 'skipped'
    else: subs.reverse()
    with pytest.raises(S.Refused): S.validate_execution(selected, reports, subs)


def test_plugin_keeps_modules_order_and_notifies_deselection(manifest, full):
    owners = S.validate_assignment(manifest, ['tests/test_a.py', 'tests/test_b.py'])
    p = S.ShardPlugin(owners, '0'); items = [SimpleNamespace(nodeid=n) for n in full]; dropped = []
    config = SimpleNamespace(hook=SimpleNamespace(pytest_deselected=lambda items: dropped.extend(items)))
    p.pytest_collection_modifyitems(None, config, items)
    p.pytest_collection_finish(SimpleNamespace(items=items))
    assert [i.nodeid for i in items] == full[:2]
    assert [i.nodeid for i in dropped] == full[2:]
    p.pytest_runtest_logreport(SimpleNamespace(**parents(full[:1])[0]))
    context = SimpleNamespace(_to_json=lambda: {'msg': 'same', 'kwargs': {}})
    for unused in range(2):
        p.pytest_runtest_logreport(SimpleNamespace(nodeid=full[0], when='call', outcome='passed', context=context))
    assert len(p.parents) == 1 and [r['ordinal'] for r in p.subtests] == [0, 1]


@pytest.mark.parametrize('change', ['collection_skip', 'selection_after_filter'])
def test_collection_errors_or_late_reordering_refuse(manifest, full, change):
    p = S.ShardPlugin(S.validate_assignment(manifest, ['tests/test_a.py', 'tests/test_b.py']), '0')
    p.selected = full[:2]; items = [SimpleNamespace(nodeid=n) for n in p.selected]
    if change == 'collection_skip': p.pytest_collectreport(SimpleNamespace(failed=False, skipped=True, nodeid='tests/test_a.py', outcome='skipped'))
    else: items.reverse()
    with pytest.raises(S.Refused): p.pytest_collection_finish(SimpleNamespace(items=items))


@pytest.fixture
def cohort(tmp_path, manifest, full):
    build = build_record(manifest)
    receipts, junits = [], []
    for shard, nodes in [('0', full[:2]), ('1', full[2:])]:
        skipped = nodes if shard == '1' else []
        subs = subtests(nodes[0]) if shard == '0' else []
        reports = parents(nodes, skipped)
        counts = S.validate_execution(nodes, reports, subs)
        j = tmp_path / f'{shard}.xml'
        addresses = {
            'tests/test_a.py::test_z': ('tests.test_a', 'test_z'),
            'tests/test_a.py::TestC::test_a[p]': ('tests.test_a.TestC', 'test_a[p]'),
            'tests/test_b.py::test_x': ('tests.test_b', 'test_x'),
        }
        j.write_text(f'<testsuites><testsuite tests="{len(nodes)+len(subs)}" skipped="{counts["skipped"]}">' + ''.join(f'<testcase classname="{addresses[n][0]}" name="{addresses[n][1]}">'+('<skipped/>' if n in skipped else '')+'</testcase>' for n in nodes) + '</testsuite></testsuites>')
        receipts.append({'state': 'PASS', 'exit_code': 0, 'shard': shard, 'identity': deepcopy(build['identity']),
                         'build_digest': S.digest(build), 'manifest_digest': S.digest(manifest), 'full_collection': full[:],
                         'selected': nodes[:], 'collection_errors': [], 'parents': reports, 'subtests': subs,
                         'counts': counts, 'junit_sha256': S.file_hash(j)})
        junits.append(j)
    return build, receipts, junits


def test_both_successful_shards_required_and_counts_separate(manifest, cohort):
    result = S.aggregate(*cohort, manifest)
    assert result['state'] == 'PASS'
    assert result['counts'] == {'passed': 2, 'skipped': 1, 'successful_subtests': 2}
    assert result['modules'] == 2


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'failed', 'build', 'identity', 'manifest', 'full', 'selected', 'collection_error', 'counts', 'junit_hash', 'junit_count'])
def test_partial_mismatched_or_forged_shards_cannot_aggregate(manifest, cohort, change):
    build, receipts, junits = cohort
    if change == 'missing': receipts.pop(); junits.pop()
    elif change == 'duplicate': receipts[1]['shard'] = '0'
    elif change == 'failed': receipts[1]['exit_code'] = 1
    elif change == 'build': receipts[1]['build_digest'] = '0'*64
    elif change == 'identity': receipts[1]['identity']['wheel']['installed_native']['sha256'] = 'd'*64
    elif change == 'manifest': receipts[1]['manifest_digest'] = '0'*64
    elif change == 'full': receipts[1]['full_collection'].reverse()
    elif change == 'selected': receipts[0]['selected'].reverse()
    elif change == 'collection_error': receipts[1]['collection_errors'] = [{'nodeid': 'x'}]
    elif change == 'counts': receipts[1]['counts']['passed'] += 1
    elif change == 'junit_hash': receipts[1]['junit_sha256'] = '0'*64
    else:
        junits[1].write_text('<testsuites><testsuite tests="99" skipped="1"><testcase/></testsuite></testsuites>')
        receipts[1]['junit_sha256'] = S.file_hash(junits[1])
    with pytest.raises(S.Refused): S.aggregate(build, receipts, junits, manifest)


def test_checked_in_partition_preserves_historical_assignment_with_explicit_new_test():
    m = json.loads(S.MANIFEST.read_bytes())
    files = [name for names in m['shards'].values() for name in names]
    owners = S.validate_assignment(m, files)
    assert [len(m['shards'][k]) for k in ('0', '1')] == [160, 140]
    assert owners['tests/test_native_ci_shards.py'] == '0'
    assert m['historical_module_counts'] == [159, 140]


@pytest.mark.parametrize('change', ['source', 'run_bool', 'attempt_missing', 'tree', 'producer', 'manifest', 'native', 'classes', 'packages', 'wheel_size', 'wheel_name'])
def test_incomplete_or_cross_source_builder_refuses(manifest, change):
    build = build_record(manifest); i = build['identity']
    if change == 'source': i['source_commit'] = 'short'
    elif change == 'run_bool': i['run_id'] = True
    elif change == 'attempt_missing': i.pop('attempt')
    elif change == 'tree': i['source_tree_digest'] = None
    elif change == 'producer': build['producer_job_key'] = 'other'
    elif change == 'manifest': build['manifest_digest'] = '0'*64
    elif change == 'native': i['wheel']['installed_native']['wheel_member_sha256'] = 'd'*64
    elif change == 'classes': i['classes'].pop()
    elif change == 'packages': i['packages'] = {}
    elif change == 'wheel_size': i['wheel']['wheel']['bytes'] = True
    else: i['wheel']['wheel']['filename'] = '../bad.whl'
    with pytest.raises(S.Refused): S.validate_build_record(build, manifest)


@pytest.mark.parametrize('change', ['none', 'run', 'attempt', 'source', 'tree', 'bytes', 'extra_wheel'])
def test_content_source_and_current_producer_checked_before_install(tmp_path, monkeypatch, manifest, change):
    build = build_record(manifest); wheel = tmp_path/'test.whl'; wheel.write_bytes(b'wheel')
    monkeypatch.setenv('GITHUB_SHA', 'a'*40); monkeypatch.setenv('GITHUB_RUN_ID', '10'); monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '1')
    monkeypatch.setattr(S, 'git', lambda *args: ('a'*40+'\n').encode())
    monkeypatch.setattr(S, 'source_tree_digest', lambda: 'c'*64)
    if change == 'run': monkeypatch.setenv('GITHUB_RUN_ID', '9')
    elif change == 'attempt': monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '2')
    elif change == 'source': monkeypatch.setenv('GITHUB_SHA', 'd'*40)
    elif change == 'tree': monkeypatch.setattr(S, 'source_tree_digest', lambda: 'd'*64)
    elif change == 'bytes': wheel.write_bytes(b'other')
    elif change == 'extra_wheel': (tmp_path/'extra.whl').write_bytes(b'wheel')
    if change == 'none': assert S.verify_transfer(build, tmp_path, manifest) == build['identity']
    else:
        with pytest.raises(S.Refused): S.verify_transfer(build, tmp_path, manifest)


def test_junit_same_count_wrong_nodes_refuses(manifest, cohort):
    build, receipts, junits = cohort
    junits[0].write_text(junits[0].read_text().replace('test_z', 'test_other'))
    receipts[0]['junit_sha256'] = S.file_hash(junits[0])
    with pytest.raises(S.Refused, match='ownership'): S.aggregate(build, receipts, junits, manifest)


def test_dormant_requires_explicit_opt_in(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'argv', ['native_ci_shards.py', 'check-manifest', '--output', str(tmp_path/'uncreated.json')])
    with pytest.raises(S.Refused, match='explicit execution'): S.main()
    assert not (tmp_path/'uncreated.json').exists()


def test_dormant_workflow_preserves_other_full_gates_and_blocks_partial_native():
    import hashlib
    import yaml
    root = SCRIPT.parents[1]
    active = root/'.github/workflows/tests.yml'
    assert hashlib.sha256(active.read_bytes()).hexdigest() == '2dc117396d676801153d4458a12d9fdd0021b80268099b85e35f00b7b6b423b1'
    old = yaml.load(active.read_text(), Loader=yaml.BaseLoader)
    new = yaml.load((root/'docs/workflows/native-two-shards.yml.in').read_text(), Loader=yaml.BaseLoader)
    assert new['on']['push'] == {'branches': ['lead/native-two-shard-qualification-20261029'], 'paths': ['.github/workflows/native-two-shards.yml']}
    branch = "github.ref == 'refs/heads/lead/native-two-shard-qualification-20261029'"
    for job in ('python-offline', 'python-no-rust', 'rust', 'viewer'):
        body = deepcopy(new['jobs'][job]); assert body.pop('if') == branch
        assert body == old['jobs'][job]
    builder = new['jobs']['python-native-build']
    assert builder['if'] == branch
    old_steps = old['jobs']['python-native-tests']['steps']
    expected_preflight = next(step for step in old_steps if step['name'] == 'Check turn-wrapper contracts before the full suite')
    assert expected_preflight in builder['steps']
    assert next(step for step in old_steps if step['name'] == 'Build Rust extension wheel') in builder['steps']
    shards = new['jobs']['python-native-tests']
    assert shards['strategy'] == {'fail-fast': 'false', 'matrix': {'shard': ['0', '1']}}
    assert shards['needs'] == ['python-native-build']
    prepare = next(step for step in shards['steps'] if step['name'] == 'Create private directories before Python starts')
    assert all(name+'=$private_root/' in prepare['run'] for name in S.PRIVATE_ENV)
    assert '>> "$GITHUB_ENV"' in prepare['run']
    names = [step['name'] for step in shards['steps']]
    assert names.index('Create private directories before Python starts') < names.index('Set up Python')
    assert names.index('Verify source producer and whole wheel before install') < names.index('Install the same verified current-source wheel') < names.index('Full default collection then owned module execution')
    barrier = new['jobs']['python-native-shard-aggregate']
    assert barrier['if'] == 'always() && '+branch
    assert barrier['needs'] == ['python-native-build', 'python-native-tests']
    assert new['jobs']['python-native']['needs'] == ['python-native-shard-aggregate', 'rust']
    downloads = [s['with']['name'] for s in barrier['steps'] if s.get('uses') == 'actions/download-artifact@v4']
    assert downloads == [stem+'-${{ github.run_id }}-${{ github.run_attempt }}' for stem in ('native-shard-build', 'native-module-shard-0', 'native-module-shard-1')]


@pytest.mark.parametrize('change', ['skip', 'subtests', 'junit_skip'])
def test_unexpected_skip_or_lost_subtest_stream_refuses(manifest, cohort, change):
    build, receipts, junits = cohort
    if change == 'skip':
        manifest['expected_skips'] = []
    elif change == 'subtests':
        manifest['expected_successful_subtests'] = 3
    else:
        junits[1].write_text(junits[1].read_text().replace('<skipped/>', ''))
        receipts[1]['junit_sha256'] = S.file_hash(junits[1])
    if change != 'junit_skip':
        build['manifest_digest'] = S.digest(manifest)
        for receipt in receipts:
            receipt['build_digest'] = S.digest(build)
            receipt['manifest_digest'] = S.digest(manifest)
    with pytest.raises(S.Refused): S.aggregate(build, receipts, junits, manifest)


@pytest.mark.parametrize('change', ['none', 'alias', 'outside'])
def test_private_evidence_paths_are_distinct_and_owned(tmp_path, monkeypatch, change):
    output = tmp_path/'owned'
    for index, name in enumerate(S.PRIVATE_ENV): monkeypatch.setenv(name, str(output/f'private-{index}'))
    if change == 'alias': monkeypatch.setenv('R007_EVIDENCE_DIR', str(output/'private-1'))
    elif change == 'outside': monkeypatch.setenv('TMPDIR', str(tmp_path/'outside'))
    if change == 'none':
        S.private_paths(output)
        assert all(Path(S.os.environ[name]).is_dir() for name in S.PRIVATE_ENV)
    else:
        with pytest.raises(S.Refused): S.private_paths(output)
