from __future__ import annotations

from .models import Transaction

# (category, keywords). First matching keyword wins, in this order.
DEFAULT_RULES: list[tuple[str, list[str]]] = [
    ("Income", ["payroll", "salary", "interest"]),
    ("Groceries", ["whole foods", "trader joe", "safeway", "tesco"]),
    ("Transport", ["uber", "lyft", "shell", "chevron", "tfl"]),
    ("Shopping", ["amazon", "target"]),
    ("Dining", ["cafe", "restaurant", "doordash", "shack", "pizza"]),
    ("Utilities", ["pg&e", "comcast", "water"]),
]


def categorize(tx: Transaction, rules: list[tuple[str, list[str]]] = DEFAULT_RULES) -> str:
    for category, keywords in rules:
        for keyword in keywords:
            if keyword in tx.description:
                return category
    return "uncategorized"


def categorize_all(transactions: list[Transaction]) -> list[Transaction]:
    for tx in transactions:
        tx.category = categorize(tx)
    return transactions
