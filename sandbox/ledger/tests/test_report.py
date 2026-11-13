from datetime import date, timedelta

from ledger.models import Transaction
from ledger.report import format_report, monthly_totals


def test_totals_by_category():
    txs = [
        Transaction(date(2026, 1, 3), "a", -20.0, category="Dining"),
        Transaction(date(2026, 1, 9), "b", -5.0, category="Dining"),
        Transaction(date(2026, 1, 9), "c", 100.0, category="Income"),
    ]
    totals = monthly_totals(txs)
    assert totals[1]["Dining"] == -25.0
    assert totals[1]["Income"] == 100.0


def test_report_current_month():
    today = date.today()
    txs = [
        Transaction(today, "x", -10.0, category="Dining"),
        Transaction(today - timedelta(days=1), "y", -5.0, category="Dining"),
    ]
    totals = monthly_totals(txs)
    assert totals[today.month]["Dining"] == -15.0


def test_empty_month():
    assert format_report({}, 3) == "No transactions."
