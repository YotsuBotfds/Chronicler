"""Opt-in real POSIX probes for the dormant builder's process ownership.

Run only after source review, in a separate POSIX selection. Set
CHRONICLER_WEALTH_TEST_LEGACY_ROOT to the exact reviewed 27f sparse checkout.
The outer child alone changes subreaper/signal state; pytest never does so.
No compiler, native package, source package, installer or world is executed.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux pidfd/subreaper qualification")
THREAD_ENV = {key: "1" for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "GOTO_NUM_THREADS",
    "RAYON_NUM_THREADS", "PYTHON_CPU_COUNT")}
THREAD_ENV.update(PATH="/usr/bin:/bin", PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0")

GUARDIAN = r'''
import ctypes, json, os, pathlib, signal, subprocess, sys, time
worker_code, controller_path, legacy_root, root_name, case = sys.argv[1:]
root = pathlib.Path(root_name)
libc = ctypes.CDLL(None, use_errno=True)
prior = ctypes.c_int()
assert libc.prctl(37, ctypes.byref(prior), 0, 0, 0) == 0 and prior.value == 0
def children():
    try:
        with pathlib.Path(f'/proc/self/task/{os.getpid()}/children').open('rb') as stream:
            raw = stream.read(65537)
    except FileNotFoundError:
        # Some kernels omit CONFIG_CHECKPOINT_RESTORE's children interface.
        # A bounded PPID scan enumerates visible direct children; a separate
        # WNOWAIT kernel probe below must confirm any empty result.
        values = []
        examined = 0
        for entry in pathlib.Path('/proc').iterdir():
            if entry.name.isascii() and entry.name.isdecimal():
                examined += 1
                assert examined <= 32768, 'guardian proc scan bound'
                row = identity(int(entry.name))
                if row is not None and row['ppid'] == os.getpid():
                    values.append(entry.name)
    else:
        assert len(raw) <= 65536
        values = raw.split()
    assert len(values) <= 64 and all(v.isdigit() for v in values)
    numbers = [int(v) for v in values]
    assert len(set(numbers)) == len(numbers) and all(pid > 0 for pid in numbers)
    if not values:
        try:
            os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        except ChildProcessError:
            return []
        raise AssertionError('guardian child ownership unresolved after empty proc observation')
    return sorted(numbers)
def identity(pid):
    try:
        with pathlib.Path(f'/proc/{pid}/stat').open('rb') as stream:
            raw = stream.read(65537)
        assert len(raw) <= 65536, 'guardian stat byte bound'
        f = raw.rsplit(b')', 1)[1].split()
        birth, ppid = int(f[19]), int(f[1])
        assert int(raw.split(b' ', 1)[0]) == pid and birth >= 0 and ppid >= 0
        return {'birth': birth, 'ppid': ppid}
    except (FileNotFoundError, ProcessLookupError):
        return None
assert children() == []
assert libc.prctl(36, 1, 0, 0, 0) == 0
worker = None
forced = False
extra = set()
error = None
exit_code = None
try:
    with (root / 'guardian-stdout.log').open('wb') as stdout, (root / 'guardian-stderr.log').open('wb') as stderr:
        worker = subprocess.Popen([sys.executable, '-I', '-B', '-c', worker_code,
            controller_path, legacy_root, root_name, case], stdin=subprocess.DEVNULL,
            stdout=stdout, stderr=stderr, start_new_session=True,
            env=os.environ.copy())  # The test launcher supplies only fixed caps/runtime paths.
        deadline = time.monotonic() + 12
        while True:
            ended = os.waitid(os.P_PID, worker.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if ended:
                exit_code = ended.si_status if ended.si_code == os.CLD_EXITED else 128 + ended.si_status
                break
            if time.monotonic() >= deadline:
                forced = True
                break
            time.sleep(.005)
except BaseException as exc:
    error = type(exc).__name__
finally:
    try:
        # The guardian remains a subreaper until every owned generation has
        # exited and been reaped. Killing a direct child causes its remaining
        # descendants to be adopted here, including detached sessions.
        until = time.monotonic() + 5
        while children():
            assert time.monotonic() < until, 'guardian cleanup deadline'
            for pid in children():
                if worker is None or pid != worker.pid:
                    extra.add(pid)
                before = identity(pid)
                if before is not None:
                    assert before['ppid'] == os.getpid(), 'guardian ownership uncertain'
                    try:
                        fd = os.pidfd_open(pid)
                    except ProcessLookupError:
                        fd = None
                    if fd is not None:
                        try:
                            after = identity(pid)
                            if after is not None:
                                assert after == before and pid in children(), 'guardian birth/ownership changed'
                                try:
                                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                                except ProcessLookupError:
                                    pass
                        finally:
                            os.close(fd)
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass
            time.sleep(.005)
        if worker is not None:
            worker.wait(timeout=1)
    finally:
        assert libc.prctl(36, prior.value, 0, 0, 0) == 0
marker = root / 'synthetic-child.json'
generation_present = None
if marker.exists():
    saved = json.loads(marker.read_text())
    current = identity(saved['pid'])
    generation_present = current is not None and current['birth'] == saved['birth']
result = dict(error=error, forced=forced, inner_exit_code=exit_code,
    direct_children_after=children(), extra_adopted_children=len(extra),
    synthetic_generation_still_present=generation_present)
(root / 'guardian.json').write_text(json.dumps(result, sort_keys=True))
'''

WORKER = r'''
import ctypes, importlib.util, json, os, pathlib, resource, signal, sys, threading, time
controller_path, legacy_root, root_name, case = sys.argv[1:]
spec = importlib.util.spec_from_file_location("wealth_floor_process_probe", controller_path)
C = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = C
spec.loader.exec_module(C)
root = pathlib.Path(root_name)
(root / "logs").mkdir()
legacy = C.legacy_helpers(legacy_root)
marker = root / "synthetic-child.json"
usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
started = time.monotonic()
error = None
output = None
supervisor = None
sender = None
sent = []
publication_result = None
previous_handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}

# Every synthetic descendant has its own finite lifetime, even if the code
# under test fails. This is longer than the prompt-cleanup assertion below and
# shorter than the enclosing outer-child timeout.
orphan_payload = r"""
import json, os, pathlib, sys, time
ready_read, ready_write = os.pipe()
child = os.fork()
if child:
    os.close(ready_write)
    os.read(ready_read, 1)
    os._exit(0)
