"""Domain exception types."""

from .network_exceptions import (
    DuplicateEntityError,
    EntityInUseError,
    EntityNotFoundError,
    EquipmentConfigurationError,
    InvalidConnectionError,
    InvalidEquipmentError,
    NetworkDomainError,
    TerminalAlreadyConnectedError,
    VoltageIncompatibilityError,
)
from .source_exceptions import (
    SourceModelError,
    SourceSequenceDataUnavailableError,
    UnsupportedSourceOperatingRegimeError,
)

__all__ = [
    "DuplicateEntityError",
    "EntityInUseError",
    "EntityNotFoundError",
    "EquipmentConfigurationError",
    "InvalidConnectionError",
    "InvalidEquipmentError",
    "NetworkDomainError",
    "SourceModelError",
    "SourceSequenceDataUnavailableError",
    "TerminalAlreadyConnectedError",
    "UnsupportedSourceOperatingRegimeError",
    "VoltageIncompatibilityError",
]
