from __future__ import annotations

import argparse
import sys

from . import storage
from .categorize import categorize_all
from .dedupe import find_duplicates
from .export import export_csv
from .importer import ImportFormatError, read_csv
from .report import format_report, monthly_totals


def cmd_import(args: argparse.Namespace) -> int:
    try:
        new = read_csv(args.file, account=args.account, currency=args.currency)
    except ImportFormatError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    categorize_all(new)
    existing = storage.load()
    storage.save(existing + new)
    print(f"Imported {len(new)} transactions into {storage.db_path()}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    month = int(args.month.split("-")[1])
    print(format_report(monthly_totals(storage.load()), month))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    count = export_csv(storage.load(), args.file)
    print(f"Wrote {count} rows to {args.file}")
    return 0


def cmd_dupes(args: argparse.Namespace) -> int:
    pairs = find_duplicates(storage.load())
    for first, _second in pairs:
        print(f"{first.date}  {first.amount:>10.2f}  {first.description}")
    print(f"{len(pairs)} duplicate pair(s)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ledger")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("import", help="import a bank CSV export")
    p.add_argument("file")
    p.add_argument("--account", default="checking")
    p.add_argument("--currency", default="USD")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("report", help="spending by category for one month")
    p.add_argument("--month", required=True, help="YYYY-MM")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("export", help="export all transactions to CSV")
    p.add_argument("file")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("dupes", help="list likely duplicate transactions")
    p.set_defaults(func=cmd_dupes)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
