"""Typed contracts for domain validation policies and services."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from power_fault_analyzer.domain.interfaces.network_contracts import NetworkAggregate
from power_fault_analyzer.domain.value_objects.diagnostic import DomainDiagnostic
from power_fault_analyzer.domain.value_objects.voltage import Voltage


class VoltageCompatibilityPolicy(Protocol):
    """Policy deciding whether a terminal's nominal voltage matches a bus."""

    def are_compatible(
        self,
        terminal_voltage: Voltage,
        bus_voltage: Voltage,
    ) -> bool: ...


class NetworkValidationService(Protocol):
    def validate_structure(
        self,
        network: NetworkAggregate,
    ) -> tuple[DomainDiagnostic, ...]: ...

    def validate_for_calculation(
        self,
        network: NetworkAggregate,
    ) -> tuple[DomainDiagnostic, ...]: ...


class NetworkTopologyProvider(Protocol):
    def get_connected_components(
        self,
        network: NetworkAggregate,
    ) -> tuple[tuple[UUID, ...], ...]: ...
