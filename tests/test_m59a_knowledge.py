"""M59a: Knowledge stats integration tests."""
import argparse
import json
import subprocess
import sys

import pytest


def test_knowledge_stats_property_exists():
    """Verify the knowledge_stats property exists on AgentBridge."""
    from chronicler.agent_bridge import AgentBridge
    assert hasattr(AgentBridge, "knowledge_stats"), "AgentBridge should have knowledge_stats property"


def test_extract_knowledge_stats_empty():
    """Verify extractor handles bundles with no knowledge_stats."""
    from chronicler.analytics import extract_knowledge_stats

    bundles = [{"metadata": {"seed": 42}}]
    result = extract_knowledge_stats(bundles)
    assert result == {"by_seed": {42: []}}


def test_extract_knowledge_stats_with_data():
    """Verify extractor routes per-turn stats by seed."""
    from chronicler.analytics import extract_knowledge_stats

    bundles = [{
        "metadata": {
            "seed": 42,
            "knowledge_stats": [
                {"packets_created": 5, "live_packet_count": 3},
                {"packets_created": 2, "live_packet_count": 4},
            ],
        }
    }]
    result = extract_knowledge_stats(bundles)
    assert len(result["by_seed"][42]) == 2
    assert result["by_seed"][42][0]["packets_created"] == 5
