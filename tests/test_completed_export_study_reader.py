"""Pure contracts; no original studies, frozen imports, comparisons or worlds run."""
from dataclasses import replace
from contextlib import redirect_stderr
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/completed_export_study_reader.py'
spec = importlib.util.spec_from_file_location('completed_export_reader_test', SCRIPT)
reader = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reader
spec.loader.exec_module(reader)


def metadata(study):
    return dict(run=dict(id=study.run,run_attempt=1,head_sha=study.control,path=study.workflow,
            status='completed',conclusion='success',repository=dict(full_name=reader.REPOSITORY)),
        artifacts=dict(total_count=1,artifacts=[dict(id=study.artifact,name=study.artifact_name,
            size_in_bytes=study.archive_bytes,expired=False,digest='sha256:'+study.archive_sha,
            expires_at='2099-01-01T00:00:00Z',workflow_run=dict(id=study.run,head_sha=study.control,repository_id=1187468861))]),
        jobs=dict(total_count=1,jobs=[dict(id=study.job,run_id=study.run,run_attempt=1,head_sha=study.control,
            name=study.job_name,status='completed',conclusion='success')]))


def archive_fixture():
    payload={'raw/baseline/off_s42/state.json':b'{"value":1}',
             'raw/candidate/off_s42/state.json':b'{"value":1}',
             'logs/compare.log':b'off_s42: 1 files, 0 differences\n1 cases, 1 files compared, 0 differences\n'}
    inventory={name:dict(bytes=len(value),sha256=reader.sha(value)) for name,value in payload.items()}
    raw=json.dumps(inventory).encode()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,value in {**payload,'inventory.json':raw,'result.json':b'{"qualified":true}'}.items():
            archive.writestr(name,value)
    return stream.getvalue(),reader.sha(raw),inventory


