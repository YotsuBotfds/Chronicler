"""Python economy oracle. Not called by the simulation; the Rust `tick_economy` is authoritative.

Stage 1 of CON-7: this module re-exports the oracle names from
``chronicler.economy`` so callers can import them from their final home.
The bodies move here in a later, separate change.
"""
from chronicler.economy import (
    accumulate_stockpile,
    allocate_trade_flow,
    apply_stockpile_cap,
    apply_storage_decay,
    apply_transit_decay,
    compute_demand,
    compute_economy,
    compute_prices,
    compute_production,
    consume_from_stockpile,
    derive_farmer_income_modifier,
    derive_food_sufficiency_from_stockpile,
    derive_merchant_margin,
    derive_merchant_trade_income,
)

__all__ = [
    "accumulate_stockpile",
    "allocate_trade_flow",
    "apply_stockpile_cap",
    "apply_storage_decay",
    "apply_transit_decay",
    "compute_demand",
    "compute_economy",
    "compute_prices",
    "compute_production",
    "consume_from_stockpile",
    "derive_farmer_income_modifier",
    "derive_food_sufficiency_from_stockpile",
    "derive_merchant_margin",
    "derive_merchant_trade_income",
]
