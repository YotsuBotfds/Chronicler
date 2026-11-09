"""A6 bounded, dated personal experience; no second residence authority."""
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, PrivateAttr

from chronicler.switch_state import SwitchStateMixin


class AdaptiveLivelihoodsState(SwitchStateMixin, BaseModel):
    enabled: bool = True
    mode: Literal["adapt", "record_only", "shuffled"] = "adapt"
    rules: Literal["1", "2", "3"] = "2"
    decision_channels: Literal["all", "no_migration_experience", "no_information", "no_work", "no_trade"] = "all"
    memory: list[dict] = Field(default_factory=list)
    work: list[dict] = Field(default_factory=list)
    known_residences: dict[int, dict[int, int]] = Field(default_factory=dict)
    trade_experience: list[dict] = Field(default_factory=list)
    last_turn: int = -1
    frame: dict | None = None
    counters: dict[str, int] = Field(default_factory=dict)
    offer_turn: int | None = None
    offers: list[dict] = Field(default_factory=list)
    offers_dropped: int = 0
    _index_turn: int | None = PrivateAttr(default=None)
    _work_index: dict = PrivateAttr(default_factory=dict)
    _offer_cache: dict = PrivateAttr(default_factory=dict)
    _record_turn: int | None = PrivateAttr(default=None)
    _record_keys: set = PrivateAttr(default_factory=set)
    _work_heap: list = PrivateAttr(default_factory=list)
    _FILL_DEFAULTS: ClassVar[bool] = True

    def __setstate__(self, state):
        super().__setstate__(state)
        self._index_turn, self._work_index, self._offer_cache = None, {}, {}
        self._record_turn, self._record_keys, self._work_heap = None, set(), []
