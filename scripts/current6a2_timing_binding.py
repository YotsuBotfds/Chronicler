"""Closed metadata joins for the HELD current6a2 external runtime binding.

This module does not authenticate a grant, attest a host or read any filesystem.
Only an independently reviewed trusted launcher can supply authentic authority.
No JSON label, caller digest or successful pure validation creates that authority.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import PurePosixPath
import re

STATIC_POLICY = {
    "kind": "HELD_CURRENT6A2_EXTERNAL_BINDING_STATIC_POLICY_V1",
    "protocol": "current6a2-timing-only-v1",
    "baseline_control_source": "9ca7e7b50e6f1a688a3a8c786f7ed1612d79579b",
    "producer_source": "6a2a7b84b7d6ea10bfa4f6574e1f5dc793c092e8",
    "builder_source_digest": "513b1087cfb977306df70075118b78c082644f2bade337c68934d08b6b318a53",
    "original_artifact": {
        "run_id": 40939929535, "attempt": 1, "artifact_id": 12925919179,
        "archive": {"bytes": 3882533, "sha256": "eb0182b8942cc3132ea62ce63e09c47d80fd9ab68d39e365ec3d41512f4519c9"},
        "build_reference": {"bytes": 1957, "sha256": "22876973493cf07d136b2ab5c9033be0a0d916e209f324fe0d494877e8e4c7b6"},
        "wheel": {"bytes": 3947205, "sha256": "a68aac26f4c5571034f10352db8b44da99acfa66aa378d1a5d90f13fc48082fc"},
        "native": {"bytes": 13765672, "sha256": "1ec3282dd43bc1ecfa2459960f19047aec5d8744406b5655aef44202585eaf72"}},
    "baseline_fake_qualification": {"bytes": 2105, "sha256": "affce04108340771b89ca319237593ebf11b9dacdfe73952d3db9569db1cdaa3"},
    "document_limits": {"registration": 1048576, "policy": 65536, "grant": 65536,
                        "envelope": 65536, "input": 1048576, "environment": 1048576, "job_clock": 65536},
    "external_leaf_names": {"grant": "root-grant.json", "envelope": "runtime-binding.json",
                            "input": "input-admission.json", "environment": "environment-admission.json",
                            "job_clock": "job-clock.json"},
    "root_fields": ["control_root", "producer_root", "native_prefix", "admission_root", "input_root", "output_root"],
    "run_fields": ["run_id", "job_id", "attempt", "nonce"],
    "static_fields": ["control_source", "registration", "policy"],
    "grant_fields": ["kind", "protocol", "static", "roots", "run", "receipts", "execution_approval",
                     "job_clock_admission_approval", "baseline_fake_qualification", "binding_fake_qualification"],
    "envelope_fields": ["kind", "protocol", "static", "roots", "run", "grant", "receipts"],
    "input_fields": ["kind", "control_source", "producer_source", "run_id", "job_id", "attempt", "nonce",
                     "source_root", "native_prefix", "qualified_CI_run", "qualified_CI_attempt", "artifact_id",
                     "archive", "build_reference", "wheel", "native", "builder_source_digest",
                     "official_origin_expiry_reauthenticated", "installed_native_file", "wheel_file",
                     "expires_at", "environment_receipt"],
    "environment_fields": ["kind", "control_source", "producer_source", "run_id", "job_id", "attempt", "nonce",
                           "source_root", "native_prefix", "manifests", "admission_source_review_sha256"],
    "environment_manifest_fields": ["interpreter", "system_dynamic_libraries", "startup", "dependency_wheels",
                                    "installed_prefix", "all_owned_write_roots"],
    "job_clock_fields": ["kind", "approval", "control_source", "producer_source", "run_id", "job_id", "attempt",
                         "nonce", "job_deadline_monotonic", "monotonic_observed", "publication_reserve_seconds"],
    "actual_job_maximum_seconds": 2700, "publication_reserve_seconds": 105,
    "trust_boundary": "HELD authenticating launcher; caller CLI digests and JSON labels confer no authority",
    "one_attempt": "Attempt1 and one exact run/job/nonce; real nonce consumption and replay prevention remain HELD",
    "environment_manifest_bodies_and_ownership_attestation": None,
    "installer_quota_and_original_body_custody": None,
}


class Refused(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Refused(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def pin(raw):
    require(type(raw) is bytes, "exact bytes")
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def fields(value, names, message):
    require(type(value) is dict and all(type(name) is str for name in value)
            and set(value) == set(names), message)


def integer(value, low=1, high=2**63-1):
    require(type(value) is int and low <= value <= high, "exact integer")


def text(value, maximum=1024):
    require(type(value) is str, "bounded exact string")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError as exc:
        raise Refused("invalid UTF-8 text") from exc
    require(0 < size <= maximum, "bounded exact string")


def digest(value, width=64):
    require(type(value) is str and re.fullmatch("[0-9a-f]{" + str(width) + "}", value), "complete lowercase digest")


def validate_pin(value, maximum=2**63-1):
    fields(value, ("bytes", "sha256"), "closed body pin")
    integer(value["bytes"], high=maximum)
    digest(value["sha256"])


def path(value):
    text(value)
    parsed = PurePosixPath(value)
    require(value.startswith("/") and not value.startswith("//") and value != "/" and str(parsed) == value
            and ".." not in parsed.parts and "\x00" not in value, "canonical absolute root/path")
    return parsed


def json_object(raw, limit, *, canonical_only=True):
    require(type(raw) is bytes and len(raw) <= limit, "bounded document bytes")
    def pairs(rows):
        value = {}
        for name, child in rows:
            require(name not in value, "duplicate JSON key")
            value[name] = child
        return value
    def invalid(_value):
        raise Refused("nonfinite JSON")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise Refused("invalid JSON document") from exc
    require(type(value) is dict, "document object")
    stack, visited = [(value, 0)], 0
    while stack:
        child, depth = stack.pop()
        visited += 1
        require(visited <= 20000 and depth <= 16, "finite document structure")
        if type(child) is dict:
            stack.extend((item, depth+1) for item in child.values())
        elif type(child) is list:
            stack.extend((item, depth+1) for item in child)
        elif type(child) is float:
            require(math.isfinite(child), "finite JSON float")
    require(not canonical_only or canonical(value) == raw, "exact canonical document bytes")
    return value


def validate_run(value):
    fields(value, STATIC_POLICY["run_fields"], "closed actual run/job/attempt/nonce")
    integer(value["run_id"]); integer(value["job_id"])
    integer(value["attempt"], 1, 1)
    digest(value["nonce"])


def validate_roots(value):
    fields(value, STATIC_POLICY["root_fields"], "closed independently admitted physical roots")
    roots = [path(item) for item in value.values()]
    require(all(left != right and not left.is_relative_to(right) and not right.is_relative_to(left)
                for i, left in enumerate(roots) for right in roots[i+1:]), "disjoint admitted roots")


def validate_static(value):
    fields(value, STATIC_POLICY["static_fields"], "closed precommitted source/registration/policy")
    digest(value["control_source"], 40)
    validate_pin(value["registration"], STATIC_POLICY["document_limits"]["registration"])
    validate_pin(value["policy"], STATIC_POLICY["document_limits"]["policy"])


def authority_reference(raw):
    """Parse an ALREADY authenticated launcher's reference; never authenticate it."""
    value = json_object(raw, 65536)
    fields(value, ("kind", "grant", "static", "roots", "run"), "closed trusted-launcher reference")
    require(value["kind"] == "AUTHENTICATED_CURRENT6A2_LAUNCHER_REFERENCE_V1", "launcher reference kind")
    validate_pin(value["grant"], 65536); validate_static(value["static"])
    validate_roots(value["roots"]); validate_run(value["run"])
    return value


