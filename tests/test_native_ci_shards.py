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
             'context': {'representation': S.CONTEXT_FORMAT, 'msg': "'same'", 'kwargs': "{'x': 1}"}} for i in range(n)]


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
    context = SimpleNamespace(msg='same', kwargs={}, _to_json=lambda: (_ for _ in ()).throw(AssertionError('raw context serialization forbidden')))
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
    additions = {
        'tests/test_health_care_experiment_policy.py': '1',
        'tests/test_health_care_policy.py': '1',
    }
    assert len(owners) == 302
    assert {name: owners[name] for name in additions} == additions
    old_owners = {name: shard for name, shard in owners.items() if name not in additions}
    assert len(old_owners) == 300
    # Canonical complete owner map from immutable parent 2572d5b9, including
    # the original shard-0 controller test. Equal counts alone allow moves.
    assert S.digest(old_owners) == 'fbde72231a68a0d4df1ca7f261501223df0fff6c3b6c14a99f337face13b26bb'
    assert owners['tests/test_native_ci_shards.py'] == '0'
    assert m['historical_module_counts'] == [159, 140]
    assert m['historical_partition_sha256'] == '0d4f05d3b53f5290f2cba3e6f6f4888a29de098cd0de6060f71a9f38a70d59cb'
    assert m['expected_skips'] == [
        'tests/test_m36_regression.py::TestInvestCultureAcceleration::test_invest_culture_directional',
        'tests/test_m38b_regression.py::TestFullCascade::test_full_cascade_end_to_end',
        'tests/test_m38b_regression.py::TestPilgrimageFrequency::test_pilgrimage_frequency_calibration',
        'tests/test_m51_legacy_integration.py::test_legacy_determinism',
        'tests/test_mutual_aid_adversarial.py::test_multiturn_disabled_matches_untouched_public_source_with_same_repaired_native',
        'tests/test_turn_artifact_lifecycle.py::test_str_wrapper_does_not_retain_view_after_return',
    ]
    # Prospective full-native seal: historical 526 plus policy source's 97.
    assert m['expected_successful_subtests'] == 623


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
    # Historical prototype contract; direct current Tests graph/delegation
    # checks live in test_native_build_lanes and test_native_wheel_receipt.
    historical = root/'tests/fixtures/ci/standard-tests-cbf6e368.yml'
    assert hashlib.sha256(historical.read_bytes()).hexdigest() == '2dc117396d676801153d4458a12d9fdd0021b80268099b85e35f00b7b6b423b1'
    old = yaml.load(historical.read_text(), Loader=yaml.BaseLoader)
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


class ContextPolicy:
    def __init__(self, scale):
        self.scale = scale

    def __repr__(self):
        return f'ContextPolicy(scale={self.scale!r})'

    def __deepcopy__(self, memo):
        raise AssertionError('diagnostic display must not deepcopy labels')


class ContextReprError:
    def __repr__(self):
        raise RuntimeError('fixture repr failure')


@pytest.mark.parametrize('kind', ['inf', 'negative_inf', 'nan', 'bytes', 'policy', 'repr_error', 'cycle', 'unicode', 'long'])
def test_raw_pytest_9_0_context_values_become_bounded_display_only(kind):
    import math
    cycle = []; cycle.append(cycle)
    values = {'inf': math.inf, 'negative_inf': -math.inf, 'nan': math.nan,
              'bytes': b'\x00raw\xff', 'policy': ContextPolicy(math.inf),
              'repr_error': ContextReprError(), 'cycle': cycle, 'unicode': '\U0001f30d'*4000, 'long': 'x'*8000}
    raw = values[kind]
    context = SimpleNamespace(msg=raw, kwargs={'value': raw},
        _to_json=lambda: (_ for _ in ()).throw(AssertionError('9.0 asdict path forbidden')))
    display = S.context_display(context)
    assert display['representation'] == S.CONTEXT_FORMAT
    assert type(display['msg']) is type(display['kwargs']) is str
    assert len(display['msg']) <= S.CONTEXT_MSG_CHARS and len(display['kwargs']) <= S.CONTEXT_KWARGS_CHARS
    assert len(S.canonical(display)) <= S.CONTEXT_JSON_BYTES
    assert json.loads(S.canonical(display)) == display
    if kind == 'repr_error': assert 'raised in repr()' in display['kwargs']
    if kind in ('inf', 'negative_inf', 'nan'): assert repr(raw) in display['kwargs']
    if kind == 'bytes': assert 'raw' in display['kwargs']
    if kind in ('long', 'unicode'): assert '...' in display['kwargs']


def test_context_capture_freezes_mutable_labels_and_preserves_repeated_reports(manifest, full):
    owners = S.validate_assignment(manifest, ['tests/test_a.py', 'tests/test_b.py'])
    plugin = S.ShardPlugin(owners, '0')
    labels = {'values': [1]}
    context = SimpleNamespace(msg='same', kwargs=labels)
    report = SimpleNamespace(nodeid=full[0], when='call', outcome='passed', context=context)
    plugin.pytest_runtest_logreport(report)
    first = deepcopy(plugin.subtests[0]['context'])
    labels['values'].append(2)
    plugin.pytest_runtest_logreport(report)
    plugin.pytest_runtest_logreport(report)
    assert plugin.subtests[0]['context'] == first
    assert plugin.subtests[1]['context'] == plugin.subtests[2]['context'] != first
    assert [r['ordinal'] for r in plugin.subtests] == [0, 1, 2]
    assert all(r['nodeid'] == full[0] and r['outcome'] == 'passed' for r in plugin.subtests)


