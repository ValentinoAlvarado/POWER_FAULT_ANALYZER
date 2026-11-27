"""Write a readable license inventory for all installed Python distributions."""
from __future__ import annotations
import argparse
import importlib.metadata as metadata
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    rows = []
    for dist in metadata.distributions():
        name = dist.metadata.get('Name')
        if not name:
            continue
        version = dist.version or 'unknown'
        license_text = dist.metadata.get('License-Expression') or dist.metadata.get('License')
        classifiers = dist.metadata.get_all('Classifier') or []
        classifiers = [value.split(' :: ', 2)[-1] for value in classifiers if value.startswith('License :: ')]
        if not license_text or license_text.strip().upper() in {'UNKNOWN', 'UNKNOWN LICENSE'}:
            license_text = '; '.join(sorted(set(classifiers))) if classifiers else 'NOASSERTION — review package metadata'
        home = dist.metadata.get('Home-page') or dist.metadata.get('Project-URL') or 'not supplied in package metadata'
        rows.append((name.lower(), f'| `{name}` | `{version}` | {license_text.replace("|", "/")} | {home.replace("|", "/")} |'))
    rows.sort(key=lambda row: row[0])
    body = ['# Python dependency license inventory', '',
            'Generated from the exact Python 3.13 release build environment. This inventory includes runtime, build and test tools; it may over-report packages not bundled into the application. Any `NOASSERTION` entry requires manual review before binary distribution.', '',
            '| Package | Version | License metadata | Project URL |', '|---|---:|---|---|']
    body.extend(row[1] for row in rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text('\n'.join(body) + '\n', encoding='utf-8')
    print(f'Python license inventory written: {args.output} ({len(rows)} packages)')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
