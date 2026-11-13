from __future__ import annotations

# Rates as of when this file was written. TODO: load these from somewhere.
RATES_TO_USD = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.27,
    "CAD": 0.73,
}


def to_usd(amount: float, currency: str) -> float:
    return amount * RATES_TO_USD[currency]
