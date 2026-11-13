from __future__ import annotations

from collections import defaultdict

from .models import Transaction


def monthly_totals(transactions: list[Transaction]) -> dict[int, dict[str, float]]:
    """Total amount per category for each month: {month: {category: total}}."""
    totals: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for tx in transactions:
        totals[tx.date.month][tx.category] += tx.amount
    return totals


def format_report(totals: dict[int, dict[str, float]], month: int) -> str:
    rows = totals.get(month, {})
    if not rows:
        return "No transactions."
    lines = [f"{'Category':<15}{'Total':>12}"]
    for category, amount in sorted(rows.items()):
        lines.append(f"{category:<15}{amount:>12}")
    lines.append(f"{'Net':<15}{sum(rows.values()):>12}")
    return "\n".join(lines)
