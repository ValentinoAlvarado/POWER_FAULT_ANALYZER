"""Structured domain diagnostics."""

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class DiagnosticSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class DomainDiagnostic:
    """A machine-readable validation or domain diagnostic."""

    code: str
    message: str
    severity: DiagnosticSeverity
    entity_id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("Diagnostic code cannot be empty.")
        if not self.message.strip():
            raise ValueError("Diagnostic message cannot be empty.")
        if not isinstance(self.severity, DiagnosticSeverity):
            raise TypeError("severity must be a DiagnosticSeverity.")
        if self.entity_id is not None and not isinstance(self.entity_id, UUID):
            raise TypeError("entity_id must be a UUID or None.")
