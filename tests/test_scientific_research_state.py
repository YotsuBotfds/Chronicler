"""Lazy research metadata must preserve legacy raw state and enabled archives."""
from __future__ import annotations

from copy import deepcopy
import pickle

import pytest

from chronicler.models import WorldState
from chronicler.scholarship_state import ScholarshipState
from chronicler.scientific_claims_state import AdoptionEffort, ProposalReceipt, ScienceMessage, ScientificClaimsState
from chronicler.scientific_research_state import ResearchAgendas, ResearchCycle
from test_scientific_claims import _world


def _plan():
    return ResearchAgendas(schema_version=1, rule="finite-retained-v1", enabled=True,
        enabled_turn=0, policy_changed_turn=0, next_open_turn=25, origin_cursor=-1, cycles=[], blocked_reason="", blocked_turn=None,
        host_seal="0" * 64, academy_births=[])


def _state():
    state = ScientificClaimsState()
    state._set_research_value(_plan())
    return state


@pytest.mark.parametrize("factory,name", [
    (ScientificClaimsState, "research_agendas"),
    (ScholarshipState, "scientific_research_identity"),
    (lambda: ProposalReceipt(seat=0, claim=0, received_turn=0), "agenda_id"),
    (lambda: ScienceMessage(kind="proposal", record=0, sender=0, recipient=1,
                           sent_turn=0, delivery_turn=1, expires_turn=6, hops=1), "agenda_id"),
    (lambda: AdoptionEffort(seat=0, region=0, recipe="irrigation", share=.5, confidence=.5, paid=1), "claim_id"),
])
def test_legacy_reads_dumps_and_copies_never_add_lazy_state(factory, name):
    value = factory()
    raw = pickle.dumps(value, protocol=5)
    keys, fields = set(value.__dict__), value.__pydantic_fields_set__.copy()
    getattr(value, name)
    assert name not in value.model_dump()
    value.model_dump_json()
    assert pickle.dumps(value, protocol=5) == raw
    assert set(value.__dict__) == keys and value.__pydantic_fields_set__ == fields
    assert deepcopy(value).__dict__ == value.__dict__
    assert not any(key.startswith("_research") or key == "_agenda_id" for key in value.__dict__)


def test_enabled_nested_world_python_json_deepcopy_and_pickle_roundtrip():
    world = _world()
    world.scientific_claims = _state()
    expected = world.model_dump(mode="json")
    for restored in (WorldState.model_validate(world.model_dump()),
                     WorldState.model_validate_json(world.model_dump_json()),
                     pickle.loads(pickle.dumps(world, protocol=5)), world.model_copy(deep=True)):
        assert restored.model_dump(mode="json") == expected
        assert restored.scientific_claims.research_agendas is not None
        restored.scientific_claims.research_agendas.next_open_turn = 50
        assert world.scientific_claims.research_agendas.next_open_turn == 25


@pytest.mark.parametrize("enabled", [True, False])
def test_nested_metadata_and_experiment_style_reconstruction_preserve_data_and_input(enabled):
    state = _state()
    state.research_agendas.enabled = enabled
    proposal = ProposalReceipt(seat=0, claim=0, received_turn=0)
    proposal._set_research_value(2)
    message = ScienceMessage(kind="proposal", record=0, sender=0, recipient=1,
                           sent_turn=25, delivery_turn=26, expires_turn=31, hops=1)
    message._set_research_value(2)
    state.proposals.append(proposal)
    state.messages.append(message)
    data = state.model_dump()
    before = deepcopy(data)
    rebuilt = type(state).model_validate({**data, "withhold_information": True})
    assert data == before
    assert rebuilt.research_agendas.model_dump() == state.research_agendas.model_dump()
    assert rebuilt.research_agendas.enabled is enabled
    assert rebuilt.proposals[0].agenda_id == rebuilt.messages[0].agenda_id == 2
    assert rebuilt.model_dump()["proposals"][0]["agenda_id"] == 2
    assert rebuilt.model_dump()["messages"][0]["agenda_id"] == 2


