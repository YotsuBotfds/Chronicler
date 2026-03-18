import numpy as np


def test_compute_gini_uniform():
    """All agents same wealth → Gini = 0."""
    from chronicler.agent_bridge import compute_gini
    arr = np.array([5.0, 5.0, 5.0, 5.0])
    assert abs(compute_gini(arr)) < 0.001


def test_compute_gini_maximal():
    """One agent has everything → Gini near 1.0."""
    from chronicler.agent_bridge import compute_gini
    arr = np.array([0.0, 0.0, 0.0, 100.0])
    assert compute_gini(arr) > 0.7


def test_compute_gini_moderate():
    """Mixed distribution → Gini in 0.2-0.6 range."""
    from chronicler.agent_bridge import compute_gini
    arr = np.array([1.0, 2.0, 5.0, 10.0, 50.0])
    g = compute_gini(arr)
    assert 0.2 < g < 0.7, f"Expected moderate Gini, got {g}"


def test_compute_gini_empty():
    from chronicler.agent_bridge import compute_gini
    arr = np.array([])
    assert compute_gini(arr) == 0.0


def test_compute_gini_single():
    from chronicler.agent_bridge import compute_gini
    arr = np.array([10.0])
    assert compute_gini(arr) == 0.0
