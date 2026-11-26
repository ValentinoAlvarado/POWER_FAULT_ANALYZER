"""Domain exceptions for source-equivalent and fault-contribution models."""


class SourceModelError(Exception):
    """Base exception for invalid source-model operations."""


class UnsupportedSourceOperatingRegimeError(SourceModelError):
    """Raised when a source does not provide the requested time regime."""


class SourceSequenceDataUnavailableError(SourceModelError):
    """Raised when a requested sequence equivalent is not specified or blocked."""
