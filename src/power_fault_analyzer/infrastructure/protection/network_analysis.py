"""Topology-integrated protection-current extraction and zone assessment."""

from __future__ import annotations

import cmath
import math
from collections.abc import Mapping, Sequence
from uuid import UUID

import numpy as np

from power_fault_analyzer.domain.enums.protection import (
    ProtectionAssessmentStatus,
    ProtectionFunction,
)
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.domain.value_objects.line_fault_result import LineFaultStudyResult
from power_fault_analyzer.domain.value_objects.protection_devices import OvercurrentRelay
from power_fault_analyzer.domain.value_objects.protection_network import (
    ProtectionBackupCheck,
    ProtectionCurrentMeasurement,
    ProtectionDeviceBinding,
    ProtectionDeviceOperation,
    ProtectionFaultScenario,
    ProtectionNetworkAssessment,
    ProtectionNetworkModel,
    ProtectionScenarioMeasurements,
    ProtectionZoneScenarioAssessment,
)
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult
from power_fault_analyzer.infrastructure.numerical.ybus import SparseYBusAssembler
from power_fault_analyzer.network.sequence_networks.models import (
    SequenceBranch,
    SequenceNetworkSet,
    SystemBaseSet,
)


class ProtectionNetworkAnalysisError(RuntimeError):
    """Raised when topology-to-protection measurements cannot be derived safely."""


class ProtectionCurrentExtractor:
    """Recover primary currents at CT locations from solved sequence-network states."""

    def __init__(self, *, assembler: SparseYBusAssembler | None = None) -> None:
        self._assembler = assembler or SparseYBusAssembler()

    def from_bus_fault(
        self,
        model: ProtectionNetworkModel,
        networks: SequenceNetworkSet,
        system_base: SystemBaseSet,
        result: ShortCircuitResult,
        *,
        calculation_networks: SequenceNetworkSet | None = None,
    ) -> Mapping[UUID, ProtectionCurrentMeasurement]:
        if not isinstance(model, ProtectionNetworkModel):
            raise TypeError("model must be a ProtectionNetworkModel.")
        if not isinstance(networks, SequenceNetworkSet):
            raise TypeError("networks must be a SequenceNetworkSet.")
        if not isinstance(system_base, SystemBaseSet):
            raise TypeError("system_base must be a SystemBaseSet.")
        if not isinstance(result, ShortCircuitResult):
            raise TypeError("result must be a ShortCircuitResult.")
        active_networks = calculation_networks or networks
        if not isinstance(active_networks, SequenceNetworkSet):
            raise TypeError("calculation_networks must be a SequenceNetworkSet or None.")
        if (
            model.network_id != networks.network_id
            or active_networks.network_id != networks.network_id
        ):
            raise ValueError("Protection model and sequence networks belong to different networks.")

        node_voltages: dict[SequenceType, np.ndarray] = {}
        for sequence in result.sequence_fault_voltages_pu:
            sequence_network = active_networks.for_sequence(sequence)
            ybus = self._assembler.assemble(sequence_network)
            try:
                fault_index = ybus.node_index[result.bus_id]
            except KeyError as exc:
                raise ProtectionNetworkAnalysisError(
                    f"Fault bus is absent from {sequence.value}-sequence Ybus."
                ) from exc
            factorization = ybus.factorize()
            prefault_voltage = factorization.solve(ybus.current_injection_pu)
            target_prefault_voltage = result.prefault_sequence_voltages_pu.get(sequence)
            if target_prefault_voltage is not None:
                calculated_at_fault = complex(prefault_voltage[fault_index])
                if abs(calculated_at_fault) <= 1e-14:
                    if abs(target_prefault_voltage) > 1e-14:
                        raise ProtectionNetworkAnalysisError(
                            "Cannot scale the prefault network state to the short-circuit "
                            "solver's equivalent voltage at the fault bus."
                        )
                else:
                    prefault_voltage *= target_prefault_voltage / calculated_at_fault
            unit_current = np.zeros(len(ybus.node_ids), dtype=np.complex128)
            unit_current[fault_index] = 1.0 + 0.0j
            transfer_column = factorization.solve(unit_current)
            sequence_fault_current = result.sequence_currents_pu.get(sequence, 0.0j)
            node_voltages[sequence] = prefault_voltage - transfer_column * sequence_fault_current

        measurements: dict[UUID, ProtectionCurrentMeasurement] = {}
        for binding in model.bindings:
            bus_id = model.binding_bus_ids[binding.id]
            phase_sequences: dict[SequenceType, complex] = {}
            for sequence, node_voltage in node_voltages.items():
                sequence_network = active_networks.for_sequence(sequence)
                branch = self._find_equipment_branch(
                    sequence_network.branches,
                    binding.monitored_equipment_id,
                    model.binding_equipment_names[binding.id],
                    bus_id,
                )
                ybus = self._assembler.assemble(sequence_network)
                phase_sequences[sequence] = self._branch_terminal_current(
                    branch,
                    bus_id,
                    node_voltage,
                    ybus.node_index,
                )
            phase_currents_pu = self._sequence_to_phase(
                phase_sequences.get(SequenceType.ZERO, 0.0j),
                phase_sequences.get(SequenceType.POSITIVE, 0.0j),
                phase_sequences.get(SequenceType.NEGATIVE, 0.0j),
            )
            current_base_a = system_base.for_bus(bus_id).base_current_ka * 1000.0
            measurements[binding.id] = ProtectionCurrentMeasurement(
                phase_current_a=max(abs(value) for value in phase_currents_pu) * current_base_a,
                earth_current_a=abs(sum(phase_currents_pu)) * current_base_a,
            )
        return measurements

    @staticmethod
    def from_line_fault(
        model: ProtectionNetworkModel,
        result: LineFaultStudyResult,
        *,
        supplemental_measurements: Mapping[UUID, ProtectionCurrentMeasurement] | None = None,
    ) -> Mapping[UUID, ProtectionCurrentMeasurement]:
        if not isinstance(model, ProtectionNetworkModel):
            raise TypeError("model must be a ProtectionNetworkModel.")
        if not isinstance(result, LineFaultStudyResult):
            raise TypeError("result must be a LineFaultStudyResult.")
        measurements = dict(supplemental_measurements or {})
        unknown_device_ids = set(measurements) - set(model.binding_by_device_id)
        if unknown_device_ids:
            raise ValueError(
                "Supplemental measurements reference protection devices outside this model."
            )
        for binding in model.bindings:
            if binding.monitored_equipment_id != result.branch_id:
                continue
            monitored_bus_id = model.binding_bus_ids[binding.id]
            if monitored_bus_id == result.from_bus_id:
                state = result.from_terminal
            elif monitored_bus_id == result.to_bus_id:
                state = result.to_terminal
            else:
                raise ProtectionNetworkAnalysisError(
                    "Line-fault terminal states do not match the CT location bus."
                )
            phase_currents = state.phase_currents_into_line_ka
            measurements[binding.id] = ProtectionCurrentMeasurement(
                phase_current_a=max(abs(value) for value in phase_currents) * 1000.0,
                earth_current_a=abs(sum(phase_currents)) * 1000.0,
            )
        return measurements

    @staticmethod
    def _find_equipment_branch(
        branches: tuple[SequenceBranch, ...],
        equipment_id: UUID,
        equipment_name: str,
        bus_id: UUID,
    ) -> SequenceBranch:
        candidates = [
            branch
            for branch in branches
            if branch.from_node_id == bus_id or branch.to_node_id == bus_id
        ]
        direct = [branch for branch in candidates if branch.id == equipment_id]
        if len(direct) == 1:
            return direct[0]
        named = [branch for branch in candidates if branch.name.startswith(f"{equipment_name}:")]
        if len(named) == 1:
            return named[0]
        raise ProtectionNetworkAnalysisError(
            f"No unique sequence branch maps protection device on equipment '{equipment_name}' "
            f"at bus '{bus_id}'. Only two-terminal branch equipment is currently measurable."
        )

    @staticmethod
    def _branch_terminal_current(
        branch: SequenceBranch,
        bus_id: UUID,
        voltages: np.ndarray,
        node_index: Mapping[UUID, int],
    ) -> complex:
        from_voltage = complex(voltages[node_index[branch.from_node_id]])
        to_voltage = complex(voltages[node_index[branch.to_node_id]])
        admittance = 1.0 / branch.series_impedance_pu
        tap = branch.tap_from
        if bus_id == branch.from_node_id:
            return complex(
                (admittance + branch.shunt_admittance_from_pu) / abs(tap) ** 2 * from_voltage
                - admittance / tap.conjugate() * to_voltage
            )
        if bus_id == branch.to_node_id:
            return complex(
                -admittance / tap * from_voltage
                + (admittance + branch.shunt_admittance_to_pu) * to_voltage
            )
        raise ProtectionNetworkAnalysisError("CT bus is not an endpoint of the selected branch.")

    @staticmethod
    def _sequence_to_phase(
        zero: complex,
        positive: complex,
        negative: complex,
    ) -> tuple[complex, complex, complex]:
        a = cmath.exp(2.0j * math.pi / 3.0)
        return (
            zero + positive + negative,
            zero + (a**2) * positive + a * negative,
            zero + a * positive + (a**2) * negative,
        )


