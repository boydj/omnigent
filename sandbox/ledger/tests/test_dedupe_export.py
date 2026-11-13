import csv
from datetime import date

from ledger.dedupe import find_duplicates
from ledger.export import export_csv
from ledger.models import Transaction


def test_finds_exact_duplicate():
    a = Transaction(date(2026, 1, 5), "Cafe Luna", -4.5)
    b = Transaction(date(2026, 1, 5), "CAFE LUNA ", -4.5)
    c = Transaction(date(2026, 1, 6), "Cafe Luna", -4.5)
    assert find_duplicates([a, b, c]) == [(a, b)]


def test_export_round_trip(tmp_path):
    out = tmp_path / "out.csv"
    txs = [Transaction(date(2026, 1, 5), "Cafe Luna", -4.5, category="Dining")]
    assert export_csv(txs, out) == 1
    rows = list(csv.DictReader(out.open()))
    assert rows[0]["description"] == "Cafe Luna"
    assert rows[0]["amount"] == "-4.50"
