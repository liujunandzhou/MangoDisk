#!/usr/bin/env python3
"""Render mangodisk-cli scan/apply JSON as a compact human-readable report.

Usage:
    mangodisk_report.py scan  /tmp/mangodisk-scan.json
    mangodisk_report.py apply /tmp/mangodisk-apply.json

Exit status is 0 even when actions failed; the report itself carries the
outcome. Input is always one JSON document as written by the CLI with
`--format json`.
"""

import json
import sys
from collections import defaultdict

GB = 1024**3


def fmt_gb(nbytes: float) -> str:
    value = nbytes / GB
    if value >= 10:
        return f"{value:7.1f} GB"
    return f"{value:7.2f} GB"


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(2)


def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot read JSON from {path}: {error}")


def render_disk(disk: dict) -> None:
    print("Disk:")
    print(f"  total {fmt_gb(disk['totalBytes'])}  used {fmt_gb(disk['usedBytes'])}  "
          f"available {fmt_gb(disk['availableBytes'])}")


def render_scan(data: dict) -> None:
    render_disk(data["disk"])
    print(f"\nReclaimable {fmt_gb(data['reclaimableBytes'])}  "
          f"safe {fmt_gb(data['safeBytes'])}  "
          f"applicable rules {data['applicableRuleCount']}  "
          f"scan {data['elapsedMs'] / 1000:.0f}s")

    rules = [r for r in data.get("rules", []) if r.get("bytes", 0) > 0]
    if not rules:
        return

    by_category: dict[str, float] = defaultdict(float)
    by_risk: dict[str, float] = defaultdict(float)
    for rule in rules:
        by_category[rule.get("category", "-")] += rule["bytes"]
        by_risk[rule.get("risk", "-")] += rule["bytes"]

    print("\nBy category:")
    for category, total in sorted(by_category.items(), key=lambda kv: -kv[1]):
        print(f"  {fmt_gb(total)}  {category}")
    print("By risk:")
    for risk, total in sorted(by_risk.items(), key=lambda kv: -kv[1]):
        print(f"  {fmt_gb(total)}  {risk}")

    print("\nTop rules (⚠ = requires quitting the owning app first):")
    for rule in sorted(rules, key=lambda r: -r["bytes"])[:15]:
        flag = "⚠" if rule.get("requiresAppClose") else " "
        print(f" {flag} {fmt_gb(rule['bytes'])}  {rule['ruleId']}  "
              f"({rule.get('risk', '-')}, {rule.get('fileCount', 0)} files)")


def render_apply(data: dict) -> None:
    cleanup = data["cleanup"]
    selected = data.get("selectedBytes", 0)
    print(f"selected {fmt_gb(selected)}  "
          f"released {fmt_gb(cleanup['releasedBytes'])}  "
          f"dryRun={cleanup['dryRun']}  "
          f"items {cleanup['affectedItemCount']} "
          f"({cleanup['failedItemCount']} failed)")

    actions = [a for a in cleanup.get("actions", [])
               if (a.get("bytesExpected") or 0) > 0
               or a.get("status") == "blocked"]
    print("\nPer-rule outcome:")
    for action in sorted(actions, key=lambda a: -(a.get("bytesExpected") or 0)):
        reason = action.get("reasonCode") or "-"
        print(f"  {action['status']:<10} "
              f"expected {fmt_gb(action.get('bytesExpected') or 0)}  "
              f"released {fmt_gb(action.get('releasedBytes') or 0)}  "
              f"[{reason}]  {action['ruleId']}")


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in ("scan", "apply"):
        fail("usage: mangodisk_report.py scan|apply <file.json>")
    mode, path = sys.argv[1], sys.argv[2]
    document = load(path)
    data = document.get("data", document)
    if mode == "scan":
        render_scan(data)
    else:
        render_apply(data)


if __name__ == "__main__":
    main()
