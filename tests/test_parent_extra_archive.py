"""Portable small-file checks; no subprocesses, native runtime or live cohorts."""
from __future__ import annotations

import gzip
import importlib.util
import json
import os
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/archive_parent_extras.py'
SPEC = importlib.util.spec_from_file_location('parent_archive_under_test', SCRIPT)
A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)


def save(path, value):
    path.write_text(json.dumps(value, sort_keys=True))


@pytest.fixture
def batch(tmp_path, monkeypatch):
    monkeypatch.setattr(A, 'MIN_FREE_BYTES', 0)
    batch = tmp_path / 'batch'
    parent = batch / 'seed_42'
    parent.mkdir(parents=True)
    for name in A.FIXED | {'memories_civ.json'}:
        (parent / name).write_bytes((name.encode() + b'\n') * 20)
    protected = {'chronicle_bundle.json': b'{"seed":42,"total_turns":500}',
                 'agent_events.arrow': b'events', 'validation_needs.arrow': b'needs',
                 'validation_economy.arrow': b'unhashed economy',
                 'validation_resource_ledger.arrow': b'unhashed resources',
                 'validation_summary/turn_1.json': b'{"turn":1}',
                 'checkpoints/turn_101.ckpt': b'exact checkpoint',
                 'nested/memories_not_top_level.json': b'not eligible'}
    for name, value in protected.items():
        path = parent / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    required = ('chronicle_bundle.json', 'agent_events.arrow', 'validation_needs.arrow',
                'validation_summary/turn_1.json')
    run = {'seed': 42, 'dir': 'seed_42', 'bundle': 'seed_42/chronicle_bundle.json',
           'total_turns': 500, 'files': {f'seed_42/{name}': A.sha(parent / name) for name in required}}
    manifest = {'kind': 'chronicler-batch', 'schema_version': 1, 'status': 'complete',
                'completed_at': '2026-10-28T00:00:00+00:00', 'seeds': [42], 'turns': 500,
                'runs': [run], 'source': {'git_sha': 'a' * 40, 'package_digest': 'b' * 64},
                'native': {'status': 'absent'}}
    save(batch / 'batch_manifest.json', manifest)
    return batch


def archive(batch, suffix='one'):
    output = batch.parent / f'archive-{suffix}'
    restored = batch.parent / f'restored-{suffix}'
    result = A.archive_parent(batch, 42, A.sha(batch / 'batch_manifest.json'), output, restored)
    return output, restored, result


def rewrite_index(output, edit):
    data = json.loads((output / 'index.json').read_text())
    edit(data)
    save(output / 'index.json', data)
    return A.sha(output / 'index.json')


def test_actual_roundtrip_preserves_every_parent_file_and_protected_input(batch):
    before = A.inventory(batch / 'seed_42')
    manifest_hash = A.sha(batch / 'batch_manifest.json')
    output, restored, result = archive(batch)
    assert result['passed'] is True and result['raw_deletion'] is False
    assert result['files'] == 4
    assert A.inventory(batch / 'seed_42') == before
    assert A.sha(batch / 'batch_manifest.json') == manifest_hash
    index = json.loads((output / 'index.json').read_text())
    assert set(index['files']) == A.FIXED | {'memories_civ.json'}
    assert index['whole_parent_inventory'] == before
    for name in index['files']:
        assert (restored / name).read_bytes() == (batch / 'seed_42' / name).read_bytes()
    assert A.verify(output, result['index_sha256'])['passed'] is True
    assert set(before) - set(index['files'])


def test_gzip_and_index_are_deterministic_for_identical_inputs(batch):
    first, _, one = archive(batch, 'first')
    second, _, two = archive(batch, 'second')
    assert one['index_sha256'] == two['index_sha256']
    assert (first / 'index.json').read_bytes() == (second / 'index.json').read_bytes()
    for path in (first / 'gzip').iterdir():
        assert path.read_bytes() == (second / 'gzip' / path.name).read_bytes()
        assert path.read_bytes()[3:8] == b'\0' * 5  # flags and mtime zero


