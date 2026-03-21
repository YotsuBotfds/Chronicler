"""Tests for M53 analytics extractors: extract_bond_health, extract_era_signals,
extract_legacy_chain_metrics."""


def test_extract_bond_health_global():
    """extract_bond_health returns global stats from relationship_stats metadata."""
    bundle = {"metadata": {"relationship_stats": [
        {"bonds_formed": 5, "bonds_dissolved_death": 1, "bonds_dissolved_structural": 2,
         "mean_rel_count": 3.2, "bond_type_count_0": 10, "bond_type_count_3": 5,
         "cross_civ_bond_fraction": 0.15},
    ]}}
    from chronicler.analytics import extract_bond_health
    result = extract_bond_health([bundle])
    assert result["mean_rel_count_per_turn"][0] == 3.2
    assert result["bonds_formed_per_turn"][0] == 5


def test_extract_era_signals():
    """extract_era_signals returns per-civ time series."""
    bundle = {"history": [
        {"turn": 0, "civ_stats": {"Aram": {"population": 100, "stability": 50, "treasury": 20, "prestige": 5, "regions": ["a", "b"], "gini": 0.4}}},
        {"turn": 1, "civ_stats": {"Aram": {"population": 120, "stability": 45, "treasury": 25, "prestige": 8, "regions": ["a", "b", "c"], "gini": 0.45}}},
    ]}
    from chronicler.analytics import extract_era_signals
    result = extract_era_signals([bundle])
    assert result["Aram"]["population"] == [100, 120]
    assert result["Aram"]["territory"] == [2, 3]
    assert result["Aram"]["gini"] == [0.4, 0.45]


def test_extract_legacy_chain_metrics():
    """extract_legacy_chain_metrics computes basic legacy stats."""
    bundle = {"metadata": {"great_persons": [
        {"name": "Kael I", "dynasty_id": 1, "born_turn": 10, "active": False, "agent_id": 100},
        {"name": "Kael II", "dynasty_id": 1, "born_turn": 50, "active": True, "agent_id": 200},
        {"name": "Zara", "dynasty_id": 2, "born_turn": 30, "active": True, "agent_id": 300},
    ]}}
    from chronicler.analytics import extract_legacy_chain_metrics
    result = extract_legacy_chain_metrics([bundle])
    # Dynasty 1 has chain length 2, dynasty 2 has chain length 1
    assert result["dynasty_chain_lengths"] == {1: 2, 2: 1}
    assert result["mean_chain_length"] == 1.5