@pytest.mark.parametrize('change', ['format', 'missing', 'extra', 'msg_type', 'kwargs_type', 'msg_bound', 'kwargs_bound'])
def test_context_display_contract_cannot_carry_raw_authority_values(change):
    context = {'representation': S.CONTEXT_FORMAT, 'msg': 'None', 'kwargs': '{}'}
    if change == 'format': context['representation'] = 'lossless-input'
    elif change == 'missing': context.pop('msg')
    elif change == 'extra': context['raw'] = b'raw'
    elif change == 'msg_type': context['msg'] = float('inf')
    elif change == 'kwargs_type': context['kwargs'] = {'value': 1}
    elif change == 'msg_bound': context['msg'] = 'x'*(S.CONTEXT_MSG_CHARS+1)
    else: context['kwargs'] = 'x'*(S.CONTEXT_KWARGS_CHARS+1)
    with pytest.raises(S.Refused): S.validate_context_display(context)


@pytest.mark.parametrize('value', [float('inf'), -float('inf'), float('nan')])
def test_authority_json_nonfinite_refusal_is_not_relaxed(value):
    with pytest.raises(ValueError): S.canonical({'identity': {'value': value}})
    assert 'value' in S.context_display(SimpleNamespace(msg=None, kwargs={'value': value}))['kwargs']


def test_actual_installed_pytest_context_uses_display_without_to_json(monkeypatch, tmp_path):
    from dataclasses import dataclass
    import hashlib
    from importlib import metadata
    import os
    import _pytest.subtests as native_pytest_context
    import _pytest._io.saferepr as native_pytest_display

    @dataclass
    class RawPolicy:
        scale: float
        payload: object
        def __deepcopy__(self, memo):
            raise AssertionError('raw label must not be deepcopied')

    cycle = []; cycle.append(cycle)
    policy = RawPolicy(float('inf'), b'raw-context')
    context = native_pytest_context.SubtestContext(msg=float('inf'), kwargs={
        'bytes': b'raw-context', 'policy': policy, 'nan': float('nan'), 'cycle': cycle, 'repr_error': ContextReprError()})
    monkeypatch.setattr(native_pytest_context.SubtestContext, '_to_json',
                        lambda self: (_ for _ in ()).throw(AssertionError('raw asdict path forbidden')))
    display = S.context_display(context)
    assert json.loads(S.canonical(display)) == display and 'raw-context' in display['kwargs']
    assert type(display['msg']) is type(display['kwargs']) is str
    # Real parent/ordinal/status metadata still passes strict JSON and ownership.
    node = 'tests/test_a.py::test_x'
    plugin = S.ShardPlugin({'tests/test_a.py': '0'}, '0')
    plugin.pytest_runtest_logreport(SimpleNamespace(nodeid=node, when='call', outcome='passed', context=context))
    assert S.validate_execution([node], parents([node]), plugin.subtests) == {'passed': 1, 'skipped': 0, 'successful_subtests': 1}
    assert json.loads(S.canonical(plugin.subtests))[0]['ordinal'] == 0
    destination = os.environ.get('SHARD_CONTEXT_METADATA_REPORT')
    if destination:
        result = {'pytest_version': metadata.version('pytest'), 'representation': display,
                  'subtests_source_sha256': hashlib.sha256(Path(native_pytest_context.__file__).read_bytes()).hexdigest(),
                  'saferepr_source_sha256': hashlib.sha256(Path(native_pytest_display.__file__).read_bytes()).hexdigest(),
                  'scope': 'Actual installed context class, scalar/report surrogates only; no suite collection/World/native runtime'}
        Path(destination).write_text(json.dumps(result, indent=2)+'\n')


def test_v2_template_changes_only_closed_registration_and_preserves_failed_v1():
    import hashlib
    root = SCRIPT.parents[1]
    old = (root/'docs/workflows/native-two-shards.yml.in').read_bytes()
    active_old = (root/'.github/workflows/native-two-shards.yml').read_bytes()
    assert old == active_old and hashlib.sha256(old).hexdigest() == '3941604d9bc3f357360f77beb3b93efca4d90faebca8a3469dbcde1b6263dfce'
    expected = old.replace(b'lead/native-two-shard-qualification-20261029', b'lead/native-two-shard-qualification-v2-20261029').replace(b'.github/workflows/native-two-shards.yml', b'.github/workflows/native-two-shards-v2.yml').replace(b'name: Dormant native module shard qualification', b'name: Dormant native module shard qualification V2')
    prepared = (root/'docs/workflows/native-two-shards-v2.yml.in').read_bytes()
    assert prepared == expected
    installed = root/'.github/workflows/native-two-shards-v2.yml'
    if installed.exists(): assert installed.read_bytes() == prepared
