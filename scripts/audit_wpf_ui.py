#!/usr/bin/env python3
"""Backwards-compatible CLI entrypoint for WPF / XAML UI static auditing.

Delegates all checks directly to audit_windows_app.run_audit(root, ui_only=True)
so UI rules remain defined in a single place without duplication.

Usage:
  python audit_wpf_ui.py <path-to-wpf-project-dir> [--strict] [--json | --sarif]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_windows_app import build_sarif_report, run_audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Static auditor for WPF XAML & C# UI projects.")
    parser.add_argument("project_dir", help="Path to the WPF project directory")
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 if any ERROR or WARN finding is reported (useful in CI)")
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument("--json", action="store_true", help="Print findings as JSON")
    output_group.add_argument("--sarif", action="store_true", help="Print findings as SARIF 2.1.0 JSON")
    args = parser.parse_args(argv)

    root = Path(args.project_dir).resolve()
    if not root.is_dir():
        print(f"Directory not found: {root}", file=sys.stderr)
        return 2

    result = run_audit(root, ui_only=True)
    findings = result["findings"]

    if args.json:
        payload = {
            "root": result["root"],
            "xaml_files": result["xaml_files"],
            "cs_files": result["cs_files"],
            "findings": findings,
        }
        print(json.dumps(payload, indent=2))
    elif args.sarif:
        print(json.dumps(build_sarif_report(result), indent=2))
    else:
        print(f"Scanned {result['xaml_files']} XAML and {result['cs_files']} C# files in {root}")
        print(f"Total findings: {len(findings)}\n")
        for item in findings:
            print(item)

    blocking = result["counts"]["error"] + result["counts"]["warn"]
    return 1 if (args.strict and blocking > 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