@pytest.mark.parametrize('change', ['running', 'missing_run', 'short', 'duplicate', 'missing_bundle', 'identity'])
def test_unfinalized_or_inconsistent_manifest_is_refused_before_output(batch, change):
    path = batch / 'batch_manifest.json'; data = json.loads(path.read_text())
    if change == 'running': data['status'] = 'running'
    elif change == 'missing_run': data['runs'] = []
    elif change == 'short': data['runs'][0]['total_turns'] = 499
    elif change == 'duplicate': data['runs'].append(data['runs'][0])
    elif change == 'missing_bundle': del data['runs'][0]['files']['seed_42/chronicle_bundle.json']
    else: data['source'] = {}
    save(path, data)
    with pytest.raises(ValueError): archive(batch)
    assert not (batch.parent / 'archive-one').exists()


def test_manifest_input_is_never_selected_even_with_allowlisted_name(batch):
    path = batch / 'batch_manifest.json'; data = json.loads(path.read_text())
    data['runs'][0]['files']['seed_42/state.json'] = A.sha(batch / 'seed_42/state.json')
    save(path, data)
    with pytest.raises(ValueError, match='validation input'): archive(batch)
    assert not (batch.parent / 'archive-one').exists()


def test_changed_required_input_and_wrong_manifest_anchor_fail_closed(batch):
    path = batch / 'batch_manifest.json'
    with pytest.raises(ValueError, match='manifest SHA'): A.archive_parent(batch, 42, '0' * 64, batch.parent/'out', batch.parent/'restore')
    (batch / 'seed_42/agent_events.arrow').write_bytes(b'changed')
    with pytest.raises(ValueError, match='validation input changed'): archive(batch)
    assert not (batch.parent / 'archive-one').exists()


@pytest.mark.parametrize('name', ['../state.json', '/state.json', 'C:/state.json', 'a/../state.json',
                                 'a//state.json', 'a\\state.json', './state.json', 'state.json/'])
def test_unsafe_manifest_and_index_paths_are_refused(batch, name):
    path = batch / 'batch_manifest.json'; data = json.loads(path.read_text())
    data['runs'][0]['files'][name] = '0' * 64
    save(path, data)
    with pytest.raises(ValueError): archive(batch)
    assert not (batch.parent / 'archive-one').exists()


@pytest.mark.parametrize('inside', ['batch', 'seed', 'existing'])
def test_outputs_are_exclusive_and_outside_all_source_inputs(batch, inside):
    output = {'batch':batch/'out', 'seed':batch/'seed_42/out', 'existing':batch.parent/'existing'}[inside]
    if inside == 'existing': output.write_bytes(b'existing preserved')
    with pytest.raises((ValueError, FileExistsError)):
        A.archive_parent(batch, 42, A.sha(batch/'batch_manifest.json'), output, batch.parent/'restore')
    if inside == 'existing': assert output.read_bytes() == b'existing preserved'


@pytest.mark.parametrize('kind', ['file_symlink', 'directory_symlink', 'hardlink', 'destination_parent'])
def test_file_and_parent_aliases_are_refused(batch, kind):
    parent = batch/'seed_42'; outside=batch.parent/'outside'
    try:
        if kind == 'hardlink': os.link(parent/'state.json', outside)
        elif kind == 'destination_parent':
            outside.symlink_to(parent, target_is_directory=True)
        elif kind == 'file_symlink':
            outside.write_bytes(b'outside');(parent/'state.json').unlink();(parent/'state.json').symlink_to(outside)
        else:
            outside.mkdir();(parent/'linked').symlink_to(outside,target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f'platform does not support requested alias fixture: {error}')
    with pytest.raises(ValueError):
        if kind == 'destination_parent':
            A.archive_parent(batch,42,A.sha(batch/'batch_manifest.json'),outside/'out',batch.parent/'restore')
        else: archive(batch)


