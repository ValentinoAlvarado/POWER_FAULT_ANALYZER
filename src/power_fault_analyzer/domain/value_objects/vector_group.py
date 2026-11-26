"""Transformer pairwise vector-group data."""

from dataclasses import dataclass

from power_fault_analyzer.domain.enums.winding_connection import WindingConnection


@dataclass(frozen=True, slots=True)
class VectorGroup:
    """Connection families and clock number for an oriented winding pair.

    The first connection is the reference/high-voltage side and the second is
    the corresponding lower-voltage side. The clock number must be 0..11.
    Neutral accessibility is represented separately by winding/terminal data.
    """

    reference_connection: WindingConnection
    secondary_connection: WindingConnection
    clock_number: int

    def __post_init__(self) -> None:
        if not isinstance(self.reference_connection, WindingConnection):
            raise TypeError("reference_connection must be a WindingConnection value.")
        if not isinstance(self.secondary_connection, WindingConnection):
            raise TypeError("secondary_connection must be a WindingConnection value.")
        if isinstance(self.clock_number, bool) or not isinstance(self.clock_number, int):
            raise TypeError("clock_number must be an integer, not bool.")
        if not 0 <= self.clock_number <= 11:
            raise ValueError("clock_number must be between 0 and 11.")

    @property
    def phase_displacement_degrees(self) -> int:
        """IEC clock displacement represented as a positive clockwise angle."""
        return self.clock_number * 30

    @property
    def notation(self) -> str:
        """Return abbreviated winding-connection and clock notation."""
        return self.notation_with_neutrals(False, False)

    def notation_with_neutrals(
        self,
        reference_neutral_available: bool,
        secondary_neutral_available: bool,
    ) -> str:
        """Return connection/clock notation including accessible neutral marks."""
        if not isinstance(reference_neutral_available, bool):
            raise TypeError("reference_neutral_available must be bool.")
        if not isinstance(secondary_neutral_available, bool):
            raise TypeError("secondary_neutral_available must be bool.")
        codes = {
            WindingConnection.STAR: "Y",
            WindingConnection.DELTA: "D",
            WindingConnection.ZIGZAG: "Z",
        }
        reference = codes[self.reference_connection]
        secondary = codes[self.secondary_connection].lower()
        if reference_neutral_available:
            if self.reference_connection is WindingConnection.DELTA:
                raise ValueError("A delta reference winding cannot expose a neutral.")
            reference += "N"
        if secondary_neutral_available:
            if self.secondary_connection is WindingConnection.DELTA:
                raise ValueError("A delta secondary winding cannot expose a neutral.")
            secondary += "n"
        return f"{reference}{secondary}{self.clock_number}"
