from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from .models import Transaction

DATE_FORMAT = "%Y-%m-%d"
REQUIRED_COLUMNS = {"date", "description", "amount"}


class ImportFormatError(Exception):
    """The CSV file could not be understood."""


def parse_amount(raw: str) -> float:
    return float(raw.strip().replace("$", ""))


def parse_date(raw: str) -> date:
    return datetime.strptime(raw.strip(), DATE_FORMAT).date()


def read_csv(path: str | Path, account: str = "checking", currency: str = "USD") -> list[Transaction]:
    """Read a bank export with at least date, description and amount columns."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ImportFormatError(f"{path}: missing columns: {', '.join(sorted(missing))}")
        transactions = []
        for lineno, row in enumerate(reader, start=2):
            try:
                transactions.append(
                    Transaction(
                        date=parse_date(row["date"]),
                        description=row["description"].strip(),
                        amount=parse_amount(row["amount"]),
                        currency=(row.get("currency") or currency).upper(),
                        account=account,
                    )
                )
            except ValueError as exc:
                raise ImportFormatError(f"{path}:{lineno}: {exc}") from exc
    return transactions