os.close(ready_read)
if sys.argv[2] == 'setsid':
    os.setsid()
raw = pathlib.Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
pathlib.Path(sys.argv[1]).write_text(json.dumps({'pid': os.getpid(), 'birth': int(raw[19])}))
os.write(ready_write, b'1')
os.close(ready_write)
until = time.monotonic() + 15
while time.monotonic() < until:
    time.sleep(.02)
os._exit(0)
"""

if case == 'guardian-fault':
    # Deliberately fail before the inner controller can acquire ownership. The
    # outer guardian must contain this real detached orphan without relying on
    # any controller cleanup code under test.
    os.execv(sys.executable, [sys.executable, '-I', '-B', '-c', orphan_payload, str(marker), 'setsid'])
elif case.startswith('publish-'):
    argv = None
elif case.startswith('cancel-'):
    payload = r"""
import json, os, pathlib, signal, sys, time
marker, terminated = map(pathlib.Path, sys.argv[1:])
first_term = None
def term(sig, frame):
    global first_term
    if first_term is None:
        first_term = time.monotonic()
        terminated.write_text('seen')
signal.signal(signal.SIGTERM, term)
raw = pathlib.Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
marker.write_text(json.dumps({'pid': os.getpid(), 'birth': int(raw[19])}))
until = time.monotonic() + 15
while time.monotonic() < until:
    if first_term is not None and time.monotonic()-first_term > .2:
        break
    time.sleep(.005)
