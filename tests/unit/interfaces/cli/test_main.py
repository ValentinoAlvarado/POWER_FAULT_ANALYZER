from __future__ import annotations

import json
from pathlib import Path

from power_fault_analyzer.application.use_cases.network_workspace import NetworkWorkspace
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.infrastructure.persistence.json_network_document_repository import (
    JSONNetworkDocumentRepository,
)
from power_fault_analyzer.interfaces.cli.main import main


def test_create_inspect_and_validate_empty_document(tmp_path: Path, capsys) -> None:
    target = tmp_path / "empty.pfan"
    assert main(["create", "CLI test network", "--output", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "created"
    assert target.exists()

    assert main(["inspect", str(target)]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["project"] == "CLI test network"
    assert inspected["counts"]["buses"] == 0

    assert main(["validate", str(target)]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["status"] == "passed"
    assert validated["validation_scope"] == "structure"


def test_validate_reports_calculation_readiness_separately(tmp_path: Path, capsys) -> None:
    target = JSONNetworkDocumentRepository().save(
        NetworkWorkspace(Network("No source network")), tmp_path / "network.pfan"
    )
    exit_code = main(["validate", str(target), "--for-calculation"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["validation_scope"] == "calculation"
    assert exit_code in {0, 1}
    assert payload["status"] in {"passed", "failed"}


def test_invalid_document_returns_cli_error(tmp_path: Path, capsys) -> None:
    assert main(["inspect", str(tmp_path / "missing.pfan")]) == 2
    assert "pfa: error:" in capsys.readouterr().err