class ReaderContracts(unittest.TestCase):
    def test_closed_registry_has_exact_producer_and_source_boundaries(self):
        self.assertEqual(set(reader.STUDIES),{'arc','recovered'})
        self.assertEqual(reader.STUDIES['arc'].baseline,'d0281e5f57c508f27cea1676f36e0e6ed1225c9d')
        self.assertEqual(reader.STUDIES['recovered'].candidate,'c76efe8552b4c6c288ebb1f813e2c0a58e5957b1')
        self.assertEqual(reader.STUDIES['arc'].archive_bytes,54791602)
        self.assertEqual(reader.NORMALIZATION,reader.core.NORMALIZATION)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            reader.main(['--study','unknown'])

    def test_official_metadata_all_identities_are_required(self):
        for study in reader.STUDIES.values():
            reader.validate_metadata(metadata(study),study)
        mutations=[lambda m:m['run'].update(head_sha='f'*40),
            lambda m:m['run'].update(run_attempt=2),lambda m:m['run'].update(run_attempt=True),
            lambda m:m['run'].update(id=float(reader.STUDIES['arc'].run)),lambda m:m['run'].update(conclusion='failure'),
            lambda m:m['artifacts'].update(total_count=2),lambda m:m['artifacts'].update(total_count=True),
            lambda m:m['artifacts']['artifacts'][0].update(expired=True),
            lambda m:m['artifacts']['artifacts'][0].update(digest='sha256:'+'0'*64),
            lambda m:m['artifacts']['artifacts'][0]['workflow_run'].update(head_sha='a'*40),
            lambda m:m['jobs']['jobs'][0].update(id=1),
            lambda m:m['jobs']['jobs'][0].update(conclusion='failure')]
        study=reader.STUDIES['arc']
        for mutate in mutations:
            data=metadata(study);mutate(data)
            with self.subTest(mutate=mutate),self.assertRaises(reader.Refusal):
                reader.validate_metadata(data,study)

    def test_streaming_inventory_verifies_complete_sets_sizes_and_content(self):
        raw,pin,expected=archive_fixture()
        study=replace(reader.STUDIES['arc'],inventory_sha=pin)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            files=reader.members(archive)
            observed=reader.stream_inventory(archive,files,study)
            self.assertEqual({name:row for name,row in observed.items() if name in expected},expected)
            with self.assertRaises(reader.Refusal):
                reader.stream_inventory(archive,files,replace(study,inventory_sha='0'*64))
            altered=dict(files);altered.pop('raw/candidate/off_s42/state.json')
            with self.assertRaises(reader.Refusal):
                reader.stream_inventory(archive,altered,study)

    def test_archive_metadata_refuses_alias_symlink_expansion_and_missing_paths(self):
        raw,pin,_=archive_fixture()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            with patch.object(reader,'MAX_TOTAL',1),self.assertRaises(reader.Refusal):
                reader.members(archive)
            with patch.object(reader,'MAX_ENTRIES',1),self.assertRaises(reader.Refusal):
                reader.members(archive)
            files=reader.members(archive)
            with self.assertRaises(reader.Refusal):
                reader.read_member(archive,files,'missing')
        empty=io.BytesIO()
        with zipfile.ZipFile(empty,'w') as archive:
            archive.writestr('raw/baseline/one/state.json',b'{}')
            archive.writestr('raw/candidate/extra/',b'')
        with zipfile.ZipFile(io.BytesIO(empty.getvalue())) as archive,self.assertRaises(reader.Refusal):
            reader.members(archive)
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            archive.writestr('raw/A',b'a');archive.writestr('raw/a',b'a')
        with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as archive,self.assertRaises(reader.Refusal):
            reader.members(archive)
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            entry=zipfile.ZipInfo('raw/link');entry.external_attr=(stat.S_IFLNK|0o777)<<16
            archive.writestr(entry,b'/tmp/target')
        with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as archive,self.assertRaises(reader.Refusal):
            reader.members(archive)

    def test_full_raw_case_registration_is_checked_independently_of_comparator(self):
        cases={'one','two'}
        inventory={f'raw/{arm}/{case}/state.json':{} for arm in ('baseline','candidate') for case in cases}
        inventory['raw/baseline/which.txt']={}
        inventory['raw/baseline/one.log']={}
        inventory['raw/candidate/two.log']={}
        reader.raw_sets(inventory,cases)
        for changed in ({key:value for key,value in inventory.items() if 'candidate/two/' not in key},
                {**inventory,'raw/candidate/extra/file':{}},{**inventory,'raw/unregistered/case/file':{}},
                {**inventory,'raw/baseline/other.txt':{}},{**inventory,'raw/candidate/unregistered.log':{}}):
            with self.assertRaises(reader.Refusal):
                reader.raw_sets(changed,cases)

    def test_casewise_output_requires_exact_nonempty_case_and_no_differences(self):
        expected={'one':3}
        reader.core.parse_comparison('one: 3 files, 0 differences\n1 cases, 3 files compared, 0 differences\n',expected)
        for text in ('one: 0 files, 0 differences\n1 cases, 0 files compared, 0 differences\n',
                     'two: 3 files, 0 differences\n1 cases, 3 files compared, 0 differences\n',
                     'one: 3 files, 1 differences\n1 cases, 3 files compared, 1 differences\n'):
            with self.assertRaises(reader.Refusal):
                reader.core.parse_comparison(text,expected)

    def test_disk_admission_includes_full_next_pair_and_reserve(self):
        required=reader.DISK_FLOOR+reader.RESERVE+123
        with patch.object(reader.shutil,'disk_usage',return_value=type('U',(),dict(free=required))()):
            reader.admission(Path('/tmp'),123)
        with patch.object(reader.shutil,'disk_usage',return_value=type('U',(),dict(free=required-1))()),self.assertRaises(reader.Refusal):
            reader.admission(Path('/tmp'),123)

    def test_derived_copy_is_exclusive_exact_and_keeps_original_zip(self):
        raw,pin,_=archive_fixture()
        with tempfile.TemporaryDirectory() as temp,zipfile.ZipFile(io.BytesIO(raw)) as archive:
            files=reader.members(archive)
            inventory=reader.stream_inventory(archive,files,replace(reader.STUDIES['arc'],inventory_sha=pin))
            root=Path(temp)/'derived'
            with patch.object(reader,'admission',return_value={}):
                reader.copy_members(archive,files,list(files),root,inventory)
                self.assertEqual(reader.core.payload_inventory(root),inventory)
                with self.assertRaises(reader.Refusal):
                    reader.copy_members(archive,files,list(files),root,inventory)
            self.assertEqual(reader.sha(raw),reader.sha(archive.fp.getvalue()))


if __name__=='__main__':
    unittest.main()
