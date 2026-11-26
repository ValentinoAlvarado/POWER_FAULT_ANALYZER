"""Code-first CLI delegating to canonical PFA domain and application services."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from power_fault_analyzer.application.use_cases.network_workspace import NetworkWorkspace
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.services.network_validation_service import (
    DefaultNetworkValidationService,
)
from power_fault_analyzer.infrastructure.persistence.json_network_document_repository import (
    JSONNetworkDocumentRepository,
)


def _repository() -> JSONNetworkDocumentRepository:
    return JSONNetworkDocumentRepository()


def _diagnostics_payload(diagnostics: Sequence[object]) -> list[dict[str, str]]:
    return [{"code": item.code, "severity": item.severity.value, "message": item.message}
            for item in diagnostics]


def command_create(args: argparse.Namespace) -> int:
    workspace = NetworkWorkspace(network=Network(args.name))
    target = _repository().save(workspace, args.output)
    print(json.dumps({"status": "created", "project_name": workspace.network.name,
        "network_id": str(workspace.network.id), "file": str(target.resolve()),
        "schema": _repository().SCHEMA_VERSION}, indent=2, ensure_ascii=False))
    return 0


def command_inspect(args: argparse.Namespace) -> int:
    workspace = _repository().load(args.project)
    network = workspace.network
    payload = {
        "project": network.name, "network_id": str(network.id),
        "document": str(args.project.resolve()), "schema": _repository().SCHEMA_VERSION,
        "counts": {"buses": len(network.buses), "equipment": len(network.equipment),
            "connections": len(network.connections), "diagram_symbols": len(workspace.diagram_symbols),
            "diagram_labels": len(workspace.diagram_labels), "study_history": len(workspace.study_history)},
        "buses": [{"id": str(bus.id), "name": bus.name,
            "nominal_voltage_kv": bus.nominal_voltage.value_kv, "kind": bus.kind.value}
            for bus in network.buses],
        "equipment": [{"id": str(item.id), "name": item.name,
            "type": type(item).__name__, "terminals": len(item.terminals)}
            for item in network.equipment],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def command_validate(args: argparse.Namespace) -> int:
    workspace = _repository().load(args.project)
    validator = DefaultNetworkValidationService()
    diagnostics = (validator.validate_for_calculation(workspace.network) if args.for_calculation
                   else validator.validate_structure(workspace.network))
    errors = [item for item in diagnostics if item.severity.value == "error"]
    warnings = [item for item in diagnostics if item.severity.value == "warning"]
    payload = {
        "project": workspace.network.name, "network_id": str(workspace.network.id),
        "validation_scope": "calculation" if args.for_calculation else "structure",
        "status": "failed" if errors else "passed",
        "summary": {"errors": len(errors), "warnings": len(warnings), "diagnostics": len(diagnostics)},
        "diagnostics": _diagnostics_payload(diagnostics),
        "important": ("A passed validation is not proof of IEC 60909 conformity, numerical accuracy, "
            "protection coordination or equipment rating adequacy."),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pfa",
        description="POWER_FAULT_ANALYZER — code-first electrical engineering platform")
    parser.add_argument("--version", action="version", version="POWER_FAULT_ANALYZER 0.1.0b1")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Create a native PFA network document")
    create.add_argument("name")
    create.add_argument("-o", "--output", type=Path, required=True)
    create.set_defaults(handler=command_create)
    inspect = commands.add_parser("inspect", help="Inspect a native PFA network document")
    inspect.add_argument("project", type=Path)
    inspect.set_defaults(handler=command_inspect)
    validate = commands.add_parser("validate", help="Validate network structure or calculation readiness")
    validate.add_argument("project", type=Path)
    validate.add_argument("--for-calculation", action="store_true")
    validate.set_defaults(handler=command_validate)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"pfa: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
