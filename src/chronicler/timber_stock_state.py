"""Persisted state of the L3 renewable timber stock (default off).

Owned by its package lane; extended by that lane only. Pure data.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TimberStockState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
