"""Tests for batch WebSocket protocol in LiveServer."""
import argparse
import json
import threading
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from chronicler.live import LiveServer


class TestBatchWebSocket:
    """Test the batch message handlers on LiveServer."""

    def test_batch_start_spawns_thread(self):
        server = LiveServer(port=0)
        msg = {
            "type": "batch_start",
            "config": {
                "seed_start": 1,
                "seed_count": 3,
                "turns": 5,
                "simulate_only": True,
                "parallel": False,
            },
        }

        with patch("chronicler.batch.run_batch") as mock_batch, \
             patch("chronicler.analytics.generate_report") as mock_report:
            mock_batch.return_value = Path("/tmp/batch_1")
            mock_report.return_value = {"metadata": {}, "anomalies": []}

            result = server._handle_batch_start(msg)
            assert result is None  # no error
            assert server._batch_thread is not None
            server._batch_thread.join(timeout=5)

    def test_batch_start_rejects_when_running(self):
        server = LiveServer(port=0)
        # Simulate a running batch thread
        server._batch_thread = threading.Thread(target=lambda: None)
        server._batch_thread.start()
        server._batch_thread.join()
        # Thread is now dead, so it should allow a new one
        # Simulate alive thread
        server._batch_thread = MagicMock()
        server._batch_thread.is_alive.return_value = True

        msg = {"type": "batch_start", "config": {}}
        result = server._handle_batch_start(msg)
        assert result is not None
        assert result["type"] == "batch_error"
        assert "already running" in result["message"]

    def test_batch_cancel_sets_event(self):
        server = LiveServer(port=0)
        assert not server._batch_cancel_event.is_set()
        server._batch_cancel_event.set()
        assert server._batch_cancel_event.is_set()

    def test_batch_progress_messages(self):
        """Verify that progress callback puts messages on snapshot_queue."""
        server = LiveServer(port=0)
        progress_calls = []

        msg = {
            "type": "batch_start",
            "config": {
                "seed_start": 1,
                "seed_count": 2,
                "turns": 3,
                "simulate_only": True,
                "parallel": False,
            },
        }

        with patch("chronicler.batch.run_batch") as mock_batch, \
             patch("chronicler.analytics.generate_report") as mock_report:
            def fake_batch(args, **kwargs):
                cb = kwargs.get("progress_cb")
                if cb:
                    cb(1, 2, 1)
                    cb(2, 2, 2)
                return Path("/tmp/batch_1")

            mock_batch.side_effect = fake_batch
            mock_report.return_value = {"metadata": {}, "anomalies": []}

            server._handle_batch_start(msg)
            server._batch_thread.join(timeout=5)

        # Collect all messages from snapshot_queue
        messages = []
        while not server.snapshot_queue.empty():
            messages.append(server.snapshot_queue.get_nowait())

        progress_msgs = [m for m in messages if m["type"] == "batch_progress"]
        assert len(progress_msgs) == 2
        assert progress_msgs[0]["completed"] == 1
        assert progress_msgs[1]["completed"] == 2

        complete_msgs = [m for m in messages if m["type"] == "batch_complete"]
        assert len(complete_msgs) == 1

    def test_batch_cancel_sends_cancelled(self):
        """Cancelled batch sends batch_cancelled message, not batch_error."""
        server = LiveServer(port=0)

        msg = {
            "type": "batch_start",
            "config": {
                "seed_start": 1,
                "seed_count": 2,
                "turns": 3,
                "simulate_only": True,
                "parallel": False,
            },
        }

        with patch("chronicler.batch.run_batch") as mock_batch:
            def fake_batch(args, **kwargs):
                cancel = kwargs.get("cancel_event")
                cancel.set()  # Simulate cancel during batch
                return Path("/tmp/batch_1")

            mock_batch.side_effect = fake_batch

            server._handle_batch_start(msg)
            server._batch_thread.join(timeout=5)

        messages = []
        while not server.snapshot_queue.empty():
            messages.append(server.snapshot_queue.get_nowait())

        cancelled_msgs = [m for m in messages if m["type"] == "batch_cancelled"]
        assert len(cancelled_msgs) == 1
        # No batch_error for cancellation
        error_msgs = [m for m in messages if m["type"] == "batch_error"]
        assert len(error_msgs) == 0

    def test_batch_error_on_exception(self):
        """Batch exception sends batch_error message."""
        server = LiveServer(port=0)

        msg = {
            "type": "batch_start",
            "config": {
                "seed_start": 1,
                "seed_count": 2,
                "turns": 3,
            },
        }

        with patch("chronicler.batch.run_batch") as mock_batch:
            mock_batch.side_effect = RuntimeError("Test failure")

            server._handle_batch_start(msg)
            server._batch_thread.join(timeout=5)

        messages = []
        while not server.snapshot_queue.empty():
            messages.append(server.snapshot_queue.get_nowait())

        error_msgs = [m for m in messages if m["type"] == "batch_error"]
        assert len(error_msgs) == 1
        assert "Test failure" in error_msgs[0]["message"]

    def test_batch_start_rejects_invalid_worker_type(self):
        server = LiveServer(port=0)

        msg = {
            "type": "batch_start",
            "config": {
                "seed_start": 1,
                "seed_count": 2,
                "turns": 3,
                "workers": "bad",
            },
        }

        result = server._handle_batch_start(msg)

        assert result is not None
        assert result["type"] == "batch_error"
        assert "workers" in result["message"]
        assert server._batch_thread is None

    def test_tuning_overrides_passed_through(self):
        """Tuning overrides from config reach run_batch as dict."""
        server = LiveServer(port=0)
        captured_kwargs = {}

        msg = {
            "type": "batch_start",
            "config": {
                "seed_start": 1,
                "seed_count": 1,
                "turns": 3,
                "simulate_only": True,
                "parallel": False,
                "tuning_overrides": {"stability.drain.drought_immediate": 10.0},
            },
        }

        with patch("chronicler.batch.run_batch") as mock_batch, \
             patch("chronicler.analytics.generate_report") as mock_report:
            def capture_batch(args, **kwargs):
                captured_kwargs.update(kwargs)
                return Path("/tmp/batch_1")

            mock_batch.side_effect = capture_batch
            mock_report.return_value = {"metadata": {}, "anomalies": []}

            server._handle_batch_start(msg)
            server._batch_thread.join(timeout=5)

        assert captured_kwargs["tuning_overrides_dict"] == {"stability.drain.drought_immediate": 10.0}

    def test_batch_start_passes_run_shape_through(self):
        """Batch config should preserve the viewer-selected run shape and models."""
        server = LiveServer(port=0)
        server._client_defaults.update({
            "local_url": "http://localhost:1234/v1",
            "sim_model": "default-sim",
            "narrative_model": "default-narr",
            "narrator": "local",
            "agents": "hybrid",
            "preset": "silk-road",
        })
        server._lobby_init = {"defaults": {"civs": 6, "regions": 12}}
        captured_args = {}

        msg = {
            "type": "batch_start",
            "config": {
                "seed_start": 5,
                "seed_count": 2,
                "turns": 25,
                "simulate_only": True,
                "parallel": False,
                "civs": 7,
                "regions": 14,
                "scenario": "dead_miles.yaml",
                "sim_model": "sim-x",
                "narrative_model": "narr-x",
                "narrator": "local",
                "agents": "shadow",
                "preset": "dark-age",
            },
        }

        with patch("chronicler.batch.run_batch") as mock_batch, \
             patch("chronicler.analytics.generate_report") as mock_report:
            def capture_batch(args, **kwargs):
                captured_args.update(vars(args))
                return Path("/tmp/batch_5")

            mock_batch.side_effect = capture_batch
            mock_report.return_value = {"metadata": {}, "anomalies": []}

            server._handle_batch_start(msg)
            server._batch_thread.join(timeout=5)

        assert captured_args["civs"] == 7
        assert captured_args["regions"] == 14
        assert captured_args["scenario"] == "dead_miles.yaml"
        assert captured_args["sim_model"] == "sim-x"
        assert captured_args["narrative_model"] == "narr-x"
        assert captured_args["narrator"] == "local"
        assert captured_args["agents"] == "shadow"
        assert captured_args["preset"] == "dark-age"
