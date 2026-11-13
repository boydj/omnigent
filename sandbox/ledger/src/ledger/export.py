from __future__ import annotations

import csv
from pathlib import Path

from .models import Transaction

COLUMNS = ["date", "description", "amount", "currency", "account", "category"]


def export_csv(transactions: list[Transaction], path: str | Path) -> int:
    """Write transactions to a CSV file for spreadsheets. Returns rows written."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for tx in transactions:
            writer.writerow(
                [tx.date.isoformat(), tx.description, f"{tx.amount:.2f}", tx.currency, tx.account, tx.category]
            )
    return len(transactions)
