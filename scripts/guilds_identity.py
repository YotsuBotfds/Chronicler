#!/usr/bin/env python3
"""Identity checks for ``--guilds``: ``scripts/agent_movements_identity.py``
with the layer's own field ``guilds``.

``compare BASE_DIR NEW_DIR``
    Every file of two run directories byte for byte (the bundle without
    ``metadata.generated_at``).

``compare-inert BASE_DIR NEW_DIR``
    The same after removing ``guilds`` from ``state.json``, every
    ``history[n]`` and the bundle's ``world_state``: runs with the switch on
    where no city forms (``--agents off``) against runs with it off.

See docs/integration/guilds.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent_movements_identity as _identity  # noqa: E402

_identity.FIELD = "guilds"
compare = _identity.compare

if __name__ == "__main__":
    sys.exit(_identity.main(sys.argv[1:]))