def test_unhashed_ledger_change_during_compression_blocks_success(batch, monkeypatch):
    original=A.gzip.GzipFile
    def changed(*args,**kwargs):
        (batch/'seed_42/validation_economy.arrow').write_bytes(b'changed unhashed ledger')
        return original(*args,**kwargs)
    monkeypatch.setattr(A.gzip,'GzipFile',changed)
    with pytest.raises(ValueError,match='parent or manifest changed'): archive(batch)
    out=batch.parent/'archive-one'
    assert json.loads((out/'status.json').read_text())['passed'] is False
    assert not (out/'archive-receipt.json').exists()
    assert not (batch.parent/'restored-one').exists()


def test_manifest_change_after_actual_restore_blocks_completion(batch, monkeypatch):
    original=A.restore
    def changed(*args,**kwargs):
        result=original(*args,**kwargs)
        path=batch/'batch_manifest.json';path.write_bytes(path.read_bytes()+b'\n')
        return result
    monkeypatch.setattr(A,'restore',changed)
    with pytest.raises(ValueError,match='during actual restore'): archive(batch)
    assert not (batch.parent/'archive-one/archive-receipt.json').exists()


def test_verify_and_restore_require_the_explicit_index_hash(batch):
    output,_,result=archive(batch)
    with pytest.raises(ValueError,match='index SHA'): A.verify(output,'0'*64)
    with pytest.raises(ValueError,match='index SHA'): A.restore(output,'0'*64,batch.parent/'other')
    assert not (batch.parent/'other').exists()
    assert A.verify(output,result['index_sha256'])['passed'] is True


@pytest.mark.parametrize('name', ['../state.json','nested/state.json','validation_economy.arrow','state.json\\x',
                                 '/state.json','C:/state.json','a//state.json','./state.json','state.json/'])
def test_trusted_index_still_cannot_restore_protected_or_escaping_names(batch,name):
    output,_,_=archive(batch)
    def edit(data): data['files'][name]=data['files'].pop('state.json')
    expected=rewrite_index(output,edit)
    with pytest.raises(ValueError): A.restore(output,expected,batch.parent/'other')
    assert not (batch.parent/'other').exists()


@pytest.mark.parametrize('corruption',['truncated','second_member','trailing','bomb','hash'])
def test_gzip_corruption_members_and_uncompressed_bounds_fail_closed(batch,corruption):
    output,_,_=archive(batch);path=output/'gzip/state.json.gz'
    if corruption=='truncated': path.write_bytes(path.read_bytes()[:-4])
    elif corruption=='second_member': path.write_bytes(path.read_bytes()+gzip.compress(b'extra',mtime=0))
    elif corruption=='trailing': path.write_bytes(path.read_bytes()+b'trailing')
    elif corruption=='bomb': path.write_bytes(gzip.compress(b'x'*(A.BLOCK*3),mtime=0))
    else: path.write_bytes(path.read_bytes()[:-1]+b'x')
    def edit(data):
        row=data['files']['state.json'];row['gzip_bytes']=path.stat().st_size;row['gzip_sha256']=A.sha(path)
    expected=rewrite_index(output,edit)
    with pytest.raises((ValueError,A.zlib.error)): A.restore(output,expected,batch.parent/'corrupt-restore')
    if (batch.parent/'corrupt-restore').exists():
        assert json.loads((batch.parent/'corrupt-restore/status.json').read_text())['passed'] is False
        partial=batch.parent/'corrupt-restore/state.json'
        assert not partial.exists() or partial.stat().st_size<=2_000


def test_restoration_survives_source_relocation_and_never_overwrites(batch):
    output,restored,result=archive(batch)
    batch.rename(batch.with_name('moved-batch'))
    assert A.restore(output,result['index_sha256'],batch.parent/'again')['passed'] is True
    with pytest.raises(FileExistsError): A.restore(output,result['index_sha256'],restored)
    assert A.verify(output,result['index_sha256'])['passed'] is True


