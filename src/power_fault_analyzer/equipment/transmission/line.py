"""Generic line equipment with per-length symmetrical-component parameters."""

from __future__ import annotations

import math
from numbers import Real
from uuid import UUID

from power_fault_analyzer.domain.entities.branch_equipment import BranchEquipmentBase
from power_fault_analyzer.domain.entities.terminal import Terminal
from power_fault_analyzer.domain.enums.equipment_family import EquipmentFamily
from power_fault_analyzer.domain.enums.line_model_kind import LineModelKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.branch_equivalent import (
    BranchEquivalentModel,
)
from power_fault_analyzer.domain.value_objects.impedance import Admittance
from power_fault_analyzer.equipment.interfaces.unresolved_equipment import EngineeringParameter
from power_fault_analyzer.equipment.transmission.line_parameters import LineParameters


class Line(BranchEquipmentBase):
    """A two-terminal line with length-scaled series and shunt parameters.

    The initial supported equivalents are series-only and nominal-pi. The
    sequence parameters are supplied explicitly; no assumption is made that
    negative-sequence parameters equal positive-sequence parameters.
    """

    __slots__ = ("_data_evidence", "_length_km", "_model_kind", "_parameters")

    def __init__(
        self,
        *,
        id: UUID,
        name: str,
        terminals: tuple[Terminal, Terminal],
        length_km: float,
        parameters: LineParameters,
        model_kind: LineModelKind = LineModelKind.NOMINAL_PI,
        data_evidence: tuple[EngineeringParameter, ...] = (),
    ) -> None:
        if isinstance(length_km, bool) or not isinstance(length_km, Real):
            raise TypeError("length_km must be a real numeric value, not bool.")
        length = float(length_km)
        if not math.isfinite(length) or length <= 0.0:
            raise ValueError("length_km must be finite and greater than zero.")
        if not isinstance(parameters, LineParameters):
            raise TypeError("parameters must be a LineParameters value.")
        if not isinstance(model_kind, LineModelKind):
            raise TypeError("model_kind must be a LineModelKind value.")
        if not isinstance(data_evidence, tuple) or any(
            not isinstance(item, EngineeringParameter) for item in data_evidence
        ):
            raise TypeError("data_evidence must be a tuple of EngineeringParameter values.")

        super().__init__(
            id=id,
            name=name,
            terminals=terminals,
            family=EquipmentFamily.TRANSMISSION,
        )
        self._length_km = length
        self._parameters = parameters
        self._model_kind = model_kind
        self._data_evidence = data_evidence

    @property
    def data_evidence(self) -> tuple[EngineeringParameter, ...]:
        return self._data_evidence

    @property
    def length_km(self) -> float:
        return self._length_km

    @property
    def parameters(self) -> LineParameters:
        return self._parameters

    @property
    def model_kind(self) -> LineModelKind:
        return self._model_kind

    def build_sequence_equivalent(self, sequence: SequenceType) -> BranchEquivalentModel:
        series_per_km = self.parameters.series_impedance_per_km.for_sequence(sequence)
        series_impedance = series_per_km.for_length(self.length_km)

        if self.model_kind is LineModelKind.SERIES_ONLY:
            zero_shunt = Admittance.zero()
            return BranchEquivalentModel(
                series_impedance=series_impedance,
                shunt_admittance_from=zero_shunt,
                shunt_admittance_to=zero_shunt,
            )

        shunt_per_km = self.parameters.shunt_admittance_per_km.for_sequence(sequence)
        total_shunt = shunt_per_km.for_length(self.length_km)
        half_shunt = total_shunt.scaled(0.5)
        return BranchEquivalentModel(
            series_impedance=series_impedance,
            shunt_admittance_from=half_shunt,
            shunt_admittance_to=half_shunt,
        )