def validate_bundle(documents, authority_raw, observed_raw):
    """Pure closed joins. Its return is metadata, never evidence of authentication."""
    fields(documents, STATIC_POLICY["document_limits"], "closed seven-document bundle")
    values = {name: json_object(documents[name], limit, canonical_only=name != "registration")
              for name, limit in STATIC_POLICY["document_limits"].items()}
    pins = {name: pin(raw) for name, raw in documents.items()}
    require(documents["policy"] == canonical(STATIC_POLICY), "exact precommitted static policy")
    authority = authority_reference(authority_raw)
    observed = json_object(observed_raw, 65536)
    fields(observed, ("static", "roots", "run", "execution_approval", "job_clock_admission_approval",
                      "envelope", "now_monotonic"), "closed caller-observed context")
    validate_static(observed["static"]); validate_roots(observed["roots"]); validate_run(observed["run"])
    validate_pin(observed["envelope"], 65536)
    text(observed["execution_approval"]); text(observed["job_clock_admission_approval"])
    now = observed["now_monotonic"]
    require(type(now) in (int, float) and math.isfinite(now) and now >= 0, "actual current monotonic domain")
    require(authority["static"] == observed["static"] and authority["roots"] == observed["roots"]
            and authority["run"] == observed["run"] and authority["grant"] == pins["grant"],
            "authenticated launcher/current source roots job grant join")
    require(observed["static"]["registration"] == pins["registration"]
            and observed["static"]["policy"] == pins["policy"]
            and observed["envelope"] == pins["envelope"], "actual immutable static/envelope bytes")
    registration = values["registration"]
    require(registration.get("producer_source") == STATIC_POLICY["producer_source"]
            and registration.get("runtime_input_admission_sha256") is None
            and registration.get("job_clock_admission_sha256") is None,
            "immutable registration contains no future runtime hashes")
    descriptor = registration.get("runtime_binding_policy")
    fields(descriptor, ("path", "bytes", "sha256"), "closed static policy descriptor")
    validate_pin({key: descriptor[key] for key in ("bytes", "sha256")}, 65536)
    require(descriptor == {
        "path": "docs/experiments/current6a2-timing-binding-policy.json", **pins["policy"]},
        "current registration pins the static policy body")
    grant, envelope = values["grant"], values["envelope"]
    fields(grant, STATIC_POLICY["grant_fields"], "closed authenticated grant schema")
    fields(envelope, STATIC_POLICY["envelope_fields"], "closed immutable envelope schema")
    require(grant["kind"] == "ROOT_AUTHORIZED_CURRENT6A2_RUNTIME_GRANT_V1"
            and envelope["kind"] == "OWNED_CURRENT6A2_RUNTIME_BINDING_V1"
            and grant["protocol"] == envelope["protocol"] == STATIC_POLICY["protocol"], "binding kinds/protocol")
    for name in ("static", "roots", "run"):
        require(grant[name] == envelope[name] == observed[name], "closed grant/envelope/current " + name)
    for value in (grant, envelope):
        validate_static(value["static"]); validate_roots(value["roots"]); validate_run(value["run"])
    validate_pin(envelope["grant"], 65536)
    require(envelope["grant"] == pins["grant"], "envelope names one exact authenticated grant")
    fields(grant["receipts"], ("input", "environment", "job_clock"), "closed receipt set")
    for name, value in grant["receipts"].items():
        validate_pin(value, STATIC_POLICY["document_limits"][name])
        require(value == pins[name], "exact observed " + name + " receipt bytes")
    fields(envelope["receipts"], ("input", "environment", "job_clock"), "closed envelope receipt set")
    for name, value in envelope["receipts"].items():
        validate_pin(value, STATIC_POLICY["document_limits"][name])
    require(envelope["receipts"] == grant["receipts"], "no quiet receipt rebind")
    for name in ("execution_approval", "job_clock_admission_approval"):
        require(grant[name] == observed[name], "same source review approval")
    validate_pin(grant["baseline_fake_qualification"], 1048576)
    require(grant["baseline_fake_qualification"] == STATIC_POLICY["baseline_fake_qualification"], "exact original165 fake authority")
    validate_pin(grant["binding_fake_qualification"], 1048576)
    for name in ("input", "environment", "job_clock"):
        value = values[name]
        fields(value, STATIC_POLICY[name + "_fields"], "closed " + name + " schema")
        require(value["control_source"] == observed["static"]["control_source"]
                and value["producer_source"] == STATIC_POLICY["producer_source"], "receipt source join")
        current_run = {key: value[key] for key in STATIC_POLICY["run_fields"]}
        validate_run(current_run)
        require(current_run == observed["run"], "receipt actual job/nonce join")
    admitted, environment, clock = values["input"], values["environment"], values["job_clock"]
    for value in (admitted, environment):
        require(value["source_root"] == observed["roots"]["producer_root"]
                and value["native_prefix"] == observed["roots"]["native_prefix"], "receipt physical source/prefix join")
    require(admitted["kind"] == "ROOT_ADMITTED_CURRENT6A2_TIMING_INPUT"
            and environment["kind"] == "ROOT_ADMITTED_CURRENT6A2_ENVIRONMENT_V1"
            and clock["kind"] == "ROOT_ADMITTED_ACTUAL_JOB_DEADLINE", "exact receipt kinds")
    original = STATIC_POLICY["original_artifact"]
    require(type(admitted["qualified_CI_run"]) is int and admitted["qualified_CI_run"] == original["run_id"]
            and type(admitted["qualified_CI_attempt"]) is int and admitted["qualified_CI_attempt"] == 1
            and type(admitted["artifact_id"]) is int and admitted["artifact_id"] == original["artifact_id"], "original6a2 own artifact")
    for name in ("archive", "build_reference", "wheel", "native"):
        validate_pin(admitted[name])
        require(admitted[name] == original[name], "exact original " + name)
    require(admitted["builder_source_digest"] == STATIC_POLICY["builder_source_digest"]
            and admitted["official_origin_expiry_reauthenticated"] is True, "source803 and separate origin dependency")
    require(path(admitted["installed_native_file"]).is_relative_to(path(observed["roots"]["native_prefix"]))
            and path(admitted["wheel_file"]).is_relative_to(path(observed["roots"]["input_root"])), "no arbitrary wheel/native path authority")
    require(type(admitted["expires_at"]) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", admitted["expires_at"]), "explicit UTC expiry")
    validate_pin(admitted["environment_receipt"], 1048576)
    require(admitted["environment_receipt"] == pins["environment"], "input/environment receipt join")
    fields(environment["manifests"], STATIC_POLICY["environment_manifest_fields"], "closed complete environment manifest references")
    for value in environment["manifests"].values():
        validate_pin(value)
    digest(environment["admission_source_review_sha256"])
    require(clock["approval"] == observed["job_clock_admission_approval"], "clock source review join")
    deadline, first = clock["job_deadline_monotonic"], clock["monotonic_observed"]
    require(type(deadline) in (int, float) and type(first) in (int, float)
            and math.isfinite(deadline) and math.isfinite(first)
            and 0 <= first <= now < deadline and deadline-first <= 2700, "same-VM bounded job deadline")
    require(type(clock["publication_reserve_seconds"]) is int
            and clock["publication_reserve_seconds"] == 105, "unchanged publication reserve")
    return {"kind": "TIMING_ONLY_EXTERNAL_BINDING_REFERENCE_V1", "static": observed["static"],
            "roots": observed["roots"], "run": observed["run"], "grant": pins["grant"],
            "envelope": pins["envelope"], "receipts": grant["receipts"],
            "baseline_fake_qualification": grant["baseline_fake_qualification"],
            "binding_fake_qualification": grant["binding_fake_qualification"],
            "external_authentication_qualification": None, "environment_body_qualification": None,
            "quota_enforcement": None, "ordinary_original_custody": None}


def forwarded_arguments(paths, pins, control_source):
    """One fixed explicit argument tuple for every bootstrap/role/hash/compare child."""
    fields(paths, ("grant", "envelope", "input", "environment", "job_clock", "output"), "closed forwarding paths")
    fields(pins, ("grant", "envelope"), "closed forwarded immutable pins")
    for value in paths.values():
        path(value)
    for value in pins.values():
        validate_pin(value, 65536)
    digest(control_source, 40)
    return ["--root-grant", paths["grant"], "--root-grant-sha256", pins["grant"]["sha256"],
            "--runtime-binding", paths["envelope"], "--runtime-binding-sha256", pins["envelope"]["sha256"],
            "--admission", paths["input"], "--environment-admission", paths["environment"],
            "--job-clock", paths["job_clock"], "--output", paths["output"], "--control-source", control_source]
