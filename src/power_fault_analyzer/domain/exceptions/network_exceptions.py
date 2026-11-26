"""Domain exceptions for network aggregate operations."""

from __future__ import annotations

from uuid import UUID


class NetworkDomainError(Exception):
    """Base exception for invalid electrical-network domain operations."""


class DuplicateEntityError(NetworkDomainError):
    """Raised when an entity identifier or network name is already registered."""


class EntityNotFoundError(NetworkDomainError):
    """Raised when an entity cannot be found in the network aggregate."""

    def __init__(self, entity_kind: str, entity_id: UUID) -> None:
        self.entity_kind = entity_kind
        self.entity_id = entity_id
        super().__init__(f"{entity_kind} with id '{entity_id}' was not found.")


class InvalidEquipmentError(NetworkDomainError):
    """Raised when an equipment object violates the equipment contract."""


class EquipmentConfigurationError(InvalidEquipmentError):
    """Raised when equipment reports error-level configuration diagnostics."""


class InvalidConnectionError(NetworkDomainError):
    """Raised when a terminal-to-bus connection violates domain rules."""


class TerminalAlreadyConnectedError(InvalidConnectionError):
    """Raised when a terminal is connected to more than one bus."""


class EntityInUseError(NetworkDomainError):
    """Raised when deleting an entity that is still referenced by connections."""


class VoltageIncompatibilityError(InvalidConnectionError):
    """Raised when terminal and bus nominal voltages are incompatible."""
