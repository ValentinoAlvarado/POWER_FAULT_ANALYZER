"""Equipment base classes and terminal-cardinality specializations."""

from __future__ import annotations

from typing import final
from uuid import UUID

from power_fault_analyzer.domain.entities._validation import validate_non_empty_name
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.value_objects.diagnostic import DomainDiagnostic


class ElectricalEquipmentBase:
    """Nominal base class implementing shared equipment identity and terminals.

    Concrete equipment classes should inherit from a cardinality-specific base
    (for example ``TwoTerminalEquipmentBase``) and declare their family.
    """

    __slots__ = ("_family", "_id", "_name", "_terminals")

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminals: tuple[Terminal, ...],
        family: EquipmentFamily = EquipmentFamily.GENERIC,
    ) -> None:
        if not isinstance(id, UUID):
            raise TypeError("Equipment id must be a UUID.")
        validate_non_empty_name(name)
        if not isinstance(family, EquipmentFamily):
            raise TypeError("family must be an EquipmentFamily value.")
        if not isinstance(terminals, tuple):
            raise TypeError("terminals must be provided as an immutable tuple.")
        if not terminals:
            raise ValueError("Equipment must expose at least one terminal.")
        if any(not isinstance(terminal, Terminal) for terminal in terminals):
            raise TypeError("Every equipment terminal must be a Terminal entity.")
        terminal_ids = [terminal.id for terminal in terminals]
        if len(terminal_ids) != len(set(terminal_ids)):
            raise ValueError("Equipment cannot contain duplicate terminal IDs.")
        if any(terminal.id == id for terminal in terminals):
            raise ValueError("A terminal ID cannot equal its owning equipment ID.")
        if any(terminal.equipment_id != id for terminal in terminals):
            raise ValueError("Every terminal equipment_id must match its owning equipment ID.")
        designations = [terminal.designation.casefold() for terminal in terminals]
        if len(designations) != len(set(designations)):
            raise ValueError("Terminal designations must be unique within equipment.")

        self._id = id
        self._name = name.strip()
        self._terminals = terminals
        self._family = family

    @property
    @final
    def id(self) -> UUID:
        return self._id

    @property
    @final
    def name(self) -> str:
        return self._name

    @property
    @final
    def terminals(self) -> tuple[Terminal, ...]:
        return self._terminals

    @property
    @final
    def family(self) -> EquipmentFamily:
        return self._family

    def validate_configuration(self) -> tuple[DomainDiagnostic, ...]:
        """Return equipment-specific diagnostics; subclasses may extend it."""
        return ()

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(id={self.id!r}, name={self.name!r}, "
            f"terminals={len(self.terminals)})"
        )


class TwoTerminalEquipmentBase(ElectricalEquipmentBase):
    """Base class for equipment exposing exactly two electrical terminals."""

    __slots__ = ()

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminals: tuple[Terminal, Terminal],
        family: EquipmentFamily = EquipmentFamily.GENERIC,
    ) -> None:
        if len(terminals) != 2:
            raise ValueError("Two-terminal equipment must expose exactly two terminals.")
        super().__init__(id=id, name=name, terminals=terminals, family=family)

    @property
    def terminal_from(self) -> Terminal:
        return self.terminals[0]

    @property
    def terminal_to(self) -> Terminal:
        return self.terminals[1]


class ThreeTerminalEquipmentBase(ElectricalEquipmentBase):
    """Base class for three-terminal equipment such as a three-winding transformer."""

    __slots__ = ()

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminals: tuple[Terminal, Terminal, Terminal],
        family: EquipmentFamily = EquipmentFamily.TRANSFORMER,
    ) -> None:
        if len(terminals) != 3:
            raise ValueError("Three-terminal equipment must expose exactly three terminals.")
        super().__init__(id=id, name=name, terminals=terminals, family=family)
