"""Default network validation service for the initial balanced-network domain."""

from __future__ import annotations

from power_fault_analyzer.domain.enums.source_sequence_status import SourceSequenceStatus
from power_fault_analyzer.domain.interfaces.network_contracts import NetworkAggregate
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.equipment.interfaces.unresolved_branch import (
    UnresolvedTwoTerminalEquipment,
)
from power_fault_analyzer.equipment.interfaces.unresolved_single_terminal import (
    UnresolvedSingleTerminalEquipment,
)
from power_fault_analyzer.equipment.sources.equivalent_source import EquivalentSource


class DefaultNetworkValidationService:
    """Validate a network for editing or calculation without solver dependencies."""

    def validate_structure(
        self,
        network: NetworkAggregate,
    ) -> tuple[DomainDiagnostic, ...]:
        diagnostics: list[DomainDiagnostic] = []
        for equipment in network.equipment:
            diagnostics.extend(equipment.validate_configuration())
        return tuple(diagnostics)

    def validate_for_calculation(
        self,
        network: NetworkAggregate,
    ) -> tuple[DomainDiagnostic, ...]:
        diagnostics = list(self.validate_structure(network))
        for equipment in network.equipment:
            if isinstance(equipment, (
                UnresolvedTwoTerminalEquipment, UnresolvedSingleTerminalEquipment,
            )):
                diagnostics.append(DomainDiagnostic(
                    code="NET-EQUIPMENT-MODEL-UNRESOLVED",
                    message=(f"{equipment.name} has unresolved technical data and is a "
                             "topology placeholder, not a calculation-ready model."),
                    severity=DiagnosticSeverity.ERROR, entity_id=equipment.id,
                ))
            if isinstance(equipment, EquivalentSource):
                unavailable = [
                    item.sequence.value for item in (
                        equipment.equivalent.positive,
                        equipment.equivalent.negative,
                        equipment.equivalent.zero,
                    ) if item.status is not SourceSequenceStatus.AVAILABLE
                ]
                if unavailable:
                    diagnostics.append(DomainDiagnostic(
                        code="NET-SOURCE-SEQUENCE-UNAVAILABLE",
                        message=(f"{equipment.name} lacks available sequence model(s): "
                                 f"{', '.join(unavailable)}."),
                        severity=DiagnosticSeverity.ERROR, entity_id=equipment.id,
                    ))
        if not network.buses:
            diagnostics.append(
                DomainDiagnostic(
                    code="NET-EMPTY-BUS",
                    message="At least one bus is required for calculation.",
                    severity=DiagnosticSeverity.ERROR,
                    entity_id=network.id,
                )
            )
        if not network.equipment:
            diagnostics.append(
                DomainDiagnostic(
                    code="NET-EMPTY-EQUIPMENT",
                    message="At least one electrical equipment item is required for calculation.",
                    severity=DiagnosticSeverity.ERROR,
                    entity_id=network.id,
                )
            )
        connected_terminal_ids = {item.terminal_id for item in network.connections}
        for terminal in network.terminals:
            if terminal.id not in connected_terminal_ids:
                diagnostics.append(
                    DomainDiagnostic(
                        code="NET-TERMINAL-UNCONNECTED",
                        message=(
                            f"Terminal '{terminal.designation}' on equipment "
                            f"'{terminal.equipment_id}' is not connected."
                        ),
                        severity=DiagnosticSeverity.ERROR,
                        entity_id=terminal.id,
                    )
                )
        return tuple(diagnostics)
