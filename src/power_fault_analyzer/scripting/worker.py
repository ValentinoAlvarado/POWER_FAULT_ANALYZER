"""Isolated-process script worker for trusted local PFA automation.

The process boundary protects the Qt event loop and allows cancellation. It is
not advertised as a hardened security sandbox; only trusted scripts should run.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

from power_fault_analyzer.infrastructure.persistence.json_network_document_repository import JSONNetworkDocumentRepository
from power_fault_analyzer.scripting.project import ScriptProject
from power_fault_analyzer.domain.enums.bus_kind import BusKind
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.enums.switching_device import SwitchingDeviceKind, SwitchPosition


_ALLOWED_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "complex": complex,
    "dict": dict, "enumerate": enumerate, "float": float, "int": int,
    "len": len, "list": list, "max": max, "min": min, "range": range,
    "reversed": reversed, "round": round, "set": set, "sorted": sorted,
    "str": str, "sum": sum, "tuple": tuple, "zip": zip,
    "ValueError": ValueError, "TypeError": TypeError,
}


class ScriptPolicyError(ValueError):
    pass


def validate_script_policy(source: str) -> None:
    tree = ast.parse(source, filename="<PFA automation>")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ScriptPolicyError("Imports are disabled in the worker API. Use the injected ScriptProject capability.")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise ScriptPolicyError("global/nonlocal declarations are not supported.")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ScriptPolicyError("Dunder names are not available in the automation API.")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ScriptPolicyError("Dunder attribute access is not available in the automation API.")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"open", "exec", "eval", "compile", "__import__"}:
                raise ScriptPolicyError(f"Call to {node.func.id!r} is not permitted.")


def execute_request(request: dict) -> dict:
    source = request.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source must be a non-empty string.")
    validate_script_policy(source)
    namespace = {
        "__builtins__": _ALLOWED_BUILTINS,
        "ScriptProject": ScriptProject,
        "BusKind": BusKind,
        "EquipmentFamily": EquipmentFamily,
        "SwitchingDeviceKind": SwitchingDeviceKind,
        "SwitchPosition": SwitchPosition,
    }
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        exec(compile(source, "<PFA Code & Automation Worker>", "exec"), namespace, namespace)
    project = namespace.get("project")
    if not isinstance(project, ScriptProject):
        raise TypeError("Script must create a ScriptProject instance named 'project'.")
    project.assert_valid()
    workspace = namespace.get("workspace", project.render())
    if workspace is not project.workspace:
        raise TypeError("workspace must be the NetworkWorkspace returned by project.render().")
    with tempfile.TemporaryDirectory(prefix="pfa-worker-") as directory:
        path = Path(directory) / "workspace.json"
        JSONNetworkDocumentRepository().save(workspace, path)
        document = json.loads(path.read_text(encoding="utf-8"))
    return {"ok": True, "project_name": project.name, "document": document,
            "captured_output": captured.getvalue()}


def main() -> int:
    try:
        request = json.loads(sys.stdin.read())
        result = execute_request(request)
        sys.stdout.write(json.dumps(result, allow_nan=False))
        return 0
    except Exception as exc:  # protocol boundary: serialize a concise failure
        sys.stdout.write(json.dumps({"ok": False, "error_type": type(exc).__name__,
                                     "error": str(exc)}, allow_nan=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
