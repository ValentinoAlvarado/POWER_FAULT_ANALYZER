"""Explicit phasor current commands for converter-interfaced sources."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.source_models import ConverterFaultCurrentCapability


@dataclass(frozen=True, slots=True)
class ConverterSequenceCurrentCommand:
    """User/vendor-supplied converter current command in all three sequences.

    This is a fixed phasor current-source command, not an inferred converter
    control law. The command is checked against declared per-sequence and total
    phase-current capabilities before it is applied to a sequence network.
    """

    source_id: UUID
    bus_id: UUID
    capability: ConverterFaultCurrentCapability
    sequence_currents_pu: Mapping[SequenceType, complex]

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, UUID) or not isinstance(self.bus_id, UUID):
            raise TypeError("source_id and bus_id must be UUID values.")
        if not isinstance(self.capability, ConverterFaultCurrentCapability):
            raise TypeError("capability must be a ConverterFaultCurrentCapability value.")
        if not isinstance(self.sequence_currents_pu, Mapping):
            raise TypeError("sequence_currents_pu must be a mapping.")
        if set(self.sequence_currents_pu) != set(SequenceType):
            raise ValueError(
                "sequence_currents_pu must explicitly define positive, negative and zero."
            )
        copied: dict[SequenceType, complex] = {}
        for sequence, value in self.sequence_currents_pu.items():
            if not isinstance(sequence, SequenceType):
                raise TypeError("Sequence-current command keys must be SequenceType values.")
            if isinstance(value, bool) or not isinstance(value, (int, float, complex)):
                raise TypeError("Sequence-current commands must be finite complex numbers.")
            current = complex(value)
            if not math.isfinite(current.real) or not math.isfinite(current.imag):
                raise ValueError("Sequence-current commands must be finite.")
            copied[sequence] = current
        object.__setattr__(self, "sequence_currents_pu", MappingProxyType(copied))

    def validate_limits(self, system_base) -> None:
        """Validate the command on the system base at the converter bus."""
        base = system_base.for_bus(self.bus_id)
        capability = self.capability.convert_base(base)
        for sequence, limit in (
            (SequenceType.POSITIVE, capability.positive_sequence_limit_pu),
            (SequenceType.NEGATIVE, capability.negative_sequence_limit_pu),
            (SequenceType.ZERO, capability.zero_sequence_limit_pu),
        ):
            current = abs(self.sequence_currents_pu[sequence])
            if limit is None and current > 1e-12:
                raise ValueError(
                    f"{sequence.value}-sequence converter current is nonzero "
                    "but its limit is unspecified."
                )
            if limit is not None and current > limit + 1e-10:
                raise ValueError(f"{sequence.value}-sequence converter current exceeds its limit.")
        i0 = self.sequence_currents_pu[SequenceType.ZERO]
        i1 = self.sequence_currents_pu[SequenceType.POSITIVE]
        i2 = self.sequence_currents_pu[SequenceType.NEGATIVE]
        a = complex(-0.5, math.sqrt(3.0) / 2.0)
        phase_currents = (
            i0 + i1 + i2,
            i0 + a**2 * i1 + a * i2,
            i0 + a * i1 + a**2 * i2,
        )
        if (
            max(abs(value) for value in phase_currents)
            > capability.overall_current_limit_pu + 1e-10
        ):
            raise ValueError("Converter phase-current command exceeds its overall current limit.")
