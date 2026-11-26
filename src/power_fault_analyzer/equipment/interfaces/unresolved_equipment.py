"""Explicit connection endpoints for equipment whose electrical data is not supplied."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from uuid import UUID

from power_fault_analyzer.domain.entities.electrical_equipment import ElectricalEquipmentBase
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.enums.equipment_interface import (
    EquipmentInterfaceKind,
    ParameterEvidenceStatus,
)
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)


@dataclass(frozen=True, slots=True)
class EngineeringParameter:
    """Parameter value with mandatory evidence state and optional provenance reference."""

    name: str
    unit: str
    value: float | str | None = None
    status: ParameterEvidenceStatus = ParameterEvidenceStatus.UNRESOLVED
    source_reference: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Parameter name cannot be empty.")
        if not isinstance(self.unit, str) or not self.unit.strip():
            raise ValueError("Parameter unit cannot be empty.")
        if not isinstance(self.status, ParameterEvidenceStatus):
            raise TypeError("status must be ParameterEvidenceStatus.")
        if isinstance(self.value, bool):
            raise TypeError("Boolean parameter values are not accepted.")
        if isinstance(self.value, Real):
            numeric = float(self.value)
            if not math.isfinite(numeric):
                raise ValueError("Numeric parameter values must be finite.")
            object.__setattr__(self, "value", numeric)
        elif self.value is not None and not isinstance(self.value, str):
            raise TypeError("Parameter value must be a finite real, string or None.")
        if (
            self.status
            in {
                ParameterEvidenceStatus.UNRESOLVED,
                ParameterEvidenceStatus.CONFLICTING,
            }
            and self.value is not None
        ):
            raise ValueError("Unresolved/conflicting parameters cannot carry an accepted value.")
        if (
            self.status
            in {
                ParameterEvidenceStatus.SOURCE_VERIFIED,
                ParameterEvidenceStatus.USER_CONFIRMED,
                ParameterEvidenceStatus.DERIVED,
            }
            and self.value is None
        ):
            raise ValueError("Resolved parameter statuses require an explicit value.")
        if self.status in {
            ParameterEvidenceStatus.SOURCE_VERIFIED,
            ParameterEvidenceStatus.USER_CONFIRMED,
            ParameterEvidenceStatus.DERIVED,
        } and (not isinstance(self.source_reference, str) or not self.source_reference.strip()):
            raise ValueError(
                "Resolved parameter statuses require a source_reference or derivation reference."
            )
        if isinstance(self.value, str):
            value = self.value.strip()
            if not value and self.status not in {
                ParameterEvidenceStatus.UNRESOLVED,
                ParameterEvidenceStatus.CONFLICTING,
            }:
                raise ValueError("Resolved text parameter values cannot be empty.")
            object.__setattr__(self, "value", value)
        if self.source_reference is not None:
            if not isinstance(self.source_reference, str) or not self.source_reference.strip():
                raise ValueError("source_reference must be a non-empty string or None.")
            object.__setattr__(self, "source_reference", self.source_reference.strip())
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "unit", self.unit.strip())


_LINE_PARAMETERS = (
    ("remote_nominal_voltage", "kV line-line"),
    ("length", "km"),
    ("r1_per_km", "ohm/km"),
    ("x1_per_km", "ohm/km"),
    ("r2_per_km", "ohm/km"),
    ("x2_per_km", "ohm/km"),
    ("r0_per_km", "ohm/km"),
    ("x0_per_km", "ohm/km"),
    ("frequency_hz", "Hz"),
    ("model_kind", "series_only or pi"),
)
_TRANSFORMER_PARAMETERS = (
    ("rated_power", "MVA"),
    ("hv_rated_voltage", "kV line-line"),
    ("lv_rated_voltage", "kV line-line"),
    ("hv_connection", "winding connection"),
    ("lv_connection", "winding connection"),
    ("vector_group_clock", "hour"),
    ("impedance_base_power", "MVA"),
    ("impedance_base_hv_voltage", "kV line-line"),
    ("frequency_hz", "Hz"),
    ("r1_pu", "pu"),
    ("x1_pu", "pu"),
    ("r2_pu", "pu"),
    ("x2_pu", "pu"),
    ("r0_pu", "pu"),
    ("x0_pu", "pu"),
    ("hv_neutral_grounding", "grounding model"),
    ("lv_neutral_grounding", "grounding model"),
)


class UnresolvedEquipmentInterface(ElectricalEquipmentBase):
    """A one-terminal boundary placeholder, never a numerical equipment model.

    It preserves the intended connection of a line or transformer bay while
    keeping absent nameplate/network data explicitly unresolved. The sequence
    builder emits an ERROR for this type and refuses to calculate through it.
    """

    __slots__ = ("_interface_kind", "_parameters")

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminal: Terminal,
        interface_kind: EquipmentInterfaceKind,
        parameters: tuple[EngineeringParameter, ...] | None = None,
    ) -> None:
        if not isinstance(terminal, Terminal):
            raise TypeError("terminal must be a Terminal entity.")
        if not isinstance(interface_kind, EquipmentInterfaceKind):
            raise TypeError("interface_kind must be EquipmentInterfaceKind.")
        expected = (
            _LINE_PARAMETERS
            if interface_kind is EquipmentInterfaceKind.TRANSMISSION_LINE
            else _TRANSFORMER_PARAMETERS
        )
        if parameters is None:
            parameters = tuple(EngineeringParameter(name=key, unit=unit) for key, unit in expected)
        if not isinstance(parameters, tuple) or any(
            not isinstance(item, EngineeringParameter) for item in parameters
        ):
            raise TypeError("parameters must be a tuple of EngineeringParameter values.")
        expected_names = {name for name, _ in expected}
        actual_names = {item.name for item in parameters}
        if actual_names != expected_names or len(actual_names) != len(parameters):
            raise ValueError("Parameter names must match the exact interface-kind requirements.")
        family = (
            EquipmentFamily.TRANSMISSION
            if interface_kind is EquipmentInterfaceKind.TRANSMISSION_LINE
            else EquipmentFamily.TRANSFORMER
        )
        super().__init__(id=id, name=name, terminals=(terminal,), family=family)
        self._interface_kind = interface_kind
        self._parameters = parameters

    @property
    def interface_kind(self) -> EquipmentInterfaceKind:
        return self._interface_kind

    @property
    def parameters(self) -> tuple[EngineeringParameter, ...]:
        return self._parameters

    @property
    def unresolved_parameters(self) -> tuple[EngineeringParameter, ...]:
        return tuple(
            item
            for item in self.parameters
            if item.status
            in {
                ParameterEvidenceStatus.UNRESOLVED,
                ParameterEvidenceStatus.CONFLICTING,
            }
        )

    @property
    def is_model_ready(self) -> bool:
        return not self.unresolved_parameters

    def validate_configuration(self) -> tuple[DomainDiagnostic, ...]:
        unresolved = self.unresolved_parameters
        if not unresolved:
            return ()
        names = ", ".join(item.name for item in unresolved)
        return (
            DomainDiagnostic(
                code="EQUIPMENT-DATA-UNRESOLVED",
                message=(
                    f"{self.name} is an interface placeholder, not a calculation model. "
                    f"Unresolved/conflicting parameters: {names}."
                ),
                severity=DiagnosticSeverity.WARNING,
                entity_id=self.id,
            ),
        )
