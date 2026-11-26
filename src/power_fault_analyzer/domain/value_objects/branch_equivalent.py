"""Equivalent two-terminal branch model for one symmetrical-component network."""

from dataclasses import dataclass

from power_fault_analyzer.domain.value_objects.impedance import Admittance, Impedance


@dataclass(frozen=True, slots=True)
class BranchEquivalentModel:
    """Series impedance and shunt admittances at both ends of a branch.

    This representation supports a series-only equivalent and a nominal-pi
    equivalent. Shunt admittances are terminal-to-reference equivalents for
    the selected sequence network.
    """

    series_impedance: Impedance
    shunt_admittance_from: Admittance
    shunt_admittance_to: Admittance

    def __post_init__(self) -> None:
        if not isinstance(self.series_impedance, Impedance):
            raise TypeError("series_impedance must be an Impedance value.")
        if not isinstance(self.shunt_admittance_from, Admittance):
            raise TypeError("shunt_admittance_from must be an Admittance value.")
        if not isinstance(self.shunt_admittance_to, Admittance):
            raise TypeError("shunt_admittance_to must be an Admittance value.")
