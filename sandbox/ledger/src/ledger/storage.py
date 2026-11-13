from __future__ import annotations

import json
import os
from pathlib import Path

from .models import Transaction


def db_path() -> Path:
    return Path(os.environ.get("LEDGER_DB", Path.home() / ".ledger" / "ledger.json"))


def load(path: Path | None = None) -> list[Transaction]:
    path = path or db_path()
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [Transaction.from_dict(item) for item in json.load(fh)]


def save(transactions: list[Transaction], path: Path | None = None) -> None:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump([tx.to_dict() for tx in transactions], fh, indent=2)
