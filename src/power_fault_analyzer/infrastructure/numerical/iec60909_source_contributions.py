"""Source-resolved fault-current decomposition over linear sequence networks."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

import numpy as np

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.interfaces.network_contracts import NetworkAggregate
from power_fault_analyzer.domain.value_objects.converter_current_command import (
    ConverterSequenceCurrentCommand,
)
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult
from power_fault_analyzer.infrastructure.numerical.short_circuit import ShortCircuitSolver
from power_fault_analyzer.infrastructure.numerical.ybus import SparseYBusAssembler, YBusMatrix
from power_fault_analyzer.network.sequence_networks.models import SequenceNetworkSet
from power_fault_analyzer.standards.iec60909.models import (
    IEC60909CalculationTrace,
    IEC60909SourceContribution,
    IEC60909SourceDescriptor,
    IEC60909SourceMode,
)
from power_fault_analyzer.standards.iec60909.scenarios import IEC60909StudyScenario
from power_fault_analyzer.standards.iec60909.source_inventory import IEC60909SourceInventoryBuilder

_SOURCE_CONTRIBUTION_METHOD = "pfa.sequence-network.source-contribution.linear-superposition.v1"
_PHASES = ("A", "B", "C")


@dataclass(frozen=True, slots=True)
class IEC60909SourceContributionAnalysis:
    """Source contribution breakdown and balance checks for one fault scenario.

    Contributions are physical sequence-network contributions obtained by linear
    superposition. They are not source-corrected IEC contributions for synchronous
    or asynchronous machines; no such correction is inferred by this component.
    """

    scenario_id: UUID
    total_result: ShortCircuitResult
    source_contributions: tuple[IEC60909SourceContribution, ...]
    sequence_balance_residual_ka: Mapping[SequenceType, float]
    phase_balance_residual_ka: Mapping[str, float]
    trace: IEC60909CalculationTrace
    method_id: str = _SOURCE_CONTRIBUTION_METHOD

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, UUID):
            raise TypeError("scenario_id must be a UUID value.")
        if not isinstance(self.total_result, ShortCircuitResult):
            raise TypeError("total_result must be a ShortCircuitResult value.")
        if not isinstance(self.source_contributions, tuple) or any(
            not isinstance(item, IEC60909SourceContribution) for item in self.source_contributions
        ):
            raise TypeError("source_contributions must be a tuple of source contribution values.")
        if len({item.source_id for item in self.source_contributions}) != len(
            self.source_contributions
        ):
            raise ValueError("Source contribution IDs must be unique.")
        for name, values, allowed_keys in (
            ("sequence_balance_residual_ka", self.sequence_balance_residual_ka, set(SequenceType)),
            ("phase_balance_residual_ka", self.phase_balance_residual_ka, set(_PHASES)),
        ):
            if not isinstance(values, Mapping):
                raise TypeError(f"{name} must be a mapping.")
            copied = {}
            for key, value in values.items():
                if key not in allowed_keys:
                    raise ValueError(f"{name} contains an unsupported key: {key!r}.")
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise TypeError(f"{name} values must be real numbers.")
                numeric = float(value)
                if not math.isfinite(numeric) or numeric < 0.0:
                    raise ValueError(f"{name} values must be finite and non-negative.")
                copied[key] = numeric
            object.__setattr__(self, name, MappingProxyType(copied))
        if not isinstance(self.trace, IEC60909CalculationTrace):
            raise TypeError("trace must be an IEC60909CalculationTrace value.")
        if self.trace.scenario_id != self.scenario_id:
            raise ValueError("Trace scenario ID does not match the analysis.")
        if self.trace.source_contributions != self.source_contributions:
            raise ValueError("Trace source contributions do not match the analysis.")
        if not isinstance(self.method_id, str) or not self.method_id.strip():
            raise ValueError("method_id must be a non-empty string.")


class IEC60909SourceContributionAnalyzer:
    """Decompose fault currents by source using sequence-domain superposition.

    The analyzer accepts existing Thevenin source models (external grids and
    rotating machines) plus explicit fixed-phasor converter commands. It retains
    the source family and model reference in each contribution. It does not apply
    IEC source-specific machine or converter correction factors.
    """

    def __init__(
        self,
        *,
        assembler: SparseYBusAssembler | None = None,
        short_circuit_solver: ShortCircuitSolver | None = None,
        inventory_builder: IEC60909SourceInventoryBuilder | None = None,
        absolute_balance_tolerance_ka: float = 1e-8,
        relative_balance_tolerance: float = 1e-8,
    ) -> None:
        for name, value in (
            ("absolute_balance_tolerance_ka", absolute_balance_tolerance_ka),
            ("relative_balance_tolerance", relative_balance_tolerance),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a real number.")
            numeric = float(value)
            if not math.isfinite(numeric) or numeric < 0.0:
                raise ValueError(f"{name} must be finite and non-negative.")
            if name == "absolute_balance_tolerance_ka":
                absolute_balance_tolerance_ka = numeric
            else:
                relative_balance_tolerance = numeric
        self._assembler = assembler or SparseYBusAssembler()
        self._solver = short_circuit_solver or ShortCircuitSolver()
        self._inventory_builder = inventory_builder or IEC60909SourceInventoryBuilder()
        self._absolute_tolerance_ka = float(absolute_balance_tolerance_ka)
        self._relative_tolerance = float(relative_balance_tolerance)

    def analyze(
        self,
        network: NetworkAggregate,
        networks: SequenceNetworkSet,
        scenario: IEC60909StudyScenario,
        *,
        converter_current_commands: tuple[ConverterSequenceCurrentCommand, ...] = (),
    ) -> IEC60909SourceContributionAnalysis:
        if not isinstance(networks, SequenceNetworkSet):
            raise TypeError("networks must be a SequenceNetworkSet value.")
        if not isinstance(scenario, IEC60909StudyScenario):
            raise TypeError("scenario must be an IEC60909StudyScenario value.")
        if scenario.network_id != networks.network_id or network.id != networks.network_id:
            raise ValueError("Scenario, physical network and sequence networks must match.")
        scenario.system_base.validate_network(network)
        if not isinstance(converter_current_commands, tuple) or any(
            not isinstance(item, ConverterSequenceCurrentCommand)
            for item in converter_current_commands
        ):
            raise TypeError("converter_current_commands must be a tuple of converter commands.")

        descriptors = self._validate_source_descriptors(network, networks, scenario.sources)
        commands = self._validate_converter_commands(descriptors, converter_current_commands)
        required_sequences = tuple(
            sequence for sequence in SequenceType if sequence in scenario.required_sequences
        )
        if not descriptors:
            raise ValueError("The sequence networks contain no identifiable in-service sources.")
        bus_base = scenario.system_base.for_bus(scenario.fault.bus_id)
        ybus_by_sequence = {
            sequence: self._assembler.assemble(networks.for_sequence(sequence))
            for sequence in required_sequences
        }
        factorization_by_sequence = {
            sequence: ybus.factorize() for sequence, ybus in ybus_by_sequence.items()
        }
        total_result = self._solver.solve(
            networks,
            scenario.fault,
            scenario.system_base,
            converter_current_commands=converter_current_commands,
        )

        contributions = []
        for descriptor in descriptors:
            source_prefault = {sequence: 0.0j for sequence in SequenceType}
            for sequence in required_sequences:
                if sequence not in descriptor.active_sequences:
                    continue
                source_prefault[sequence] = self._source_prefault_voltage(
                    descriptor,
                    sequence,
                    networks,
                    ybus_by_sequence[sequence],
                    factorization_by_sequence[sequence],
                    scenario.fault.bus_id,
                    commands,
                )
            source_result = self._solver.solve(
                networks,
                scenario.fault,
                scenario.system_base,
                prefault_sequence_voltage_override=source_prefault,
                converter_current_commands=converter_current_commands,
            )
            sequence_currents = {
                sequence: current_pu * bus_base.base_current_ka
                for sequence, current_pu in source_result.sequence_currents_pu.items()
                if sequence in scenario.required_sequences
            }
            phase_currents = {
                phase: source_result.phase_currents_ka[index] for index, phase in enumerate(_PHASES)
            }
            contributions.append(
                IEC60909SourceContribution(
                    source_id=descriptor.source_id,
                    source_name=descriptor.name,
                    source_family=descriptor.family,
                    source_mode=descriptor.mode,
                    sequence_currents_ka=sequence_currents,
                    phase_currents_ka=phase_currents,
                    model_reference=descriptor.model_reference,
                )
            )

        sequence_residuals, phase_residuals = self._balance_residuals(
            tuple(contributions), total_result
        )
        self._assert_balanced(
            sequence_residuals,
            total_result.sequence_currents_pu,
            bus_base.base_current_ka,
        )
        self._assert_phase_balanced(phase_residuals, total_result.phase_currents_ka)
        contribution_tuple = tuple(contributions)
        assumptions = tuple(scenario.assumptions) + (
            (
                "Source currents are decomposed by linear superposition of declared sequence-network "
                "Norton injections and explicit converter current commands."
            ),
            (
                "The decomposition uses supplied physical sequence models. IEC source-specific "
                "correction factors for synchronous/asynchronous machines and converters "
                "are not applied."
            ),
            (
                "Converter contributions are fixed externally supplied sequence-current phasors. "
                "No converter control law or voltage-dependent response is inferred."
            ),
        )
        trace = IEC60909CalculationTrace(
            scenario_id=scenario.scenario_id,
            source_contributions=contribution_tuple,
            assumptions=assumptions,
            standard_edition="IEC 60909-0:2026",
        )
        return IEC60909SourceContributionAnalysis(
            scenario_id=scenario.scenario_id,
            total_result=total_result,
            source_contributions=contribution_tuple,
            sequence_balance_residual_ka=sequence_residuals,
            phase_balance_residual_ka=phase_residuals,
            trace=trace,
        )

    def _source_prefault_voltage(
        self,
        descriptor: IEC60909SourceDescriptor,
        sequence: SequenceType,
        networks: SequenceNetworkSet,
        ybus: YBusMatrix,
        factorization,
        fault_bus_id: UUID,
        commands: Mapping[UUID, ConverterSequenceCurrentCommand],
    ) -> complex:
        sequence_network = networks.for_sequence(sequence)
        injection = np.zeros(len(ybus.node_ids), dtype=np.complex128)
        if descriptor.mode is IEC60909SourceMode.VOLTAGE_SOURCE:
            source_vector = ybus.source_current_injections_pu.get(descriptor.source_id)
            if source_vector is None:
                raise ValueError(
                    f"Voltage source '{descriptor.name}' has no stamped Norton injection "
                    f"in the {sequence.value}-sequence network."
                )
            injection += source_vector
        else:
            command = commands[descriptor.source_id]
            if descriptor.source_id not in sequence_network.nonlinear_source_ids:
                raise ValueError(
                    f"Current-source '{descriptor.name}' is not registered in the "
                    f"{sequence.value}-sequence network."
                )
            registered_bus = sequence_network.converter_bus_ids.get(descriptor.source_id)
            if registered_bus != command.bus_id:
                raise ValueError(
                    f"Converter command bus does not match '{descriptor.name}' "
                    "sequence-network connection."
                )
            capability = sequence_network.converter_capabilities.get(descriptor.source_id)
            if capability != command.capability:
                raise ValueError(
                    f"Converter command capability does not match '{descriptor.name}' network data."
                )
            injection[ybus.node_index[command.bus_id]] += command.sequence_currents_pu[sequence]

        node_voltages = factorization.solve(injection)
        return complex(node_voltages[ybus.node_index[fault_bus_id]])

    def _validate_source_descriptors(
        self,
        network: NetworkAggregate,
        networks: SequenceNetworkSet,
        supplied: tuple[IEC60909SourceDescriptor, ...],
    ) -> tuple[IEC60909SourceDescriptor, ...]:
        if not isinstance(supplied, tuple) or any(
            not isinstance(item, IEC60909SourceDescriptor) for item in supplied
        ):
            raise TypeError("scenario.sources must be a tuple of IEC60909SourceDescriptor values.")
        expected = self._inventory_builder.build(network, networks)
        expected_by_id = {item.source_id: item for item in expected}
        supplied_by_id = {item.source_id: item for item in supplied}
        if len(supplied_by_id) != len(supplied):
            raise ValueError("Scenario source descriptors contain duplicate IDs.")
        if set(supplied_by_id) != set(expected_by_id):
            raise ValueError(
                "Scenario source descriptors must match the sources stamped in the "
                "sequence networks exactly."
            )
        for source_id, descriptor in supplied_by_id.items():
            expected_descriptor = expected_by_id[source_id]
            if not descriptor.in_service:
                raise ValueError(
                    f"Source '{descriptor.name}' is marked out of service but remains "
                    "stamped in the sequence networks."
                )
            if (
                descriptor.name != expected_descriptor.name
                or descriptor.family is not expected_descriptor.family
                or descriptor.mode is not expected_descriptor.mode
                or descriptor.active_sequences != expected_descriptor.active_sequences
                or descriptor.model_reference != expected_descriptor.model_reference
            ):
                raise ValueError(
                    f"Scenario descriptor for '{descriptor.name}' disagrees with the "
                    "sequence-network model."
                )
        return tuple(sorted(supplied, key=lambda item: (item.name.casefold(), str(item.source_id))))

    @staticmethod
    def _validate_converter_commands(
        descriptors: tuple[IEC60909SourceDescriptor, ...],
        supplied: tuple[ConverterSequenceCurrentCommand, ...],
    ) -> Mapping[UUID, ConverterSequenceCurrentCommand]:
        by_source = {item.source_id: item for item in supplied}
        if len(by_source) != len(supplied):
            raise ValueError("Converter current commands must have unique source IDs.")
        expected = {
            item.source_id for item in descriptors if item.mode is IEC60909SourceMode.CURRENT_SOURCE
        }
        if set(by_source) != expected:
            raise ValueError(
                "Converter current commands must match exactly the current-source descriptors."
            )
        return MappingProxyType(by_source)

    @staticmethod
    def _balance_residuals(
        contributions: tuple[IEC60909SourceContribution, ...],
        total_result: ShortCircuitResult,
    ) -> tuple[Mapping[SequenceType, float], Mapping[str, float]]:
        sequence_totals = {
            sequence: sum(
                contribution.sequence_currents_ka.get(sequence, 0.0j)
                for contribution in contributions
            )
            for sequence in total_result.sequence_currents_pu
        }
        sequence_residuals = {
            sequence: abs(
                sequence_totals[sequence]
                - total_result.sequence_currents_pu[sequence] * total_result.base_current_ka
            )
            for sequence in total_result.sequence_currents_pu
        }
        phase_residuals = {
            phase: abs(
                sum(
                    contribution.phase_currents_ka.get(phase, 0.0j)
                    for contribution in contributions
                )
                - total_result.phase_currents_ka[index]
            )
            for index, phase in enumerate(_PHASES)
        }
        return MappingProxyType(sequence_residuals), MappingProxyType(phase_residuals)

    def _assert_balanced(
        self,
        residuals: Mapping[SequenceType, float],
        total_currents_pu: Mapping[SequenceType, complex],
        base_current_ka: float,
    ) -> None:
        for sequence, residual in residuals.items():
            total_ka = abs(total_currents_pu[sequence] * base_current_ka)
            tolerance = self._absolute_tolerance_ka + self._relative_tolerance * max(total_ka, 1.0)
            if residual > tolerance:
                raise ArithmeticError(
                    f"Source sequence contributions do not reconstruct the total "
                    f"{sequence.value}-sequence fault current."
                )

    def _assert_phase_balanced(
        self,
        residuals: Mapping[str, float],
        total_phase_currents_ka: tuple[complex, complex, complex],
    ) -> None:
        for index, phase in enumerate(_PHASES):
            total_ka = abs(total_phase_currents_ka[index])
            tolerance = self._absolute_tolerance_ka + self._relative_tolerance * max(total_ka, 1.0)
            if residuals[phase] > tolerance:
                raise ArithmeticError(
                    f"Source phase contributions do not reconstruct phase {phase} fault current."
                )
