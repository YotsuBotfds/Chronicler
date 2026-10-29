"""One closed prospective cbf/3ee runtime; no fallback or runtime imports.

Expected checkpoint schemas remain a fail-closed freeze requirement, not a claim
that the completed standard-CI wheel receipt measured checkpoint schemas.
"""
from copy import deepcopy

DEFAULT_POLICY = CLOUD_POLICY = "cloud-cbf-3ee"
NAMES = (DEFAULT_POLICY,)
SOURCE = "cbf6e368ebd218c1f54179bee4accffc1ab2a4c0"
PACKAGE_DIGEST = "1f1c720880e45e0e835e033da216b3deee1f755a497b8e189abaf97c2fe9f656"
REMOTE_REGISTRATION = "docs/experiments/natural-practice-observer-registration-2026-10-29.md"

_EXPECTED_SCHEMAS = {'AgentSimulator': {'version': 1,
                    'fingerprint': 'dcf0c34097c88451',
                    'schema_sha256': '0b792f3ec33ac68605caf7b6d66fa7462c919b52e6f489f0e3dd7fa42f9fba3b'},
 'EcologySimulator': {'version': 1,
                      'fingerprint': '4ab7f8c199b5e5f8',
                      'schema_sha256': 'bf7daf59c53773518770b90f5a5dee5b71e63d2a62d2af6c756922a07a503aff'},
 'PoliticsSimulator': {'version': 1,
                       'fingerprint': 'b1a710f3450f5015',
                       'schema_sha256': '48e27b42f817e0057ad5f15bf2c2e8d8cca072314a9ca666753f2c9341c47395'}}
_PACKAGES = {'numpy': '2.5.4',
 'scipy': '1.18.1',
 'pyarrow': '26.0.0',
 'pydantic': '2.12.5',
 'arro3-core': '0.9.1',
 'chronicler-agents': '0.1.0'}

_ARTIFACT = {'repository': 'YotsuBotfds/Chronicler',
 'id': 12882944002,
 'run_id': 40841527996,
 'control_sha': 'cbf6e368ebd218c1f54179bee4accffc1ab2a4c0',
 'branch': 'lead/research-practice-observer-runner-seam-20261029',
 'name': 'native-wheel-cbf6e368ebd218c1f54179bee4accffc1ab2a4c0',
 'bytes': 3850581,
 'sha256': '9cc55c9dbf7939056f0b0613e3e54e74798a782463719185d41b1fe129ebe2cf',
 'manifest_path': 'ci-native-wheel/manifest.json',
 'manifest_bytes': 944,
 'manifest_sha256': 'b12919544f9ea2d520aeb01efa664c8e436cb887d39d2a543b343c2ee8aa507d',
 'wheel_path': 'chronicler-agents/target/wheels/chronicler_agents-0.1.0-cp313-cp313-manylinux_2_34_x86_64.whl',
 'wheel_bytes': 3915395,
 'wheel_sha256': '556c6677c4cb998cd6ad4b284d0f67a7e79368f86831b458c3885943de3b95ac',
 'native_member': 'chronicler_agents/chronicler_agents.cpython-313-x86_64-linux-gnu.so',
 'native_bytes': 13695168,
 'native_sha256': '3ee06a53b3c16dcba01bc53c8fe1dd97e530754a61d65fe2c1396b158b48e6d0',
 'crate_tree': '912a1a2489f8f8c548df19302bb2c0a4365fc32e',
 'pyproject_sha256': 'd14f5588112927a0d8d889c30f04af90e81bc2cf4096b9ed91d8a51d83a2ac32',
 'lock_sha256': '986547c01fd1dcd9bf598404124fde4ddc1e3d67db9a1d595a5304f18dacee10',
 'python_version': '3.13.17'}


def policy(name=DEFAULT_POLICY):
    if type(name) is not str or name not in NAMES:
        raise ValueError("unregistered practice-study runtime policy")
    return dict(name=name, producer_sha=SOURCE, package_digest=PACKAGE_DIGEST,
        crate_tree=_ARTIFACT["crate_tree"], native_sha256=_ARTIFACT["native_sha256"],
        native_bytes=_ARTIFACT["native_bytes"], python="3.13.17", packages=deepcopy(_PACKAGES),
        schemas=deepcopy(_EXPECTED_SCHEMAS), artifact=deepcopy(_ARTIFACT), execution_registration=REMOTE_REGISTRATION)


def validate_runtime(name, actual, same):
    """Verify recorded or live metadata without loading a native extension."""
    selected = policy(name)
    def require(condition, message):
        if not condition:
            raise ValueError("runtime policy " + message)
    source, native, env = actual["source"], actual["native"], actual["environment"]
    require(source["git_sha"] == selected["producer_sha"] and
            source["package_digest"] == selected["package_digest"], "producer/package differs")
    require(native["status"] == "found" and native["sha256"] == selected["native_sha256"] and
            type(native["bytes"]) is int and native["bytes"] == selected["native_bytes"], "compiled bytes differ")
    require(type(actual["compiled_origin"]) is str and native["module_file"] == actual["compiled_origin"],
            "compiled origin differs")
    require(same(actual["available_compiled_classes"], selected["schemas"]), "class schemas differ")
    require(env["python"] == selected["python"] and env["implementation"] == "CPython" and
            type(env["platform"]) is str and env["platform"].startswith("Linux-") and
            env["machine"] == "x86_64" and type(env["affinity_cpu_count"]) is int and
            env["affinity_cpu_count"] == 1, "Python/platform/affinity differs")
    require(same(env["packages"], selected["packages"]), "locked package versions differ")
    expected_threads = {name: "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS",
        "GOTO_NUM_THREADS", "RAYON_NUM_THREADS", "PYTHON_CPU_COUNT")}
    expected_threads.update(PYTHONHASHSEED="0", OPENBLAS_THREAD_TIMEOUT="16")
    require(set(env["thread_env"]) == set(expected_threads) and
            same(env["thread_env"], {name: expected_threads[name] for name in env["thread_env"]}),
            "thread/hash settings differ")
    return selected
