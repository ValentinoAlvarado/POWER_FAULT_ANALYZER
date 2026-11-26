"""Physical line parameters used to derive sequence branch equivalents."""

from dataclasses import dataclass

from power_fault_analyzer.domain.value_objects.frequency import Frequency
from power_fault_analyzer.domain.value_objects.sequence_parameters import (
    SequenceAdmittancePerLengthSet,
    SequenceImpedancePerLengthSet,
)


@dataclass(frozen=True, slots=True)
class LineParameters:
    """Per-kilometre series and shunt parameters at a reference frequency.

    Parameters are already expressed in symmetrical components. Geometry-based
    parameter derivation (conductor geometry, Carson/Pollaczek formulations,
    sheath bonding, etc.) belongs to a separate modeling service.
    """

    series_impedance_per_km: SequenceImpedancePerLengthSet
    shunt_admittance_per_km: SequenceAdmittancePerLengthSet
    reference_frequency: Frequency

    def __post_init__(self) -> None:
        if not isinstance(self.series_impedance_per_km, SequenceImpedancePerLengthSet):
            raise TypeError("series_impedance_per_km must be a SequenceImpedancePerLengthSet.")
        if not isinstance(self.shunt_admittance_per_km, SequenceAdmittancePerLengthSet):
            raise TypeError("shunt_admittance_per_km must be a SequenceAdmittancePerLengthSet.")
        if not isinstance(self.reference_frequency, Frequency):
            raise TypeError("reference_frequency must be a Frequency value.")
