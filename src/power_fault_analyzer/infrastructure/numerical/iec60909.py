"""Restricted IEC 60909-0:2026 calculations for network-feeder systems."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import replace
from uuid import UUID

import networkx as nx

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.iec60909 import IEC60909CurrentCase
from power_fault_analyzer.domain.enums.sequence_equipment_kind import SequenceEquipmentKind
from power_fault_analyzer.domain.enums.sequence_source_kind import SequenceSourceKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.domain.value_objects.fault_specification import FaultSpecification
from power_fault_analyzer.domain.value_objects.iec60909_study import (
    IEC60909StudyResult,
    IEC60909StudySpecification,
)
from power_fault_analyzer.infrastructure.numerical.short_circuit import (
    ShortCircuitCalculationError,
    ShortCircuitSolver,
)
from power_fault_analyzer.network.sequence_networks.models import (
    SequenceBranch,
    SequenceNetwork,
    SequenceNetworkSet,
    SequenceShunt,
    SystemBaseSet,
)
from power_fault_analyzer.standards.iec60909.current_calculation import (
    calculate_network_feeder_breaking_current,
    calculate_network_feeder_steady_state_current,
    calculate_single_fed_three_phase_dc_and_asymmetrical_breaking,
    calculate_single_fed_three_phase_peak_current,
    initial_symmetrical_current_method_id,
    unavailable_dc_and_asymmetrical_breaking_results,
)
from power_fault_analyzer.standards.iec60909.models import IEC60909SourceFamily


class IEC60909CalculationError(ShortCircuitCalculationError):
    """Raised when a study is outside the implemented IEC 60909 model class."""


class IEC60909Calculator:
    """Calculate supported network-feeder short circuits using IEC 60909 conventions.

    Multiple external network-feeder equivalents may participate in the initial
    symmetrical-current calculation through the combined sequence-network
    Thevenin equivalent. Breaking and steady-state quantities are available only
    for network-feeder source classes with their clause-specific fault restrictions.
    Peak and thermal quantities remain limited to the baseline single-fed radial
    three-phase subset. Clause 10 DC/asymmetrical breaking is available only for that
    same single-fed radial network-feeder subset when first-pole opening time is supplied.
    Machine, converter, multi-feed peak, three-winding transformer correction and
    line-interior methods are not inferred.
    """

    _STANDARD_EDITION = "IEC 60909-0:2026"
    _BOLTED_TOLERANCE = 1e-12

    def __init__(self, *, short_circuit_solver: ShortCircuitSolver | None = None) -> None:
        self._short_circuit_solver = short_circuit_solver or ShortCircuitSolver()

    def calculate(
        self,
        networks: SequenceNetworkSet,
        fault: FaultSpecification,
        system_base: SystemBaseSet,
        study: IEC60909StudySpecification,
    ) -> IEC60909StudyResult:
        """Return initial, peak, breaking, steady-state and thermal results where supported."""
        if not isinstance(networks, SequenceNetworkSet):
            raise TypeError("networks must be a SequenceNetworkSet value.")
        if not isinstance(fault, FaultSpecification):
            raise TypeError("fault must be a FaultSpecification value.")
        if not isinstance(system_base, SystemBaseSet):
            raise TypeError("system_base must be a SystemBaseSet value.")
        if not isinstance(study, IEC60909StudySpecification):
            raise TypeError("study must be an IEC60909StudySpecification value.")
        if abs(fault.fault_impedance_pu) > self._BOLTED_TOLERANCE:
            raise IEC60909CalculationError(
                "This IEC 60909 increment supports bolted faults only; "
                "fault impedance must be zero."
            )

        bus_base = system_base.for_bus(fault.bus_id)
        voltage_factor = study.voltage_factor(bus_base.base_voltage_kv)
        required_sequences = self._required_sequences(fault.fault_type)
        feeder_count = self._validate_supported_sources(networks, fault)
        self._validate_transformer_scope(networks, required_sequences)
        self._validate_minimum_line_resistance(networks, study, required_sequences)

        corrected_networks, transformer_factors = self._apply_network_corrections(
            networks, study, required_sequences
        )
        base_result = self._short_circuit_solver.solve(
            corrected_networks,
            fault,
            system_base,
            prefault_sequence_voltage_override={
                SequenceType.POSITIVE: complex(voltage_factor, 0.0),
                SequenceType.NEGATIVE: 0.0j,
                SequenceType.ZERO: 0.0j,
            },
        )
        initial_current = base_result.maximum_phase_current_ka
        if initial_current <= 0.0 or not math.isfinite(initial_current):
            raise IEC60909CalculationError(
                "The calculated initial symmetrical short-circuit current is not "
                "positive and finite."
            )

        diagnostics = [
            DomainDiagnostic(
                code="IEC60909-RESTRICTED-NETWORK-FEEDER-METHOD",
                message=(
                    "This result uses the restricted network-feeder model. It is not a "
                    "declaration of full IEC 60909 compliance; machine and converter correction "
                    "models, multi-feed peak-current methods and line-interior procedures remain "
                    "outside this increment."
                ),
                severity=DiagnosticSeverity.WARNING,
            )
        ]
        if self._has_ignored_positive_negative_branch_shunts(networks, required_sequences):
            diagnostics.append(
                DomainDiagnostic(
                    code="IEC60909-POSITIVE-NEGATIVE-SHUNTS-NEGLECTED",
                    message=(
                        "Positive- and negative-sequence line/transformer branch shunt "
                        "admittances were omitted according to the IEC short-circuit "
                        "calculation assumptions. Zero-sequence shunt treatment is retained."
                    ),
                    severity=DiagnosticSeverity.INFO,
                )
            )

        if study.current_case is IEC60909CurrentCase.MAXIMUM:
            diagnostics.append(
                DomainDiagnostic(
                    code="IEC60909-LINE-RESISTANCE-REFERENCE-UNVERIFIED",
                    message=(
                        "Maximum-case line resistance is used exactly as supplied. Confirm that "
                        "the input resistance corresponds to the applicable reference conductor "
                        "temperature before using the result for equipment rating."
                    ),
                    severity=DiagnosticSeverity.WARNING,
                )
            )
        elif study.network_feeder_impedance_multiplier == 1.0:
            diagnostics.append(
                DomainDiagnostic(
                    code="IEC60909-MINIMUM-FEEDER-LEVEL-UNCHANGED",
                    message=(
                        "The minimum case retains the declared external-grid Thevenin impedance. "
                        "Provide a feeder impedance multiplier if the utility minimum fault level "
                        "differs from the entered source data."
                    ),
                    severity=DiagnosticSeverity.WARNING,
                )
            )

        peak_factor: float | None = None
        peak_current: float | None = None
        thermal_m: float | None = None
        thermal_n: float | None = None
        thermal_current: float | None = None
        joule_integral: float | None = None
        dc_component_at_separation: float | None = None
        asymmetrical_breaking_current: float | None = None
        current_method_references: dict[str, str] = {
            "I''k": initial_symmetrical_current_method_id(fault.fault_type)
        }
        unavailable_quantity_reasons: dict[str, str] = {}

        radial = self._fault_component_is_radial(corrected_networks.positive, fault.bus_id)
        if (
            study.current_case is IEC60909CurrentCase.MAXIMUM
            and fault.fault_type is FaultType.THREE_PHASE
            and radial
            and feeder_count == 1
        ):
            z_th = base_result.driving_point_impedances_pu[SequenceType.POSITIVE]
            try:
                peak_outcome = calculate_single_fed_three_phase_peak_current(initial_current, z_th)
            except (TypeError, ValueError) as exc:
                raise IEC60909CalculationError(str(exc)) from exc
            peak_factor = peak_outcome.factor
            peak_current = peak_outcome.result.value
            current_method_references["ip"] = peak_outcome.result.method_id
            thermal_m = self._thermal_dc_factor(
                peak_factor, study.frequency_hz, study.fault_duration_s
            )
            thermal_n = 1.0
            thermal_current = initial_current * math.sqrt(thermal_m + thermal_n)
            joule_integral = initial_current**2 * (thermal_m + thermal_n) * study.fault_duration_s
            thermal_method = "IEC60909-0:2026/14/baseline-single-fed-radial-three-phase-subset"
            current_method_references["Ith"] = thermal_method
            current_method_references["J"] = thermal_method
        else:
            if feeder_count > 1:
                peak_reason = (
                    "The multi-fed peak-current procedure has not yet been implemented. "
                    "The single-fed Clause 8.1 factor is not transferred to multiple sources."
                )
            elif not radial:
                peak_reason = (
                    "The faulted positive-sequence component is meshed; the single-fed radial "
                    "Clause 8.1 factor is not applicable."
                )
            elif fault.fault_type is not FaultType.THREE_PHASE:
                peak_reason = (
                    "The unbalanced-fault peak-current procedure has not yet been implemented."
                )
            else:
                peak_reason = "Peak current is not evaluated for the selected minimum-current case."
            unavailable_quantity_reasons["ip"] = peak_reason
            if study.current_case is IEC60909CurrentCase.MAXIMUM:
                diagnostics.append(
                    DomainDiagnostic(
                        code="IEC60909-PEAK-NOT-EVALUATED",
                        message=peak_reason,
                        severity=DiagnosticSeverity.WARNING,
                    )
                )

        # All active sources have already passed _validate_supported_sources,
        # so this strategy receives only the explicitly modelled network feeders.
        network_feeder_families = tuple(
            IEC60909SourceFamily.NETWORK_FEEDER for _ in range(feeder_count)
        )
        breaking_result = calculate_network_feeder_breaking_current(
            initial_current, network_feeder_families, fault.fault_type
        )
        breaking_current = breaking_result.value
        if breaking_result.status.value == "calculated":
            current_method_references["Ib"] = breaking_result.method_id
        else:
            unavailable_quantity_reasons["Ib"] = breaking_result.reason or (
                "The applicable symmetrical breaking-current method is unavailable."
            )

        steady_result = calculate_network_feeder_steady_state_current(
            initial_current, network_feeder_families, fault.fault_type
        )
        steady_state_current = steady_result.value
        if steady_result.status.value == "calculated":
            current_method_references["Ik"] = steady_result.method_id
        else:
            unavailable_quantity_reasons["Ik"] = steady_result.reason or (
                "The applicable steady-state method is unavailable."
            )

        dc_outcome = None
        if (
            study.current_case is IEC60909CurrentCase.MAXIMUM
            and fault.fault_type is FaultType.THREE_PHASE
            and feeder_count == 1
            and radial
            and breaking_current is not None
            and study.first_pole_contact_separation_time_s is not None
        ):
            z_th = base_result.driving_point_impedances_pu[SequenceType.POSITIVE]
            try:
                dc_outcome = calculate_single_fed_three_phase_dc_and_asymmetrical_breaking(
                    initial_current_ka=initial_current,
                    breaking_current_ka=breaking_current,
                    positive_sequence_thevenin_impedance_pu=z_th,
                    frequency_hz=study.frequency_hz,
                    first_pole_contact_separation_time_s=(
                        study.first_pole_contact_separation_time_s
                    ),
                )
            except (TypeError, ValueError) as exc:
                raise IEC60909CalculationError(str(exc)) from exc
            dc_component_at_separation = dc_outcome.dc_component_ka
            asymmetrical_breaking_current = dc_outcome.asymmetrical_breaking_current_ka
            current_method_references["iDC_supplement"] = dc_outcome.method_id
            current_method_references["Ibasym_supplement"] = dc_outcome.method_id
            unavailable_quantity_reasons["iDC"] = (
                "A supplementary R/X exponential estimate is available in "
                "dc_component_at_separation_ka, but final-edition IEC 60909-0:2026 "
                "Clause 10 conformity has not been established."
            )
            unavailable_quantity_reasons["Ibasym"] = (
                "A supplementary RMS combination estimate is available in "
                "asymmetrical_breaking_current_ka, but final-edition IEC 60909-0:2026 "
                "Clause 10 conformity has not been established."
            )

        if dc_outcome is None and study.first_pole_contact_separation_time_s is None:
            dc_reason = (
                "First-pole contact-separation time is not supplied. Clause 10 also "
                "requires the applicable source/topology procedure; no DC or "
                "asymmetrical breaking value is inferred."
            )
        elif dc_outcome is None:
            dc_reason = (
                "The supplied study is outside the restricted Clause 10 single-fed radial "
                "three-phase network-feeder subset. Multi-fed, meshed, unbalanced, machine "
                "and converter cases require separate procedures."
            )
        else:
            dc_reason = ""

        if dc_outcome is None:
            dc_results = unavailable_dc_and_asymmetrical_breaking_results(dc_reason)
            for item in dc_results:
                unavailable_quantity_reasons[item.quantity.value] = item.reason or (
                    "The Clause 10 result is not implemented for this study."
                )
            diagnostics.append(
                DomainDiagnostic(
                    code="IEC60909-DC-ASYMMETRICAL-BREAKING-NOT-EVALUATED",
                    message=(
                        "The DC component and asymmetrical breaking current were not evaluated "
                        "because this study is outside the implemented single-fed radial "
                        "three-phase network-feeder Clause 10 subset or lacks opening-time data."
                    ),
                    severity=DiagnosticSeverity.WARNING,
                )
            )

        if thermal_current is None:
            thermal_reason = (
                "The IEC 60909-0:2026 Clause 14 thermal method is not implemented for this "
                "study class. The available result is limited to the maximum, single-fed, "
                "radial, three-phase network-feeder subset; no m/n factors are inferred "
                "for other source or topology classes."
            )
            unavailable_quantity_reasons["Ith"] = thermal_reason
            unavailable_quantity_reasons["J"] = thermal_reason

        return IEC60909StudyResult(
            standard_edition=self._STANDARD_EDITION,
            base_result=base_result,
            current_case=study.current_case,
            voltage_factor=voltage_factor,
            equivalent_voltage_pu=complex(voltage_factor, 0.0),
            initial_symmetrical_current_ka=initial_current,
            peak_current_factor=peak_factor,
            peak_current_ka=peak_current,
            breaking_current_ka=breaking_current,
            steady_state_current_ka=steady_state_current,
            thermal_factor_dc=thermal_m,
            thermal_factor_ac=thermal_n,
            thermal_equivalent_current_ka=thermal_current,
            joule_integral_ka2s=joule_integral,
            fault_duration_s=study.fault_duration_s,
            frequency_hz=study.frequency_hz,
            applied_transformer_correction_factors={
                str(key): value for key, value in transformer_factors.items()
            },
            diagnostics=tuple(diagnostics),
            calculation_networks=corrected_networks,
            current_method_references=current_method_references,
            unavailable_quantity_reasons=unavailable_quantity_reasons,
            first_pole_contact_separation_time_s=(study.first_pole_contact_separation_time_s),
            dc_component_at_separation_ka=dc_component_at_separation,
            asymmetrical_breaking_current_ka=asymmetrical_breaking_current,
        )

    def _validate_supported_sources(
        self, networks: SequenceNetworkSet, fault: FaultSpecification
    ) -> int:
        """Validate that only external network-feeder voltage sources are active.

        One or more feeder equivalents are accepted for the initial symmetrical
        current. Every declared feeder must provide the sequence data required by
        the fault connection. Machine and converter sources remain excluded until
        their source-specific IEC correction procedures are implemented.
        """
        positive = networks.positive
        if positive.requires_nonlinear_source_solver:
            raise IEC60909CalculationError(
                "Converter current-source contributions need a dedicated IEC 60909 converter "
                "correction model and are not supported by this calculation increment."
            )
        active_sources = [
            item for item in positive.shunts if item.source_kind is not SequenceSourceKind.PASSIVE
        ]
        if not active_sources:
            raise IEC60909CalculationError(
                "At least one external network-feeder source is required for this IEC calculation."
            )
        unsupported = tuple(
            item
            for item in active_sources
            if item.source_kind is not SequenceSourceKind.NETWORK_FEEDER
        )
        if unsupported:
            names = ", ".join(item.name for item in unsupported)
            raise IEC60909CalculationError(
                "Only ExternalGrid network-feeder sources are currently accepted by the IEC "
                "calculator. Synchronous/asynchronous machines and generic Thevenin sources "
                f"require source-specific IEC correction models; unsupported: {names}."
            )
        feeder_ids = {item.id for item in active_sources}
        if len(feeder_ids) != len(active_sources):
            raise IEC60909CalculationError(
                "The positive-sequence network contains duplicate source IDs."
            )

        for sequence in self._required_sequences(fault.fault_type):
            model = networks.for_sequence(sequence)
            if model.requires_nonlinear_source_solver:
                raise IEC60909CalculationError(
                    f"A nonlinear converter source is present in the required {sequence.value} "
                    "sequence network."
                )
            sequence_source_ids = set()
            for shunt in model.shunts:
                if shunt.source_kind is SequenceSourceKind.PASSIVE:
                    if abs(shunt.source_voltage_pu) > 1e-12:
                        raise IEC60909CalculationError(
                            f"Passive shunt '{shunt.name}' has a non-zero internal source voltage; "
                            "classify the source explicitly before an IEC study."
                        )
                    continue
                if shunt.source_kind is not SequenceSourceKind.NETWORK_FEEDER:
                    raise IEC60909CalculationError(
                        f"Source '{shunt.name}' is not an external network feeder; its IEC "
                        "source correction model is not implemented."
                    )
                sequence_source_ids.add(shunt.id)
            if sequence_source_ids != feeder_ids:
                missing = feeder_ids - sequence_source_ids
                unexpected = sequence_source_ids - feeder_ids
                raise IEC60909CalculationError(
                    f"The {sequence.value}-sequence network must contain the same external "
                    f"feeder IDs as the positive-sequence network. Missing={sorted(map(str, missing))}; "
                    f"unexpected={sorted(map(str, unexpected))}. Check declared sequence impedances."
                )
        return len(feeder_ids)

    @staticmethod
    def _required_sequences(fault_type: FaultType) -> tuple[SequenceType, ...]:
        if fault_type is FaultType.THREE_PHASE:
            return (SequenceType.POSITIVE,)
        if fault_type is FaultType.LINE_TO_LINE:
            return (SequenceType.POSITIVE, SequenceType.NEGATIVE)
        return (SequenceType.POSITIVE, SequenceType.NEGATIVE, SequenceType.ZERO)

    @staticmethod
    def _validate_transformer_scope(
        networks: SequenceNetworkSet, required_sequences: tuple[SequenceType, ...]
    ) -> None:
        for sequence in required_sequences:
            model = networks.for_sequence(sequence)
            for branch in model.branches:
                if branch.equipment_kind is SequenceEquipmentKind.THREE_WINDING_TRANSFORMER:
                    raise IEC60909CalculationError(
                        "Three-winding transformer IEC correction is not implemented; "
                        f"transformer '{branch.name}' requires a validated three-winding model."
                    )
            for shunt in model.shunts:
                if shunt.equipment_kind is SequenceEquipmentKind.THREE_WINDING_TRANSFORMER:
                    raise IEC60909CalculationError(
                        "Three-winding transformer IEC correction is not implemented; "
                        f"transformer shunt '{shunt.name}' requires an explicit model."
                    )

    @staticmethod
    def _validate_minimum_line_resistance(
        networks: SequenceNetworkSet,
        study: IEC60909StudySpecification,
        required_sequences: tuple[SequenceType, ...],
    ) -> None:
        if study.current_case is not IEC60909CurrentCase.MINIMUM:
            return
        for sequence in required_sequences:
            has_lines = any(
                branch.equipment_kind is SequenceEquipmentKind.LINE
                for branch in networks.for_sequence(sequence).branches
            )
            if not has_lines:
                continue
            if sequence is SequenceType.ZERO:
                if study.minimum_zero_sequence_line_resistance_factor is None:
                    raise IEC60909CalculationError(
                        "Minimum unbalanced line studies require "
                        "minimum_zero_sequence_line_resistance_factor for zero-sequence "
                        "earth-return and mutual resistance temperature effects."
                    )
            elif study.minimum_line_resistance_factor is None:
                raise IEC60909CalculationError(
                    "Minimum-case line studies require minimum_line_resistance_factor = "
                    "R(theta_end)/R(input) for positive/negative conductor resistance."
                )

    def _apply_network_corrections(
        self,
        networks: SequenceNetworkSet,
        study: IEC60909StudySpecification,
        required_sequences: tuple[SequenceType, ...],
    ) -> tuple[SequenceNetworkSet, Mapping[UUID, float]]:
        transformer_metadata: dict[UUID, tuple[float, float]] = {}
        for sequence in required_sequences:
            model = networks.for_sequence(sequence)
            for item in (*model.branches, *model.shunts):
                if item.equipment_kind is not SequenceEquipmentKind.TWO_WINDING_TRANSFORMER:
                    continue
                reactance = item.transformer_reactance_pu
                voltage = item.transformer_correction_voltage_kv
                if reactance is None or voltage is None:
                    raise IEC60909CalculationError(
                        f"Two-winding transformer '{item.name}' lacks rated xT or "
                        "LV voltage metadata."
                    )
                previous = transformer_metadata.get(item.id)
                metadata = (reactance, voltage)
                if previous is not None and (
                    not math.isclose(previous[0], reactance, rel_tol=1e-8, abs_tol=1e-10)
                    or not math.isclose(previous[1], voltage, rel_tol=1e-8, abs_tol=1e-10)
                ):
                    raise IEC60909CalculationError(
                        f"Transformer '{item.name}' has inconsistent correction "
                        "metadata across sequences."
                    )
                transformer_metadata[item.id] = metadata

        transformer_factors: dict[UUID, float] = {}
        for transformer_id, (reactance, low_voltage_kv) in transformer_metadata.items():
            c_max = study.maximum_voltage_factor(low_voltage_kv)
            factor = 0.95 * c_max / (1.0 + 0.6 * reactance)
            if not math.isfinite(factor) or factor <= 0.0:
                raise IEC60909CalculationError(
                    f"Calculated transformer correction factor is invalid for '{transformer_id}'."
                )
            transformer_factors[transformer_id] = factor

        corrected_models: dict[SequenceType, SequenceNetwork] = {
            sequence: networks.for_sequence(sequence)
            for sequence in SequenceType
            if sequence not in required_sequences
        }
        for sequence in required_sequences:
            model = networks.for_sequence(sequence)
            branches: list[SequenceBranch] = []
            for branch in model.branches:
                corrected_branch = branch
                if branch.equipment_kind is SequenceEquipmentKind.TWO_WINDING_TRANSFORMER:
                    factor = transformer_factors[branch.id]
                    corrected_branch = replace(
                        branch,
                        series_impedance_pu=branch.series_impedance_pu * factor,
                        shunt_admittance_from_pu=branch.shunt_admittance_from_pu / factor,
                        shunt_admittance_to_pu=branch.shunt_admittance_to_pu / factor,
                    )
                elif (
                    branch.equipment_kind is SequenceEquipmentKind.LINE
                    and study.current_case is IEC60909CurrentCase.MINIMUM
                ):
                    resistance_factor = (
                        study.minimum_zero_sequence_line_resistance_factor
                        if sequence is SequenceType.ZERO
                        else study.minimum_line_resistance_factor
                    )
                    if resistance_factor is not None:
                        corrected_branch = replace(
                            branch,
                            series_impedance_pu=complex(
                                branch.series_impedance_pu.real * resistance_factor,
                                branch.series_impedance_pu.imag,
                            ),
                        )

                if sequence in (
                    SequenceType.POSITIVE,
                    SequenceType.NEGATIVE,
                ) and branch.equipment_kind in (
                    SequenceEquipmentKind.LINE,
                    SequenceEquipmentKind.TWO_WINDING_TRANSFORMER,
                    SequenceEquipmentKind.THREE_WINDING_TRANSFORMER,
                ):
                    corrected_branch = replace(
                        corrected_branch,
                        shunt_admittance_from_pu=0.0j,
                        shunt_admittance_to_pu=0.0j,
                    )
                branches.append(corrected_branch)

            shunts: list[SequenceShunt] = []
            for shunt in model.shunts:
                if shunt.source_kind is SequenceSourceKind.NETWORK_FEEDER:
                    shunts.append(
                        replace(
                            shunt,
                            admittance_pu=(
                                shunt.admittance_pu / study.network_feeder_impedance_multiplier
                            ),
                        )
                    )
                elif shunt.equipment_kind is SequenceEquipmentKind.TWO_WINDING_TRANSFORMER:
                    factor = transformer_factors[shunt.id]
                    shunts.append(replace(shunt, admittance_pu=shunt.admittance_pu / factor))
                else:
                    shunts.append(shunt)
            corrected_models[sequence] = replace(
                model,
                branches=tuple(branches),
                shunts=tuple(shunts),
            )

        return (
            SequenceNetworkSet(
                positive=corrected_models[SequenceType.POSITIVE],
                negative=corrected_models[SequenceType.NEGATIVE],
                zero=corrected_models[SequenceType.ZERO],
            ),
            transformer_factors,
        )

    @staticmethod
    def _has_ignored_positive_negative_branch_shunts(
        networks: SequenceNetworkSet,
        required_sequences: tuple[SequenceType, ...],
    ) -> bool:
        for sequence in required_sequences:
            if sequence is SequenceType.ZERO:
                continue
            model = networks.for_sequence(sequence)
            for branch in model.branches:
                if branch.equipment_kind in (
                    SequenceEquipmentKind.LINE,
                    SequenceEquipmentKind.TWO_WINDING_TRANSFORMER,
                    SequenceEquipmentKind.THREE_WINDING_TRANSFORMER,
                ) and (
                    abs(branch.shunt_admittance_from_pu) > 1e-15
                    or abs(branch.shunt_admittance_to_pu) > 1e-15
                ):
                    return True
        return False

    @staticmethod
    def _fault_component_is_radial(network: SequenceNetwork, fault_bus_id: UUID) -> bool:
        graph = nx.MultiGraph()
        graph.add_nodes_from(node.id for node in network.nodes)
        graph.add_edges_from(
            (branch.from_node_id, branch.to_node_id) for branch in network.branches
        )
        if fault_bus_id not in graph:
            return False
        component_nodes = nx.node_connected_component(graph, fault_bus_id)
        component = graph.subgraph(component_nodes)
        return nx.is_tree(component)

    @staticmethod
    def _thermal_dc_factor(peak_factor: float, frequency_hz: float, duration_s: float) -> float:
        logarithm = math.log(peak_factor - 1.0)
        denominator = 2.0 * frequency_hz * duration_s * logarithm
        exponent = 4.0 * frequency_hz * duration_s * logarithm
        if abs(denominator) <= 1e-15:
            return 2.0
        value = math.expm1(exponent) / denominator
        if not math.isfinite(value) or value <= 0.0:
            raise IEC60909CalculationError("Thermal DC-component factor m is invalid.")
        return value
