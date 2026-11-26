from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "verify_release_license_review.py"
SPEC = importlib.util.spec_from_file_location("verify_release_license_review", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_release_license_review_blocks_unreviewed_noassertion(tmp_path: Path, capsys) -> None:
    inventory = tmp_path / "inventory.md"
    review = tmp_path / "review.csv"
    inventory.write_text(
        "| Package | Version | License metadata | Project URL |\n"
        "|---|---:|---|---|\n"
        "| `example-dist` | `1.2.3` | NOASSERTION — review package metadata | https://example.test |\n",
        encoding="utf-8",
    )
    review.write_text(
        "package,version,confirmed_license,source_url,reviewed_by,notes\n",
        encoding="utf-8",
    )

    assert MODULE.main.__name__ == "main"
    # Exercise the command-line contract without mutating process-global argv.
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(MODULE_PATH), "--inventory", str(inventory), "--review", str(review)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "example-dist==1.2.3" in result.stderr


def test_release_license_review_accepts_completed_exact_version_record(tmp_path: Path) -> None:
    inventory = tmp_path / "inventory.md"
    review = tmp_path / "review.csv"
    inventory.write_text(
        "| Package | Version | License metadata | Project URL |\n"
        "|---|---:|---|---|\n"
        "| `example-dist` | `1.2.3` | NOASSERTION — review package metadata | https://example.test |\n",
        encoding="utf-8",
    )
    with review.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["package", "version", "confirmed_license", "source_url", "reviewed_by", "notes"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "package": "example-dist",
                "version": "1.2.3",
                "confirmed_license": "MIT",
                "source_url": "https://example.test/LICENSE",
                "reviewed_by": "Release maintainer",
                "notes": "Verified against the exact source distribution for version 1.2.3.",
            }
        )

    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(MODULE_PATH), "--inventory", str(inventory), "--review", str(review)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout
