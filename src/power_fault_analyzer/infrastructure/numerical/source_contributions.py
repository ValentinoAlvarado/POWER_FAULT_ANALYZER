"""Source superposition and explicit converter-current network solvers."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

import numpy as np

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.converter_current_command import (
    ConverterSequenceCurrentCommand,
)
from power_fault_analyzer.infrastructure.numerical.ybus import SparseYBusAssembler, YBusMatrix
from power_fault_analyzer.network.sequence_networks.models import (
    SequenceNetwork,
    SequenceNetworkSet,
    SystemBaseSet,
)


@dataclass(frozen=True, slots=True)
class SourceVoltageContributionResult:
    """Linear superposition of Thevenin-source contributions at one bus."""

    sequence: SequenceType
    bus_id: UUID
    contributions_pu: Mapping[UUID, complex]
    total_voltage_pu: complex
    reconstructed_voltage_pu: complex
    residual_pu: float

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, SequenceType) or not isinstance(self.bus_id, UUID):
            raise TypeError("sequence and bus_id must be valid identifiers.")
        if not isinstance(self.contributions_pu, Mapping):
            raise TypeError("contributions_pu must be a mapping.")
        copied = {key: complex(value) for key, value in self.contributions_pu.items()}
        if any(not isinstance(key, UUID) for key in copied):
            raise TypeError("Contribution keys must be source UUID values.")
        if any(
            not math.isfinite(value.real) or not math.isfinite(value.imag)
            for value in copied.values()
        ):
            raise ValueError("Source voltage contributions must be finite.")
        object.__setattr__(self, "contributions_pu", MappingProxyType(copied))
        for name in ("total_voltage_pu", "reconstructed_voltage_pu"):
            value = complex(getattr(self, name))
            if not math.isfinite(value.real) or not math.isfinite(value.imag):
                raise ValueError(f"{name} must be finite.")
            object.__setattr__(self, name, value)
        if not math.isfinite(self.residual_pu) or self.residual_pu < 0.0:
            raise ValueError("residual_pu must be finite and non-negative.")


class SourceVoltageContributionCalculator:
    """Decompose a linear sequence-network bus voltage by independent source."""

    def calculate(self, ybus: YBusMatrix, bus_id: UUID) -> SourceVoltageContributionResult:
        if not isinstance(ybus, YBusMatrix):
            raise TypeError("ybus must be a YBusMatrix value.")
        if not isinstance(bus_id, UUID):
            raise TypeError("bus_id must be a UUID value.")
        try:
            index = ybus.node_index[bus_id]
        except KeyError as exc:
            raise KeyError(f"Bus '{bus_id}' is not present in the sequence Ybus.") from exc
        if not ybus.source_current_injections_pu:
            raise ValueError("Ybus does not expose independent Thevenin source injections.")
        factorization = ybus.factorize()
        contributions = {}
        for source_id, injection in ybus.source_current_injections_pu.items():
            voltage = factorization.solve(injection)
            contributions[source_id] = complex(voltage[index])
        reconstructed = sum(contributions.values(), 0.0j)
        total = factorization.solve(ybus.current_injection_pu)
        total_voltage = complex(total[index])
        return SourceVoltageContributionResult(
            sequence=ybus.sequence,
            bus_id=bus_id,
            contributions_pu=contributions,
            total_voltage_pu=total_voltage,
            reconstructed_voltage_pu=reconstructed,
            residual_pu=abs(total_voltage - reconstructed),
        )


@dataclass(frozen=True, slots=True)
class SequenceCurrentInjectionResult:
    """Nodal sequence voltages for a network with explicit converter current commands."""

    sequence: SequenceType
    node_voltages_pu: Mapping[UUID, complex]
    converter_injections_pu: Mapping[UUID, complex]
    residual_norm: float

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, SequenceType):
            raise TypeError("sequence must be a SequenceType value.")
        for name in ("node_voltages_pu", "converter_injections_pu"):
            mapping = getattr(self, name)
            if not isinstance(mapping, Mapping):
                raise TypeError(f"{name} must be a mapping.")
            copied = {key: complex(value) for key, value in mapping.items()}
            if any(not isinstance(key, UUID) for key in copied):
                raise TypeError(f"{name} keys must be UUID values.")
            if any(not math.isfinite(v.real) or not math.isfinite(v.imag) for v in copied.values()):
                raise ValueError(f"{name} values must be finite.")
            object.__setattr__(self, name, MappingProxyType(copied))
        if not math.isfinite(self.residual_norm) or self.residual_norm < 0.0:
            raise ValueError("residual_norm must be finite and non-negative.")


class ConverterCurrentInjectionSolver:
    """Solve linear sequence networks with explicitly commanded converter currents.

    The solver applies fixed sequence-current phasors supplied by the study
    engineer or vendor model. It does not infer PLL, grid-forming, current
    priority, limiter, or dynamic control behavior from a current limit alone.
    """

    def __init__(self, *, assembler: SparseYBusAssembler | None = None) -> None:
        self._assembler = assembler or SparseYBusAssembler()

    def solve_all(
        self,
        networks: SequenceNetworkSet,
        system_base: SystemBaseSet,
        commands: tuple[ConverterSequenceCurrentCommand, ...],
    ) -> Mapping[SequenceType, SequenceCurrentInjectionResult]:
        if not isinstance(networks, SequenceNetworkSet):
            raise TypeError("networks must be a SequenceNetworkSet value.")
        if not isinstance(system_base, SystemBaseSet):
            raise TypeError("system_base must be a SystemBaseSet value.")
        if not isinstance(commands, tuple) or any(
            not isinstance(item, ConverterSequenceCurrentCommand) for item in commands
        ):
            raise TypeError("commands must be a tuple of ConverterSequenceCurrentCommand values.")
        source_ids = tuple(item.source_id for item in commands)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Converter current commands must have unique source IDs.")
        by_source = {item.source_id: item for item in commands}
        reference_capabilities = networks.positive.converter_capabilities
        if set(reference_capabilities) != set(source_ids):
            raise ValueError(
                "Every converter source must have a capability model in the sequence network."
            )
        for command in commands:
            if reference_capabilities.get(command.source_id) != command.capability:
                raise ValueError(
                    "Converter command capability does not match the registered source model."
                )
            command.validate_limits(system_base)
        results = {}
        for sequence in SequenceType:
            network = networks.for_sequence(sequence)
            if set(network.nonlinear_source_ids) != set(by_source):
                raise ValueError(
                    f"Current commands must match the {sequence.value}-sequence "
                    "converter source IDs exactly."
                )
            results[sequence] = self.solve_sequence(network, sequence, by_source, system_base)
        return MappingProxyType(results)

    def solve_sequence(
        self,
        network: SequenceNetwork,
        sequence: SequenceType,
        commands: Mapping[UUID, ConverterSequenceCurrentCommand],
        system_base: SystemBaseSet,
    ) -> SequenceCurrentInjectionResult:
        if not isinstance(network, SequenceNetwork) or network.sequence is not sequence:
            raise TypeError("network must be a SequenceNetwork for the requested sequence.")
        if not isinstance(system_base, SystemBaseSet):
            raise TypeError("system_base must be a SystemBaseSet value.")
        if set(commands) != set(network.nonlinear_source_ids):
            raise ValueError(
                "Current commands must match the sequence network converter source IDs exactly."
            )
        if set(network.converter_bus_ids) != set(commands):
            raise ValueError("Sequence network lacks registered converter bus mappings.")
        if set(network.converter_capabilities) != set(commands):
            raise ValueError("Sequence network lacks registered converter capability data.")
        for source_id, command in commands.items():
            if not isinstance(command, ConverterSequenceCurrentCommand):
                raise TypeError("commands values must be ConverterSequenceCurrentCommand values.")
            command.validate_limits(system_base)
            if command.bus_id != network.converter_bus_ids[source_id]:
                raise ValueError(
                    "Converter command bus does not match registered equipment connection."
                )
            if command.capability != network.converter_capabilities[source_id]:
                raise ValueError(
                    "Converter command capability differs from registered equipment data."
                )
        ybus = self._assembler.assemble(network)
        rhs = ybus.current_injection_pu.copy()
        converter_injections = {}
        for source_id in network.nonlinear_source_ids:
            try:
                command = commands[source_id]
            except KeyError as exc:
                raise ValueError(f"Missing current command for converter '{source_id}'.") from exc
            if command.bus_id not in ybus.node_index:
                raise ValueError("Converter command bus is not present in the sequence network.")
            value = command.sequence_currents_pu[sequence]
            rhs[ybus.node_index[command.bus_id]] += value
            converter_injections[source_id] = value
        solution = ybus.factorize().solve(rhs)
        residual = float(np.linalg.norm(ybus.matrix @ solution - rhs))
        return SequenceCurrentInjectionResult(
            sequence=sequence,
            node_voltages_pu={
                node_id: complex(solution[index]) for index, node_id in enumerate(ybus.node_ids)
            },
            converter_injections_pu=converter_injections,
            residual_norm=residual,
        )
