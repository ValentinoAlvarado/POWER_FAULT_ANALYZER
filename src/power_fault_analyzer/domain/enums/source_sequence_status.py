"""Availability states for source sequence equivalents."""

from enum import StrEnum


class SourceSequenceStatus(StrEnum):
    AVAILABLE = "available"
    BLOCKED = "blocked"
    UNSPECIFIED = "unspecified"