class ProtectionNetworkAnalyzer:
    """Evaluate device operation, zone coverage and explicit backup selectivity."""

    def analyze(
        self,
        model: ProtectionNetworkModel,
        scenarios: Sequence[ProtectionScenarioMeasurements],
    ) -> ProtectionNetworkAssessment:
        if not isinstance(model, ProtectionNetworkModel):
            raise TypeError("model must be a ProtectionNetworkModel.")
        scenario_inputs = tuple(scenarios)
        if any(not isinstance(item, ProtectionScenarioMeasurements) for item in scenario_inputs):
            raise TypeError("scenarios must contain ProtectionScenarioMeasurements values.")
        known_device_ids = {item.id for item in model.bindings}
        for item in scenario_inputs:
            unknown_device_ids = set(item.device_currents_a) - known_device_ids
            if unknown_device_ids:
                raise ValueError(
                    "Scenario measurements reference protection devices outside this model."
                )
        scenario_ids = [item.scenario.id for item in scenario_inputs]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("Scenario IDs must be unique within one protection assessment.")

        operations: list[ProtectionDeviceOperation] = []
        zone_assessments: list[ProtectionZoneScenarioAssessment] = []
        diagnostics: list[DomainDiagnostic] = list(model.diagnostics)
        scenario_results: list[ProtectionFaultScenario] = []

        for scenario_input in scenario_inputs:
            scenario = scenario_input.scenario
            scenario_results.append(scenario)
            scenario_operations: dict[UUID, ProtectionDeviceOperation] = {}
            for binding in model.bindings:
                measurement = scenario_input.device_currents_a.get(binding.id)
                operation = self._evaluate_binding(binding, scenario.id, measurement)
                scenario_operations[binding.id] = operation
                operations.append(operation)
                diagnostics.extend(operation.diagnostics)

            matching_zones = tuple(
                zone for zone in model.zones if scenario.location_id in zone.protected_element_ids
            )
            if not matching_zones:
                diagnostics.append(
                    DomainDiagnostic(
                        code="PROTECTION-FAULT-LOCATION-OUTSIDE-ALL-ZONES",
                        message=(
                            f"Fault location '{scenario.name}' is not included in any "
                            "configured protection zone."
                        ),
                        severity=DiagnosticSeverity.ERROR,
                        entity_id=scenario.location_id,
                    )
                )
            for zone in matching_zones:
                primary_status, primary_diagnostics = self._primary_coverage(
                    zone.primary_device_ids, scenario_operations
                )
                diagnostics.extend(primary_diagnostics)
                backup_checks = tuple(
                    self._backup_check(relationship, scenario_operations)
                    for relationship in zone.backup_relationships
                )
                zone_status = self._combined_status(
                    (primary_status, *(item.status for item in backup_checks))
                )
                zone_diagnostics = list(primary_diagnostics)
                for check in backup_checks:
                    if check.status is ProtectionAssessmentStatus.FAIL:
                        zone_diagnostics.append(
                            DomainDiagnostic(
                                code="PROTECTION-BACKUP-COORDINATION-FAILED",
                                message=(
                                    f"Backup device '{check.backup_device_id}' does not maintain "
                                    "the required margin over its primary device."
                                ),
                                severity=DiagnosticSeverity.ERROR,
                                entity_id=check.backup_device_id,
                            )
                        )
                zone_assessments.append(
                    ProtectionZoneScenarioAssessment(
                        scenario_id=scenario.id,
                        zone_id=zone.id,
                        status=zone_status,
                        primary_coverage=primary_status,
                        backup_checks=backup_checks,
                        diagnostics=tuple(zone_diagnostics),
                    )
                )

        overall_status = self._combined_status(tuple(item.status for item in zone_assessments))
        if any(item.code == "PROTECTION-FAULT-LOCATION-OUTSIDE-ALL-ZONES" for item in diagnostics):
            overall_status = ProtectionAssessmentStatus.FAIL
        if not zone_assessments and not any(
            item.code == "PROTECTION-FAULT-LOCATION-OUTSIDE-ALL-ZONES" for item in diagnostics
        ):
            diagnostics.append(
                DomainDiagnostic(
                    code="PROTECTION-NO-ZONE-SCENARIO-MATCH",
                    message=(
                        "No generated fault scenario intersects a configured protection zone."
                    ),
                    severity=DiagnosticSeverity.WARNING,
                )
            )
            overall_status = ProtectionAssessmentStatus.NOT_EVALUATED
        return ProtectionNetworkAssessment(
            network_id=model.network_id,
            status=overall_status,
            scenarios=tuple(scenario_results),
            device_operations=tuple(operations),
            zone_assessments=tuple(zone_assessments),
            diagnostics=tuple(diagnostics),
        )

    @staticmethod
    def _evaluate_binding(
        binding: ProtectionDeviceBinding,
        scenario_id: UUID,
        measurement: ProtectionCurrentMeasurement | None,
    ) -> ProtectionDeviceOperation:
        diagnostics: list[DomainDiagnostic] = []
        if measurement is None:
            diagnostics.append(
                DomainDiagnostic(
                    code="PROTECTION-DEVICE-CURRENT-NOT-AVAILABLE",
                    message=(
                        f"No current measurement was supplied for protection device "
                        f"'{binding.device.name}' in this scenario."
                    ),
                    severity=DiagnosticSeverity.WARNING,
                    entity_id=binding.id,
                )
            )
            return ProtectionDeviceOperation(
                scenario_id=scenario_id,
                device_id=binding.id,
                measured_current_a=None,
                picked_up=None,
                stage=None,
                operating_time_s=None,
                clearing_time_s=None,
                diagnostics=tuple(diagnostics),
            )

        device = binding.device
        if isinstance(device, OvercurrentRelay):
            current = (
                measurement.earth_current_a
                if device.function is ProtectionFunction.EARTH
                else measurement.phase_current_a
            )
            response = device.operate(current)
            if response.picked_up:
                clearing_time = None
                if binding.breaker is not None:
                    clearing_time = (
                        response.operating_time_s + binding.breaker.total_clearing_time_s
                    )
                else:
                    diagnostics.append(
                        DomainDiagnostic(
                            code="PROTECTION-RELAY-BREAKER-NOT-ASSIGNED",
                            message=(
                                f"Relay '{device.name}' picks up, but no circuit breaker is "
                                "bound; complete clearing time cannot be evaluated."
                            ),
                            severity=DiagnosticSeverity.WARNING,
                            entity_id=device.id,
                        )
                    )
                return ProtectionDeviceOperation(
                    scenario_id=scenario_id,
                    device_id=device.id,
                    measured_current_a=current,
                    picked_up=True,
                    stage=response.stage,
                    operating_time_s=response.operating_time_s,
                    clearing_time_s=clearing_time,
                    diagnostics=tuple(diagnostics),
                )
            return ProtectionDeviceOperation(
                scenario_id=scenario_id,
                device_id=device.id,
                measured_current_a=current,
                picked_up=False,
                stage=None,
                operating_time_s=None,
                clearing_time_s=None,
            )

        current = measurement.phase_current_a
        clearing_time = device.total_clearing_time(current)
        if clearing_time is None:
            diagnostics.append(
                DomainDiagnostic(
                    code="PROTECTION-FUSE-CURRENT-OUTSIDE-CHARACTERISTIC",
                    message=(
                        f"Current {current:.6g} A lies outside the manufacturer curve range "
                        f"for fuse '{device.name}'; no extrapolation is performed."
                    ),
                    severity=DiagnosticSeverity.WARNING,
                    entity_id=device.id,
                )
            )
            return ProtectionDeviceOperation(
                scenario_id=scenario_id,
                device_id=device.id,
                measured_current_a=current,
                picked_up=None,
                stage=None,
                operating_time_s=None,
                clearing_time_s=None,
                diagnostics=tuple(diagnostics),
            )
        return ProtectionDeviceOperation(
            scenario_id=scenario_id,
            device_id=device.id,
            measured_current_a=current,
            picked_up=True,
            stage=None,
            operating_time_s=clearing_time,
            clearing_time_s=clearing_time,
        )

    @staticmethod
    def _primary_coverage(
        primary_device_ids: tuple[UUID, ...],
        operations: Mapping[UUID, ProtectionDeviceOperation],
    ) -> tuple[ProtectionAssessmentStatus, tuple[DomainDiagnostic, ...]]:
        values = [operations[item] for item in primary_device_ids]
        if any(item.picked_up is True and item.clearing_time_s is not None for item in values):
            return ProtectionAssessmentStatus.PASS, ()
        if any(item.picked_up is None for item in values) or any(
            item.picked_up is True and item.clearing_time_s is None for item in values
        ):
            return (
                ProtectionAssessmentStatus.NOT_EVALUATED,
                (
                    DomainDiagnostic(
                        code="PROTECTION-PRIMARY-COVERAGE-NOT-EVALUATED",
                        message=(
                            "Primary-zone coverage is incomplete because one or more primary "
                            "device currents or clearing paths are unavailable."
                        ),
                        severity=DiagnosticSeverity.WARNING,
                    ),
                ),
            )
        return (
            ProtectionAssessmentStatus.FAIL,
            (
                DomainDiagnostic(
                    code="PROTECTION-ZONE-UNCOVERED",
                    message="No primary protection device picks up and clears this fault scenario.",
                    severity=DiagnosticSeverity.ERROR,
                ),
            ),
        )

    @staticmethod
    def _backup_check(
        relationship,
        operations: Mapping[UUID, ProtectionDeviceOperation],
    ) -> ProtectionBackupCheck:
        primary = operations[relationship.primary_device_id]
        backup = operations[relationship.backup_device_id]
        if backup.picked_up is False:
            status = ProtectionAssessmentStatus.FAIL
            margin = None
        elif (
            primary.picked_up is None
            or backup.picked_up is None
            or primary.clearing_time_s is None
            or backup.clearing_time_s is None
        ):
            status = ProtectionAssessmentStatus.NOT_EVALUATED
            margin = None
        else:
            margin = backup.clearing_time_s - primary.clearing_time_s
            status = (
                ProtectionAssessmentStatus.PASS
                if margin >= relationship.minimum_coordination_interval_s
                else ProtectionAssessmentStatus.FAIL
            )
        return ProtectionBackupCheck(
            primary_device_id=relationship.primary_device_id,
            backup_device_id=relationship.backup_device_id,
            minimum_required_margin_s=relationship.minimum_coordination_interval_s,
            achieved_margin_s=margin,
            status=status,
        )

    @staticmethod
    def _combined_status(
        statuses: Sequence[ProtectionAssessmentStatus],
    ) -> ProtectionAssessmentStatus:
        values = tuple(statuses)
        if not values:
            return ProtectionAssessmentStatus.NOT_EVALUATED
        if ProtectionAssessmentStatus.FAIL in values:
            return ProtectionAssessmentStatus.FAIL
        if ProtectionAssessmentStatus.NOT_EVALUATED in values:
            return ProtectionAssessmentStatus.NOT_EVALUATED
        return ProtectionAssessmentStatus.PASS
