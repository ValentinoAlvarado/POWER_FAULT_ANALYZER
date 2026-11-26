"""Fail a tagged release when package-license metadata has not been reviewed."""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

UNKNOWN = "NOASSERTION — review package metadata"
ROW = re.compile(r"^\| `(?P<name>[^`]+)` \| `(?P<version>[^`]+)` \| (?P<license>[^|]+) \|", re.MULTILINE)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    args = parser.parse_args()

    if not args.inventory.is_file():
        print(f"License inventory not found: {args.inventory}", file=sys.stderr)
        return 2
    if not args.review.is_file():
        print(f"License review register not found: {args.review}", file=sys.stderr)
        return 2

    unresolved: set[tuple[str, str]] = set()
    for match in ROW.finditer(args.inventory.read_text(encoding="utf-8")):
        license_value = match.group("license").strip()
        if "NOASSERTION" in license_value.upper() or license_value.upper() in {"UNKNOWN", ""}:
            unresolved.add((match.group("name").strip(), match.group("version").strip()))

    reviewed: dict[tuple[str, str], dict[str, str]] = {}
    with args.review.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            key = (row.get("package", "").strip(), row.get("version", "").strip())
            if key[0] and key[1]:
                reviewed[key] = row

    missing = []
    for package, version in sorted(unresolved, key=lambda x: (x[0].lower(), x[1])):
        row = reviewed.get((package, version))
        if not row or any(not row.get(field, "").strip() for field in ("confirmed_license", "source_url", "reviewed_by", "notes")):
            missing.append((package, version))

    if missing:
        print("Release blocked: package-license metadata requires human review.", file=sys.stderr)
        for package, version in missing:
            print(f"  - {package}=={version}", file=sys.stderr)
        print(
            "Review each exact version, then complete RELEASE_LICENSE_REVIEW.csv with "
            "confirmed_license, source_url, reviewed_by and notes. Do not guess a license.",
            file=sys.stderr,
        )
        return 1

    print(f"PASS: all {len(unresolved)} packages with incomplete metadata have explicit review records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
