"""Project workspace operations independent of the desktop toolkit."""

from __future__ import annotations

from pathlib import Path

from power_fault_analyzer.application.ports.project_repository import ProjectRepositoryPort
from power_fault_analyzer.domain.projects.models import Project, TheveninStudySettings


class ProjectWorkspaceService:
    def __init__(self, repository: ProjectRepositoryPort) -> None:
        self._repository = repository

    def create(
        self,
        name: str = "Untitled Project",
        description: str = "",
        study_settings: TheveninStudySettings | None = None,
    ) -> Project:
        return Project.create(
            name=name,
            description=description,
            study_settings=study_settings,
        )

    def open(self, path: str | Path) -> Project:
        return self._repository.load(path)

    def save(self, project: Project, path: str | Path) -> Path:
        return self._repository.save(project, path)
