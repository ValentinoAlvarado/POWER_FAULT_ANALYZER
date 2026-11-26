"""Current-quantity calculation contracts for IEC 60909 strategies."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.standards.iec60909.correction_factors import (
    IEC60909CorrectionFactorSet,
    validate_factor_references,
)
from power_fault_analyzer.standards.iec60909.models import (
    IEC60909CalculationQuantity,
    IEC60909QuantityResult,
    IEC60909QuantityStatus,
    IEC60909SourceContribution,
    IEC60909SourceFamily,
)
from power_fault_analyzer.standards.iec60909.scenarios import IEC60909StudyScenario


@dataclass(frozen=True, slots=True)
class IEC60909CurrentCalculationRequest:
    """Immutable input bundle consumed by one IEC current-calculation strategy."""

    scenario: IEC60909StudyScenario
    source_contributions: tuple[IEC60909SourceContribution, ...]
    correction_factors: IEC60909CorrectionFactorSet

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, IEC60909StudyScenario):
            raise TypeError("scenario must be an IEC60909StudyScenario value.")
        if not isinstance(self.source_contributions, tuple) or any(
            not isinstance(item, IEC60909SourceContribution) for item in self.source_contributions
        ):
            raise TypeError("source_contributions must be a tuple of source contributions.")
        if not isinstance(self.correction_factors, IEC60909CorrectionFactorSet):
            raise TypeError("correction_factors must be an IEC60909CorrectionFactorSet value.")
        if self.correction_factors.scenario_id != self.scenario.scenario_id:
            raise ValueError("Correction factors must belong to the request scenario.")
        validate_factor_references(self.correction_factors.factors, scenario=self.scenario)
        descriptors = {item.source_id: item for item in self.scenario.sources if item.in_service}
        supplied = {item.source_id: item for item in self.source_contributions}
        if len(supplied) != len(self.source_contributions):
            raise ValueError("A calculation request cannot repeat a source contribution.")
        if set(supplied) != set(descriptors):
            raise ValueError(
                "Calculation source contributions must match the scenario source IDs exactly."
            )
        for source_id, contribution in supplied.items():
            descriptor = descriptors[source_id]
            if (
                contribution.source_name != descriptor.name
                or contribution.source_family is not descriptor.family
                or contribution.source_mode is not descriptor.mode
                or contribution.model_reference != descriptor.model_reference
            ):
                raise ValueError(
                    "Source contribution metadata does not match its scenario descriptor."
                )
            if not set(contribution.sequence_currents_ka).issubset(
                self.scenario.required_sequences
            ):
                raise ValueError(
                    "Source contribution contains a sequence not required by the fault connection."
                )


class IEC60909CurrentCalculationStrategy(Protocol):
    """Port for one clause-mapped current calculation method."""

    @property
    def quantity(self) -> IEC60909CalculationQuantity:
        """Quantity produced by this strategy."""
        ...

    @property
    def method_id(self) -> str:
        """Stable identifier for reproducibility and result traceability."""
        ...

    def is_applicable(self, request: IEC60909CurrentCalculationRequest) -> bool:
        """Return whether this strategy supports the explicit scenario class."""
        ...

    def calculate(self, request: IEC60909CurrentCalculationRequest) -> IEC60909QuantityResult:
        """Calculate one quantity or return an explicit unavailable/not-applicable result."""
        ...


def validate_strategy_result(
    strategy: IEC60909CurrentCalculationStrategy,
    result: IEC60909QuantityResult,
) -> None:
    """Enforce quantity/method consistency at the strategy boundary."""
    if not isinstance(result, IEC60909QuantityResult):
        raise TypeError("A current-calculation strategy must return IEC60909QuantityResult.")
    if result.quantity is not strategy.quantity:
        raise ValueError("Strategy result quantity does not match the strategy contract.")
    if (
        result.status is IEC60909QuantityStatus.CALCULATED
        and result.method_id != strategy.method_id
    ):
        raise ValueError("Calculated result method_id does not match the strategy identifier.")


@dataclass(frozen=True, slots=True)
class IEC60909PeakCurrentOutcome:
    """Peak-current result and its dimensionless peak factor."""

    factor: float
    result: IEC60909QuantityResult

    def __post_init__(self) -> None:
        if isinstance(self.factor, bool) or not isinstance(self.factor, (int, float)):
            raise TypeError("factor must be a real number, not bool.")
        numeric = float(self.factor)
        if not math.isfinite(numeric) or numeric <= 1.0:
            raise ValueError("factor must be finite and greater than one.")
        if not isinstance(self.result, IEC60909QuantityResult):
            raise TypeError("result must be an IEC60909QuantityResult value.")
        if self.result.quantity is not IEC60909CalculationQuantity.PEAK_CURRENT:
            raise ValueError("Peak-current outcome must contain an ip result.")
        if self.result.status is not IEC60909QuantityStatus.CALCULATED:
            raise ValueError("A peak-current outcome must contain a calculated result.")
        object.__setattr__(self, "factor", numeric)


def calculate_single_fed_three_phase_peak_current(
    initial_current_ka: float,
    positive_sequence_thevenin_impedance_pu: complex,
) -> IEC60909PeakCurrentOutcome:
    """Calculate the existing radial, single-fed three-phase peak-current subset.

    This policy preserves the baseline Clause 8.1 implementation. It must not be
    selected for multiple-fed, meshed or unbalanced cases.
    """
    initial = _positive_finite(initial_current_ka, "initial_current_ka")
    impedance = complex(positive_sequence_thevenin_impedance_pu)
    if not math.isfinite(impedance.real) or not math.isfinite(impedance.imag):
        raise ValueError("positive_sequence_thevenin_impedance_pu must be finite.")
    if impedance.real < -1e-12 or impedance.imag <= 0.0:
        raise ValueError("Peak-current calculation requires R >= 0 and X > 0.")

    resistance_ratio = max(0.0, impedance.real) / impedance.imag
    factor = 1.02 + 0.98 * math.exp(-3.0 * resistance_ratio)
    peak_current = factor * math.sqrt(2.0) * initial
    result = IEC60909QuantityResult(
        quantity=IEC60909CalculationQuantity.PEAK_CURRENT,
        status=IEC60909QuantityStatus.CALCULATED,
        value=peak_current,
        unit="kA",
        method_id=("IEC60909-0:2026/8.1/single-fed-three-phase-radial-network-feeder"),
    )
    return IEC60909PeakCurrentOutcome(factor=factor, result=result)


def calculate_network_feeder_breaking_current(
    initial_current_ka: float,
    source_families: tuple[IEC60909SourceFamily, ...],
    fault_type: FaultType,
) -> IEC60909QuantityResult:
    """Return Ib for a study whose active sources are all network feeders.

    Network-feeder sources are represented by voltage-source equivalents with no
    rotating-machine AC decrement. Machine and converter cases are rejected here
    and require their own Clause 9 strategies.
    """
    initial = _positive_finite(initial_current_ka, "initial_current_ka")
    if not isinstance(source_families, tuple) or not source_families:
        raise ValueError("source_families must be a non-empty tuple.")
    if any(not isinstance(item, IEC60909SourceFamily) for item in source_families):
        raise TypeError("source_families must contain IEC60909SourceFamily values.")
    if not isinstance(fault_type, FaultType):
        raise TypeError("fault_type must be a FaultType value.")
    if fault_type is not FaultType.THREE_PHASE:
        if any(item is not IEC60909SourceFamily.NETWORK_FEEDER for item in source_families):
            return _unavailable_quantity(
                IEC60909CalculationQuantity.BREAKING_CURRENT,
                "The Clause 9.3 source-specific procedure is unavailable when rotating "
                "machines or converter sources participate.",
            )
        return IEC60909QuantityResult(
            quantity=IEC60909CalculationQuantity.BREAKING_CURRENT,
            status=IEC60909QuantityStatus.CALCULATED,
            value=initial,
            unit="kA",
            method_id=("IEC60909-0:2026/9.3/unbalanced-network-feeder-contributions"),
        )
    if any(item is not IEC60909SourceFamily.NETWORK_FEEDER for item in source_families):
        return _unavailable_quantity(
            IEC60909CalculationQuantity.BREAKING_CURRENT,
            "The source inventory contains a non-network-feeder source; apply its "
            "source-specific Clause 9 method.",
        )

    source_count = len(source_families)
    clause = "9.1.5" if source_count == 1 else "9.2"
    return IEC60909QuantityResult(
        quantity=IEC60909CalculationQuantity.BREAKING_CURRENT,
        status=IEC60909QuantityStatus.CALCULATED,
        value=initial,
        unit="kA",
        method_id=f"IEC60909-0:2026/{clause}/network-feeder-contribution",
    )


def calculate_network_feeder_steady_state_current(
    initial_current_ka: float,
    source_families: tuple[IEC60909SourceFamily, ...],
    fault_type: FaultType,
) -> IEC60909QuantityResult:
    """Return the supported three-phase steady-state network-feeder current.

    For unbalanced faults, the returned current is the maximum phase RMS value
    from the sequence-network solution. The equality with the initial value is
    limited to installations made exclusively of network-feeder voltage sources;
    rotating machines and converter sources require their own Clause 11 method.
    """
    initial = _positive_finite(initial_current_ka, "initial_current_ka")
    if not isinstance(source_families, tuple) or not source_families:
        raise ValueError("source_families must be a non-empty tuple.")
    if any(not isinstance(item, IEC60909SourceFamily) for item in source_families):
        raise TypeError("source_families must contain IEC60909SourceFamily values.")
    if not isinstance(fault_type, FaultType):
        raise TypeError("fault_type must be a FaultType value.")
    if fault_type is not FaultType.THREE_PHASE:
        if any(item is not IEC60909SourceFamily.NETWORK_FEEDER for item in source_families):
            return _unavailable_quantity(
                IEC60909CalculationQuantity.STEADY_STATE_CURRENT,
                "The Clause 11.3 source-specific procedure is unavailable when rotating "
                "machines or converter sources participate.",
            )
        return IEC60909QuantityResult(
            quantity=IEC60909CalculationQuantity.STEADY_STATE_CURRENT,
            status=IEC60909QuantityStatus.CALCULATED,
            value=initial,
            unit="kA",
            method_id=("IEC60909-0:2026/11.3/unbalanced-network-feeder-contributions"),
        )
    if any(item is not IEC60909SourceFamily.NETWORK_FEEDER for item in source_families):
        return _unavailable_quantity(
            IEC60909CalculationQuantity.STEADY_STATE_CURRENT,
            "The source inventory contains a non-network-feeder source; apply its "
            "source-specific Clause 11 method.",
        )
    clause = "11.2.5" if len(source_families) == 1 else "11.2.6"
    return IEC60909QuantityResult(
        quantity=IEC60909CalculationQuantity.STEADY_STATE_CURRENT,
        status=IEC60909QuantityStatus.CALCULATED,
        value=initial,
        unit="kA",
        method_id=f"IEC60909-0:2026/{clause}/network-feeder-contribution",
    )


@dataclass(frozen=True, slots=True)
class IEC60909DCAndAsymmetricalBreakingOutcome:
    """Supplementary R/X envelope estimate for a single-fed three-phase feeder.

    This engineering estimate is not marked as an IEC 60909-0:2026 Clause 10
    calculation until the final-edition equation and all applicability conditions
    have been independently checked against the licensed text.
    """

    dc_component_ka: float
    asymmetrical_breaking_current_ka: float
    method_id: str

    def __post_init__(self) -> None:
        _nonnegative_finite(self.dc_component_ka, "dc_component_ka")
        _positive_finite(self.asymmetrical_breaking_current_ka, "asymmetrical_breaking_current_ka")
        if not isinstance(self.method_id, str) or not self.method_id.strip():
            raise ValueError("method_id must be a non-empty string.")


def calculate_single_fed_three_phase_dc_and_asymmetrical_breaking(
    *,
    initial_current_ka: float,
    breaking_current_ka: float,
    positive_sequence_thevenin_impedance_pu: complex,
    frequency_hz: float,
    first_pole_contact_separation_time_s: float,
) -> IEC60909DCAndAsymmetricalBreakingOutcome:
    """Calculate a supplementary single-fed, three-phase network-feeder R/X estimate.

    The DC envelope is evaluated using the equivalent positive-sequence R/X at
    the fault point. The exponential R/X relation is retained as a separate
    engineering estimate; it is not asserted here as a verified Clause 10 method
    for the final 2026 edition. Multiple-fed, meshed, unbalanced, rotating-machine
    and converter cases are intentionally excluded.
    """
    initial = _positive_finite(initial_current_ka, "initial_current_ka")
    breaking = _positive_finite(breaking_current_ka, "breaking_current_ka")
    frequency = _positive_finite(frequency_hz, "frequency_hz")
    separation = _positive_finite(
        first_pole_contact_separation_time_s, "first_pole_contact_separation_time_s"
    )
    if frequency not in (50.0, 60.0):
        raise ValueError("frequency_hz must be 50 Hz or 60 Hz.")
    impedance = complex(positive_sequence_thevenin_impedance_pu)
    if not math.isfinite(impedance.real) or not math.isfinite(impedance.imag):
        raise ValueError("positive_sequence_thevenin_impedance_pu must be finite.")
    if impedance.real < -1e-12 or impedance.imag <= 0.0:
        raise ValueError("The Clause 10 R/X subset requires R >= 0 and X > 0.")

    resistance_ratio = max(0.0, impedance.real) / impedance.imag
    decay_exponent = -2.0 * math.pi * frequency * separation * resistance_ratio
    dc_component = math.sqrt(2.0) * initial * math.exp(decay_exponent)
    asymmetrical = math.hypot(breaking, dc_component)
    return IEC60909DCAndAsymmetricalBreakingOutcome(
        dc_component_ka=dc_component,
        asymmetrical_breaking_current_ka=asymmetrical,
        method_id=("PFA-ENGINEERING/RX-DC-DECAY/single-fed-three-phase-network-feeder/v1"),
    )


def unavailable_dc_and_asymmetrical_breaking_results(
    reason: str,
) -> tuple[IEC60909QuantityResult, IEC60909QuantityResult]:
    """Declare IEC Clause 10 outputs unavailable for an unsupported study class."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason must be a non-empty string.")
    return (
        _unavailable_quantity(IEC60909CalculationQuantity.DC_COMPONENT, reason),
        _unavailable_quantity(IEC60909CalculationQuantity.ASYMMETRICAL_BREAKING_CURRENT, reason),
    )


