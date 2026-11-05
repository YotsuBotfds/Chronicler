"""Persisted state of the L4 public grain convoys (default off).

Owned by its package lane; extended by that lane only. Pure data.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class GrainConvoyState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
