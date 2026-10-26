"""The transport contract: what a bundle and the live protocol carry.

``transport_contract.json`` (next to this module) is the one list; the
viewer imports the same file (``viewer/src/lib/transport.ts``). Static
bundles, the Batch Lab's ``bundle_loaded`` message, live ``init`` and
``turn`` messages and the reconnect ``init`` all carry every field it names:

* ``snapshot_fields``: the ``TurnSnapshot`` fields every snapshot has;
* ``snapshot_systems``: its optional per-system summaries (omitted while
  their system is off);
* ``bundle_systems``: optional top-level bundle fields with their own
  versions (in-world historiography and languages);
* ``bundle_carriers``: top-level fields that travel with the history
  (dead civs' omitted rows, ``snapshot_pruning``);
* ``turn_message_keys``: keys a live ``turn`` message adds to its snapshot.

Adding a snapshot field or an optional system means adding it to the JSON
file; ``tests/test_historical_parity.py`` checks the lists against
``TurnSnapshot`` and a fixture holding every system.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

_CONTRACT = json.loads(Path(__file__).with_name("transport_contract.json").read_text(encoding="utf-8"))

CONTRACT_VERSION: int = _CONTRACT["version"]
SNAPSHOT_FIELDS: tuple[str, ...] = tuple(_CONTRACT["snapshot_fields"])
SNAPSHOT_SYSTEMS: tuple[str, ...] = tuple(_CONTRACT["snapshot_systems"])
BUNDLE_SYSTEMS: tuple[str, ...] = tuple(_CONTRACT["bundle_systems"])
BUNDLE_CARRIERS: tuple[str, ...] = tuple(_CONTRACT["bundle_carriers"])
TURN_MESSAGE_KEYS: tuple[str, ...] = tuple(_CONTRACT["turn_message_keys"])
_SNAPSHOT_KEYS = frozenset(SNAPSHOT_FIELDS + SNAPSHOT_SYSTEMS)


def bundle_systems(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """The bundle-level systems and carriers ``bundle`` holds (present, not None)."""
    return {key: bundle[key] for key in BUNDLE_SYSTEMS + BUNDLE_CARRIERS
            if key in bundle and bundle[key] is not None}


def snapshot_from_turn_message(message: Mapping[str, Any]) -> dict[str, Any]:
    """The history row of a live ``turn`` message: its snapshot fields and systems."""
    return {key: value for key, value in message.items() if key in _SNAPSHOT_KEYS}
