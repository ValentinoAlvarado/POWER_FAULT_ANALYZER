"""Execute a bus-fault study on a physical multi-bus Network aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from power_fault_analyzer.application.ports.sequence_network_factory import (
    SequenceNetworkFactoryPort,
)
from power_fault_analyzer.application.ports.short_circuit_solver import ShortCircuitSolverPort
from power_fault_analyzer.domain.aggregates.network import Network
from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.services.network_validation_service import (
    DefaultNetworkValidationService,
)
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.domain.value_objects.fault_specification import FaultSpecification
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult
from power_fault_analyzer.network.sequence_networks.models import SequenceNetworkSet, SystemBaseSet
from power_fault_analyzer.results.report_builder import EngineeringStudyReportBuilder
from power_fault_analyzer.results.result_models import EngineeringStudyReport


class NetworkStudyValidationError(ValueError):
    """Raised when the selected physical network is not ready for short-circuit analysis."""


@dataclass(frozen=True, slots=True)
class NetworkStudyExecution:
    result: ShortCircuitResult
    report: EngineeringStudyReport
    networks: SequenceNetworkSet
    system_base: SystemBaseSet
    diagnostics: tuple[DomainDiagnostic, ...]


class RunNetworkShortCircuitStudy:
    def __init__(
        self,
        solver: ShortCircuitSolverPort,
        sequence_network_factory: SequenceNetworkFactoryPort,
        validator: DefaultNetworkValidationService | None = None,
    ) -> None:
        self._solver = solver
        self._network_factory = sequence_network_factory
        self._validator = validator or DefaultNetworkValidationService()

    def execute(
        self,
        network: Network,
        *,
        fault_bus_id,
        fault_type: FaultType,
        fault_impedance_pu: complex,
        base_power_mva: float,
        project_name: str,
    ) -> NetworkStudyExecution:
        if not isinstance(network, Network):
            raise TypeError("network must be a Network aggregate.")
        if not isinstance(fault_type, FaultType):
            raise TypeError("fault_type must be FaultType.")
        network.get_bus(fault_bus_id)
        diagnostics = self._validator.validate_for_calculation(network)
        errors = tuple(item for item in diagnostics if item.severity is DiagnosticSeverity.ERROR)
        if errors:
            message = "\n".join(f"{item.code}: {item.message}" for item in errors)
            raise NetworkStudyValidationError(message)

        base = SystemBaseSet.from_network(network, base_power_mva)
        sequence_networks = self._network_factory.build_all(network, base)
        sequence_diagnostics = (
            *sequence_networks.positive.diagnostics,
            *sequence_networks.negative.diagnostics,
            *sequence_networks.zero.diagnostics,
        )
        errors = tuple(
            item for item in sequence_diagnostics if item.severity is DiagnosticSeverity.ERROR
        )
        if errors:
            message = "\n".join(f"{item.code}: {item.message}" for item in errors)
            raise NetworkStudyValidationError(message)

        fault = FaultSpecification(fault_type, fault_bus_id, fault_impedance_pu)
        result = self._solver.solve(sequence_networks, fault, base)
        bus = network.get_bus(fault_bus_id)
        now = datetime.now(UTC)
        report_builder = EngineeringStudyReportBuilder(
            project_name=project_name,
            study_name=f"Short-circuit at {bus.name}",
            network=network,
            generated_at=now,
            study_id=uuid4(),
            limitations=(
                "Results include only electrical quantities exposed by the solver.",
                "This is a general symmetrical-components network fault study; no IEC 60909 correction procedure is applied.",
            ),
        )
        report_builder.add_short_circuit_result(
            result,
            location_name=bus.name,
            fault_id=f"{network.name}-{bus.name}-{now.strftime('%Y%m%dT%H%M%S%fZ')}",
        )
        report_builder.add_assumption(
            "Voltage bases are taken from the nominal line-to-line voltage of each registered bus."
        )
        report_builder.add_assumption(
            "Each equipment sequence model is included only when an explicit domain adapter provides it."
        )
        report_builder.add_assumption(
            f"System three-phase base power: {base_power_mva:g} MVA; fault impedance: "
            f"{fault_impedance_pu.real:g}{fault_impedance_pu.imag:+g}j p.u."
        )
        for equipment in network.equipment:
            for parameter in getattr(equipment, "data_evidence", ()):
                report_builder.add_assumption(
                    f"Input provenance: {equipment.name}.{parameter.name}="
                    f"{parameter.value} {parameter.unit}; status={parameter.status.value}; "
                    f"reference={parameter.source_reference}."
                )
        return NetworkStudyExecution(
            result=result,
            report=report_builder.build(),
            networks=sequence_networks,
            system_base=base,
            diagnostics=diagnostics + sequence_diagnostics,
        )
