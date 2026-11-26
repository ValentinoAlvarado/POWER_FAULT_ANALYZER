"""Parameter dialogs that collect explicit engineering inputs before use cases execute."""

from __future__ import annotations

from uuid import UUID

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from power_fault_analyzer.application.use_cases.network_editing import (
    LineInput,
    SynchronousGeneratorInput,
)
from power_fault_analyzer.domain.enums.fault_type import FaultType
from power_fault_analyzer.domain.enums.grounding_mode import GroundingMode
from power_fault_analyzer.domain.enums.winding_connection import WindingConnection
from power_fault_analyzer.domain.value_objects.neutral_grounding import NeutralGrounding


class ComplexInput(QWidget):
    def __init__(self, real: str = "", imag: str = "", parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.real = QLineEdit(real)
        self.imag = QLineEdit(imag)
        self.real.setPlaceholderText("R / real")
        self.imag.setPlaceholderText("X / imaginary")
        layout.addWidget(self.real)
        layout.addWidget(QLabel("+ j"))
        layout.addWidget(self.imag)

    def value(self, label: str) -> complex:
        try:
            return complex(float(self.real.text()), float(self.imag.text()))
        except ValueError as exc:
            raise ValueError(f"Enter both real and imaginary values for {label}.") from exc


class BusDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add AC Bus")
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. 101")
        self.voltage = QDoubleSpinBox()
        self.voltage.setRange(0.001, 1_000_000.0)
        self.voltage.setDecimals(4)
        self.voltage.setValue(13.8)
        layout = QFormLayout(self)
        layout.addRow("Bus identifier", self.name)
        layout.addRow("Nominal voltage L-L (kV)", self.voltage)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> tuple[str, float]:
        name = self.name.text().strip()
        if not name:
            raise ValueError("Bus identifier cannot be empty.")
        return name, self.voltage.value()


class GeneratorDialog(QDialog):
    def __init__(self, buses, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Synchronous Generator — Sequence Model")
        self.resize(620, 680)
        self.name = QLineEdit("G1")
        self.bus = QComboBox()
        for bus in buses:
            self.bus.addItem(f"{bus.name} · {bus.nominal_voltage.value_kv:g} kV", str(bus.id))
        self.base_mva = QLineEdit("100")
        self.frequency = QLineEdit("60")
        self.e1 = ComplexInput("1.0", "0.0")
        self.impedances = {
            "positive_subtransient": ComplexInput(),
            "positive_transient": ComplexInput(),
            "positive_synchronous": ComplexInput(),
            "negative": ComplexInput(),
            "zero": ComplexInput(),
        }
        self.grounding = QComboBox()
        self.grounding.addItem("Ungrounded", GroundingMode.UNGROUNDED.value)
        self.grounding.addItem("Solidly grounded", GroundingMode.SOLID.value)
        self.grounding.addItem("Impedance grounded", GroundingMode.IMPEDANCE.value)
        self.neutral_impedance = ComplexInput("0", "0")
        self.stator = QComboBox()
        self.stator.addItem("Star (Y)", WindingConnection.STAR.value)
        self.stator.addItem("Delta (Δ)", WindingConnection.DELTA.value)

        form = QFormLayout()
        form.addRow("Identification", self.name)
        form.addRow("Connection bus", self.bus)
        form.addRow("Machine base (MVA)", self.base_mva)
        form.addRow("Frequency (Hz)", self.frequency)
        form.addRow("Prefault E1 (p.u.)", self.e1)
        for key, label in (
            ("positive_subtransient", "Positive subtransient Z1'' (p.u.)"),
            ("positive_transient", "Positive transient Z1' (p.u.)"),
            ("positive_synchronous", "Positive synchronous Z1 (p.u.)"),
            ("negative", "Negative sequence Z2 (p.u.)"),
            ("zero", "Machine zero sequence Z0 (p.u.)"),
        ):
            form.addRow(label, self.impedances[key])
        form.addRow("Stator connection", self.stator)
        form.addRow("Neutral grounding", self.grounding)
        form.addRow("Neutral Zn (Ω)", self.neutral_impedance)

        note = QLabel(
            "All sequence impedances and machine base data are required. No sequence values are inferred. "
            "The neutral impedance is the physical Zn; the domain applies the 3Zn zero-sequence contribution."
        )
        note.setWordWrap(True)
        note.setObjectName("dialogNote")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(note)
        root.addWidget(buttons)

    def specification(self) -> SynchronousGeneratorInput:
        if not self.name.text().strip() or self.bus.currentIndex() < 0:
            raise ValueError("A generator name and connected bus are required.")
        mode = GroundingMode(self.grounding.currentData())
        if mode is GroundingMode.UNGROUNDED:
            neutral = NeutralGrounding.ungrounded()
        elif mode is GroundingMode.SOLID:
            neutral = NeutralGrounding.solid()
        else:
            z_n = self.neutral_impedance.value("neutral grounding Zn")
            neutral = NeutralGrounding.through_impedance(z_n.real, z_n.imag)
        return SynchronousGeneratorInput(
            name=self.name.text().strip(),
            bus_id=UUID(self.bus.currentData()),
            base_power_mva=_required_float(self.base_mva, "machine base MVA"),
            frequency_hz=_required_float(self.frequency, "frequency"),
            positive_subtransient_pu=self.impedances["positive_subtransient"].value("Z1''"),
            positive_transient_pu=self.impedances["positive_transient"].value("Z1'"),
            positive_synchronous_pu=self.impedances["positive_synchronous"].value("Z1"),
            negative_pu=self.impedances["negative"].value("Z2"),
            zero_pu=self.impedances["zero"].value("Z0"),
            prefault_voltage_pu=self.e1.value("prefault E1"),
            neutral_grounding=neutral,
            stator_connection=WindingConnection(self.stator.currentData()),
        )


class LineDialog(QDialog):
    def __init__(
        self,
        buses,
        parent=None,
        *,
        from_bus_id: UUID | None = None,
        to_bus_id: UUID | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Transmission Line — Series-Only Sequence Model")
        self.resize(560, 470)
        self.name = QLineEdit("L1")
        self.from_bus = QComboBox()
        self.to_bus = QComboBox()
        for bus in buses:
            label = f"{bus.name} · {bus.nominal_voltage.value_kv:g} kV"
            self.from_bus.addItem(label, str(bus.id))
            self.to_bus.addItem(label, str(bus.id))
        if from_bus_id is not None:
            index = self.from_bus.findData(str(from_bus_id))
            if index >= 0:
                self.from_bus.setCurrentIndex(index)
        if to_bus_id is not None:
            index = self.to_bus.findData(str(to_bus_id))
            if index >= 0:
                self.to_bus.setCurrentIndex(index)
        elif self.to_bus.count() > 1:
            self.to_bus.setCurrentIndex(1)
        self.length = QLineEdit("1.0")
        self.frequency = QLineEdit("60")
        self.parameters = {
            "positive": ComplexInput(),
            "negative": ComplexInput(),
            "zero": ComplexInput(),
        }
        form = QFormLayout()
        form.addRow("Identification", self.name)
        form.addRow("From bus", self.from_bus)
        form.addRow("To bus", self.to_bus)
        form.addRow("Length (km)", self.length)
        form.addRow("Reference frequency (Hz)", self.frequency)
        form.addRow("Z1 per km (Ω/km)", self.parameters["positive"])
        form.addRow("Z2 per km (Ω/km)", self.parameters["negative"])
        form.addRow("Z0 per km (Ω/km)", self.parameters["zero"])
        note = QLabel(
            "This palette command creates an explicit series-only line model. "
            "Shunt capacitance/conductance is not inferred; use another line model when shunt data is available."
        )
        note.setWordWrap(True)
        note.setObjectName("dialogNote")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(note)
        root.addWidget(buttons)

    def specification(self) -> LineInput:
        if self.from_bus.currentData() == self.to_bus.currentData():
            raise ValueError("A line must connect two distinct buses.")
        if not self.name.text().strip():
            raise ValueError("Line identification cannot be empty.")
        return LineInput(
            name=self.name.text().strip(),
            from_bus_id=UUID(self.from_bus.currentData()),
            to_bus_id=UUID(self.to_bus.currentData()),
            length_km=_required_float(self.length, "line length"),
            positive_ohm_per_km=self.parameters["positive"].value("Z1 per km"),
            negative_ohm_per_km=self.parameters["negative"].value("Z2 per km"),
            zero_ohm_per_km=self.parameters["zero"].value("Z0 per km"),
            frequency_hz=_required_float(self.frequency, "frequency"),
        )


class FaultStudyDialog(QDialog):
    def __init__(
        self,
        buses,
        default_base_mva: float = 100.0,
        default_fault_type: FaultType = FaultType.THREE_PHASE,
        default_fault_impedance: complex = 0j,
        default_bus_id=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Short-Circuit Study Setup")
        self.bus = QComboBox()
        for item in buses:
            self.bus.addItem(f"{item.name} · {item.nominal_voltage.value_kv:g} kV", str(item.id))
        self.fault = QComboBox()
        for kind, label in (
            (FaultType.THREE_PHASE, "Three-phase balanced"),
            (FaultType.SINGLE_LINE_TO_GROUND, "Single line-to-ground (A-G)"),
            (FaultType.LINE_TO_LINE, "Line-to-line (B-C)"),
            (FaultType.DOUBLE_LINE_TO_GROUND, "Double line-to-ground (B-C-G)"),
        ):
            self.fault.addItem(label, kind.value)
        fault_index = self.fault.findData(default_fault_type.value)
        if fault_index >= 0:
            self.fault.setCurrentIndex(fault_index)
        bus_index = self.bus.findData(str(default_bus_id)) if default_bus_id else 0
        if bus_index >= 0:
            self.bus.setCurrentIndex(bus_index)
        self.base = QDoubleSpinBox()
        self.base.setRange(0.000001, 1_000_000.0)
        self.base.setDecimals(6)
        self.base.setValue(default_base_mva)
        self.rf = QLineEdit(f"{complex(default_fault_impedance).real:.12g}")
        self.xf = QLineEdit(f"{complex(default_fault_impedance).imag:.12g}")
        form = QFormLayout()
        form.addRow("Faulted bus", self.bus)
        form.addRow("Fault classification", self.fault)
        form.addRow("System base (MVA)", self.base)
        form.addRow("Fault resistance Rf (p.u.)", self.rf)
        form.addRow("Fault reactance Xf (p.u.)", self.xf)
        note = QLabel(
            "Phase convention follows the solver: A-G for SLG and B-C for line-to-line / double-line-ground."
        )
        note.setWordWrap(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def values(self):
        return (
            UUID(self.bus.currentData()),
            FaultType(self.fault.currentData()),
            complex(
                _required_float(self.rf, "fault resistance"),
                _required_float(self.xf, "fault reactance"),
            ),
            self.base.value(),
        )


def _required_float(widget: QLineEdit, label: str) -> float:
    try:
        return float(widget.text())
    except ValueError as exc:
        raise ValueError(f"Enter a valid numeric value for {label}.") from exc


class EquivalentSourceDialog(QDialog):
    """Create an explicit Thevenin sequence source; no impedance is inferred."""

    def __init__(self, buses, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Thevenin Equivalent Source")
        self.resize(560, 410)
        self.name = QLineEdit("Grid Equivalent")
        self.bus = QComboBox()
        for bus in buses:
            self.bus.addItem(f"{bus.name} · {bus.nominal_voltage.value_kv:g} kV", str(bus.id))
        self.base_mva = QLineEdit("100")
        self.frequency = QLineEdit("60")
        self.prefault = ComplexInput("1.0", "0.0")
        self.impedances = {
            "positive": ComplexInput("0.08", "0.24"),
            "negative": ComplexInput("0.11", "0.31"),
            "zero": ComplexInput("0.18", "0.52"),
        }
        form = QFormLayout()
        form.addRow("Identification", self.name)
        form.addRow("Connection bus", self.bus)
        form.addRow("System base (MVA)", self.base_mva)
        form.addRow("Frequency (Hz)", self.frequency)
        form.addRow("Prefault E1 (p.u.)", self.prefault)
        form.addRow("Positive sequence Z1 (p.u.)", self.impedances["positive"])
        form.addRow("Negative sequence Z2 (p.u.)", self.impedances["negative"])
        form.addRow("Zero sequence Z0 (p.u.)", self.impedances["zero"])
        note = QLabel(
            "The three sequence equivalents and prefault positive-sequence voltage "
            "are entered explicitly. No grounding or zero-sequence path is inferred."
        )
        note.setWordWrap(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(note)
        root.addWidget(buttons)

    def specification(self) -> tuple[str, object, float, complex, complex, complex, complex, float]:
        from uuid import UUID

        if not self.name.text().strip() or self.bus.currentIndex() < 0:
            raise ValueError("A source name and connected bus are required.")
        return (
            self.name.text().strip(),
            UUID(self.bus.currentData()),
            _required_float(self.base_mva, "system base MVA"),
            self.prefault.value("prefault E1"),
            self.impedances["positive"].value("Z1"),
            self.impedances["negative"].value("Z2"),
            self.impedances["zero"].value("Z0"),
            _required_float(self.frequency, "frequency"),
        )


class ResolveLineBoundaryDialog(QDialog):
    """Explicit line and remote-grid data entry for a PFA-ES-001 line boundary."""

    def __init__(self, interface, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Resolve Line Boundary — Line + Remote Thevenin Equivalent")
        self.resize(620, 760)
        self.interface = interface
        self.remote_bus = QLineEdit("GRID-REMOTE-220")
        self.line_name = QLineEdit(interface.name.split(" · ", 1)[0])
        self.length = QLineEdit()
        self.frequency = QLineEdit()
        self.line_z = {name: ComplexInput() for name in ("positive", "negative", "zero")}
        self.source_name = QLineEdit("GRID-TH-REMOTE")
        self.source_base = QLineEdit()
        self.prefault = ComplexInput()
        self.source_z = {name: ComplexInput() for name in ("positive", "negative", "zero")}
        self.evidence = QLineEdit()
        form = QFormLayout()
        form.addRow("Remote bus identifier", self.remote_bus)
        form.addRow("Line identifier", self.line_name)
        form.addRow("Line length (km)", self.length)
        form.addRow("Reference frequency (Hz)", self.frequency)
        for sequence, label in (("positive", "Z1"), ("negative", "Z2"), ("zero", "Z0")):
            form.addRow(f"Line {label} (ohm/km)", self.line_z[sequence])
        form.addRow("Remote equivalent identifier", self.source_name)
        form.addRow("Remote equivalent base (MVA)", self.source_base)
        form.addRow("Prefault voltage E1 (p.u.)", self.prefault)
        for sequence, label in (("positive", "Z1"), ("negative", "Z2"), ("zero", "Z0")):
            form.addRow(f"Remote source {label} (p.u.)", self.source_z[sequence])
        form.addRow("Data source / reference", self.evidence)
        note = QLabel(
            "The remote bus uses the connected 220 kV boundary voltage. The line is an explicit "
            "series-only equivalent: shunt capacitance is not inferred. All six line sequence "
            "components and all three remote-source sequence impedances are mandatory. Enter a "
            "datasheet/nameplate/document reference; values are recorded as USER_CONFIRMED, not "
            "independently SOURCE_VERIFIED."
        )
        note.setWordWrap(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(note)
        root.addWidget(buttons)

    def accept(self) -> None:
        try:
            self.specification()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Invalid Line Boundary Data", str(exc))
            return
        super().accept()

    def specification(self):
        from power_fault_analyzer.application.use_cases.resolve_substation_boundary import (
            ResolveLineBoundaryInput,
        )

        if (
            not self.remote_bus.text().strip()
            or not self.line_name.text().strip()
            or not self.source_name.text().strip()
        ):
            raise ValueError("Remote bus, line and source identifiers are required.")
        line = {
            key: value.value(f"line {key} impedance per km") for key, value in self.line_z.items()
        }
        source = {
            key: value.value(f"remote source {key} impedance")
            for key, value in self.source_z.items()
        }
        prefault = self.prefault.value("prefault voltage E1")
        return ResolveLineBoundaryInput(
            interface_id=self.interface.id,
            remote_bus_name=self.remote_bus.text().strip(),
            line_name=self.line_name.text().strip(),
            length_km=_required_float(self.length, "line length"),
            frequency_hz=_required_float(self.frequency, "frequency"),
            positive_r_ohm_per_km=line["positive"].real,
            positive_x_ohm_per_km=line["positive"].imag,
            negative_r_ohm_per_km=line["negative"].real,
            negative_x_ohm_per_km=line["negative"].imag,
            zero_r_ohm_per_km=line["zero"].real,
            zero_x_ohm_per_km=line["zero"].imag,
            source_name=self.source_name.text().strip(),
            source_base_mva=_required_float(self.source_base, "remote equivalent base MVA"),
            source_prefault_voltage_pu=prefault,
            source_positive_r_pu=source["positive"].real,
            source_positive_x_pu=source["positive"].imag,
            source_negative_r_pu=source["negative"].real,
            source_negative_x_pu=source["negative"].imag,
            source_zero_r_pu=source["zero"].real,
            source_zero_x_pu=source["zero"].imag,
            evidence_reference=self.evidence.text().strip(),
        )


class ResolveTransformerBoundaryDialog(QDialog):
    """Nameplate, vector-group, sequence and neutral data entry for a transformer bay."""

    def __init__(self, interface, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Resolve Transformer Boundary — Two-Winding Model")
        self.resize(640, 900)
        self.interface = interface
        self.low_bus = QLineEdit("BUS-LV-01")
        self.transformer_name = QLineEdit(interface.name.split(" · ", 1)[0])
        self.rated_power = QLineEdit()
        self.impedance_base = QLineEdit()
        self.lv_voltage = QLineEdit()
        self.frequency = QLineEdit()
        self.clock = QLineEdit()
        self.hv_connection = QComboBox()
        self.lv_connection = QComboBox()
        for combo in (self.hv_connection, self.lv_connection):
            combo.addItem("Star (Y)", WindingConnection.STAR.value)
            combo.addItem("Delta (D)", WindingConnection.DELTA.value)
            combo.addItem("Zigzag (Z)", WindingConnection.ZIGZAG.value)
            combo.setCurrentIndex(-1)
        self.hv_grounding_mode = QComboBox()
        self.lv_grounding_mode = QComboBox()
        for combo in (self.hv_grounding_mode, self.lv_grounding_mode):
            combo.addItem("Ungrounded", GroundingMode.UNGROUNDED.value)
            combo.addItem("Solidly grounded", GroundingMode.SOLID.value)
            combo.addItem("Impedance grounded", GroundingMode.IMPEDANCE.value)
            combo.setCurrentIndex(-1)
        self.hv_neutral = ComplexInput()
        self.lv_neutral = ComplexInput()
        self.hv_connection.currentIndexChanged.connect(self._update_grounding_controls)
        self.lv_connection.currentIndexChanged.connect(self._update_grounding_controls)
        self.hv_grounding_mode.currentIndexChanged.connect(self._update_grounding_controls)
        self.lv_grounding_mode.currentIndexChanged.connect(self._update_grounding_controls)
        self.sequence = {name: ComplexInput() for name in ("positive", "negative", "zero")}
        self.evidence = QLineEdit()
        form = QFormLayout()
        form.addRow("Low-voltage bus identifier", self.low_bus)
        form.addRow("Transformer identifier", self.transformer_name)
        form.addRow("Rated power (MVA)", self.rated_power)
        form.addRow("Impedance data base (MVA)", self.impedance_base)
        form.addRow("LV rated voltage L-L (kV)", self.lv_voltage)
        form.addRow("Frequency (Hz)", self.frequency)
        form.addRow("HV winding connection", self.hv_connection)
        form.addRow("LV winding connection", self.lv_connection)
        form.addRow("Vector-group clock number (0–11)", self.clock)
        form.addRow("HV neutral grounding", self.hv_grounding_mode)
        form.addRow("HV neutral impedance R+jX (ohm)", self.hv_neutral)
        form.addRow("LV neutral grounding", self.lv_grounding_mode)
        form.addRow("LV neutral impedance R+jX (ohm)", self.lv_neutral)
        for sequence, label in (("positive", "Z1"), ("negative", "Z2"), ("zero", "Z0")):
            form.addRow(f"Transformer {label} (p.u. on declared base)", self.sequence[sequence])
        form.addRow("Data source / reference", self.evidence)
        note = QLabel(
            "HV voltage is taken from the existing 220 kV bay terminal; the LV voltage, rated "
            "power, impedance base, vector group, sequence impedances and neutral grounding "
            "must be entered explicitly. Delta windings do not have accessible neutrals. "
            "Values are recorded as USER_CONFIRMED with the supplied reference."
        )
        note.setWordWrap(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(note)
        root.addWidget(buttons)
        self._update_grounding_controls()

    def _update_grounding_controls(self, *_args) -> None:
        for connection, mode, impedance in (
            (self.hv_connection, self.hv_grounding_mode, self.hv_neutral),
            (self.lv_connection, self.lv_grounding_mode, self.lv_neutral),
        ):
            is_delta = connection.currentData() == WindingConnection.DELTA.value
            mode.setEnabled(not is_delta)
            impedance.setEnabled(
                not is_delta and mode.currentData() == GroundingMode.IMPEDANCE.value
            )
            if is_delta:
                mode.setCurrentIndex(-1)

    def _grounding(
        self, connection: QComboBox, mode: QComboBox, impedance: ComplexInput, side: str
    ):
        connection_value = WindingConnection(connection.currentData())
        if connection_value is WindingConnection.DELTA:
            return None
        if mode.currentData() is None:
            raise ValueError(f"Select an explicit {side} neutral grounding mode.")
        grounding_mode = GroundingMode(mode.currentData())
        if grounding_mode is GroundingMode.UNGROUNDED:
            return NeutralGrounding.ungrounded()
        if grounding_mode is GroundingMode.SOLID:
            return NeutralGrounding.solid()
        value = impedance.value(f"{side} neutral impedance")
        return NeutralGrounding.through_impedance(value.real, value.imag)

    def accept(self) -> None:
        try:
            self.specification()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Invalid Transformer Boundary Data", str(exc))
            return
        super().accept()

    def specification(self):
        from power_fault_analyzer.application.use_cases.resolve_substation_boundary import (
            ResolveTransformerBoundaryInput,
        )

        if not self.low_bus.text().strip() or not self.transformer_name.text().strip():
            raise ValueError("Low-voltage bus and transformer identifiers are required.")
        if self.hv_connection.currentData() is None or self.lv_connection.currentData() is None:
            raise ValueError("Select both HV and LV winding connections.")
        clock_number = _required_float(self.clock, "vector-group clock number")
        if not clock_number.is_integer():
            raise ValueError("Vector-group clock number must be an integer from 0 to 11.")
        clock_value = int(clock_number)
        return ResolveTransformerBoundaryInput(
            interface_id=self.interface.id,
            low_bus_name=self.low_bus.text().strip(),
            transformer_name=self.transformer_name.text().strip(),
            rated_power_mva=_required_float(self.rated_power, "transformer rated power"),
            impedance_base_mva=_required_float(self.impedance_base, "transformer impedance base"),
            low_rated_voltage_kv=_required_float(self.lv_voltage, "LV rated voltage"),
            frequency_hz=_required_float(self.frequency, "frequency"),
            hv_connection=WindingConnection(self.hv_connection.currentData()),
            lv_connection=WindingConnection(self.lv_connection.currentData()),
            vector_group_clock=clock_value,
            positive_r_pu=self.sequence["positive"].value("Z1").real,
            positive_x_pu=self.sequence["positive"].value("Z1").imag,
            negative_r_pu=self.sequence["negative"].value("Z2").real,
            negative_x_pu=self.sequence["negative"].value("Z2").imag,
            zero_r_pu=self.sequence["zero"].value("Z0").real,
            zero_x_pu=self.sequence["zero"].value("Z0").imag,
            hv_grounding=self._grounding(
                self.hv_connection, self.hv_grounding_mode, self.hv_neutral, "HV"
            ),
            lv_grounding=self._grounding(
                self.lv_connection, self.lv_grounding_mode, self.lv_neutral, "LV"
            ),
            evidence_reference=self.evidence.text().strip(),
        )
