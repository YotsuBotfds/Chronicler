"""Historical parity checks that need child processes or sockets.

Outside the offline oracle lane (it blocks both): the gap summaries' bytes
under different ``PYTHONHASHSEED`` values, and the live server's origin and
session-token checks over real WebSocket connections.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_GAP_SCRIPT = r"""
import json
from chronicler.curator import build_gap_summaries
from chronicler.models import (CivSnapshot, Event, NarrativeMoment, NarrativeRole,
                               TechEra, TurnSnapshot)

def row(pop):
    return CivSnapshot(population=pop, military=50, economy=50, culture=50, stability=50,
                       treasury=100, asabiya=0.5, tech_era=TechEra.IRON, trait="bold",
                       regions=["R"], leader_name="L", alive=True)

names = [f"Realm {chr(65 + i)}{i * 7 % 5}" for i in range(16)]
history = [TurnSnapshot(turn=t, civ_stats={n: row(100 if t <= 3 else 101 + i) for i, n in enumerate(names)},
                        region_control={}, relationships={}) for t in range(1, 10)]
def moment(lo, hi):
    return NarrativeMoment(anchor_turn=lo, turn_range=(lo, hi),
                           events=[Event(turn=lo, event_type="war", actors=["A"], description="w", importance=5)],
                           named_events=[], score=5.0, causal_links=[],
                           narrative_role=NarrativeRole.CLIMAX, bonus_applied=0.0)
gaps = build_gap_summaries([moment(0, 2), moment(6, 8)], [], history)
print(json.dumps([g.model_dump(mode="json") for g in gaps]))
"""


def _gap_bytes(hashseed: str) -> bytes:
    env = dict(os.environ, PYTHONHASHSEED=hashseed,
               PYTHONPATH=os.pathsep.join([str(ROOT / "src"), os.environ.get("PYTHONPATH", "")]))
    return subprocess.run([sys.executable, "-c", _GAP_SCRIPT], env=env, check=True,
                          capture_output=True, timeout=60).stdout


def test_gap_summary_bytes_do_not_depend_on_the_hash_seed():
    outputs = {seed: _gap_bytes(seed) for seed in ("1", "2", "3")}
    assert outputs["1"] and len(set(outputs.values())) == 1, outputs


# --- live server: origins and the session token ----------------------------------

@pytest.fixture
def lobby_server():
    from chronicler.live import LiveServer

    server = LiveServer(port=0, allowed_origins=["http://viewer.test:8080"])
    server._lobby_init = {"type": "init", "state": "lobby", "scenarios": [], "models": [""],
                          "defaults": {"turns": 5, "civs": 2, "regions": 3, "seed": None}}
    server.start()
    try:
        yield server
    finally:
        server.stop()


async def _first_message(uri: str, origin: str | None):
    import json

    import websockets.asyncio.client as ws_client

    async with ws_client.connect(uri, origin=origin) as ws:
        return json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))


def _refused(uri: str, origin: str | None) -> int:
    from websockets.exceptions import InvalidStatus

    with pytest.raises(InvalidStatus) as info:
        asyncio.run(_first_message(uri, origin))
    return info.value.response.status_code


def test_untrusted_origin_is_refused_even_with_the_token(lobby_server):
    assert _refused(lobby_server.ws_url(), "https://untrusted.example") == 403


def test_missing_or_wrong_token_is_refused(lobby_server):
    base = f"ws://localhost:{lobby_server._actual_port}"
    assert _refused(base, "http://localhost:5173") == 403
    assert _refused(base + "/?token=wrong", "http://localhost:5173") == 403
    assert _refused(base + "/?token=", None) == 403


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:4173",
                                    "http://viewer.test:8080", None])
def test_allowed_origin_with_the_token_connects(lobby_server, origin):
    msg = asyncio.run(_first_message(lobby_server.ws_url(), origin))
    assert msg["state"] == "lobby"


def test_the_printed_viewer_link_carries_the_server_and_token(lobby_server):
    from urllib.parse import parse_qs, urlsplit

    from chronicler.live import LiveServer

    link = urlsplit(lobby_server.viewer_url())
    query = parse_qs(link.query)
    assert f"{link.scheme}://{link.netloc}" == "http://localhost:5173"
    assert query["ws"] == [f"ws://localhost:{lobby_server._actual_port}"]
    assert query["token"] == [lobby_server.token]
    assert LiveServer(port=0).token != LiveServer(port=0).token  # per session
