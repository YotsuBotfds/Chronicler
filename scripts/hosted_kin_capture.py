"""Ordinary trusted hosted Kin acquisition; explicit opt-in, no import-time runtime.

The two tmpfs capacities cover declared outputs/temp/cache paths. They are not
a filesystem sandbox, a whole-job disk/RSS cap, or the held32MiB lease design.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time

MIB = 1024**2
GIB = 1024**3
DATA_CAP = 496*MIB
CONTROL_CAP = 16*MIB
LOG_CAP = 2*MIB
RUN_REF = 'refs/heads/lead/kin-decision-capture-20261030'
ROOT = Path(__file__).resolve().parents[1]


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def raw(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def digest(path):
    with path.open('rb') as stream:
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'bytes': path.stat().st_size, 'sha256': value}


def regular(path, maximum):
    s = path.lstat()
    need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_size <= maximum,
         'regular single-link bounded input/output required')
    return s


def put(path, value, maximum):
    body = value if type(value) is bytes else raw(value)
    need(len(body) <= maximum, 'bounded control record exceeded')
    with path.open('xb') as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o444)
    return digest(path)


def context():
    need(os.environ.get('GITHUB_ACTIONS') == 'true' and
         os.environ.get('GITHUB_REF') == RUN_REF and
         os.environ.get('GITHUB_JOB') == 'kin-capture', 'exact hosted capture job/ref required')


def verified(wheels):
    # Reuse the qualified lower verifier without its functional CLI/job gate.
    from hosted_native_functional_smoke import verified_identity, schemas
    identity, package = verified_identity(wheels)
    return identity, schemas(package)


def record(wheels, output):
    files = list(wheels.glob('*.whl'))
    need(len(files) == 1 and files[0].stat().st_size <= 8*MIB, 'one fresh bounded wheel')
    identity, schemas = verified(wheels)
    put(output, {'kind': 'trusted-kin-current-build-v1', 'actual_job': 'kin-capture',
        'identity': identity, 'raw_schemas': schemas,
        'standard_native_producer_admission_claim': False}, MIB//4)
    need(sum(p.stat().st_size for p in output.parent.rglob('*') if p.is_file()) <= 9*MIB,
         '9MiB separate builder artifact exceeded')
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
        stream.write('build_upload=true\n')


def unescape(value):
    return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), value)


def mount_info(path, capacity, inodes):
    need(path.is_absolute() and path.resolve() == path and path.is_dir(), 'canonical mount path')
    rows = []
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        left, right = line.split(' - ', 1)
        fields, tail = left.split(), right.split()
        if unescape(fields[4]) == str(path):
            rows.append((fields, tail))
    need(len(rows) == 1, 'one exact mount required')
    fields, tail = rows[0]
    need(tail[0] == 'tmpfs' and {'rw', 'nodev', 'nosuid', 'noexec'} <= set(fields[5].split(',')),
         'tmpfs mount flags required')
    s, v = path.stat(), os.statvfs(path)
    need(s.st_uid == os.getuid() and stat.S_IMODE(s.st_mode) == 0o700 and
         v.f_blocks*v.f_frsize == capacity and v.f_files == inodes, 'mount size/inode/owner mismatch')
    return {'path': str(path), 'device': s.st_dev, 'inode': s.st_ino,
            'capacity_bytes': capacity, 'inode_limit': inodes,
            'mount_id': fields[0], 'flags': fields[5], 'filesystem': tail[0]}


def host_admission():
    available = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            available['MemAvailable_bytes'] = int(line.split()[1])*1024
    available['tmp_free_bytes'] = shutil.disk_usage('/tmp').free
    need(available.get('MemAvailable_bytes', 0) >= 6*GIB and
         available['tmp_free_bytes'] >= 3*GIB, 'ordinary hosted RAM/tmp admission failed')
    return available


def census(root, inode_limit):
    rows, directories = {}, []
    for path in sorted(root.rglob('*')):
        s = path.lstat()
        name = str(path.relative_to(root))
        if stat.S_ISDIR(s.st_mode):
            directories.append(name)
        else:
            need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'unexpected output type/link')
            rows[name] = {**digest(path), 'mode': oct(stat.S_IMODE(s.st_mode))}
        need(len(rows)+len(directories)+1 <= inode_limit, 'output inode envelope exceeded')
    v = os.statvfs(root)
    return {'files': rows, 'directories': directories,
            'file_count': len(rows), 'file_bytes': sum(x['bytes'] for x in rows.values()),
            'allocated_bytes': (v.f_blocks-v.f_bfree)*v.f_frsize,
            'available_bytes': v.f_bavail*v.f_frsize,
            'free_inodes': v.f_ffree}


def summary(value):
    return {k: value[k] for k in ('file_count', 'file_bytes', 'allocated_bytes',
                                 'available_bytes', 'free_inodes')}


def freeze_tree(path):
    for item in path.rglob('*'):
        if item.is_file() and not item.is_symlink():
            item.chmod(0o444)
    for item in sorted(path.rglob('*'), reverse=True):
        if item.is_dir():
            item.chmod(0o555)
    path.chmod(0o555)


def phase(name, arguments, control, env, stdin_body=None):
    """Drain one trusted child without giving its ordinary files a2MiB cap."""
    log, metrics = control/(name+'.log'), control/(name+'.metrics.txt')
    command = ['/usr/bin/time', '-o', str(metrics), '-f',
        'measurement=GNU_time_phase_command_tree\nuser_seconds=%U\nsystem_seconds=%S\n'
        'elapsed_seconds=%e\nexit_code=%x\nmax_rss_kib=%M\nwrapper_and_build_overhead=excluded',
        '/usr/bin/timeout', '--foreground', '--signal=KILL', '108s', '/usr/bin/prlimit',
        '--cpu=30:30', '--as=2147483648:2147483648', '--fsize=67108864:67108864',
        '--core=0:0', '--', *arguments]
    start = time.monotonic()
    count, refusal, returncode = 0, None, None
    process = None
    with log.open('xb') as output:
        try:
            process = subprocess.Popen(command, cwd=ROOT, env=env,
                stdin=subprocess.PIPE if stdin_body is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            if stdin_body is not None:
                process.stdin.write(stdin_body)
                process.stdin.close()
            os.set_blocking(process.stdout.fileno(), False)
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    if time.monotonic()-start >= 110:
                        refusal = 'owner_110second_deadline'
                        break
                    for key, _ in selector.select(.1):
                        block = os.read(key.fd, 16384)
                        if not block:
                            selector.unregister(key.fileobj)
                            continue
                        allowed = LOG_CAP-count
                        output.write(block[:allowed])
                        count += min(allowed, len(block))
                        if len(block) > allowed:
                            refusal = 'joint_diagnostic_limit'
                            break
                    if refusal:
                        break
                if refusal is None:
                    returncode = process.wait(timeout=max(.01, 110-(time.monotonic()-start)))
        except BaseException as exc:
            refusal = type(exc).__name__
        finally:
            if process is not None:
                if refusal is not None or process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                returncode = process.wait(timeout=2)
                process.stdout.close()
            output.flush()
            os.fsync(output.fileno())
    log.chmod(0o444)
    observed = {'kind': 'ACTUAL_TRUSTED_PHASE', 'phase': name, 'argv': arguments,
        'actual_process_returncode': returncode, 'refusal': refusal,
        'joint_diagnostic_bytes': count, 'raw_diagnostics_complete': refusal is None,
        'owner_observed_wall_seconds': time.monotonic()-start,
        'limits': {'wall_seconds': 110, 'CPU_seconds': 30, 'CPU_count': 1,
                   'AS_bytes_per_process': 2*GIB, 'ordinary_file_bytes': 64*MIB,
                   'joint_diagnostic_bytes': LOG_CAP}, 'passed': False}
    if metrics.exists():
        regular(metrics, 4096)
        values = dict(line.split('=', 1) for line in metrics.read_text().splitlines() if '=' in line)
        observed['GNU_time'] = values
        try:
            times = [float(values[k]) for k in ('user_seconds', 'system_seconds', 'elapsed_seconds')]
            observed['passed'] = (returncode == 0 and refusal is None and
                values.get('measurement') == 'GNU_time_phase_command_tree' and
                values.get('wrapper_and_build_overhead') == 'excluded' and
                values.get('exit_code') == '0' and all(math.isfinite(x) and x >= 0 for x in times) and
                sum(times[:2]) <= 30 and times[2] <= 110)
        except (KeyError, ValueError):
            pass
        metrics.chmod(0o444)
    put(control/(name+'.json'), observed, 16384)
    return observed


def cp_gate(path, control):
    from chronicler.run_checkpoint import read_header
    from capture_kin_root_exposure import _header
    regular(path, 64*MIB)
    header, _ = read_header(path)
    put(control/'checkpoint-header.json', header, 65536)
    _header(header)  # Same unchanged shape/horizon/raw-section gate as the driver.
    config = header['run_config']
    need(config.get('agent_mode') == 'hybrid' and config.get('validation_sidecar') is True and
         config.get('decision_ablation') is None and config.get('output_args', {}).get('simulate_only') is True and
         config.get('output_args', {}).get('narrator') == 'local', 'plain current checkpoint configuration')
    path.chmod(0o444)
    return digest(path)


def selected(control, data, outcome):
    destination = control/'selected'
    destination.mkdir()
    roles = {'identity.json': 65536, 'schemas.json': 192*1024,
             'checkpoint-header.json': 65536, 'generation.json': 16384,
             'capture.json': 16384, 'generation.metrics.txt': 4096,
             'capture.metrics.txt': 4096, 'census-summary.json': 65536,
             'outcome.json': 16384}
    for name, maximum in roles.items():
        source = control/name
        if source.exists():
            regular(source, maximum)
            put(destination/name, source.read_bytes(), maximum)
    capture = data/'kin-capture'
    for name in ('receipt.json', 'exposure.json'):
        source = capture/name
        if source.exists():
            regular(source, 65536)
            put(destination/name, source.read_bytes(), 65536)
    large = {}
    for name, maximum in (('cohort.json', MIB), ('wire.json', 32*MIB+65536)):
        source = capture/name
        if source.exists():
            regular(source, maximum)
            large[name] = digest(source)
    cohort = capture/'cohort.json'
    if cohort.exists():
        projection = {'projection_only': True, 'original': large['cohort.json'],
                      'full_member_list_retained_here': False}
        try:
            value = json.loads(cohort.read_bytes())
            projection.update({k: value[k] for k in ('kind', 'fork_turn', 'cohort_method_version',
                'community_method_version', 'members_at_fork', 'alive_at_fork', 'nonmembers_at_fork',
                'projected_rows', 'nonmember_decision_rows_captured')})
            projection['member_ids_canonical_JSON_LF_sha256'] = hashlib.sha256(raw(value['member_ids'])).hexdigest()
        except (ValueError, KeyError, TypeError) as exc:
            projection['projection_unavailable'] = type(exc).__name__
        put(destination/'cohort-projection.json', projection, 16384)
    put(destination/'large-remote-originals.json', {'raw_wire_and_full_cohort_retained_locally': False,
        'original_data_files': large, 'checkpoint': outcome.get('checkpoint'),
        'scope': 'Full bodies remain in remote originals; these are exact pins, not replay proof.'}, 16384)
    files = {p.name: digest(p) for p in destination.iterdir()}
    put(destination/'manifest.json', {'files': files, 'self_excluded': 'manifest.json',
        'later_file_closed_by_its_own_whole_control_accounting': 'final-accounting.json'}, 16384)
    need(sum(p.stat().st_size for p in destination.iterdir()) <= MIB, '1MiB compact selection exceeded')
    return destination


def final_accounting(control, destination, data_census):
    before = census(control, 128)
    log_bytes = sum(v['bytes'] for k, v in before['files'].items() if k.endswith('.log'))
    need(log_bytes <= 4*MIB, 'joint phase log planning envelope exceeded')
    value = {'kind': 'ACTUAL_FINAL_WHOLE_OUTPUT_ACCOUNTING', 'data': summary(data_census),
        'control_files_except_this_record': before['files'],
        'self_excluded_path': 'selected/final-accounting.json',
        'data_capacity_bytes': DATA_CAP, 'control_capacity_bytes': CONTROL_CAP,
        'final_control_file_bytes_including_self': before['file_bytes'],
        'scope': 'Declared output files and mounts; no unknown HOME/wholejob/RSS/readlease claim.'}
    for _ in range(8):
        expected = before['file_bytes']+len(raw(value))
        if value['final_control_file_bytes_including_self'] == expected:
            break
        value['final_control_file_bytes_including_self'] = expected
    else:
        raise ValueError('final accounting size did not stabilize')
    need(expected-log_bytes <= 8*MIB, 'other control planning envelope exceeded')
    put(destination/'final-accounting.json', value, 65536)
    after = census(control, 128)
    need(after['file_bytes'] == expected and after['allocated_bytes'] <= CONTROL_CAP and
         sum(p.stat().st_size for p in destination.iterdir()) <= MIB,
         'final control/selected output envelope exceeded')
    freeze_tree(destination)


def run(wheels, build, base):
    data, control = base/'data', base/'control'
    # No World or checkpoint decode occurs until both exact capacities pass.
    mounts = {'data': mount_info(data, DATA_CAP, 4096),
              'control': mount_info(control, CONTROL_CAP, 128)}
    need(mounts['data']['device'] != mounts['control']['device'] and
         not list(data.iterdir()) and not list(control.iterdir()), 'fresh distinct output mounts required')
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
        stream.write('originals_upload=true\n')
    cpu = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {cpu})
    outcome = {'kind': 'TRUSTED_KIN_CAPTURE_OUTCOME', 'capture_complete': False, 'mounts': mounts,
        'initial_civilizations': 4, 'required_checkpoint_civilizations': 4,
        'configured_horizon': 500, 'requested_checkpoint_turn': 101,
        'requested_capture': [101, 102], 'CPU_affinity': [cpu],
        'old32MiB_sandbox_runtime_leases_wholejob_fit_science': None,
        'output_scope': 'Declared outputs/temp/cache only; unknown HOME/filesystem writes outside these mounts are not bounded here.'}
    checkpoint = data/'warmup/checkpoint_turn_101.ckpt'
    try:
        recorded = json.loads(build.read_bytes())
        identity, schemas = verified(wheels)
        need(recorded['kind'] == 'trusted-kin-current-build-v1' and
             recorded['actual_job'] == 'kin-capture' and recorded['identity'] == identity and
             recorded['raw_schemas'] == schemas, 'same-source fresh installed wheel/schema identity')
        put(control/'identity.json', identity, 65536)
        put(control/'schemas.json', schemas, 192*1024)
        outcome['before_generation_admission'] = host_admission()
        (data/'warmup').mkdir()
        for name in ('tmp', 'cache', 'cache/mpl'):
            (data/name).mkdir(exist_ok=True)
        env = {**os.environ, 'PYTHONPATH': str(ROOT/'src')+os.pathsep+str(ROOT),
            'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(data/'tmp'),
            'TMP': str(data/'tmp'), 'TEMP': str(data/'tmp'),
            'XDG_CACHE_HOME': str(data/'cache'), 'MPLCONFIGDIR': str(data/'cache/mpl')}
        generation = [sys.executable, '-X', 'cpu_count=1', '-B', '-m', 'chronicler.main',
            '--seed', '42', '--turns', '500', '--civs', '4', '--regions', '8',
            '--worldgen', 'template', '--agents', 'hybrid', '--agent-scale-mode', 'exact',
            '--validation-sidecar', '--simulate-only', '--narrator', 'local', '--state-every', '500',
            '--interactive', '--pause-every', '101', '--checkpoint-turns', '101',
            '--output', str(data/'warmup/chronicle.md'), '--state', str(data/'warmup/state.json')]
        observed = phase('generation', generation, control, env, b'quit\n')
        outcome['generation_passed'] = observed['passed']
        need(observed['passed'], 'generation did not complete successfully; capture not attempted')
        regular(checkpoint, 64*MIB)
        outcome['checkpoint'] = digest(checkpoint)
        need(cp_gate(checkpoint, control) == outcome['checkpoint'], 'checkpoint changed during header gate')
        first = census(data, 4096)
        put(control/'generation-census.json', first, 3*MIB)
        need(first['file_bytes']-outcome['checkpoint']['bytes'] <= 128*MIB and
             first['file_bytes'] <= 256*MIB and first['available_bytes'] >= 240*MIB,
             'generation output envelope/complete future capture reservation failed')
        freeze_tree(data/'warmup')
        outcome['before_capture_admission'] = host_admission()
        need(mount_info(data, DATA_CAP, 4096) == mounts['data'] and
             mount_info(control, CONTROL_CAP, 128) == mounts['control'],
             'output mounts changed before resumed World phase')
        after_identity, after_schemas = verified(wheels)
        need(after_identity == identity and after_schemas == schemas, 'runtime changed before capture')
        capture = [sys.executable, '-X', 'cpu_count=1', '-B',
            str(ROOT/'scripts/capture_kin_root_exposure.py'), '--enable-acquisition',
            '--checkpoint', str(checkpoint), '--output', str(data/'kin-capture')]
        captured = phase('capture', capture, control, env)
        outcome['capture_passed'] = captured['passed']
        need(captured['passed'], 'capture actual command failed')
        receipt = json.loads((data/'kin-capture/receipt.json').read_bytes())
        exposure = json.loads((data/'kin-capture/exposure.json').read_bytes())
        need(receipt['status'] == 'captured' and receipt['source_turn'] == 101 and
             receipt['checkpoint'] == outcome['checkpoint'] and
             digest(checkpoint) == outcome['checkpoint'], 'complete one-turn/parent checkpoint join failed')
        need(exposure['status'] == 'complete_capture', 'partial frame is not complete acquisition')
        final = census(data, 4096)
        capture_files = {k: v for k, v in final['files'].items() if k.startswith('kin-capture/')}
        driver_bytes = sum(v['bytes'] for k, v in capture_files.items() if '/' not in k[len('kin-capture/'):])
        exports = sum(v['bytes'] for k, v in capture_files.items() if k.startswith('kin-capture/run/'))
        need(driver_bytes < 34*MIB and exports <= 192*MIB, 'driver/resume export envelope exceeded')
        outcome.update({'capture_complete': True, 'capture_status': exposure['status'],
            'checkpoint_civilizations': 4, 'completed_capture_turn': 102,
            'driver_file_bytes': driver_bytes, 'ordinary_resume_export_bytes': exports,
            'cohort_and_wire_scope': 'Member-selected current-source first decision; no historical membership, causal RR or temporal effect qualification.'})
    except BaseException as exc:
        outcome['error'] = {'type': type(exc).__name__, 'reason': str(exc)[:512]}
    # Separate controls can record data-ENOSPC, resource failures and partial originals.
    try:
        freeze_tree(data)
        final = census(data, 4096)
        put(control/'final-data-census.json', final, 3*MIB)
        control_before = census(control, 128)
        put(control/'census-summary.json', {'data': summary(final),
            'control_before_final_records': summary(control_before),
            'combined_hard_capacity_bytes': DATA_CAP+CONTROL_CAP,
            'controls_final_census_is_a_prior_snapshot': True}, 65536)
        outcome['final_data'] = summary(final)
        outcome['overall_success_also_requires'] = 'actual owner exit0, selected manifest and final whole-output accounting'
        put(control/'outcome.json', outcome, 16384)
        destination = selected(control, data, outcome)
        final_accounting(control, destination, final)
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
            stream.write('selected_upload=true\n')
    finally:
        freeze_tree(data)
        freeze_tree(control)
    print(json.dumps({'passed': outcome['capture_complete'], 'generation_passed': outcome.get('generation_passed'),
        'capture_passed': outcome.get('capture_passed'), 'scope': 'trusted current first-decision only'}))
    return 0 if outcome['capture_complete'] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('record-wheel', 'run'))
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--wheel-dir', type=Path, required=True)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    need(args.execute, 'explicit hosted execution required')
    context()
    if args.command == 'record-wheel':
        record(args.wheel_dir, args.output)
        return 0
    return run(args.wheel_dir, args.build, args.output)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'passed': False, 'owner_failure': type(exc).__name__}))
        raise SystemExit(2)
