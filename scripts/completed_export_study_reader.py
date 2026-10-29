#!/usr/bin/env python3
"""Reinspect two fixed completed export studies, streaming one case pair at a time."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import importlib.metadata
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time
from types import SimpleNamespace
import zipfile

sys.dont_write_bytecode = True
CORE_SHA = '2bacde640402ce64ac52e284f3eb63d3462e1b00ec299ae8a21e1b6f065c649c'
GIB = 1024**3
DISK_FLOOR = 3 * GIB
RESERVE = 16 * 1024**2
MAX_ENTRIES = 2048
MAX_MEMBER = 32 * 1024**2
MAX_TOTAL = 512 * 1024**2
MAX_JSON = 32 * 1024**2
WALL_SECONDS = 600
REPOSITORY = 'YotsuBotfds/Chronicler'
HELPER_PATH = 'scripts/arc_output_identity_qualification.py'
NORMALIZATION = 'metadata.generated_at only; logs/run_manifest.json excluded by existing comparator'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def core_module():
    path = Path(__file__).with_name('default_output_identity_reader.py')
    if sha(path.read_bytes()) != CORE_SHA:
        raise ValueError('reviewed reader core differs')
    return module(path, '_completed_export_contract_core')


core = core_module()
require, Refusal = core.require, core.Refusal
git_source = module(Path(__file__).with_name('export_study_git.py'), '_completed_export_git')


@dataclass(frozen=True)
class Study:
    run: int
    job: int
    control: str
    baseline: str
    candidate: str
    artifact: int
    artifact_name: str
    archive_bytes: int
    archive_sha: str
    inventory_sha: str
    wheel_sha: str
    native_sha: str
    helper_sha: str
    workflow: str
    job_name: str
    source_pair: str | None


STUDIES = {
    'arc': Study(40793636869, 123184654671, '9e800f812dc884d70e16f49103e1542f6aface91',
        'd0281e5f57c508f27cea1676f36e0e6ed1225c9d', '249a4e1879cf5fbbb070de11f478f19825f51419',
        12863585862, 'arc-output-identity-40793636869-1', 54791602,
        'bfaa8fc0b7ae44fd9074c6ebad446706c8d0d95e62afdb09a1c8fb5654542d4c',
        'a64b3f4b3d208c6adcb78500e508eb1058cdc2fa5c261e50c3ab53bc89cfcb31',
        '54616417b94036ec91a40b69b94ad2b608d3b66666c93dd2b20e05af176cc58f',
        '06db5e19bdda13d7a536b236d677348f5ea7cb5adad2929962f0485192f9b4d6',
        '0f8081e3c6bbc59902733fb798d5a1db03119d897363605490286c553e4cfaff',
        '.github/workflows/arc-output-identity.yml', 'arc-output-identity', None),
    'recovered': Study(40796958774, 123195635121, '8bbc8f00864c771ec3ad167bf7baf6510c6b0f79',
        '2f9d618b70f3304c02dcaeef12996b4a99e074c0', 'c76efe8552b4c6c288ebb1f813e2c0a58e5957b1',
        12864342689, 'recovered-output-identity-40796958774-1', 54786758,
        '36b26c277b961480f94389f36af7d3c668ad44367937922e55d399f06fa931e1',
        'eb9a78584a9892cbd7d4e76f18d043140390afd736975f4c8ca237a10e373c0c',
        'bc17bb2561a4d014202c1f70846b31ace97ae00a98be2247dcfc3c4965b463ca',
        '06db5e19bdda13d7a536b236d677348f5ea7cb5adad2929962f0485192f9b4d6',
        '0d3a2c5db023a47a82307d3a9b789eebd979915e52be66e7208f0c93a94540f5',
        '.github/workflows/recovered-output-identity.yml', 'recovered-output-identity', 'recovered'),
}


def bind_study(study):
    # A fresh private instance of the immutable reviewed core gets only closed
    # identity pins. Its code, NORMALIZATION and comparator rules are unchanged.
    for name, value in dict(CONTROL=study.control, BASELINE=study.baseline, CANDIDATE=study.candidate,
            ARTIFACT_ID=study.artifact, RUN_ID=study.run, ARCHIVE_BYTES=study.archive_bytes,
            ARCHIVE_SHA=study.archive_sha, INVENTORY_SHA=study.inventory_sha,
            WHEEL_SHA=study.wheel_sha, NATIVE_SHA=study.native_sha).items():
        setattr(core, name, value)
    require(core.NORMALIZATION == NORMALIZATION, 'normalization differs')


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def admission(path, next_bytes=0):
    free = shutil.disk_usage(path).free
    require(type(next_bytes) is int and next_bytes >= 0, 'invalid derived-copy budget')
    require(free >= DISK_FLOOR + next_bytes + RESERVE, '3 GiB plus derived-copy budget and reserve refused')
    return dict(free_bytes=free, next_copy_bytes=next_bytes, floor_bytes=DISK_FLOOR, reserve_bytes=RESERVE)


def exact_fields(value, expected):
    return type(value) is dict and all(type(value.get(key)) is type(item) and value[key] == item for key, item in expected.items())


def validate_metadata(metadata, study):
    require(type(metadata) is dict and set(metadata) == {'run', 'artifacts', 'jobs'}, 'metadata roles differ')
    run, artifacts, jobs = (metadata[key] for key in ('run', 'artifacts', 'jobs'))
    require(exact_fields(run, dict(id=study.run, run_attempt=1))
            and run.get('head_sha') == study.control and run.get('path') == study.workflow
            and run.get('status') == 'completed' and run.get('conclusion') == 'success'
            and run.get('repository', {}).get('full_name') == REPOSITORY, 'producer run identity differs')
    require(type(artifacts.get('artifacts')) is list and exact_fields(artifacts, dict(total_count=1))
            and len(artifacts['artifacts']) == 1, 'producer artifact set incomplete or different')
    artifact = artifacts['artifacts'][0]
    origin = artifact.get('workflow_run', {})
    require(exact_fields(artifact, dict(id=study.artifact, name=study.artifact_name, size_in_bytes=study.archive_bytes)) and artifact.get('expired') is False
            and artifact.get('digest') == 'sha256:' + study.archive_sha
            and exact_fields(origin, dict(id=study.run, head_sha=study.control, repository_id=1187468861)), 'producer artifact identity differs')
    require(datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc),
            'producer artifact expired')
    require(type(jobs.get('jobs')) is list and exact_fields(jobs, dict(total_count=1)) and len(jobs['jobs']) == 1,
            'producer job set incomplete or different')
    job = jobs['jobs'][0]
    require(exact_fields(job, dict(id=study.job, run_id=study.run, run_attempt=1))
            and job.get('head_sha') == study.control and job.get('name') == study.job_name
            and job.get('status') == 'completed' and job.get('conclusion') == 'success',
            'producer job identity differs')


def members(archive, *, allow_directories=False):
    rows = archive.infolist()
    require(len(rows) <= MAX_ENTRIES, 'archive entry bound exceeded')
    require(allow_directories or not any(row.is_dir() for row in rows), 'unregistered outer directory record')
    require(all(0 <= row.file_size <= MAX_MEMBER for row in rows)
            and sum(row.file_size for row in rows) <= MAX_TOTAL, 'archive expansion bound exceeded')
    return core.archive_members(archive)


def read_member(archive, files, name, limit=MAX_JSON):
    require(name in files and files[name].file_size <= limit, 'required bounded archive member missing')
    with archive.open(files[name]) as stream:
        raw = stream.read(limit + 1)
    require(len(raw) == files[name].file_size and len(raw) <= limit, 'archive member bounds differ')
    return raw


def stream_inventory(archive, files, study):
    raw = read_member(archive, files, 'inventory.json')
    require(sha(raw) == study.inventory_sha, 'original inventory pin differs')
    expected = core.validate_file_map(core.strict_json(raw))
    require(not {'inventory.json', 'result.json'} & set(expected), 'inventory self-reference')
    observed = {}
    for name, item in files.items():
        digest, count = hashlib.sha256(), 0
        with archive.open(item) as stream:
            while block := stream.read(min(1024**2, item.file_size - count + 1)):
                count += len(block)
                require(count <= item.file_size, 'archive stream exceeds declared size')
                digest.update(block)
        require(count == item.file_size, 'archive member incomplete')
        observed[name] = dict(bytes=count, sha256=digest.hexdigest())
    require({'inventory.json', 'result.json'} <= set(observed), 'original receipt missing')
    require({name: value for name, value in observed.items() if name not in ('inventory.json', 'result.json')} == expected,
            'complete payload file set, sizes or hashes differ')
    return observed


def copy_members(archive, files, names, destination, inventory):
    require(not destination.exists(), 'derived copy destination exists')
    total = sum(files[name].file_size for name in names)
    observation = admission(destination.parent, total)
    destination.mkdir(mode=0o700)
    for name in names:
        core.relative_name(name)
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(files[name]) as stream, path.open('xb') as output:
            count, digest = 0, hashlib.sha256()
            while block := stream.read(min(1024**2, files[name].file_size - count + 1)):
                count += len(block)
                require(count <= files[name].file_size, 'derived copy stream exceeds bounds')
                output.write(block)
                digest.update(block)
        require(dict(bytes=count, sha256=digest.hexdigest()) == inventory[name], 'derived copy differs')
        path.chmod(0o444)
    require(core.payload_inventory(destination) == {name: inventory[name] for name in names}, 'derived copied tree differs')
    return observation


def verify_native(archive, files, inventory, study):
    wheels = [name for name in inventory if name.startswith('wheels/')]
    natives = [name for name in inventory if name.startswith('native/')]
    require(len(wheels) == len(natives) == 1 and wheels[0].endswith('.whl')
            and natives[0].endswith(tuple(__import__('importlib.machinery', fromlist=['EXTENSION_SUFFIXES']).EXTENSION_SUFFIXES)),
            'wheel or compiled-copy set differs')
    require(inventory[wheels[0]]['sha256'] == study.wheel_sha
            and inventory[natives[0]]['sha256'] == study.native_sha, 'wheel/native pin differs')
    raw = read_member(archive, files, wheels[0], MAX_MEMBER)
    with zipfile.ZipFile(io.BytesIO(raw)) as wheel:
        wheel_files = members(wheel, allow_directories=True)
        compiled = [name for name in wheel_files if name.endswith(tuple(__import__('importlib.machinery', fromlist=['EXTENSION_SUFFIXES']).EXTENSION_SUFFIXES))]
        require(len(compiled) == 1, 'compiled wheel member differs')
        item = wheel_files[compiled[0]]
        digest, count = hashlib.sha256(), 0
        with wheel.open(item) as stream:
            while block := stream.read(1024**2):
                digest.update(block)
                count += len(block)
                require(count <= MAX_MEMBER, 'compiled wheel member bound exceeded')
        require(count == item.file_size == inventory[natives[0]]['bytes'] and digest.hexdigest() == study.native_sha,
                'wheel member and retained native bytes differ')
    return dict(wheel=wheels[0], wheel_sha256=study.wheel_sha, native_copy=natives[0], native_sha256=study.native_sha)


def write_git_file(repo, ref, relative, destination, expected):
    raw = git_source.read_blob(repo, ref, relative)
    require(dict(bytes=len(raw), sha256=sha(raw)) == {key: expected[key] for key in ('bytes', 'sha256')},
            'frozen derived source differs')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(raw)
    destination.chmod(0o444)


def verify_source_records(repo, metadata, study, output):
    freeze = core.read_json(metadata / 'freeze.json')
    before = freeze['sources']
    require(before == core.read_json(metadata / 'sources-after.json'), 'original before/after sources differ')
    require(set(before) == {'baseline', 'candidate', 'control'}, 'original source role set differs')
    require(freeze.get('script_sha256') == study.helper_sha, 'original helper pin differs')
    verified = {}
    for role, ref in (('control', study.control), ('baseline', study.baseline), ('candidate', study.candidate)):
        require(before[role].get('sha') == ref, 'original source role revision differs')
        verified[role] = git_source.verify_snapshot(repo, before[role])
    require(len({row['crate_tree'] for row in verified.values()}) == 1, 'original crate trees differ')
    helper_path = output / 'derived-control' / HELPER_PATH
    write_git_file(repo, study.control, HELPER_PATH, helper_path, verified['control']['files'][HELPER_PATH])
    require(core.digest(helper_path)['sha256'] == study.helper_sha, 'derived helper source pin differs')
    helper = module(helper_path, '_frozen_completed_export_helper')
    require(freeze.get('matrix') == json.loads(json.dumps(helper.CASES)) and freeze.get('thread_caps') == helper.CAPS,
            'original registered matrix or caps differ')
    affinity = freeze.get('affinity')
    require(type(affinity) is list and len(affinity) == 1 and type(affinity[0]) is int, 'original affinity differs')
    baseline_script = output / 'derived-baseline' / 'scripts/turn_speed_identity.py'
    write_git_file(repo, study.baseline, 'scripts/turn_speed_identity.py', baseline_script,
                   verified['baseline']['files']['scripts/turn_speed_identity.py'])
    helper.require_matrix(baseline_script)
    view = output / 'derived-candidate'
    selected = [name for name in verified['candidate']['files'] if name.startswith('src/chronicler/') and name.endswith('.py')]
    selected += ['scripts/turn_speed_identity.py', 'scripts/cities_identity.py']
    admission(output, sum(verified['candidate']['files'][name]['bytes'] for name in selected))
    view_map = git_source.materialize_python_view(repo, study.candidate, view,
        ['scripts/turn_speed_identity.py', 'scripts/cities_identity.py'])
    helper.require_matrix(view / 'scripts/turn_speed_identity.py')
    require(core.payload_inventory(view) == view_map, 'bounded source view differs')
    return freeze, verified, helper, view, view_map


def raw_sets(inventory, cases):
    actual = {arm: set() for arm in ('baseline', 'candidate')}
    allowed_root_files = {'which.txt'} | {case + '.log' for case in cases}
    for name in inventory:
        if not name.startswith('raw/'):
            continue
        parts = name.split('/')
        require(len(parts) >= 3 and parts[1] in actual, 'raw arm path differs')
        if len(parts) == 3:
            require(parts[2] in allowed_root_files, 'unexpected raw arm-root file')
        else:
            require(parts[2] in cases, 'unexpected raw case directory')
            actual[parts[1]].add(parts[2])
    require(all(values == set(cases) for values in actual.values()), 'raw complete nine-case sets differ')


def compare_case(scratch, view, counts, output, caps, deadline):
    remaining = deadline - time.monotonic()
    require(remaining > 0, 'aggregate reader time bound exceeded')
    environment = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'LANG', 'LC_ALL', 'LD_LIBRARY_PATH') if key in os.environ}
    environment.update(caps, PYTHONPATH=str(view / 'src'), PYTHONDONTWRITEBYTECODE='1',
                       PYTHONNOUSERSITE='1', PYTHONHASHSEED='0', PYTHONOPTIMIZE='0')
    command = [sys.executable, str(view / 'scripts/turn_speed_identity.py'), 'compare',
               str(scratch / 'raw/baseline'), str(scratch / 'raw/candidate')]
    with output.open('xb') as log:
        result = subprocess.run(command, cwd=output.parent, env=environment, stdout=log,
                                stderr=subprocess.STDOUT, timeout=min(180, remaining))
    require(result.returncode == 0, 'frozen case comparator failed')
    require(output.stat().st_size <= core.COMPARE_LIMIT, 'frozen comparator log exceeds bound')
    return dict(command=command, **core.parse_comparison(output.read_text(), counts))


def inspect(study, archive_path, metadata_path, repo, output, report, deadline):
    require(sys.version_info[:2] == (3, 13) and sys.flags.optimize == 0, 'Python 3.13 without optimization required')
    require(importlib.util.find_spec('chronicler_agents') is None, 'reader must have no native package')
    require(len(os.sched_getaffinity(0)) == 1, 'reader affinity must be one CPU')
    with metadata_path.open('rb') as stream:
        metadata_bytes = stream.read(MAX_JSON + 1)
    require(len(metadata_bytes) <= MAX_JSON, 'producer metadata bound exceeded')
    validate_metadata(core.strict_json(metadata_bytes), study)
    report['producer_metadata_sha256'] = sha(metadata_bytes)
    require(not archive_path.is_symlink() and stat.S_ISREG(archive_path.stat().st_mode), 'original archive must be regular')
    require(core.digest(archive_path, study.archive_bytes) == dict(bytes=study.archive_bytes, sha256=study.archive_sha),
            'original archive digest or size differs')
    bind_study(study)
    with zipfile.ZipFile(archive_path) as archive:
        report['phase'] = 'inventory'
        files = members(archive)
        inventory = stream_inventory(archive, files, study)
        write(output / 'verified-payload.json', inventory)
        metadata_names = [name for name in files if name in ('inventory.json', 'result.json', 'freeze.json', 'sources-after.json')
                          or name.startswith(('probes/', 'audits/'))]
        report['phase'] = 'metadata-copy'
        derived_metadata = output / 'derived-metadata'
        copy_members(archive, files, metadata_names, derived_metadata, inventory)
        report['phase'] = 'sources'
        freeze, verified, helper, view, view_map = verify_source_records(repo, derived_metadata, study, output)
        result = core.read_json(derived_metadata / 'result.json')
        require(result.get('source_pair') == study.source_pair, 'original source-pair selector differs')
        rows = core.validate_result(result, helper.CASES)
        require(all(result['package_digests'][arm] == git_source.package_digest(verified[arm])
                    for arm in ('baseline', 'candidate')), 'running package digest differs from exact frozen source')
        report['phase'] = 'native-links'
        native = verify_native(archive, files, inventory, study)
        report['phase'] = 'probes'
        core.verify_probes(derived_metadata, inventory, result, helper.CASES)
        probes = [core.read_json(derived_metadata / name) for name in inventory
                  if name.startswith('probes/') and name.endswith('.json')]
        require(all(row['affinity'] == freeze['affinity'] and row['environment'] == probes[0]['environment']
                    for row in probes), 'cross-case runtime environment or affinity differs')
        require(all(all(value == helper.CAPS[key] for key, value in row['environment']['thread_env'].items() if key in helper.CAPS)
                    for row in probes), 'recorded thread cap differs')
        require(all(os.environ.get(key) == value for key, value in helper.CAPS.items()), 'reader thread cap differs')
        report['original_environment'] = probes[0]['environment']
        report['original_affinity'] = freeze['affinity']
        raw_sets(inventory, helper.CASES)
        results, all_counts, case_summaries = [], {}, []
        for case in helper.CASES:
            report['phase'] = 'case-' + case
            print(json.dumps(dict(study=report['study'], phase=report['phase'], status='start')), flush=True)
            names = [name for name in files if any(name.startswith(f'raw/{arm}/{case}/') for arm in ('baseline', 'candidate'))
                     or name in (f'audits/baseline-{case}.json', f'audits/candidate-{case}.json')]
            scratch = output / 'derived-case-scratch'
            budget = copy_members(archive, files, names, scratch, inventory)
            marker = scratch / '.derived-reader-scratch.json'
            write(marker, dict(kind='derived-export-reader-case', case=case, archive_sha256=study.archive_sha))
            selected_inventory = {name: inventory[name] for name in names}
            selected_helper = SimpleNamespace(CASES={case: helper.CASES[case]}, COMMON=helper.COMMON,
                SIDECARS=helper.SIDECARS, require_stamp=helper.require_stamp, case_contract=helper.case_contract)
            counts, summaries = core.verify_cases(scratch, selected_inventory,
                [row for row in rows if row['case'] == case], selected_helper, view)
            require(set(counts) == {case} and counts[case] > 0, 'case comparison is empty or different')
            all_counts.update(counts)
            case_summaries.extend(summaries)
            compare = compare_case(scratch, view, counts, output / (case + '-compare.log'), helper.CAPS, deadline)
            require({name: row for name, row in core.payload_inventory(scratch).items() if name != marker.name} == selected_inventory,
                    'frozen comparator changed copied raw bytes')
            require(core.read_json(marker) == dict(kind='derived-export-reader-case', case=case, archive_sha256=study.archive_sha),
                    'derived scratch ownership marker differs')
            require(core.payload_inventory(view) == view_map, 'frozen comparator changed source-view bytes')
            results.append(dict(case=case, admission=budget, **compare))
            write(output / (case + '-result.json'), results[-1])
            print(json.dumps(dict(study=report['study'], phase=report['phase'], status='complete', files_compared=counts[case])), flush=True)
            # Only this explicitly marked derived copy is retired. The immutable
            # ZIP contains every original byte and is never removed or rewritten.
            shutil.rmtree(scratch)
        require(set(all_counts) == set(helper.CASES) and len(results) == 9, 'nine-case comparison incomplete')
        original_compare = core.parse_comparison(read_member(archive, files, 'logs/compare.log', core.COMPARE_LIMIT).decode(), all_counts)
        report['phase'] = 'after-sources'
        for source in verified.values():
            git_source.verify_snapshot(repo, source)
        require(core.payload_inventory(view) == view_map, 'derived source changed after audit')
        require(core.payload_inventory(derived_metadata) == {name: inventory[name] for name in metadata_names}, 'derived metadata changed after audit')
        require(core.digest(output / 'derived-control' / HELPER_PATH)['sha256'] == study.helper_sha, 'derived helper changed after audit')
        require(core.digest(output / 'derived-baseline/scripts/turn_speed_identity.py') == {key: verified['baseline']['files']['scripts/turn_speed_identity.py'][key] for key in ('bytes', 'sha256')}, 'baseline matrix source changed after audit')
        require(not any(name == 'chronicler_agents' or name.startswith('chronicler_agents.') for name in sys.modules),
                'reader loaded a native module')
        require(core.digest(archive_path, study.archive_bytes) == dict(bytes=study.archive_bytes, sha256=study.archive_sha),
                'original archive changed')
        require(core.digest(metadata_path, MAX_JSON)['sha256'] == report['producer_metadata_sha256'], 'producer metadata changed')
        require(time.monotonic() <= deadline, 'aggregate reader time bound exceeded')
        report.update(qualified=True, phase='complete', payload_files=len(inventory),
            total_expansion_bytes=sum(row['bytes'] for row in inventory.values()),
            complete_source_snapshots={role:dict(sha=row['sha'], crate_tree=row['crate_tree'], files=len(row['files']))
                for role, row in verified.items()},native_links=native,cases=case_summaries,comparison=results,
            original_comparison=original_compare,source_view_files=len(view_map),
            normalization=NORMALIZATION,arrow_scope='Payload bytes hashed and compared; no Arrow decoding or schema validation.',
            source_scope='Complete frozen tracked Git blobs/modes verified; derived Python-only view, not a reconstructed worktree.',
            scope='Read-only casewise audit of completed exports; no worlds, native pools, test reruns or added normalization.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', choices=tuple(STUDIES), required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--git-repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    study = STUDIES[args.study]
    require(all(not path.is_symlink() and path.is_file() for path in (args.archive, args.metadata)), 'reader inputs must be regular non-symlink files')
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink(), 'reader output must be fresh')
    require(not output.resolve().is_relative_to(Path(__file__).resolve().parents[1])
            and not output.resolve().is_relative_to(args.git_repo.resolve()), 'reader output must be external')
    admission(output.parent)
    output.mkdir()
    started = time.monotonic()
    own_root = Path(__file__).resolve().parents[1]
    reader_head = subprocess.check_output(['git', '-C', str(own_root), 'rev-parse', 'HEAD'], timeout=10, text=True).strip()
    require(not subprocess.check_output(['git', '-C', str(own_root), 'status', '--porcelain', '--untracked-files=all'], timeout=10), 'reader source must be committed and clean')
    code_pins = {path.name: core.digest(path) for path in (Path(__file__), Path(git_source.__file__), Path(core.__file__))}
    report = dict(qualified=False, study=args.study, original_run_id=study.run, original_artifact_id=study.artifact,
        original_control=study.control, baseline=study.baseline, candidate=study.candidate,
        archive_bytes=study.archive_bytes, archive_sha256=study.archive_sha, phase='admission', reader_code=code_pins, reader_git_sha=reader_head,
        reader_python=sys.version, reader_executable=sys.executable, reader_affinity=sorted(os.sched_getaffinity(0)),
        reader_packages={name: importlib.metadata.version(name) for name in ('numpy','scipy','pyarrow','pydantic')},
        reader_native_package_present=importlib.util.find_spec('chronicler_agents') is not None,
        limits=dict(disk_floor=DISK_FLOOR,reserve=RESERVE,max_entries=MAX_ENTRIES,max_member=MAX_MEMBER,max_total=MAX_TOTAL,max_json=MAX_JSON,qualification_seconds=WALL_SECONDS,per_compare_seconds=180,git_command_seconds=git_source.COMMAND_TIMEOUT))
    try:
        inspect(study, args.archive.resolve(), args.metadata.resolve(), args.git_repo.resolve(), output, report, started + WALL_SECONDS)
        require(all(core.digest(Path(__file__).with_name(name)) == pin for name, pin in code_pins.items()), 'reader source changed')
        require(time.monotonic() <= started + WALL_SECONDS, 'aggregate qualification deadline exceeded')
    except Exception as error:
        report['qualified'] = False
        report['error'] = str(error) if type(error) in (Refusal, git_source.SnapshotError) else type(error).__name__
    report['reader_seconds'] = time.monotonic() - started
    write(output / 'reader-result.json', report)
    print(json.dumps({key:report.get(key) for key in ('qualified','study','phase','error','payload_files','reader_seconds')},allow_nan=False),flush=True)
    return 0 if report['qualified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
