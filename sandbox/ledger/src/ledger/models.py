from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date


@dataclass
class Transaction:
    """One line from a bank statement. Negative amounts are money going out."""

    date: date
    description: str
    amount: float
    currency: str = "USD"
    account: str = "checking"
    category: str = "uncategorized"

    def key(self) -> tuple:
        """Identity used for duplicate detection."""
        return (self.date, self.description.strip().lower(), round(self.amount, 2), self.account)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["date"] = self.date.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Transaction:
        return cls(
            date=date.fromisoformat(data["date"]),
            description=data["description"],
            amount=float(data["amount"]),
            currency=data.get("currency", "USD"),
            account=data.get("account", "checking"),
            category=data.get("category", "uncategorized"),
        )
