"""Typed structural contracts for the electrical network domain."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.value_objects.connection import Connection
from power_fault_analyzer.domain.value_objects.diagnostic import DomainDiagnostic
from power_fault_analyzer.domain.value_objects.voltage import Voltage


@runtime_checkable
class ElectricalElement(Protocol):
    """Structural contract for any identifiable electrical element."""

    @property
    def id(self) -> UUID: ...

    @property
    def name(self) -> str: ...


@runtime_checkable
class BusContract(ElectricalElement, Protocol):
    @property
    def nominal_voltage(self) -> Voltage: ...


@runtime_checkable
class TerminalContract(Protocol):
    """Read-only terminal contract; implementations should be immutable entities."""

    @property
    def id(self) -> UUID: ...

    @property
    def equipment_id(self) -> UUID: ...

    @property
    def designation(self) -> str: ...

    @property
    def rated_voltage(self) -> Voltage: ...


@runtime_checkable
class TerminalProvider(Protocol):
    @property
    def terminals(self) -> tuple[TerminalContract, ...]: ...


@runtime_checkable
class ElectricalEquipment(ElectricalElement, TerminalProvider, Protocol):
    """Structural equipment contract; exposed identity and terminals are stable."""

    @property
    def family(self) -> EquipmentFamily: ...

    def validate_configuration(self) -> tuple[DomainDiagnostic, ...]: ...


@runtime_checkable
class NetworkAggregate(Protocol):
    """Public contract implemented by the Network aggregate root."""

    @property
    def id(self) -> UUID: ...

    @property
    def name(self) -> str: ...

    @property
    def buses(self) -> tuple[BusContract, ...]: ...

    @property
    def equipment(self) -> tuple[ElectricalEquipment, ...]: ...

    @property
    def terminals(self) -> tuple[TerminalContract, ...]: ...

    @property
    def connections(self) -> tuple[Connection, ...]: ...

    def add_bus(self, bus: BusContract) -> None: ...

    def add_equipment(self, equipment: ElectricalEquipment) -> None: ...

    def connect(self, terminal_id: UUID, bus_id: UUID) -> Connection: ...

    def disconnect(self, terminal_id: UUID) -> None: ...

    def remove_bus(self, bus_id: UUID) -> None: ...

    def remove_equipment(self, equipment_id: UUID) -> None: ...

    def get_bus(self, bus_id: UUID) -> BusContract: ...

    def get_equipment(self, equipment_id: UUID) -> ElectricalEquipment: ...
