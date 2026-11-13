from __future__ import annotations

from .models import Transaction


def find_duplicates(transactions: list[Transaction]) -> list[tuple[Transaction, Transaction]]:
    """Pairs of transactions that look like the same bank line imported twice."""
    duplicates = []
    for i, first in enumerate(transactions):
        for second in transactions[i + 1 :]:
            if first.key() == second.key():
                duplicates.append((first, second))
    return duplicates