def test_large_single_member_is_bounded_and_decodes_exactly(batch):
    raw=(b'abc123'*A.BLOCK)[:A.BLOCK*2+19]
    (batch/'seed_42/memories_civ.json').write_bytes(raw)
    _,restored,_=archive(batch)
    assert (restored/'memories_civ.json').read_bytes()==raw


@pytest.mark.parametrize('kind',['gzip_file','gzip_directory','restore_parent'])
def test_archive_and_restore_parent_aliases_fail_closed(batch,kind):
    output,_,result=archive(batch);outside=batch.parent/'alias-target'
    try:
        if kind=='gzip_file':
            path=output/'gzip/state.json.gz';os.link(path,outside)
        elif kind=='gzip_directory':
            (output/'gzip').rename(outside);(output/'gzip').symlink_to(outside,target_is_directory=True)
        else: outside.symlink_to(batch/'seed_42',target_is_directory=True)
    except (OSError,NotImplementedError) as error:
        pytest.skip(f'platform does not support requested alias fixture: {error}')
    with pytest.raises(ValueError):
        if kind=='restore_parent': A.restore(output,result['index_sha256'],outside/'restore')
        else: A.verify(output,result['index_sha256'])


@pytest.mark.parametrize('change',['grow','shrink'])
def test_changing_source_size_is_bounded_before_archive_can_succeed(batch,monkeypatch,change):
    original=A.gzip.GzipFile
    def changed(*args,**kwargs):
        path=batch/'seed_42/memories_civ.json'
        path.write_bytes(b'x'*(2*A.BLOCK) if change=='grow' else b'')
        return original(*args,**kwargs)
    monkeypatch.setattr(A.gzip,'GzipFile',changed)
    with pytest.raises(ValueError,match='source (grew|shrank)'): archive(batch)
    output=batch.parent/'archive-one'
    assert not (output/'archive-receipt.json').exists()
    assert (batch/'seed_42/memories_civ.json').exists()


def test_empty_regular_files_have_exact_restores(batch):
    (batch/'seed_42/state.json').write_bytes(b'')
    _,restored,_=archive(batch)
    assert (restored/'state.json').read_bytes()==b''


def test_parent_size_bound_is_checked_before_hashing_large_file(batch,monkeypatch):
    monkeypatch.setattr(A,'MAX_PARENT_BYTES',1)
    def forbidden(path): raise AssertionError('over-bound file must not be hashed')
    monkeypatch.setattr(A,'snapshot',forbidden)
    with pytest.raises(ValueError,match='inventory exceeds'): A.inventory(batch/'seed_42')


def test_entry_bound_includes_directories_and_stops_before_any_hash(batch,monkeypatch):
    root=batch/'seed_42'
    for number in range(8): (root/f'empty-{number}').mkdir()
    monkeypatch.setattr(A,'MAX_PARENT_ENTRIES',5)
    def forbidden(path): raise AssertionError('over-entry tree must fail before any file hash')
    monkeypatch.setattr(A,'snapshot',forbidden)
    with pytest.raises(ValueError,match='entry bound'): A.inventory(root)


def test_snapshots_include_change_time_even_if_bytes_and_mtime_are_restored(batch):
    path=batch/'seed_42/state.json';before=A.snapshot(path)
    raw=path.read_bytes();path.write_bytes(b'different');path.write_bytes(raw)
    os.utime(path,ns=(path.stat().st_atime_ns,before['mtime_ns']))
    after=A.snapshot(path)
    assert before['sha256']==after['sha256'] and before['mtime_ns']==after['mtime_ns']
    if before['ctime_ns']==after['ctime_ns']:
        pytest.skip('filesystem change-time resolution cannot distinguish this fixture')
    assert before!=after


