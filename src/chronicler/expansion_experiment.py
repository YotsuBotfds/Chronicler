"""Validated experiment controls applied after normal run configuration.

An explicit request can change only the registered controls of one enabled
expansion system, including validated finite-research activation/pause within
enabled science. It cannot replace state, advance time, enable a host system
or alter native inputs directly. Ordinary runs never import this module.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re

from chronicler.artifact_io import strict_json_dumps

SCHEMA_VERSION = 1
CONTROL_FIELDS = {
    "harvest_forecasts": ("policy",),
    "ritual_gatherings": ("contact_enabled", "bonds_enabled"),
    "health_care": ("care_enabled", "injury_rate", "impairment", "care_fraction", "recovery_work"),
    "scientific_claims": ("withhold_information", "transmission_enabled", "uninformative_tests", "publication_rule"),
}
_BOOLEAN_CONTROLS = {"care_enabled", "contact_enabled", "bonds_enabled", "withhold_information",
                     "transmission_enabled", "uninformative_tests", "research_enabled"}
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
_REQUEST_FIELDS = {
    "schema_version", "experiment", "cohort", "feature", "arm", "controls", "fork",
    "parent_checkpoint", "registration",
}


def _identifier(value, name):
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"experiment {name} must be a bounded plain identifier")
    return value


def controls_for_state(feature: str, state) -> dict:
    """Copy the complete source-owned control configuration, never episode data."""
    if feature not in CONTROL_FIELDS or state is None:
        raise ValueError("experiment requires an enabled known expansion system")
    result = {name: deepcopy(getattr(state, name)) for name in CONTROL_FIELDS[feature]}
    if feature == "health_care":
        from chronicler.health_care import get_health_care_policy
        policy = get_health_care_policy(state)
        if policy != "spouse":
            result["care_policy"] = policy
    return result


def allowed_control_fields(feature: str) -> set[str]:
    """Actual request controls; research metadata is never a mutable field."""
    return (set(CONTROL_FIELDS[feature])
            | ({"research_enabled"} if feature == "scientific_claims" else set())
            | ({"care_policy"} if feature == "health_care" else set()))


def _research_identity(state):
    plan = state.research_agendas
    return ({"mode": "legacy"} if plan is None else
            {"mode": plan.rule, **plan.model_dump(mode="json")})


def _parent_identity(parent, world, *, resumed):
    if parent is None:
        if resumed:
            raise ValueError("an experiment fork requires its parent checkpoint path")
        return None
    if (not resumed or not isinstance(parent, dict) or set(parent) != {"path", "sha256"}
            or not isinstance(parent["path"], str) or not isinstance(parent["sha256"], str)):
        raise ValueError("parent_checkpoint must name the resumed checkpoint path and SHA-256")
    from chronicler.batch_manifest import file_sha256
    from chronicler.run_checkpoint import read_header
    path = Path(parent["path"])
    digest = file_sha256(path)
    if digest != parent["sha256"]:
        raise ValueError("experiment parent checkpoint SHA-256 differs")
    header, _body = read_header(path)
    if header.get("turn") != world.turn or header.get("seed") != world.seed:
        raise ValueError("experiment parent checkpoint seed/turn differs from the restored world")
    return {"path": str(path.resolve()), "sha256": digest, "turn": world.turn,
            "seed": world.seed, "identity": deepcopy(header.get("identity")),
            "flags": deepcopy(header.get("flags")), "exact": header.get("exact") is True}


def apply_expansion_experiment(world, run_config: dict, request: dict, *, resumed: bool) -> dict:
    """Validate first, apply controls once, and return a fully resolved receipt.

    ``execute_run`` calls this after its ordinary fresh/default configuration
    or checkpoint restore. Every resumed request is an explicitly labelled
    intervention fork. With no request, exact continuation preserves the saved
    configuration and receipt without calling this helper.
    """
    if not isinstance(request, dict) or set(request) - _REQUEST_FIELDS:
        raise ValueError("unknown or malformed expansion experiment request")
    if type(request.get("schema_version")) is not int or request["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported expansion experiment schema_version")
    feature = request.get("feature")
    if not isinstance(feature, str) or feature not in CONTROL_FIELDS:
        raise ValueError("unknown expansion experiment feature")
    experiment = _identifier(request.get("experiment"), "name")
    arm = _identifier(request.get("arm"), "arm")
    cohort = request.get("cohort")
    if cohort not in ("development", "confirmatory"):
        raise ValueError("experiment cohort must be development or confirmatory")
    fork = request.get("fork")
    if type(fork) is not bool or fork != bool(resumed):
        raise ValueError("resumed experiment controls require an explicit fork=True request")
    controls = request.get("controls")
    if not isinstance(controls, dict) or set(controls) - allowed_control_fields(feature):
        raise ValueError("unknown experiment control fields")
    for name, value in controls.items():
        if name in _BOOLEAN_CONTROLS and type(value) is not bool:
            raise ValueError(f"experiment control {name} must be a boolean")
        if name not in _BOOLEAN_CONTROLS and name not in ("policy", "publication_rule", "care_policy") and type(value) not in (int, float):
            raise ValueError(f"experiment control {name} must be a finite number")
    state = getattr(world, feature, None)
    before = controls_for_state(feature, state)
    health_policy_receipt = feature == "health_care" and (
        "care_policy" in controls or "care_policy" in before)
    if health_policy_receipt:
        from chronicler.health_care import get_health_care_policy, set_health_care_policy
        before["care_policy"] = get_health_care_policy(state)
    # Pydantic's source-owned schema validates enum choices, finite bounds and
    # existing state. Only control fields are copied back after all validation.
    candidate = type(state).model_validate({**state.model_dump(), **{
        name: value for name, value in controls.items() if name != "research_enabled"}})
    after = controls_for_state(feature, candidate)
    if health_policy_receipt:
        # An explicitly requested return to the omitted legacy value must
        # remain an applied control and appear in both sides of the receipt.
        after["care_policy"] = get_health_care_policy(candidate)
    research_policy = None
    if feature == "scientific_claims" and ("research_enabled" in controls or state.research_agendas is not None):
        from chronicler.scientific_research import set_research_agendas_enabled, validate_state
        # A private candidate host avoids installing a seal before every
        # requested control, archive, parent and registration is validated.
        view = world.model_copy(deep=False)
        view.scientific_claims = candidate
        if world.scholarship is not None:
            view.scholarship = world.scholarship.model_copy(deep=True)
        if "research_enabled" in controls:
            set_research_agendas_enabled(view, controls["research_enabled"])
        elif candidate.research_agendas is not None:
            validate_state(view, allow_absent_host=True)
        research_policy = {"before": _research_identity(state), "after": _research_identity(candidate),
                           "requested_enabled": controls.get("research_enabled")}
    parent = _parent_identity(request.get("parent_checkpoint"), world, resumed=resumed)
    registration = request.get("registration")
    if registration is not None:
        if (not isinstance(registration, dict) or set(registration) != {"path", "sha256"}
                or not isinstance(registration["path"], str)):
            raise ValueError("experiment registration must name a file and its SHA-256")
        from chronicler.batch_manifest import file_sha256
        if file_sha256(Path(registration["path"])) != registration["sha256"]:
            raise ValueError("experiment registration SHA-256 differs")
        registration = deepcopy(registration)
    elif cohort == "confirmatory":
        raise ValueError("confirmatory experiments require a recorded registration file")
    from chronicler.batch_manifest import native_identity, source_identity
    receipt = {
        "schema_version": SCHEMA_VERSION, "experiment": experiment, "cohort": cohort,
        "feature": feature, "arm": arm, "intervention_fork": fork,
        "applied_before_turn": world.turn, "seed": world.seed,
        "controls_before": before, "controls_after": after,
        "parent_checkpoint": parent, "registration": registration,
        "source": source_identity(), "native": native_identity(),
        "previous_experiment": deepcopy(run_config.get("expansion_experiment")),
    }
    if research_policy is not None:
        receipt["research_policy"] = research_policy
    strict_json_dumps(receipt)
    if feature == "health_care" and "care_policy" in controls:
        set_health_care_policy(world, after["care_policy"])
    if "research_enabled" in controls:
        # Invoke the validated API; never setattr a derived mode or lineage.
        set_research_agendas_enabled(world, controls["research_enabled"])
    for name, value in after.items():
        if feature == "health_care" and name == "care_policy":
            continue
        setattr(state, name, value)
    return receipt
