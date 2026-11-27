from __future__ import annotations

import json
from pathlib import Path

from power_fault_analyzer.scripting.worker import execute_request, main


def test_file_protocol_returns_serialized_workspace(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    response = tmp_path / "response.json"
    request.write_text(
        json.dumps({
            "source": (
                'project = ScriptProject("Frozen worker test")\n'
                'project.add_bus("BUS-01", voltage_kv=13.8)\n'
                'project.assert_valid()\n'
                'workspace = project.render()\n'
            )
        }),
        encoding="utf-8",
    )

    assert main(str(request), str(response)) == 0
    payload = json.loads(response.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["project_name"] == "Frozen worker test"
    assert len(payload["document"]["network"]["buses"]) == 1


def test_file_protocol_serializes_script_errors_without_console_streams(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    response = tmp_path / "response.json"
    request.write_text(json.dumps({"source": "project = 42"}), encoding="utf-8")

    assert main(str(request), str(response)) == 1
    payload = json.loads(response.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["error_type"] == "TypeError"
    assert "Script must create a ScriptProject" in payload["error"]


def test_worker_captures_print_output() -> None:
    result = execute_request({
        "source": (
            'project = ScriptProject("Captured output test")\\n'
            'project.add_bus("BUS-01", voltage_kv=13.8)\\n'
            'print("PFA automation output")\\n'
        )
    })

    assert result["ok"] is True
    assert result["captured_output"] == "PFA automation output\\n"
