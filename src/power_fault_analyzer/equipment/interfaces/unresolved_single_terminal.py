"""Single-terminal placeholder for equipment with unresolved technical data."""
from __future__ import annotations
from uuid import UUID
from power_fault_analyzer.domain.entities.electrical_equipment import ElectricalEquipmentBase
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.value_objects.diagnostic import DiagnosticSeverity, DomainDiagnostic
from .unresolved_equipment import EngineeringParameter
from power_fault_analyzer.domain.enums.equipment_interface import ParameterEvidenceStatus


class UnresolvedSingleTerminalEquipment(ElectricalEquipmentBase):
    __slots__ = ("_equipment_kind", "_parameters")

    def __init__(self, *, id: UUID, name: str, terminal: Terminal,
                 equipment_kind: str, family: EquipmentFamily,
                 parameters: tuple[EngineeringParameter, ...]) -> None:
        if not isinstance(equipment_kind, str) or not equipment_kind.strip():
            raise ValueError("equipment_kind must be non-empty.")
        if not isinstance(family, EquipmentFamily):
            raise TypeError("family must be EquipmentFamily.")
        if not isinstance(parameters, tuple) or not parameters:
            raise ValueError("parameters must be a non-empty tuple.")
        if any(not isinstance(item, EngineeringParameter) for item in parameters):
            raise TypeError("parameters must contain EngineeringParameter values.")
        super().__init__(id=id, name=name, terminals=(terminal,), family=family)
        self._equipment_kind = equipment_kind.strip()
        self._parameters = parameters

    @property
    def equipment_kind(self) -> str:
        return self._equipment_kind

    @property
    def parameters(self) -> tuple[EngineeringParameter, ...]:
        return self._parameters

    @property
    def is_model_ready(self) -> bool:
        return all(item.status not in {ParameterEvidenceStatus.UNRESOLVED,
                                       ParameterEvidenceStatus.CONFLICTING}
                   for item in self.parameters)

    def validate_configuration(self) -> tuple[DomainDiagnostic, ...]:
        if self.is_model_ready:
            return ()
        names = ", ".join(item.name for item in self.parameters
                          if item.status in {ParameterEvidenceStatus.UNRESOLVED,
                                             ParameterEvidenceStatus.CONFLICTING})
        return (DomainDiagnostic(
            code="EQUIPMENT-DATA-UNRESOLVED",
            message=f"{self.name} is a topology placeholder, not a numerical model. "
                    f"Unresolved parameters: {names}.",
            severity=DiagnosticSeverity.WARNING, entity_id=self.id),)
