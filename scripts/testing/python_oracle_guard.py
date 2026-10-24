"""Test-only guard for the selected Python oracle lane; never a product patch."""
from datetime import datetime, timezone
import importlib.abc
import json
import os
from pathlib import Path
import platform
import sys
from types import ModuleType


NATIVE_IMPORT_ATTEMPTS = []
BLOCKED_IO = []
LOCAL_HOSTNAME_READS = 0
REPORTS = {"passed": 0, "failed": 0, "skipped": 0}
FACTORY_CALLS = {"ecology": 0, "politics": 0}


def native_modules():
    result = []
    for name, module in tuple(sys.modules.items()):
        if name == "chronicler_agents" or name.startswith("chronicler_agents."):
            if isinstance(module, ModuleType):
                result.append({"name": name, "file": vars(module).get("__file__")})
    return result


if any(name == "chronicler_agents" or name.startswith("chronicler_agents.") for name in sys.modules):
    raise RuntimeError("Native package was loaded before offline guard")


class HeldNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "chronicler_agents" or fullname.startswith("chronicler_agents."):
            NATIVE_IMPORT_ATTEMPTS.append(fullname)
            raise ModuleNotFoundError("Native runtime is held in this test lane", name=fullname)
        return None


FINDER = HeldNative()
sys.meta_path.insert(0, FINDER)


def audit(event, args):
    global LOCAL_HOSTNAME_READS
    if event == "socket.gethostname":
        # Windows platform.platform() records local host identity for checkpoints.
        # This reads OS metadata; it neither creates a socket nor resolves DNS.
        LOCAL_HOSTNAME_READS += 1
        return
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
        BLOCKED_IO.append(event)
        raise RuntimeError(f"Offline test lane forbids {event}")


# Checkpoints record platform.platform(). On Linux its first call runs
# ``uname -p`` for the processor name; resolve that cached host metadata now,
# before the hook, so no test spawns the process.
platform.platform()
sys.addaudithook(audit)


def no_ecology(world):
    FACTORY_CALLS["ecology"] += 1
    return None


def no_politics(world):
    FACTORY_CALLS["politics"] += 1
    return None


def pytest_configure(config):
    import chronicler.main as main
    main._create_ecology_runtime = no_ecology
    main._create_politics_runtime = no_politics


def pytest_runtest_logreport(report):
    if report.when == "call":
        REPORTS[report.outcome] += 1
    elif report.failed or report.skipped:
        REPORTS[report.outcome] += 1


def pytest_sessionfinish(session, exitstatus):
    import chronicler.main as main
    loaded = native_modules()
    active = FINDER in sys.meta_path and main._create_ecology_runtime is no_ecology and main._create_politics_runtime is no_politics
    if loaded or BLOCKED_IO or not active:
        session.exitstatus = 1
    receipt = {
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "state": "PASS" if not loaded and not BLOCKED_IO and active else "FAILED",
        "guard_active_at_finish": active,
        "main_source": main.__file__,
        "native_modules_loaded": loaded,
        "native_import_attempts_blocked": NATIVE_IMPORT_ATTEMPTS,
        "runtime_factories_replaced_before_collection": True,
        "python_oracle_factory_calls": FACTORY_CALLS,
        "blocked_io_attempts": BLOCKED_IO,
        "local_hostname_metadata_reads": LOCAL_HOSTNAME_READS,
        "test_reports": REPORTS,
        "pytest_exitstatus": int(session.exitstatus),
    }
    with Path(os.environ["CHRONICLER_OFFLINE_GUARD_REPORT"]).open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
