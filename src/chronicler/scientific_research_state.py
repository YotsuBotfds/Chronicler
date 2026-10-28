"""Finite retained research metadata; no simulation imports or default state."""
from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

MAX_CYCLES = 10
FUNDING_WINDOW = 24
OPENING_INTERVAL = 25
ORIGINAL_WINDOW = 12


class ResearchCycle(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True,
                              revalidate_instances="always")

    id: int = Field(ge=0, lt=MAX_CYCLES)
    legacy_adopted: bool
    opening_roster_complete: bool
    opened_turn: int | None
    origin_seat: int = Field(ge=0)
    participants: list[int] = Field(max_length=20)
    claims: list[int] = Field(min_length=2, max_length=2)
    trials: list[int] = Field(max_length=4)
    announcement_event_id: str
    closed_turn: int | None
    close_reason: str
    unfunded_originals: list[int] = Field(max_length=2)
    unfunded_replications: list[int] = Field(max_length=2)
    slot_reasons: dict[str, str] = Field(max_length=4)

    @model_validator(mode="after")
    def identities(self):
        for values in (self.participants, self.claims, self.trials,
                       self.unfunded_originals, self.unfunded_replications):
            if any(type(value) is not int or value < 0 for value in values) or len(values) != len(set(values)):
                raise ValueError("research references must be unique nonnegative integer IDs")
        if not self.legacy_adopted and (not self.opening_roster_complete or self.opened_turn is None
                                       or self.opened_turn < 0 or self.origin_seat not in self.participants):
            raise ValueError("new agendas require an actual opening and complete participant roster")
        if self.closed_turn is not None and (self.closed_turn < 0 or (
                self.opened_turn is not None and self.closed_turn < self.opened_turn)):
            raise ValueError("agenda closure precedes its opening")
        return self


class ResearchAgendas(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True,
                              revalidate_instances="always")

    schema_version: Literal[1]
    rule: Literal["finite-retained-v1"]
    enabled: bool
    enabled_turn: int = Field(ge=0)
    next_open_turn: int = Field(ge=0)
    origin_cursor: int = Field(ge=-1)
    cycles: list[ResearchCycle] = Field(max_length=MAX_CYCLES)
    blocked_reason: str
    blocked_turn: int | None

    @model_validator(mode="after")
    def cycle_ids(self):
        if [cycle.id for cycle in self.cycles] != list(range(len(self.cycles))):
            raise ValueError("research cycle IDs must be append-only consecutive integers")
        if self.blocked_turn is not None and self.blocked_turn < 0:
            raise ValueError("research blocked date must be nonnegative")
        return self


def _nested_filter(value, name):
    """The child selection, or None when a field is selected whole."""
    if isinstance(value, Mapping):
        item = value.get(name)
        return None if item is True or item is Ellipsis else item
    return None


class LazyResearchModel(BaseModel):
    """No declared/default fields: legacy dictionaries and pickle stay intact.

    Enabled data is installed only by explicit validation/activation. Nested
    WorldState serialization uses these core-schema hooks, rather than a
    model_dump/model_validate override that nested models could bypass.
    """

    lazy_name: ClassVar[str]
    lazy_backing: ClassVar[str]
    lazy_payload: ClassVar[type]

    @classmethod
    def _validate_research_value(cls, value, context=None):
        if cls.lazy_payload is int:
            if type(value) is not int or value < 0:
                raise ValueError("agenda identity must be a nonnegative integer")
            return value
        if value is None:
            raise ValueError("present research state cannot be null")
        # Serialized payloads must be complete; defaults cannot reset an archive.
        if isinstance(value, Mapping) and set(value) != set(cls.lazy_payload.model_fields):
            raise ValueError("research payload must contain its complete declared state")
        return cls.lazy_payload.model_validate(value, strict=True, context=context)

    def _research_value(self):
        if self.lazy_name in self.__dict__:
            raise ValueError("unvalidated research update; use model_validate or the activation API")
        if self.lazy_backing not in self.__dict__:
            return None
        value = self.__dict__[self.lazy_backing]
        if self.lazy_payload is int:
            if type(value) is not int or value < 0:
                raise ValueError("malformed stored agenda identity")
        elif (not isinstance(value, self.lazy_payload)
              or set(self.lazy_payload.model_fields) - value.__dict__.keys()):
            raise ValueError("malformed stored research state")
        else:
            self.lazy_payload.model_validate(value, strict=True)
        return value

    def _set_research_value(self, value):
        self.__dict__[self.lazy_backing] = self._validate_research_value(value)

    @model_validator(mode="wrap")
    @classmethod
    def _read_research(cls, value, handler, info):
        if not isinstance(value, Mapping) or cls.lazy_name not in value:
            result = handler(value)
            result._research_value()  # malformed old pickle must not mean disabled
            return result
        copied = dict(value)
        research = copied.pop(cls.lazy_name)
        parsed = cls._validate_research_value(research, info.context)
        result = handler(copied)
        result.__dict__[cls.lazy_backing] = parsed
        return result

    @model_serializer(mode="wrap")
    def _write_research(self, handler, info):
        result = handler(self)
        value = self._research_value()
        if value is None:
            return result
        name, include, exclude = self.lazy_name, info.include, info.exclude
        if include is not None and name not in include:
            return result
        if exclude is not None and (name in exclude and (not isinstance(exclude, Mapping)
                or exclude[name] is True or exclude[name] is Ellipsis)):
            return result
        if isinstance(value, BaseModel):
            result[name] = value.model_dump(mode=info.mode, include=_nested_filter(include, name),
                exclude=_nested_filter(exclude, name), context=info.context, by_alias=info.by_alias,
                exclude_unset=info.exclude_unset, exclude_defaults=info.exclude_defaults,
                exclude_none=info.exclude_none, round_trip=info.round_trip)
        else:
            result[name] = value
        return result

    def __eq__(self, other):
        equal = super().__eq__(other)
        if equal is True and isinstance(other, LazyResearchModel):
            return self._research_value() == other._research_value()
        return equal
