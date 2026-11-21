"""Command line entry for the Apex SLA demo checker."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

from .apex import lint_project, parse_sla_table

SERVICE_FILE = "force-app/main/default/classes/ServiceTicketSlaService.cls"


def _table(root: Path) -> dict[str, int] | None:
    path = root / SERVICE_FILE
    if not path.exists():
        return None
    return parse_sla_table(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    """Return 0 when clean, 1 when findings exist, 2 for a missing folder, file or bad input."""
    parser = argparse.ArgumentParser(
        prog="slacheck",
        description="Static checks for the Apex SLA demo. Nothing is compiled, run or deployed.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    lint = sub.add_parser("lint", help="check classes, triggers and their metadata files")
    lint.add_argument("path", nargs="?", default=".")
    table = sub.add_parser("table", help="print the SLA hours table read from the Apex class")
    table.add_argument("path", nargs="?", default=".")
    due = sub.add_parser("due", help="work out a due time from the Apex table")
    due.add_argument("--priority", required=True)
    due.add_argument("--opened", required=True, help='for example "2026-11-20 09:00"')
    due.add_argument("--path", default=".")
    args = parser.parse_args(argv)
    root = Path(getattr(args, "path", "."))
    if not root.is_dir():
        print(f"Folder not found: {root}", file=sys.stderr)
        return 2
    if args.command == "lint":
        findings = lint_project(root)
        for f in findings:
            print(f)
        print(f"{len(findings)} finding(s)")
        return 1 if findings else 0
    hours = _table(root)
    if hours is None:
        print(f"Not found: {SERVICE_FILE}", file=sys.stderr)
        return 2
    if not hours:
        print("No SLA_HOURS map found in the class", file=sys.stderr)
        return 2
    if args.command == "table":
        for priority, h in hours.items():
            print(f"{priority:<10}{h:>4} hours")
        return 0
    try:
        opened = datetime.strptime(args.opened, "%Y-%m-%d %H:%M")
    except ValueError:
        print("Bad input: --opened must look like 2026-11-20 09:00", file=sys.stderr)
        return 2
    used = args.priority if args.priority in hours else "Normal"
    if used not in hours:
        print("Bad input: priority unknown and the table has no Normal row", file=sys.stderr)
        return 2
    print(f"{args.priority} -> {used} ({hours[used]} h): due {opened + timedelta(hours=hours[used]):%Y-%m-%d %H:%M}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
