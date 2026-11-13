from datetime import date

from ledger.categorize import categorize
from ledger.models import Transaction


def tx(description: str) -> Transaction:
    return Transaction(date(2026, 1, 5), description, -10.0)


def test_known_merchants():
    assert categorize(tx("whole foods market #123")) == "Groceries"
    assert categorize(tx("uber trip")) == "Transport"
    assert categorize(tx("payroll acme corp")) == "Income"


def test_unknown_merchant():
    assert categorize(tx("mystery vendor")) == "uncategorized"
