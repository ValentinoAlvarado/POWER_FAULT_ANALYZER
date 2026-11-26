"""Orchestrate automatic bus-fault scenarios and attach solved branch currents to CTs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.iec60909 import IEC60909CurrentCase
from power_fault_analyzer.domain.enums.protection_network import ProtectionFaultLocationKind
from power_fault_analyzer.domain.interfaces.network_contracts import NetworkAggregate
from power_fault_analyzer.domain.value_objects.fault_specification import FaultSpecification
from power_fault_analyzer.domain.value_objects.iec60909_study import (
    IEC60909StudySpecification,
)
from power_fault_analyzer.domain.value_objects.line_fault_result import LineFaultStudyResult
from power_fault_analyzer.domain.value_objects.protection_network import (
    ProtectionCurrentMeasurement,
    ProtectionFaultScenario,
    ProtectionNetworkAssessment,
    ProtectionNetworkModel,
    ProtectionScenarioMeasurements,
)
from power_fault_analyzer.infrastructure.numerical.iec60909 import IEC60909Calculator
from power_fault_analyzer.infrastructure.protection.network_analysis import (
    ProtectionCurrentExtractor,
    ProtectionNetworkAnalyzer,
)
from power_fault_analyzer.infrastructure.protection.scenarios import ProtectionScenarioCatalog
from power_fault_analyzer.network.sequence_networks.models import (
    SequenceNetworkSet,
    SystemBaseSet,
)


class ProtectionFaultStudyRunner:
    """Generate and solve IEC bus-fault cases for a configured protection network.

    This orchestration is limited to the ND-008 IEC single-network-feeder bus
    method. Line-interior scenarios can be added from ND-007 LineFaultStudyResult
    values; they are not relabeled as IEC 60909 maximum/minimum cases.
    """

    def __init__(
        self,
        *,
        scenario_catalog: ProtectionScenarioCatalog | None = None,
        current_extractor: ProtectionCurrentExtractor | None = None,
        protection_analyzer: ProtectionNetworkAnalyzer | None = None,
        iec_calculator: IEC60909Calculator | None = None,
    ) -> None:
        self._catalog = scenario_catalog or ProtectionScenarioCatalog()
        self._extractor = current_extractor or ProtectionCurrentExtractor()
        self._analyzer = protection_analyzer or ProtectionNetworkAnalyzer()
        self._iec_calculator = iec_calculator or IEC60909Calculator()

    def run_bus_fault_matrix(
        self,
        network: NetworkAggregate,
        protection_model: ProtectionNetworkModel,
        sequence_networks: SequenceNetworkSet,
        system_base: SystemBaseSet,
        *,
        maximum_study: IEC60909StudySpecification,
        minimum_study: IEC60909StudySpecification,
        fault_types: Sequence[FaultType] = (
            FaultType.THREE_PHASE,
            FaultType.SINGLE_LINE_TO_GROUND,
            FaultType.LINE_TO_LINE,
            FaultType.DOUBLE_LINE_TO_GROUND,
        ),
    ) -> ProtectionNetworkAssessment:
        if not isinstance(network, NetworkAggregate):
            raise TypeError("network must implement NetworkAggregate.")
        if not isinstance(protection_model, ProtectionNetworkModel):
            raise TypeError("protection_model must be a ProtectionNetworkModel.")
        if not isinstance(sequence_networks, SequenceNetworkSet):
            raise TypeError("sequence_networks must be a SequenceNetworkSet.")
        if protection_model.network_id != network.id:
            raise ValueError("Protection model belongs to a different physical network.")
        if sequence_networks.network_id != network.id:
            raise ValueError("Sequence networks belong to a different physical network.")
        if not isinstance(system_base, SystemBaseSet):
            raise TypeError("system_base must be a SystemBaseSet.")
        if not isinstance(maximum_study, IEC60909StudySpecification):
            raise TypeError("maximum_study must be an IEC60909StudySpecification.")
        if not isinstance(minimum_study, IEC60909StudySpecification):
            raise TypeError("minimum_study must be an IEC60909StudySpecification.")
        system_base.validate_network(network)
        if maximum_study.frequency_hz != minimum_study.frequency_hz:
            raise ValueError("Maximum and minimum studies must use the same network frequency.")
        if maximum_study.current_case is not IEC60909CurrentCase.MAXIMUM:
            raise ValueError("maximum_study must declare IEC60909CurrentCase.MAXIMUM.")
        if minimum_study.current_case is not IEC60909CurrentCase.MINIMUM:
            raise ValueError("minimum_study must declare IEC60909CurrentCase.MINIMUM.")

        planned = self._catalog.generate(
            network,
            fault_types=fault_types,
            include_bus_faults=True,
            include_line_faults=False,
        )
        measured: list[ProtectionScenarioMeasurements] = []
        for scenario in planned:
            specification = (
                maximum_study
                if scenario.current_case is IEC60909CurrentCase.MAXIMUM
                else minimum_study
            )
            fault = FaultSpecification(
                fault_type=scenario.fault_type,
                bus_id=scenario.location_id,
            )
            result = self._iec_calculator.calculate(
                sequence_networks,
                fault,
                system_base,
                specification,
            )
            device_currents = self._extractor.from_bus_fault(
                protection_model,
                sequence_networks,
                system_base,
                result.base_result,
                calculation_networks=result.calculation_networks,
            )
            measured.append(
                ProtectionScenarioMeasurements(
                    scenario=scenario,
                    device_currents_a=device_currents,
                )
            )
        return self._analyzer.analyze(protection_model, measured)

    def add_line_fault_measurements(
        self,
        protection_model: ProtectionNetworkModel,
        scenario: ProtectionFaultScenario,
        line_fault_result: LineFaultStudyResult,
        *,
        supplemental_measurements: Mapping[UUID, ProtectionCurrentMeasurement] | None = None,
    ) -> ProtectionScenarioMeasurements:
        if not isinstance(protection_model, ProtectionNetworkModel):
            raise TypeError("protection_model must be a ProtectionNetworkModel.")
        if not isinstance(scenario, ProtectionFaultScenario):
            raise TypeError("scenario must be a ProtectionFaultScenario.")
        if not isinstance(line_fault_result, LineFaultStudyResult):
            raise TypeError("line_fault_result must be a LineFaultStudyResult.")
        if scenario.location_kind is not ProtectionFaultLocationKind.LINE:
            raise ValueError("scenario must describe an interior-line fault.")
        if scenario.location_id != line_fault_result.branch_id:
            raise ValueError("Line-fault result branch does not match the planned scenario.")
        if scenario.fault_type is not line_fault_result.fault_result.fault_type:
            raise ValueError("Line-fault result fault type does not match the planned scenario.")
        if abs(float(scenario.fraction_from) - line_fault_result.fraction_from) > 1e-9:
            raise ValueError("Line-fault result location does not match the planned scenario.")
        device_currents = self._extractor.from_line_fault(
            protection_model,
            line_fault_result,
            supplemental_measurements=supplemental_measurements,
        )
        return ProtectionScenarioMeasurements(
            scenario=scenario,
            device_currents_a=device_currents,
        )

    def assess_scenarios(
        self,
        protection_model: ProtectionNetworkModel,
        scenarios: Sequence[ProtectionScenarioMeasurements],
    ) -> ProtectionNetworkAssessment:
        return self._analyzer.analyze(protection_model, scenarios)