def test_hashing_a_growing_stream_reads_only_recorded_size_plus_one(batch,monkeypatch):
    from io import BytesIO
    path=batch/'seed_42/state.json';size=path.stat().st_size;original=Path.open;seen=[]
    class Growing(BytesIO):
        def read(self,count=-1):
            assert count>0
            result=super().read(count);seen.append(len(result));return result
    def opened(self,*args,**kwargs):
        if self==path and args==('rb',):return Growing(b'x'*(size+A.BLOCK*2))
        return original(self,*args,**kwargs)
    monkeypatch.setattr(Path,'open',opened)
    with pytest.raises(ValueError,match='hash byte bound'): A.sha(path)
    assert sum(seen)==size+1


def test_decode_bounds_compressed_growth_after_its_initial_snapshot(batch,monkeypatch):
    from io import BytesIO
    output,_,result=archive(batch);path=output/'gzip/state.json.gz'
    row=json.loads((output/'index.json').read_text())['files']['state.json']
    raw=path.read_bytes();original=Path.open;opens=0;seen=[]
    class Growing(BytesIO):
        def read(self,count=-1):
            assert count>0
            result=super().read(count);seen.append(len(result));return result
    def opened(self,*args,**kwargs):
        nonlocal opens
        if self==path and args==('rb',):
            opens+=1
            if opens==2:return Growing(raw+b'x'*(A.BLOCK*2))
        return original(self,*args,**kwargs)
    monkeypatch.setattr(Path,'open',opened)
    with pytest.raises(ValueError,match='compressed byte bound'): A.decode(path,row)
    assert sum(seen)==row['gzip_bytes']+1


def test_stream_writes_reserve_next_block_before_writing(batch,monkeypatch):
    original=A.space;reservations=[]
    def recorded(path,additional=0):
        reservations.append(additional);return original(path,additional)
    monkeypatch.setattr(A,'space',recorded)
    archive(batch)
    assert reservations and all(value>=A.BLOCK for value in reservations)


def test_duplicate_index_keys_are_rejected_even_with_matching_trusted_hash(batch):
    output,_,_=archive(batch)
    path=output/'index.json';text=path.read_text();path.write_text(text.replace('"version": 1','"version": 1, "version": 1'))
    with pytest.raises(ValueError,match='duplicate'): A.verify(output,A.sha(path))


@pytest.mark.parametrize('change',['array','boolean_version'])
def test_malformed_manifest_object_or_boolean_schema_is_refused(batch,change):
    path=batch/'batch_manifest.json';data=json.loads(path.read_text())
    if change=='array':data=[]
    else:data['schema_version']=True
    save(path,data)
    with pytest.raises(ValueError): archive(batch)
    assert not (batch.parent/'archive-one').exists()


@pytest.mark.parametrize('change',['array','boolean_version'])
def test_malformed_index_object_or_boolean_schema_is_refused(batch,change):
    output,_,_=archive(batch);path=output/'index.json';data=json.loads(path.read_text())
    if change=='array':data=[]
    else:data['version']=True
    save(path,data)
    with pytest.raises(ValueError): A.verify(output,A.sha(path))


def test_fixed_source_and_space_bounds_refuse_before_archive_output(batch,monkeypatch):
    monkeypatch.setattr(A,'MAX_SELECTED_BYTES',10)
    with pytest.raises(ValueError,match='raw byte'): archive(batch)
    assert not (batch.parent/'archive-one').exists()
    monkeypatch.setattr(A,'MAX_SELECTED_BYTES',64<<20)
    monkeypatch.setattr(A,'MIN_FREE_BYTES',1<<80)
    with pytest.raises(ValueError,match='free-space'): archive(batch)
    assert not (batch.parent/'archive-one').exists()


def test_no_raw_delete_or_unbounded_command_is_exposed():
    with pytest.raises(SystemExit): A.main(['delete','--raw'])
    with pytest.raises(SystemExit): A.main(['archive','--delete-originals'])
