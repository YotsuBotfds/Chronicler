"""D3 persisted war experience; native identities remain pool-scoped."""
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, PrivateAttr

from chronicler.switch_state import SwitchStateMixin


class WarConsequencesState(SwitchStateMixin, BaseModel):
    enabled: bool = True
    mode: Literal["active", "record_only"] = "active"
    last_turn: int = -1
    pending: list[dict] = Field(default_factory=list)
    history: list[dict] = Field(default_factory=list)
    history_dropped: int = 0
    frame: dict | None = None
    separation: dict | None = None
    counters: dict[str, int] = Field(default_factory=dict)
    threats: dict[int, dict] = Field(default_factory=dict)
    pending_threats: dict[int, dict] = Field(default_factory=dict)
    returns: dict[int, dict] = Field(default_factory=dict)
    # Stable per-turn hook keys survive exact restore; the set is a cache.
    noted_turn: int | None = None
    noted_keys: list[tuple] = Field(default_factory=list)
    _key_set: set = PrivateAttr(default_factory=set)
    _FILL_DEFAULTS: ClassVar[bool] = True

    def __setstate__(self, state):
        super().__setstate__(state)
        self._key_set = set(map(tuple, self.noted_keys))
