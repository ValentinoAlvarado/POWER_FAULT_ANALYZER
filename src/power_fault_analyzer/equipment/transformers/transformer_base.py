"""Shared transformer entity behavior and winding invariants."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from power_fault_analyzer.domain.entities.electrical_equipment import ElectricalEquipmentBase
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.enums.winding_designation import WindingDesignation
from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.transformer_winding import TransformerWinding


class TransformerEquipmentBase(ElectricalEquipmentBase, ABC):
    """Base entity for transformer equipment of explicit terminal cardinality."""

    __slots__ = ("_frequency", "_windings")

    @property
    @abstractmethod
    def winding_count(self) -> int:
        """Exact number of windings supported by the concrete transformer."""

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminals: tuple[Terminal, ...],
        windings: tuple[TransformerWinding, ...],
        frequency: Frequency,
    ) -> None:
        if not isinstance(terminals, tuple) or not terminals:
            raise TypeError("terminals must be a non-empty immutable tuple.")
        if any(not isinstance(item, Terminal) for item in terminals):
            raise TypeError("Every transformer terminal must be a Terminal entity.")
        if not isinstance(windings, tuple) or not windings:
            raise TypeError("windings must be a non-empty immutable tuple.")
        if any(not isinstance(item, TransformerWinding) for item in windings):
            raise TypeError("Every winding must be a TransformerWinding value.")
        if not isinstance(frequency, Frequency):
            raise TypeError("frequency must be a Frequency value.")
        if len(terminals) != len(windings):
            raise ValueError("Transformer terminal count must equal winding count.")
        if len(windings) != self.winding_count:
            raise ValueError(
                f"{type(self).__name__} requires exactly {self.winding_count} windings."
            )
        designations = tuple(item.designation for item in windings)
        if len(designations) != len(set(designations)):
            raise ValueError("Transformer winding designations must be unique.")
        for terminal, winding in zip(terminals, windings, strict=True):
            if terminal.designation.upper() != winding.designation.value:
                raise ValueError(
                    "Terminal designations must match winding order: "
                    f"expected {winding.designation.value!r}, got {terminal.designation!r}."
                )
            tolerance = max(1e-9, winding.rated_voltage_kv * 1e-9)
            if abs(terminal.rated_voltage.value_kv - winding.rated_voltage_kv) > tolerance:
                raise ValueError(
                    f"Terminal voltage for {winding.designation.value} does not match "
                    "the winding rated voltage."
                )
        super().__init__(
            id=id,
            name=name,
            terminals=terminals,
            family=EquipmentFamily.TRANSFORMER,
        )
        self._frequency = frequency
        self._windings = windings

    @property
    def frequency(self) -> Frequency:
        return self._frequency

    @property
    def windings(self) -> tuple[TransformerWinding, ...]:
        return self._windings

    def get_winding(self, designation: WindingDesignation) -> TransformerWinding:
        if not isinstance(designation, WindingDesignation):
            raise TypeError("designation must be a WindingDesignation value.")
        for winding in self.windings:
            if winding.designation is designation:
                return winding
        raise KeyError(designation)
