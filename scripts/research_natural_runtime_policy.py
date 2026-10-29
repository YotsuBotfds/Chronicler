"""Closed prospective runtime policies; no imports, installs or activation."""
from copy import deepcopy

DEFAULT_POLICY = "local-fb20"
CLOUD_POLICY = "cloud-fullgate-06db"
NAMES = (DEFAULT_POLICY, CLOUD_POLICY)
SOURCE = "c76efe8552b4c6c288ebb1f813e2c0a58e5957b1"
PACKAGE_DIGEST = "cdfc449158d36611c751a0f7b4f6c29d594fb95ec6e341d9a7693f219abd5b5c"
REMOTE_REGISTRATION = "docs/experiments/scientific-research-natural-remote-execution-2026-10-29.md"

_SCHEMAS = {
    "AgentSimulator": {
        "version": 1,
        "fingerprint": "dcf0c34097c88451",
        "schema_sha256": "0b792f3ec33ac68605caf7b6d66fa7462c919b52e6f489f0e3dd7fa42f9fba3b"
    },
    "EcologySimulator": {
        "version": 1,
        "fingerprint": "4ab7f8c199b5e5f8",
        "schema_sha256": "bf7daf59c53773518770b90f5a5dee5b71e63d2a62d2af6c756922a07a503aff"
    },
    "PoliticsSimulator": {
        "version": 1,
        "fingerprint": "b1a710f3450f5015",
        "schema_sha256": "48e27b42f817e0057ad5f15bf2c2e8d8cca072314a9ca666753f2c9341c47395"
    }
}
_PACKAGES = {
    "numpy": "2.5.4",
    "scipy": "1.18.1",
    "pyarrow": "26.0.0",
    "pydantic": "2.12.5",
    "arro3-core": "0.9.1",
    "chronicler-agents": "0.1.0"
}
_ARTIFACT = {
    "repository": "YotsuBotfds/Chronicler",
    "id": 12861488234,
    "run_id": 40791402289,
    "control_sha": "27f0f3d11a1a171e1539353eb2c3a0fb896f0939",
    "name": "full-gates-wheel-40791402289-1",
    "bytes": 3767198,
    "sha256": "7483e15561648466bd9b64139b70c67cde7c6d7deaf8697f4f5355d3d3de4faf",
    "manifest_bytes": 3049,
    "manifest_sha256": "013a57c5e59993587acd65eb33c6ff1d16984796de11dbec81df686eb33210d3",
    "wheel_path": "wheels/chronicler_agents-0.1.0-cp313-cp313-manylinux_2_34_x86_64.whl",
    "wheel_bytes": 3831429,
    "wheel_sha256": "049f91bbd03582240491e0c487d560deebb31a2ab9754d2c5bac2a7804206f64",
    "native_member": "chronicler_agents/chronicler_agents.cpython-313-x86_64-linux-gnu.so",
    "native_bytes": 13443872,
    "native_sha256": "06db5e19bdda13d7a536b236d677348f5ea7cb5adad2929962f0485192f9b4d6",
    "crate_tree": "a4703ef4e9a21b5dbb194d318536a46e6ca8b71c",
    "pyproject_sha256": "d14f5588112927a0d8d889c30f04af90e81bc2cf4096b9ed91d8a51d83a2ac32",
    "lock_sha256": "986547c01fd1dcd9bf598404124fde4ddc1e3d67db9a1d595a5304f18dacee10",
    "python_version": "3.13.17"
}


def policy(name=DEFAULT_POLICY):
    if type(name) is not str or name not in NAMES:
        raise ValueError("unregistered natural-research runtime policy")
    cloud = name == CLOUD_POLICY
    return dict(name=name, producer_sha=SOURCE, package_digest=PACKAGE_DIGEST,
        crate_tree=_ARTIFACT["crate_tree"],
        native_sha256=_ARTIFACT["native_sha256"] if cloud else
            "fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317",
        native_bytes=_ARTIFACT["native_bytes"] if cloud else 13446424,
        python="3.13.17" if cloud else "3.13.5", packages=deepcopy(_PACKAGES),
        schemas=deepcopy(_SCHEMAS), artifact=deepcopy(_ARTIFACT) if cloud else None,
        execution_registration=REMOTE_REGISTRATION if cloud else None)


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
