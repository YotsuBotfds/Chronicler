"""Fourteen explicit V3 contracts. No Native, collection, build or subprocess."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
V2 = 'scripts/testing/native_shards_manifest.json'
V3 = 'scripts/testing/native_shards_manifest_v3.json'


@pytest.fixture
def helper():
    spec = importlib.util.spec_from_file_location('native_v3_contract_subject', ROOT/'scripts/native_ci_shards.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest(profile='v2'):
    return {'schema_version':1, 'shards':{'0':['tests/test_a.py'], '1':['tests/test_b.py']},
            'expected_skips':[], 'expected_successful_subtests':0, 'scope':profile}


def ref_double(S, monkeypatch, path, value):
    """Finite Git protocol only, explicitly not a real Git/source attestation."""
    reference, tree, blob = 'a'*40, 'b'*40, 'c'*40
    raw = json.dumps(value, indent=2).encode()+b'\n'
    calls = []
    def fake(command, *, cwd, env):
        assert cwd == S.ROOT and env['GIT_NO_LAZY_FETCH']=='1'
        args = command[1:]
        assert args[0]=='--no-replace-objects'
        calls.append(args)
        if args[1:]==['cat-file','-t',reference]: return b'commit\n'
        if args[1:]==['rev-parse','--verify',reference+'^{tree}']: return (tree+'\n').encode()
        if args[1:]==['ls-tree','-r','-z','--full-tree',tree,'--',path,'tests']:
            rows = [('100644','blob',blob,path),('100644','blob','d'*40,'tests/test_a.py'),
                    ('100755','blob','e'*40,'tests/test_b.py')]
            return b''.join((' '.join(row[:3])+'\t'+row[3]).encode()+b'\0' for row in rows)
        if args[1:]==['cat-file','-s',blob]: return (str(len(raw))+'\n').encode()
        if args[1:]==['cat-file','blob',blob]: return raw
        raise AssertionError(('unregistered Git request',args))
    monkeypatch.setattr(S.subprocess,'check_output',fake)
    def no_current(*args): raise AssertionError('immutable lookup used current source')
    monkeypatch.setattr(S,'read_json',no_current)
    monkeypatch.setattr(S,'source_modules',no_current)
    return reference, tree, blob, raw, calls


def test_default_current_bytes_and_read_order_remain_v2(helper,monkeypatch,tmp_path):
    S=helper;value=manifest();traces=[];outputs=[]
    def read(path):
        assert path==S.MANIFEST
        traces.append('physical manifest');return value
    def modules(): traces.append('current index');return ['tests/test_b.py','tests/test_a.py']
    def no_ref(*args,**kwargs): raise AssertionError('current path invoked immutable lookup')
    monkeypatch.setattr(S,'read_json',read);monkeypatch.setattr(S,'source_modules',modules)
    monkeypatch.setattr(S,'check_ref_manifest',no_ref)
    for index,extra in enumerate(([],['--manifest',V2])):
        output=tmp_path/str(index)
        monkeypatch.setattr(sys,'argv',['native_ci_shards.py','check-manifest','--execute','--output',str(output),*extra])
        S.main();outputs.append(output.read_bytes())
    expected=S.canonical({'state':'PASS','manifest_digest':S.digest(value),'modules':2})
    assert outputs==[expected,expected] and traces==['physical manifest','current index']*2


def test_default_immutable_bytes_and_five_git_reads_remain_v2(helper,monkeypatch,tmp_path):
    S=helper;value=manifest();reference,tree,blob,raw,calls=ref_double(S,monkeypatch,V2,value)
    output=tmp_path/'ref.json'
    monkeypatch.setattr(sys,'argv',['native_ci_shards.py','check-manifest','--execute','--source-ref',reference,'--output',str(output)])
    S.main()
    expected={'state':'PASS','source_ref':reference,'source_commit':reference,'source_tree':tree,
        'scope':'Git manifest/default test-module layout only; no pytest collection, execution or producer/wheel admission',
        'manifest_path':V2,'manifest_blob':blob,'manifest_sha256':S.hashlib.sha256(raw).hexdigest(),
        'manifest_digest':S.digest(value),'modules':2}
    assert output.read_bytes()==S.canonical(expected) and len(calls)==5


def test_v3_immutable_lookup_reads_selected_blob_and_modules_from_one_tree(helper,monkeypatch,tmp_path):
    S=helper;value=manifest('v3');reference,tree,blob,raw,calls=ref_double(S,monkeypatch,V3,value)
    output=tmp_path/'v3.json'
    monkeypatch.setattr(sys,'argv',['native_ci_shards.py','check-manifest','--execute','--source-ref',reference,'--manifest',V3,'--output',str(output)])
    S.main();result=json.loads(output.read_bytes())
    assert result['source_ref']==result['source_commit']==reference and result['source_tree']==tree
    assert result['manifest_path']==V3 and result['manifest_blob']==blob
    assert result['manifest_sha256']==S.hashlib.sha256(raw).hexdigest() and result['manifest_digest']==S.digest(value)
    assert result['modules']==2 and len(calls)==5


@pytest.mark.parametrize('command',['check-manifest','record-build','verify-transfer','run','aggregate'])
def test_v3_selection_reaches_each_real_command_boundary(helper,monkeypatch,tmp_path,command):
    S=helper;value=manifest('v3');build={'manifest_digest':S.digest(value),'identity':{'fake':'identity'}}
    build_path=tmp_path/'build.json';wheel=tmp_path/'wheel';output=tmp_path/'output';reads=[];writes=[];consumed=[]
    class Reached(RuntimeError): pass
    def read(path):
        reads.append(path)
        if path==S.ROOT/V3:return value
        if path==build_path:return build
        raise AssertionError(('unexpected metadata read',path))
    def current(path):
        assert path==wheel;consumed.append(('current identity',path));return build['identity']
    def transfer(record,path,selected):
        assert record is build and path==wheel and selected is value
        consumed.append(('transfer',selected))
        if command=='run':raise Reached('before runtime/native/pytest')
        return build['identity']
    def validate(record,selected):
        assert record is build and selected is value
        consumed.append(('aggregate',selected));raise Reached('before aggregate identity/Git/runtime reads')
    monkeypatch.setattr(S,'read_json',read);monkeypatch.setattr(S,'source_modules',lambda:['tests/test_a.py','tests/test_b.py'])
    monkeypatch.setattr(S,'write_json',lambda path,record:writes.append((path,record)))
    monkeypatch.setattr(S,'current_identity',current);monkeypatch.setattr(S,'verify_transfer',transfer)
    monkeypatch.setattr(S,'validate_build_record',validate);monkeypatch.setattr(S,'private_paths',lambda path:consumed.append(('private',path)))
    monkeypatch.setenv('GITHUB_JOB','python-native-build' if command=='record-build' else 'python-native-shard-aggregate')
    monkeypatch.setattr(sys,'argv',['native_ci_shards.py',command,'--execute','--manifest',V3,
        '--output',str(output),'--build',str(build_path),'--wheel-dir',str(wheel),'--shard','0'])
    if command in ('run','aggregate'):
        with pytest.raises(Reached):S.main()
        assert not writes
    else:
        S.main();assert len(writes)==1 and writes[0][0]==output
        if command=='check-manifest':assert writes[0][1]=={'state':'PASS','manifest_digest':S.digest(value),'modules':2}
        elif command=='record-build':
            assert writes[0][1]['identity'] is build['identity'] and writes[0][1]['manifest_digest']==S.digest(value)
            assert writes[0][1]['producer_job_key']=='python-native-build' and consumed==[('current identity',wheel)]
        else:assert writes[0][1]['identity'] is build['identity'] and consumed==[('transfer',value)]
    assert reads[0]==S.ROOT/V3 and S.MANIFEST not in reads
    if command=='run':assert consumed==[('private',output),('transfer',value)]
    if command=='aggregate':assert consumed==[('aggregate',value)]


@pytest.mark.parametrize('producer,consumer',[('v2','v3'),('v3','v2')])
def test_crossed_profile_build_digest_refuses_before_runtime_identity(helper,producer,consumer):
    S=helper;build={'kind':'native-shard-current-build-v1','producer_job_key':'python-native-build',
                  'manifest_digest':S.digest(manifest(producer))}
    with pytest.raises(S.Refused,match='build module manifest differs'):
        S.validate_build_record(build,manifest(consumer))


@pytest.mark.parametrize('path',['/tmp/native_shards_manifest_v3.json','scripts/testing/../testing/native_shards_manifest_v3.json'])
def test_illegal_manifest_paths_refuse_before_git_or_files(helper,monkeypatch,path):
    S=helper;calls=[]
    def forbidden(*args,**kwargs):calls.append(args);raise AssertionError('illegal selector reached I/O')
    monkeypatch.setattr(S.subprocess,'check_output',forbidden)
    with pytest.raises(S.Refused,match='closed manifest selector'):S.check_ref_manifest('a'*40,manifest=path)
    assert calls==[]


def test_v3_is_only_whole_m36_transfer_with_same_skips_subtests_and_history(helper):
    S=helper;v2=json.loads((ROOT/V2).read_bytes());v3=json.loads((ROOT/V3).read_bytes());module='tests/test_m36_regression.py'
    assert set(v2)==set(v3) and v2['scope'] in v3['scope'] and 'not V3 owner-order evidence' in v3['scope']
    assert [len(v2['shards'][k]) for k in ('0','1')]==[161,144]
    assert [len(v3['shards'][k]) for k in ('0','1')]==[160,145]
    all_modules=sorted(n for names in v2['shards'].values() for n in names)
    a=S.validate_assignment(v2,all_modules);b=S.validate_assignment(v3,all_modules)
    assert len(a)==len(b)==305 and {n:(a[n],b[n]) for n in a if a[n]!=b[n]}=={module:('0','1')}
    assert len(v3['expected_skips'])==6 and v3['expected_skips']==v2['expected_skips']
    assert v3['expected_successful_subtests']==v2['expected_successful_subtests']==623
    inverse=deepcopy(v3);inverse['scope']=v2['scope'];inverse['shards']['1'].remove(module);inverse['shards']['0']=sorted(inverse['shards']['0']+[module])
    assert inverse==v2


def test_duplicate_and_missing_ownership_still_refuse(helper):
    S=helper;duplicate=manifest();duplicate['shards']['1']=['tests/test_a.py','tests/test_b.py']
    with pytest.raises(S.Refused,match='duplicate module ownership'):
        S.validate_assignment(duplicate,['tests/test_a.py','tests/test_b.py'])
    with pytest.raises(S.Refused,match='missing or unknown source module'):
        S.validate_assignment(manifest(),['tests/test_a.py','tests/test_b.py','tests/test_missing.py'])
