"""Fixture-only cgroup hierarchy tests; no machine resource probes."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "wealth_floor_build_resources", Path(__file__).parents[1] / "scripts/wealth_floor_build_resources.py")
resources = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(resources)


def fixture(*, member="/build/job", mount="/sys/fs/cgroup"):
    files = {
        "/proc/self/cgroup": f"0::{member}\n",
        "/proc/self/mountinfo": f"41 20 0:30 / {mount} rw,nosuid - cgroup2 cgroup rw\n",
        "/proc/meminfo": "MemTotal: 5000000 kB\nMemAvailable: 2000000 kB\n",
    }
    for path in ("/", "/build", "/build/job"):
        directory = mount + ("" if path == "/" else path)
        files[directory + "/cgroup.controllers"] = "cpu memory pids\n"
        files[directory + "/cgroup.subtree_control"] = "cpu memory\n"
        if path != "/":
            files[directory + "/memory.max"] = "max\n"
            files[directory + "/memory.current"] = "100\n"
    return files


def observe(files):
    reads = []
    def read(path):
        reads.append(path)
        if path not in files:
            raise FileNotFoundError(path)
        value = files[path]
        if isinstance(value, Exception):
            raise value
        return value
    return resources.memory_admission(read_text=read), reads


def test_parent_sibling_usage_can_tighten_unbounded_leaf():
    files = fixture()
    files['/sys/fs/cgroup/build/memory.max'] = '1000\n'
    files['/sys/fs/cgroup/build/memory.current'] = '850\n'
    result, reads = observe(files)
    assert result['available_bytes'] == 150
    assert [r['cgroup_path'] for r in result['visible_ancestors']] == ['/', '/build', '/build/job']
    assert result['visible_ancestors'][0]['observation'] == 'unbounded_local_root'
    assert '/sys/fs/cgroup/build/memory.current' in reads
    assert 'namespace-invisible' in result['visibility_limits'][0]


def test_all_visible_limits_and_host_are_minimized():
    files = fixture()
    files['/sys/fs/cgroup/memory.max'] = '2000\n'
    files['/sys/fs/cgroup/memory.current'] = '1800\n'
    files['/sys/fs/cgroup/build/job/memory.max'] = '1000\n'
    files['/sys/fs/cgroup/build/job/memory.current'] = '700\n'
    assert observe(files)[0]['available_bytes'] == 200
    files['/proc/meminfo'] = 'MemAvailable: 0 kB\n'
    assert observe(files)[0]['available_bytes'] == 0


def test_over_limit_has_zero_available_headroom():
    files = fixture()
    files['/sys/fs/cgroup/build/memory.max'] = '99\n'
    assert observe(files)[0]['available_bytes'] == 0


def test_disabled_local_controller_inherits_visible_parent_limit():
    files = fixture()
    files['/sys/fs/cgroup/build/memory.max'] = '1000\n'
    files['/sys/fs/cgroup/build/memory.current'] = '800\n'
    files['/sys/fs/cgroup/build/cgroup.subtree_control'] = 'cpu\n'
    files['/sys/fs/cgroup/build/job/cgroup.controllers'] = 'cpu\n'
    files['/sys/fs/cgroup/build/job/cgroup.subtree_control'] = '\n'
    del files['/sys/fs/cgroup/build/job/memory.max']
    del files['/sys/fs/cgroup/build/job/memory.current']
    result, _ = observe(files)
    assert result['available_bytes'] == 200
    assert result['visible_ancestors'][-1]['observation'] == 'no_local_memory_controller_inherits_visible_parents'


def test_process_at_visible_root_with_positive_controller_files():
    result, _ = observe(fixture(member='/'))
    assert len(result['visible_ancestors']) == 1
    assert result['available_bytes'] == 2000000 * 1024


def test_mountinfo_escaped_space_maps_to_real_path():
    files = fixture(mount='/sys/cgroup space')
    files['/proc/self/mountinfo'] = '41 20 0:30 / /sys/cgroup\\040space rw - cgroup2 cgroup rw\n'
    result, _ = observe(files)
    assert result['cgroup_mount'] == '/sys/cgroup space'


@pytest.mark.parametrize('membership', ['2:memory:/build/job\n', '0::/build/job\n2:cpu:/x\n',
                                         '0::/a\n0::/b\n', '0::/../x\n', '0:://x\n', ''])
def test_unsupported_membership_refuses(membership):
    files = fixture(); files['/proc/self/cgroup'] = membership
    with pytest.raises(resources.ResourceRefused): observe(files)


@pytest.mark.parametrize('mountinfo', [
    '41 20 0:30 /hidden /sys/fs/cgroup rw - cgroup2 cgroup rw\n',
    '41 20 0:30 / /one rw - cgroup2 cgroup rw\n42 20 0:30 / /two rw - cgroup2 cgroup rw\n',
    '41 20 0:30 / /sys/fs/cgroup rw - tmpfs tmpfs rw\n',
    'malformed\n',
    '41 20 0:30 / /sys/../cgroup rw - cgroup2 cgroup rw\n',
    '41 20 0:30 / /sys/\\777cgroup rw - cgroup2 cgroup rw\n',
])
def test_unsupported_or_ambiguous_mount_refuses(mountinfo):
    files = fixture(); files['/proc/self/mountinfo'] = mountinfo
    with pytest.raises(resources.ResourceRefused): observe(files)


@pytest.mark.parametrize('path', ['/proc/self/cgroup', '/proc/self/mountinfo', '/proc/meminfo',
                                  '/sys/fs/cgroup/cgroup.controllers', '/sys/fs/cgroup/build/cgroup.subtree_control',
                                  '/sys/fs/cgroup/build/job/memory.current'])
def test_missing_required_evidence_or_partial_memory_pair_refuses(path):
    files = fixture(); del files[path]
    with pytest.raises(resources.ResourceRefused): observe(files)


def test_missing_pair_under_enabled_parent_refuses():
    files = fixture()
    del files['/sys/fs/cgroup/build/job/memory.max']; del files['/sys/fs/cgroup/build/job/memory.current']
    with pytest.raises(resources.ResourceRefused, match='enabled memory'): observe(files)


def test_existing_memory_pair_under_disabled_parent_refuses():
    files = fixture(); files['/sys/fs/cgroup/build/cgroup.subtree_control'] = 'cpu\n'
    with pytest.raises(resources.ResourceRefused, match='contradict'): observe(files)


@pytest.mark.parametrize('bad', ['-1\n', 'nan\n', '1 2\n', str(2**64), 'max\n'])
def test_bad_current_counter_refuses(bad):
    files = fixture(); files['/sys/fs/cgroup/build/memory.current'] = bad
    with pytest.raises(resources.ResourceRefused): observe(files)


@pytest.mark.parametrize('bad', ['MemAvailable: 1 kB\nMemAvailable: 2 kB\n',
                               'MemAvailable: 1 MB\n', 'MemFree: 2 kB\n'])
def test_host_available_is_required_and_unambiguous(bad):
    files = fixture(); files['/proc/meminfo'] = bad
    with pytest.raises(resources.ResourceRefused): observe(files)


def test_permissions_are_never_treated_as_absent_unbounded_files():
    files = fixture(); files['/sys/fs/cgroup/memory.max'] = PermissionError('not logged')
    with pytest.raises(resources.ResourceRefused, match='unreadable'): observe(files)


def test_controller_evidence_must_be_consistent():
    files = fixture(); files['/sys/fs/cgroup/cgroup.controllers'] = 'cpu\n'
    with pytest.raises(resources.ResourceRefused, match='availability evidence'): observe(files)


def test_fixture_reader_and_bounded_text_prevent_runtime_fallback(monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('real filesystem resource probe')
    monkeypatch.setattr(resources, '_default_read', forbidden)
    assert observe(fixture())[0]['available_bytes'] == 2000000 * 1024
    files = fixture(); files['/proc/meminfo'] = 'x' * (resources.MAX_FILE_BYTES + 1)
    with pytest.raises(resources.ResourceRefused, match='byte bound'): observe(files)


def test_deep_hierarchy_refuses_before_ancestor_expansion_or_resource_reads(monkeypatch):
    class NoParentExpansion(resources.PurePosixPath):
        @property
        def parents(self):
            raise AssertionError('over-depth hierarchy expanded')
    monkeypatch.setattr(resources, 'PurePosixPath', NoParentExpansion)
    files = fixture(member='/' + '/'.join(['a'] * resources.MAX_ANCESTORS))
    with pytest.raises(resources.ResourceRefused, match='ancestor bound'): observe(files)


@pytest.mark.parametrize('changed_path', ['/proc/self/cgroup', '/proc/self/mountinfo'])
def test_process_migration_or_remount_during_observation_refuses(changed_path):
    files = fixture()
    changed = {'/proc/self/cgroup': '0::/elsewhere\n',
               '/proc/self/mountinfo': '41 20 0:30 / /other rw - cgroup2 cgroup rw\n'}
    calls = {}
    def read(path):
        calls[path] = calls.get(path, 0) + 1
        if path == changed_path and calls[path] > 1:
            return changed[path]
        if path not in files:
            raise FileNotFoundError(path)
        return files[path]
    with pytest.raises(resources.ResourceRefused, match='changed during observation'):
        resources.memory_admission(read_text=read)
