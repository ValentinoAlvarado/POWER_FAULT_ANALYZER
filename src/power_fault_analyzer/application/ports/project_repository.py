"""Output port for loading and saving project aggregates."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from power_fault_analyzer.domain.projects.models import Project


class ProjectRepositoryPort(Protocol):
    def load(self, path: str | Path) -> Project: ...

    def save(self, project: Project, path: str | Path) -> Path: ...
