def test_determinism_scrubbed_comparison():
    """Scrubbed comparison ignores generated_at timestamp."""
    bundle_a = {"metadata": {"generated_at": "2026-03-21T10:00:00Z", "seed": 42},
                "world_state": {"turn": 100}, "history": {"Aram": []}}
    bundle_b = {"metadata": {"generated_at": "2026-03-21T10:05:00Z", "seed": 42},
                "world_state": {"turn": 100}, "history": {"Aram": []}}
    from chronicler.validate import scrubbed_equal
    assert scrubbed_equal(bundle_a, bundle_b)

    bundle_c = dict(bundle_b)
    bundle_c["world_state"] = {"turn": 101}
    assert not scrubbed_equal(bundle_a, bundle_c)