def _unavailable_quantity(
    quantity: IEC60909CalculationQuantity, reason: str
) -> IEC60909QuantityResult:
    return IEC60909QuantityResult(
        quantity=quantity,
        status=IEC60909QuantityStatus.UNAVAILABLE,
        value=None,
        unit="kA",
        reason=reason,
    )


def _nonnegative_finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number, not bool.")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0:
        raise ValueError(f"{name} must be finite and non-negative.")
    return numeric


def _positive_finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number, not bool.")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0.0:
        raise ValueError(f"{name} must be finite and positive.")
    return numeric


def initial_symmetrical_current_method_id(fault_type: FaultType) -> str:
    """Return the Clause 7 method reference for the supported bus-fault class."""
    if not isinstance(fault_type, FaultType):
        raise TypeError("fault_type must be a FaultType value.")
    clauses = {
        FaultType.THREE_PHASE: "7.2/three-phase",
        FaultType.LINE_TO_LINE: "7.3/line-to-line",
        FaultType.DOUBLE_LINE_TO_GROUND: "7.4/line-to-line-with-earth",
        FaultType.SINGLE_LINE_TO_GROUND: "7.5/line-to-earth",
    }
    return f"IEC60909-0:2026/{clauses[fault_type]}/initial-symmetrical-current"
