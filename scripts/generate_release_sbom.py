"""Generate a CycloneDX 1.6 inventory of installed Python distributions."""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.metadata as metadata
import json
import re
import sys
import uuid
from pathlib import Path


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--repository", default="https://github.com/ValentinoAlvarado/POWER_FAULT_ANALYZER")
    args = parser.parse_args()

    components = []
    for dist in metadata.distributions():
        name = dist.metadata.get("Name")
        version = dist.version
        if not name or not version:
            continue
        license_value = dist.metadata.get("License-Expression") or dist.metadata.get("License")
        classifiers = dist.metadata.get_all("Classifier") or []
        license_names = [c.split(" :: ", 2)[-1] for c in classifiers if c.startswith("License :: ")]
        licenses = []
        if license_value and license_value.strip() not in {"UNKNOWN", "UNKNOWN LICENSE"}:
            licenses.append({"license": {"name": license_value.strip()}})
        elif license_names:
            licenses.extend({"license": {"name": value}} for value in sorted(set(license_names)))
        else:
            licenses.append({"license": {"name": "NOASSERTION — inspect package metadata"}})
        purl = f"pkg:pypi/{norm(name)}@{version}"
        component = {
            "type": "library",
            "name": name,
            "version": version,
            "purl": purl,
            "bom-ref": purl,
            "licenses": licenses,
        }
        home = dist.metadata.get("Home-page")
        if home:
            component["externalReferences"] = [{"type": "website", "url": home}]
        components.append(component)

    components.sort(key=lambda item: (item["name"].lower(), item["version"]))
    root_ref = f"pkg:generic/POWER_FAULT_ANALYZER@{args.version}"
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": now,
            "component": {
                "type": "application",
                "name": "POWER_FAULT_ANALYZER",
                "version": args.version,
                "bom-ref": root_ref,
                "licenses": [{"expression": "GPL-3.0-or-later"}],
                "externalReferences": [{"type": "vcs", "url": args.repository}],
            },
            "tools": {"components": [{"type": "application", "name": "PFA release SBOM generator", "version": "1.0.0"}]},
        },
        "components": components,
        "dependencies": [{"ref": root_ref, "dependsOn": [item["bom-ref"] for item in components]}]
        + [{"ref": item["bom-ref"], "dependsOn": []} for item in components],
        "properties": [
            {"name": "pfa:inventory-scope", "value": "All Python distributions installed in the Windows release build environment; includes build and test tools as well as runtime packages."},
            {"name": "pfa:license-review", "value": "Packages marked NOASSERTION require manual license review before binary redistribution."},
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bom, indent=2) + "\n", encoding="utf-8")
    print(f"CycloneDX SBOM written: {args.output} ({len(components)} Python distributions)")
    unknown = sum(any("NOASSERTION" in x.get("license", {}).get("name", "") for x in c.get("licenses", [])) for c in components)
    print(f"Packages requiring manual license metadata review: {unknown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