"""
    argv = [sys.executable, '-I', '-B', '-c', payload, str(marker), str(root/'termination-seen')]
    def cancel_during_work_and_cleanup():
        until = time.monotonic() + 3
        while not marker.exists() and time.monotonic() < until:
            time.sleep(.002)
        if not marker.exists():
            sent.append('missing-start-marker')
            return
        first_signal = signal.SIGTERM if case == 'cancel-SIGTERM' else signal.SIGINT
        os.kill(os.getpid(), first_signal)
        sent.append('work')
        until = time.monotonic() + 3
        while not (root/'termination-seen').exists() and time.monotonic() < until:
            time.sleep(.002)
        if (root/'termination-seen').exists():
            os.kill(os.getpid(), signal.SIGINT if first_signal == signal.SIGTERM else signal.SIGTERM)
            sent.append('cleanup')
    sender = threading.Thread(target=cancel_during_work_and_cleanup, daemon=True)
elif case == 'normal':
    payload = "import time\ns=time.process_time()\nwhile time.process_time()-s < .08: pass\nprint('ok')\n"
    argv = [sys.executable, '-I', '-B', '-c', payload]
else:
    argv = [sys.executable, '-I', '-B', '-c', orphan_payload, str(marker), case]
    # Force the initial lease to observe an exited but unreaped leader. This
    # verifies the real WNOWAIT/birth path, not only a comfortably leased child.
    original_stat = legacy.process_stat
    first = True
    def exited_leader_stat(pid):
        global first
        if first:
            first = False
            until = time.monotonic() + 3
            while time.monotonic() < until:
                row = original_stat(pid)
                if row is not None and row['state'] == 'Z':
                    return row
                time.sleep(.001)
            raise AssertionError('synthetic leader did not exit before initial lease')
        return original_stat(pid)
    legacy.process_stat = exited_leader_stat

try:
    with C.Cancellation() as cancellation:
        with C.SubreaperLease() as lease:
            if case.startswith('publish-'):
                publication = root/'publication'; publication.mkdir()
                payload_file = publication/'synthetic-payload.txt'; payload_file.write_bytes(b'unchanged fixture bytes\n')
                payload_hash = C.sha(payload_file)
                expired = False
                original_inventory, original_write = C.inventory, C.write_json
                def inventory_then_expire(*args, **kwargs):
                    global expired
                    result = original_inventory(*args, **kwargs)
                    if case == 'publish-heavy':
                        expired = True
                    return result
                def write_then_expire(path, value):
                    global expired
                    original_write(path, value)
                    if case == 'publish-commit' and pathlib.Path(path).name == 'completion.json' and value.get('publication_complete') is True:
                        expired = True
                C.inventory, C.write_json = inventory_then_expire, write_then_expire
                def check():
                    C.B.require(not expired, 'synthetic publication deadline expiry')
                report = {'status': 'build_complete_pending_job', 'historical_reuse_eligible': True,
                          'candidate_worlds_admitted': False, 'scope': 'synthetic publication fixture only'}
                try:
                    C.publish_complete(publication, report, check, lambda: {
                        'controller_measured_cpu_seconds': time.process_time(), 'scope': 'synthetic fixture'})
                except C.B.BridgeRefused:
                    pass
                else:
                    raise AssertionError('expiry retained positive publication')
                canonical = C.bounded_json(publication/'build-manifest.json')
                completion = C.bounded_json(publication/'completion.json')
                light_manifest = publication/'light/build-manifest.json'
                publication_result = dict(raw_incomplete=canonical['status'] == 'incomplete' and canonical['historical_reuse_eligible'] is False,
                    completion_negative=completion['publication_complete'] is False,
                    light_incomplete=not light_manifest.exists() or C.bounded_json(light_manifest)['historical_reuse_eligible'] is False,
                    payload_preserved=C.sha(payload_file) == payload_hash,
                    superseded_positive_seals=len(list(publication.glob('incomplete-completion.json'))))
            else:
                supervisor = C.make_supervisor(legacy, root, time.monotonic() + 35, lease, cancellation=cancellation)
                # Resource floors belong to actual build admission. These tiny
                # probes exercise lifecycle only and make no live RAM/disk call.
                supervisor.admission = lambda *args, **kwargs: None
                if sender is not None:
                    sender.start()
                output = supervisor.command('synthetic', argv, os.environ.copy(), root)
except BaseException as exc:
    error = type(exc).__name__
if sender is not None:
    sender.join(timeout=3)
usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
subreaper = ctypes.c_int()
assert ctypes.CDLL(None).prctl(37, ctypes.byref(subreaper), 0, 0, 0) == 0
result = dict(error=error, elapsed_seconds=time.monotonic()-started,
    direct_children=C.direct_children(), subreaper_after=subreaper.value,
    output=None if output is None else output.decode(),
    cancellation_signals_sent=sent,
    handlers_restored=all(signal.getsignal(sig) == handler for sig, handler in previous_handlers.items()),
    publication=publication_result,
    waited_children_cpu_seconds=(usage_after.ru_utime+usage_after.ru_stime)-(usage_before.ru_utime+usage_before.ru_stime),
    cleanup_complete=None if supervisor is None else supervisor.cleanup_complete,
    native_or_source_modules=[name for name in sys.modules if name == 'chronicler_agents'
        or name.startswith('chronicler_agents.') or name == 'chronicler' or name.startswith('chronicler.')])
if marker.exists():
    child = json.loads(marker.read_text())
    current = legacy.process_stat(child['pid'])
    result['synthetic_generation_still_present'] = current is not None and current['birth'] == child['birth']
(root / 'outcome.json').write_text(json.dumps(result, sort_keys=True))
'''


def probe(tmp_path, case):
    legacy = os.environ.get("CHRONICLER_WEALTH_TEST_LEGACY_ROOT")
    if not legacy:
        pytest.skip("explicit source-pinned legacy helper checkout required; separate reviewed POSIX lane")
    command = [sys.executable, "-I", "-B", "-c", GUARDIAN, WORKER,
               str(ROOT / "scripts/wealth_floor_native_build_controller.py"), legacy, str(tmp_path), case]
    result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=THREAD_ENV.copy(),
                            start_new_session=True, timeout=30)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")[-4000:]
    guardian = json.loads((tmp_path / "guardian.json").read_text())
    assert guardian['error'] is None
    assert guardian['forced'] is False
    assert guardian['inner_exit_code'] == 0
    assert guardian['direct_children_after'] == []
    if case == 'guardian-fault':
        return guardian
    assert guardian['extra_adopted_children'] == 0
    return json.loads((tmp_path / "outcome.json").read_text())


def test_normal_owned_child_is_reaped_and_waited_cpu_is_truthful(tmp_path):
    result = probe(tmp_path, "normal")
    assert result['error'] is None
    assert result['output'] == 'ok\n'
    assert result['cleanup_complete'] is True
    assert result['waited_children_cpu_seconds'] >= .05
    assert result['direct_children'] == []
    assert result['subreaper_after'] == 0
    assert result['native_or_source_modules'] == []
    assert result['handlers_restored'] is True


def test_guardian_contains_detached_orphan_when_inner_controller_is_bypassed(tmp_path):
    result = probe(tmp_path, 'guardian-fault')
    assert result['extra_adopted_children'] == 1
    assert result['synthetic_generation_still_present'] is False


@pytest.mark.parametrize('case', ['same-session', 'setsid'])
def test_already_exited_leader_orphan_is_cleaned_and_refused(tmp_path, case):
    result = probe(tmp_path, case)
    assert result['error'] is not None
    assert result['elapsed_seconds'] < 3
    assert result['synthetic_generation_still_present'] is False
    assert result['direct_children'] == []
    assert result['subreaper_after'] == 0
    assert result['native_or_source_modules'] == []


@pytest.mark.parametrize('case', ['cancel-SIGTERM', 'cancel-SIGINT'])
def test_repeated_cancellation_during_child_cleanup_is_deferred(tmp_path, case):
    result = probe(tmp_path, case)
    assert result['error'] == 'BridgeRefused'
    assert result['elapsed_seconds'] < 3
    assert result['cancellation_signals_sent'] == ['work', 'cleanup']
    assert result['handlers_restored'] is True
    assert result['cleanup_complete'] is True
    assert result['synthetic_generation_still_present'] is False
    assert result['direct_children'] == []
    assert result['subreaper_after'] == 0
    assert result['native_or_source_modules'] == []


@pytest.mark.parametrize('case', ['publish-heavy', 'publish-commit'])
def test_publication_expiry_invalidates_raw_and_light_positive_paths(tmp_path, case):
    result = probe(tmp_path, case)
    assert result['error'] is None
    assert result['publication']['raw_incomplete'] is True
    assert result['publication']['completion_negative'] is True
    assert result['publication']['light_incomplete'] is True
    assert result['publication']['payload_preserved'] is True
    assert result['publication']['superseded_positive_seals'] == (1 if case == 'publish-commit' else 0)
    assert result['handlers_restored'] is True
    assert result['direct_children'] == []
    assert result['subreaper_after'] == 0
    assert result['native_or_source_modules'] == []
