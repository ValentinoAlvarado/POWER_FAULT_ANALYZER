"""Persistence port for a physical network and its independent diagram layout."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from power_fault_analyzer.application.use_cases.network_workspace import NetworkWorkspace


class NetworkDocumentRepositoryPort(Protocol):
    def load(self, path: str | Path) -> NetworkWorkspace: ...

    def save(self, workspace: NetworkWorkspace, path: str | Path) -> Path: ...
