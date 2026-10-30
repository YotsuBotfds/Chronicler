"""Opt-in trusted hosted functional checks; no import-time native operations.

This custom job reuses the lower-level native wheel verifier. It does not claim
standard native-producer eligibility, sandbox containment or32MiB owner fit.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.machinery import EXTENSION_SUFFIXES, ExtensionFileLoader
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

RUN_REF = 'refs/heads/lead/native-functional-smoke-20261030'
CLASSES = ('AgentSimulator', 'EcologySimulator', 'PoliticsSimulator')
SELECTORS = (
    'tests/test_decision_delivery_native.py::test_decision_delivery_api_configuration_is_transient_and_keeps_recorded_schema',
    'tests/test_decision_delivery_moves_native.py::test_move_delivery_api_keeps_old_positional_and_three_batch_schema_contract',
)
MIB = 1024**2
CAPS = {'before.bin': MIB, 'after.bin': MIB, 'observation.json': MIB//2,
        'contracts.xml': 65536, 'smoke.log': 2*MIB, 'metrics.txt': 4096,
        'failure.json': 16384, 'outcome.json': 16384, 'manifest.json': 16384}
ROOT = Path(__file__).resolve().parents[1]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(body):
    return hashlib.sha256(body).hexdigest()


def raw(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def write(path, body, limit):
    require(type(body) is bytes and len(body) <= limit, 'output bound')
    with path.open('xb') as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o444)


def context():
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and
            os.environ.get('GITHUB_REF') == RUN_REF, 'explicit hosted run ref required')
    require(os.environ.get('GITHUB_JOB') == 'native-functional', 'wrong custom smoke job')


def verified_identity(wheel_dir):
    # Deliberately do not call record-build or spoof GITHUB_JOB eligibility.
    from native_ci_shards import current_identity
    identity = current_identity(wheel_dir)
    import chronicler_agents as package
    import chronicler_agents.chronicler_agents as native
    require(type(native.__loader__) is ExtensionFileLoader and
            str(native.__file__).endswith(tuple(EXTENSION_SUFFIXES)), 'compiled origin')
    require(all(isinstance(getattr(package, n, None), type) and
                getattr(package, n) is getattr(native, n, None) for n in CLASSES),
            'real package/compiled class identity')
    require(Path(native.__file__).is_relative_to(Path(sys.prefix)), 'fresh environment origin')
    require(identity['wheel']['installed_native']['sha256'] ==
            sha(Path(native.__file__).read_bytes()), 'installed body identity')
    return identity, package


def record(wheel_dir, output):
    wheels = list(wheel_dir.glob('*.whl'))
    require(len(wheels) == 1 and wheels[0].stat().st_size <= 8*MIB, 'one bounded fresh wheel')
    identity, _ = verified_identity(wheel_dir)
    value = {'kind': 'trusted-native-functional-build-v1', 'identity': identity,
             'actual_job': os.environ['GITHUB_JOB'],
             'verifier': 'native_ci_shards.current_identity/native_wheel_receipt.wheel_receipt',
             'standard_native_producer_admission_claim': False}
    write(output, raw(value), 65536)
    require(sum(p.stat().st_size for p in output.parent.rglob('*') if p.is_file()) <= 9*MIB,
            '9MiB builder artifact bound')
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
        stream.write('build_upload=true\n')


def schemas(package):
    result = {}
    for name in CLASSES:
        value = getattr(package, name).checkpoint_schema()
        require(type(value) is tuple and len(value) == 3 and
                type(value[0]) is int and 0 < value[0] < 2**32 and
                type(value[1]) is str and re.fullmatch('[0-9a-f]{16}', value[1]) and
                type(value[2]) is str and 0 < len(value[2].encode()) <= 65536,
                'complete raw schema tuple')
        result[name] = list(value)
    return result


def empty_api(package):
    # One direct empty instance. The selected existing tests add one each.
    sim = package.AgentSimulator(1, 42)
    baseline = sim.checkpoint_state()
    require(type(baseline) is bytes and 0 < len(baseline) <= MIB, 'initial state bound')
    comparisons, getters, exceptions = [], [], []

    def stable(label):
        value = sim.checkpoint_state()
        require(type(value) is bytes and value == baseline, 'persistent bytes changed')
        comparisons.append({'label': label, 'bytes': len(value), 'sha256': sha(value)})

    def fresh(label):
        for ordinal in range(3):
            require(sim.get_health_care_observation() is None, 'fresh getter not None')
            getters.append({'label': label, 'ordinal': ordinal, 'is_none': True})
        stable(label)

    def reject(label, error, call):
        try:
            call()
        except Exception as exc:
            require(type(exc) is error, 'exact exception type')
            exceptions.append({'label': label, 'type': error.__name__})
        else:
            raise ValueError('invalid API input accepted')
        stable(label)

    fresh('fresh_default')
    for label, args, kwargs, error in (
        ('digest31', (0, b'x'*31), {}, ValueError),
        ('digest33', (0, b'x'*33), {}, ValueError),
        ('turns0', (0, b'x'*32), {'turns': 0}, ValueError),
        ('turns33', (0, b'x'*32), {'turns': 33}, ValueError),
        ('end_overflow', (2**32-1, b'x'*32), {'turns': 32}, ValueError),
        ('start_negative', (-1, b'x'*32), {}, OverflowError),
        ('start_u32_overflow', (2**32, b'x'*32), {}, OverflowError),
        ('turns_negative', (0, b'x'*32), {'turns': -1}, OverflowError),
        ('turns_u32_overflow', (0, b'x'*32), {'turns': 2**32}, OverflowError),
        ('turns_positional', (0, b'x'*32, 1), {}, TypeError),
        ('digest_none', (0, None), {}, TypeError),
    ):
        reject(label, error, lambda: sim.configure_health_care_observation(*args, **kwargs))
    fresh('after_invalid_configurations')
    require(sim.configure_health_care_observation(0, b'Z'*32) is True, 'default configuration')
    stable('configured_default32')
    fresh('configured_before_preparation')
    reject('duplicate_configuration', ValueError,
           lambda: sim.configure_health_care_observation(0, b'Z'*32, turns=32))
    require(sim.prepare_health_work([], [], [], .5, .2) == [], 'legacy five arguments')
    stable('legacy_five_prepared')
    reject('invalid_policy', ValueError,
           lambda: sim.prepare_health_work([], [], [], .5, .2, care_policy='kin'))
    require(sim.prepare_health_work([], [], [], .5, .2, care_policy='retained_kin') == [],
            'retained policy keyword')
    stable('retained_keyword_prepared')
    reject('policy_keyword_only', TypeError,
           lambda: sim.prepare_health_work([], [], [], .5, .2, 'retained_kin'))
    final = sim.checkpoint_state()
    require(type(final) is bytes and final == baseline, 'final persistent equality')
    return {'empty_constructor': [1, 42], 'fresh_getters': getters,
            'rejections': exceptions, 'persistent_comparisons': comparisons,
            'full_serialized_equality': True}, baseline, final


def child_limits():
    resource.setrlimit(resource.RLIMIT_CPU, (24, 24))
    # Only JUnit is written by the child; its diagnostics use the bounded pipe.
    resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))


def contracts(output, deadline):
    command = [sys.executable, '-X', 'cpu_count=1', '-B', '-m', 'pytest', '-q',
               '--tb=short', '-p', 'no:cacheprovider', *SELECTORS,
               '--basetemp='+str(output/'pytest'), '--junitxml='+str(output/'contracts.xml')]
    env = {**os.environ, 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
           'PYTHONDONTWRITEBYTECODE': '1'}
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, preexec_fn=child_limits)
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    try:
        while True:
            require(time.monotonic() < deadline, 'functional deadline')
            block = process.stdout.read(16384)
            if not block:
                break
            require(os.fstat(1).st_size+len(block) < 2*MIB, 'joint2MiB diagnostics bound')
            sys.stdout.buffer.write(block)
            sys.stdout.buffer.flush()
        require(process.wait(timeout=max(.01, deadline-time.monotonic())) == 0,
                'selected native contracts failed')
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
    junit = output/'contracts.xml'
    require(junit.stat().st_size <= 65536, 'JUnit bound')
    tree = ET.fromstring(junit.read_bytes())
    cases = list(tree.iter('testcase'))
    actual = [(c.get('classname'), c.get('name')) for c in cases]
    expected = [(n.split('::')[0][:-3].replace('/', '.'), n.split('::')[1]) for n in SELECTORS]
    require(actual == expected and len(cases) == 2 and
            not any(list(tree.iter(n)) for n in ('failure', 'error', 'skipped')) and
            sum(int(s.get('tests')) for s in tree.iter('testsuite')) == 2,
            'exact two passes required; skips are not success')
    junit.chmod(0o444)
    return {'selectors': list(SELECTORS), 'passed': 2, 'skipped': 0,
            'raw_JUnit_retained': True, 'detailed_phase_event_stream_retained': False}


def run(wheel_dir, build, output):
    start = time.monotonic()
    cpu = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {cpu})
    resource.setrlimit(resource.RLIMIT_CPU, (5, 30))
    resource.setrlimit(resource.RLIMIT_AS, (2*1024**3, 2*1024**3))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2*MIB, 2*MIB))
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('105s smoke deadline')))
    signal.alarm(105)
    require(output.is_dir() and output.is_absolute() and
            {p.name for p in output.iterdir()} <= {'smoke.log', 'metrics.txt'}, 'fresh smoke output')
    require(stat_log(output/'smoke.log') == (os.fstat(1).st_dev, os.fstat(1).st_ino) ==
            (os.fstat(2).st_dev, os.fstat(2).st_ino), 'one joint regular diagnostic log')
    recorded = json.loads(build.read_bytes())
    require(recorded['kind'] == 'trusted-native-functional-build-v1', 'custom build kind')
    identity, package = verified_identity(wheel_dir)
    require(identity == recorded['identity'] and recorded['actual_job'] == os.environ['GITHUB_JOB'],
            'fresh same-source/job wheel identity')
    before_schema = schemas(package)
    api, before, after = empty_api(package)
    require(schemas(package) == before_schema, 'raw schemas changed')
    write(output/'before.bin', before, MIB)
    write(output/'after.bin', after, MIB)
    selected = contracts(output, start+104)
    require(os.fstat(1).st_size < 2*MIB, 'diagnostic cap reached')
    report = {'kind': 'trusted-hosted-native-functional-smoke-v1', 'state': 'PASS',
              'identity': identity, 'raw_schemas': before_schema, 'empty_API': api,
              'capture_interface_contracts': selected,
              'simulator_instances_in_declared_paths': 3,
              'instance_basis': 'one empty instance plus one in each source-checked direct native fixture',
              'Worlds': 0, 'ticks': 0, 'checkpoint_decodes_or_restores': 0,
              'capture_status': 'interface_available_without_turn',
              'actual_capture_or_historical_Kin_exposure': None,
              'persistent_before': {'bytes': len(before), 'sha256': sha(before)},
              'persistent_after': {'bytes': len(after), 'sha256': sha(after)},
              'functional_wall_before_report_seconds': time.monotonic()-start,
              'AS_bytes_per_process': 2*1024**3, 'CPU_affinity': [cpu],
              'sandbox_runtime_lease32MiB_owner_World_science_main_qualification': None}
    write(output/'observation.json', raw(report), CAPS['observation.json'])
    signal.alarm(0)


def stat_log(path):
    import stat
    s = path.lstat()
    require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'regular unique log')
    return s.st_dev, s.st_ino


def seal(output, actual_exit):
    require(output.is_dir(), 'missing functional output')
    files = {}
    for path in output.iterdir():
        if path.is_dir() and path.name == 'pytest':
            continue  # pytest-private runtime cost, not retained smoke artifact.
        require(path.name in CAPS and path.is_file() and not path.is_symlink() and
                path.stat().st_nlink == 1 and path.stat().st_size <= CAPS[path.name],
                'fixed artifact role/size')
        files[path.name] = {'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes())}
    require('metrics.txt' in files and 'smoke.log' in files, 'missing actual diagnostics/measurement')
    metrics = dict(line.split('=', 1) for line in (output/'metrics.txt').read_text().splitlines() if '=' in line)
    require(metrics.get('measurement') == 'GNU_time_functional_command_tree' and
            metrics.get('wrapper_and_build_overhead') == 'excluded', 'measurement scope')
    measured = [float(metrics[k]) for k in ('user_seconds', 'system_seconds', 'elapsed_seconds')]
    require(all(0 <= v < float('inf') for v in measured) and
            sum(measured[:2]) <= 30 and measured[2] <= 110, 'functional resource excess')
    if actual_exit == 0:
        require(json.loads((output/'observation.json').read_bytes())['state'] == 'PASS' and
                (output/'before.bin').read_bytes() == (output/'after.bin').read_bytes() and
                metrics.get('exit_code') == '0', 'complete functional success')
    result = {'kind': 'trusted-functional-outcome', 'actual_exit_code': actual_exit,
              'passed': actual_exit == 0, 'measurement': metrics,
              'scope': 'Installed functional/schema/interface only; no sandbox,32MiB owner, World or science claim'}
    write(output/'outcome.json', raw(result), CAPS['outcome.json'])
    files['outcome.json'] = {'bytes': (output/'outcome.json').stat().st_size,
                             'sha256': sha((output/'outcome.json').read_bytes())}
    write(output/'manifest.json', raw({'files': files, 'self_excluded_only': 'manifest.json'}),
          CAPS['manifest.json'])
    require(sum(p.stat().st_size for p in output.iterdir() if p.is_file()) <= 5*MIB,
            '5MiB smoke artifact bound')
    for name in CAPS:
        if (output/name).is_file():
            (output/name).chmod(0o444)
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
        stream.write('smoke_upload=true\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('record-wheel', 'run', 'seal'))
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--wheel-dir', type=Path)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--actual-exit', type=int)
    args = parser.parse_args()
    require(args.execute, 'explicit hosted execution required')
    context()
    if args.command == 'record-wheel':
        record(args.wheel_dir, args.output)
    elif args.command == 'run':
        try:
            run(args.wheel_dir, args.build, args.output)
        except BaseException as exc:
            try:
                write(args.output/'failure.json', raw({'kind': 'functional-smoke-negative',
                      'exception': type(exc).__name__, 'reason': str(exc)[:512],
                      'sandbox_or32MiB_qualification': None}), CAPS['failure.json'])
            except BaseException:
                pass
            return 2
    else:
        require(type(args.actual_exit) is int and 0 <= args.actual_exit <= 255, 'actual command exit')
        seal(args.output, args.actual_exit)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
