from __future__ import annotations

from pathlib import Path

from power_fault_analyzer.application.use_cases.project_workspace import ProjectWorkspaceService
from power_fault_analyzer.domain.projects.models import Project
from power_fault_analyzer.infrastructure.persistence.json_project_repository import (
    JSONProjectRepository,
)


def test_workspace_creates_and_round_trips_a_project(tmp_path: Path) -> None:
    service = ProjectWorkspaceService(JSONProjectRepository())
    project = service.create("REF-3PH-001B", "First external benchmark desktop study")

    saved_path = service.save(project, tmp_path / "ref-3ph-001b")
    loaded = service.open(saved_path)

    assert saved_path.suffix == ".pfa"
    assert loaded == project
    assert loaded.name == "REF-3PH-001B"


def test_project_repository_rejects_unsupported_schema(tmp_path: Path) -> None:
    target = tmp_path / "wrong-schema.pfa"
    target.write_text('{"schema_version":"99.0"}', encoding="utf-8")

    try:
        JSONProjectRepository().load(target)
    except ValueError as exc:
        assert "Unsupported project schema" in str(exc)
    else:
        raise AssertionError("Unsupported project schema was accepted.")


def test_project_default_is_a_domain_aggregate() -> None:
    project = Project.create()

    assert project.project_id is not None
    assert project.study_history == ()
