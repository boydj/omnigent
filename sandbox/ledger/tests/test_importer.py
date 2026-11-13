from datetime import date
from pathlib import Path

import pytest

from ledger.importer import ImportFormatError, parse_amount, read_csv

DATA = Path(__file__).parent.parent / "sample-data"


def test_reads_iso_dated_export():
    txs = read_csv(DATA / "checking-2026-01.csv")
    assert len(txs) == 12
    assert txs[0].date == date(2026, 1, 2)
    assert txs[0].amount == 3200.00


def test_dollar_sign_is_ignored():
    assert parse_amount("$12.50") == 12.50


def test_missing_columns_are_reported(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("when,what\n2026-01-01,coffee\n")
    with pytest.raises(ImportFormatError, match="missing columns: amount, date, description"):
        read_csv(bad)