def test_serialization_selection_omits_or_filters_lazy_payload_without_leaking():
    state = _state()
    assert "research_agendas" not in state.model_dump(exclude={"research_agendas"})
    assert "research_agendas" not in state.model_dump(include={"cohort"})
    assert state.model_dump(include={"research_agendas": {"enabled"}}) == {"research_agendas": {"enabled": True}}
    filtered = state.model_dump(exclude={"research_agendas": {"enabled_turn"}}, mode="json")
    assert "enabled_turn" not in filtered["research_agendas"]
    assert state.model_dump(include={"research_agendas"}) == {"research_agendas": _plan().model_dump()}


@pytest.mark.parametrize("bad", [None, {}, {"schema_version": 1}, {"unexpected": True}])
def test_present_null_or_incomplete_external_state_is_rejected_without_mutation(bad):
    data = {"research_agendas": bad}
    before = deepcopy(data)
    with pytest.raises(ValueError):
        ScientificClaimsState.model_validate(data)
    assert data == before


@pytest.mark.parametrize("bad", [None, {}, False, 2])
def test_malformed_pickle_backing_never_falls_through_as_legacy(bad):
    state = ScientificClaimsState()
    state.__dict__["_research_agendas"] = bad
    restored = pickle.loads(pickle.dumps(state))
    with pytest.raises(ValueError):
        _ = restored.research_agendas
    with pytest.raises(ValueError):
        restored.model_dump()


@pytest.mark.parametrize("bad", [None, -1, True, "1"])
def test_present_proposal_agenda_identity_is_strict(bad):
    with pytest.raises(ValueError):
        ProposalReceipt.model_validate(dict(seat=0, claim=0, received_turn=0, agenda_id=bad))


def test_distinct_enabled_archive_values_are_not_equal():
    a, b = _state(), _state()
    assert a == b
    b.research_agendas.next_open_turn = 50
    assert a != b and a.model_dump() != b.model_dump()


def test_incomplete_constructed_payload_is_rejected_on_access():
    state = ScientificClaimsState()
    state.__dict__["_research_agendas"] = ResearchAgendas.model_construct(schema_version=1)
    with pytest.raises(ValueError):
        _ = state.research_agendas


def test_mutated_payload_list_is_revalidated_instead_of_becoming_legacy():
    state = _state()
    state.research_agendas.cycles.append("invalid after validation")
    with pytest.raises(ValueError):
        _ = state.research_agendas
    with pytest.raises(ValueError):
        state.model_dump()


def test_unvalidated_model_copy_external_update_is_rejected():
    state = ScientificClaimsState().model_copy(update={"research_agendas": _plan()})
    with pytest.raises(ValueError, match="unvalidated research update"):
        _ = state.research_agendas


def test_adopted_legacy_unknown_opening_is_none_never_negative():
    values = dict(id=0, legacy_adopted=True, opening_roster_complete=False, opened_turn=None,
        origin_seat=0, participants=[0], claims=[0, 1], trials=[], announcement_event_id="",
        closed_turn=None, close_reason="", unfunded_originals=[], unfunded_replications=[], slot_reasons={})
    assert ResearchCycle(**values).opened_turn is None
    with pytest.raises(ValueError):
        ResearchCycle(**{**values, "opened_turn": -1})


def test_allocation_topic_is_lazy_and_old_missing_identity_is_unknown_not_zero():
    old = AdoptionEffort(seat=0, region=0, recipe="irrigation", share=1., confidence=.5, paid=1)
    assert old.claim_id is None and "claim_id" not in old.model_dump()
    old._set_research_value(0)
    restored = AdoptionEffort.model_validate_json(old.model_dump_json())
    assert restored.claim_id == 0 and restored.model_dump()["claim_id"] == 0


@pytest.mark.parametrize("bad", [None, {}, {"schema_version": 1, "seal": "bad"}])
def test_present_invalid_research_host_identity_never_means_unbound(bad):
    with pytest.raises(ValueError):
        ScholarshipState.model_validate({"scientific_research_identity": bad})
