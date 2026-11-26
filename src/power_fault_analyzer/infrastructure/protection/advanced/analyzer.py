"""Network-aware orchestration for differential, directional and distance functions."""

from __future__ import annotations

import math
from collections.abc import Sequence
from numbers import Real

from power_fault_analyzer.domain.enums.protection import ProtectionAssessmentStatus
from power_fault_analyzer.domain.value_objects.advanced_protection import (
    AdvancedProtectionFunctionAssessment,
    AdvancedProtectionNetworkAssessment,
    AdvancedProtectionScenarioAssessment,
    AdvancedProtectionScenarioMeasurements,
    DifferentialMeasurement,
    DifferentialProtectionSettings,
    DirectionalMeasurement,
    DirectionalOvercurrentSettings,
    DistanceMeasurement,
    DistanceProtectionSettings,
)
from power_fault_analyzer.domain.value_objects.protection_network import ProtectionNetworkModel
from power_fault_analyzer.infrastructure.protection.advanced.evaluators import (
    CurrentTransformerSaturationEvaluator,
    DifferentialProtectionEvaluator,
    DirectionalOvercurrentEvaluator,
    DistanceProtectionEvaluator,
)


class AdvancedProtectionNetworkAnalyzer:
    """Evaluate advanced relay functions attached to the ND-010 protection network.

    ``expected_to_operate`` is an explicit test/study expectation, not inferred from
    topology. It lets a study distinguish a correctly operated element from a correctly
    restrained element without pretending that zone membership alone proves direction.
    """

    def __init__(self) -> None:
        self._differential = DifferentialProtectionEvaluator()
        self._directional = DirectionalOvercurrentEvaluator()
        self._distance = DistanceProtectionEvaluator()
        self._ct = CurrentTransformerSaturationEvaluator()

    def analyze(
        self,
        model: ProtectionNetworkModel,
        scenarios: Sequence[AdvancedProtectionScenarioMeasurements],
        *,
        system_frequency_hz: float,
    ) -> AdvancedProtectionNetworkAssessment:
        if not isinstance(model, ProtectionNetworkModel):
            raise TypeError("model must be a ProtectionNetworkModel.")
        if isinstance(system_frequency_hz, bool) or not isinstance(system_frequency_hz, Real):
            raise TypeError("system_frequency_hz must be a real number, not bool.")
        frequency = float(system_frequency_hz)
        if not math.isfinite(frequency) or frequency <= 0.0:
            raise ValueError("system_frequency_hz must be finite and positive.")
        scenario_inputs = tuple(scenarios)
        if any(
            not isinstance(item, AdvancedProtectionScenarioMeasurements) for item in scenario_inputs
        ):
            raise TypeError("scenarios must contain AdvancedProtectionScenarioMeasurements values.")
        scenario_ids = tuple(item.scenario_id for item in scenario_inputs)
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("Advanced protection scenario IDs must be unique.")

        function_bindings = {item.id: item for item in model.advanced_function_bindings}
        ct_bindings = {item.protection_device_id: item for item in model.ct_performance_bindings}
        scenario_results: list[AdvancedProtectionScenarioAssessment] = []
        all_statuses: list[ProtectionAssessmentStatus] = []
        for scenario in scenario_inputs:
            unknown_functions = set(scenario.function_measurements) - set(function_bindings)
            unknown_ct_devices = set(scenario.ct_primary_currents_a) - set(ct_bindings)
            if unknown_functions:
                raise ValueError(
                    "Scenario references advanced functions outside this protection model."
                )
            if unknown_ct_devices:
                raise ValueError(
                    "Scenario references CT performance models outside this protection model."
                )

            function_results: list[AdvancedProtectionFunctionAssessment] = []
            statuses: list[ProtectionAssessmentStatus] = []
            for function_id, binding in function_bindings.items():
                supplied = scenario.function_measurements.get(function_id)
                if supplied is None:
                    function_results.append(
                        AdvancedProtectionFunctionAssessment(
                            scenario_id=scenario.scenario_id,
                            function_id=function_id,
                            zone_id=binding.zone_id,
                            status=ProtectionAssessmentStatus.NOT_EVALUATED,
                            operated=None,
                            operation_result=None,
                            reason="No phasor measurement was supplied for this function.",
                        )
                    )
                    statuses.append(ProtectionAssessmentStatus.NOT_EVALUATED)
                    continue
                function = binding.function
                measurement = supplied.measurement
                result = self._evaluate_function(function, measurement)
                operated = result.operated
                status = (
                    ProtectionAssessmentStatus.PASS
                    if operated is supplied.expected_to_operate
                    else ProtectionAssessmentStatus.FAIL
                )
                function_results.append(
                    AdvancedProtectionFunctionAssessment(
                        scenario_id=scenario.scenario_id,
                        function_id=function_id,
                        zone_id=binding.zone_id,
                        status=status,
                        operated=operated,
                        operation_result=result,
                        reason=(
                            "Observed operation matches the declared study expectation."
                            if status is ProtectionAssessmentStatus.PASS
                            else "Observed operation does not match the declared study expectation."
                        ),
                    )
                )
                statuses.append(status)

            ct_results = {}
            diagnostics: list[str] = []
            for device_id, ct_binding in ct_bindings.items():
                current = scenario.ct_primary_currents_a.get(device_id)
                if current is None:
                    diagnostics.append(
                        f"CT current for protection device {device_id} was not supplied; "
                        "saturation was not evaluated."
                    )
                    statuses.append(ProtectionAssessmentStatus.NOT_EVALUATED)
                    continue
                ct_result = self._ct.evaluate(
                    ct_binding.performance_model,
                    current,
                    system_frequency_hz=frequency,
                )
                ct_results[device_id] = ct_result
                statuses.append(ct_result.status)
                diagnostics.extend(ct_result.diagnostics)

            scenario_status = self._combined_status(statuses)
            all_statuses.append(scenario_status)
            scenario_results.append(
                AdvancedProtectionScenarioAssessment(
                    scenario_id=scenario.scenario_id,
                    function_assessments=tuple(function_results),
                    ct_assessments=ct_results,
                    status=scenario_status,
                    diagnostics=tuple(diagnostics),
                )
            )
        return AdvancedProtectionNetworkAssessment(
            network_id=model.network_id,
            scenarios=tuple(scenario_results),
            status=self._combined_status(all_statuses),
        )

    def _evaluate_function(self, function, measurement):
        if isinstance(function, DifferentialProtectionSettings):
            if not isinstance(measurement, DifferentialMeasurement):
                raise TypeError("Differential relay requires DifferentialMeasurement.")
            return self._differential.evaluate(function, measurement)
        if isinstance(function, DirectionalOvercurrentSettings):
            if not isinstance(measurement, DirectionalMeasurement):
                raise TypeError("Directional relay requires DirectionalMeasurement.")
            return self._directional.evaluate(function, measurement)
        if isinstance(function, DistanceProtectionSettings):
            if not isinstance(measurement, DistanceMeasurement):
                raise TypeError("Distance relay requires DistanceMeasurement.")
            return self._distance.evaluate(function, measurement)
        raise TypeError("Unsupported advanced protection settings.")

    @staticmethod
    def _combined_status(
        statuses: Sequence[ProtectionAssessmentStatus],
    ) -> ProtectionAssessmentStatus:
        if not statuses or all(
            item is ProtectionAssessmentStatus.NOT_EVALUATED for item in statuses
        ):
            return ProtectionAssessmentStatus.NOT_EVALUATED
        if any(item is ProtectionAssessmentStatus.FAIL for item in statuses):
            return ProtectionAssessmentStatus.FAIL
        if any(item is ProtectionAssessmentStatus.NOT_EVALUATED for item in statuses):
            return ProtectionAssessmentStatus.NOT_EVALUATED
        return ProtectionAssessmentStatus.PASS
