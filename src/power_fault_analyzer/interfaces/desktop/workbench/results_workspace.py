"""Scientific results presentation for phase quantities, sequences and phasors."""

from __future__ import annotations

import cmath

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.short_circuit_result import ShortCircuitResult


class PhasorDiagram(QWidget):
    """A phase-vector plot with an engineering reference axis and common scale."""

    _PHASES = (("A", QColor("#2563EB")), ("B", QColor("#DC2626")), ("C", QColor("#059669")))

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._values: tuple[complex, ...] = ()
        self._title = "Phase current phasors"
        self.setMinimumSize(360, 300)

    def set_values(self, values: tuple[complex, ...], title: str) -> None:
        self._values = values
        self._title = title
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))
        painter.setPen(QPen(QColor("#0F172A")))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        painter.drawText(16, 22, self._title)
        if len(self._values) != 3:
            painter.setPen(QColor("#64748B"))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "No numerical result available"
            )
            return

        center = QPointF(self.width() * 0.48, self.height() * 0.56)
        radius = min(self.width() * 0.34, self.height() * 0.36)
        maximum = max(abs(value) for value in self._values)
        if maximum <= 1e-15:
            maximum = 1.0
        painter.setPen(QPen(QColor("#CBD5E1"), 1.0, Qt.PenStyle.DashLine))
        for fraction in (0.25, 0.5, 0.75, 1.0):
            painter.drawEllipse(center, radius * fraction, radius * fraction)
        painter.setPen(QPen(QColor("#94A3B8"), 1.0))
        painter.drawLine(
            QPointF(center.x() - radius, center.y()), QPointF(center.x() + radius, center.y())
        )
        painter.drawLine(
            QPointF(center.x(), center.y() - radius), QPointF(center.x(), center.y() + radius)
        )
        painter.setPen(QColor("#64748B"))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(int(center.x() + radius - 12), int(center.y() - 7), "Re")
        painter.drawText(int(center.x() + 7), int(center.y() - radius + 10), "Im")

        for index, (label, color) in enumerate(self._PHASES):
            value = self._values[index]
            x = center.x() + value.real / maximum * radius * 0.88
            y = center.y() - value.imag / maximum * radius * 0.88
            endpoint = QPointF(x, y)
            painter.setPen(QPen(color, 2.4))
            painter.drawLine(center, endpoint)
            direction = endpoint - center
            length = max(1.0, (direction.x() ** 2 + direction.y() ** 2) ** 0.5)
            ux, uy = direction.x() / length, direction.y() / length
            normal = QPointF(-uy, ux)
            tip = endpoint
            base = endpoint - QPointF(ux * 10, uy * 10)
            head = QPolygonF((tip, base + normal * 4.5, base - normal * 4.5))
            painter.setBrush(color)
            painter.drawPolygon(head)
            painter.setPen(color)
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.drawText(QPointF(x + 7, y - 7), label)
        painter.end()


class ResultsWorkspace(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.summary = QLabel("No study has been executed.")
        self.summary.setObjectName("resultsSummary")
        layout.addWidget(self.summary)

        split = QHBoxLayout()
        self.phase_table = QTableWidget(0, 8)
        self.phase_table.setHorizontalHeaderLabels(
            [
                "Phase",
                "|I| p.u.",
                "∠I °",
                "I kA",
                "|V| p.u.",
                "∠V °",
                "V kV L-N",
                "I (rectangular p.u.)",
            ]
        )
        self.phase_table.setSortingEnabled(True)
        self.phase_table.horizontalHeader().setStretchLastSection(True)
        split.addWidget(self.phase_table, 3)

        self.phasor_plot = PhasorDiagram()
        split.addWidget(self.phasor_plot, 2)
        layout.addLayout(split, 3)

        self.sequence_table = QTableWidget(0, 6)
        self.sequence_table.setHorizontalHeaderLabels(
            ["Sequence", "|I| p.u.", "∠I °", "|V| p.u.", "∠V °", "Zth p.u."]
        )
        self.sequence_table.setSortingEnabled(True)
        self.sequence_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.sequence_table, 2)
        self.provenance = QLabel("Calculation provenance will appear here.")
        self.provenance.setWordWrap(True)
        self.provenance.setObjectName("provenancePanel")
        layout.addWidget(self.provenance)

    def clear(self) -> None:
        self.summary.setText("No study has been executed.")
        self.phase_table.setRowCount(0)
        self.sequence_table.setRowCount(0)
        self.phasor_plot.set_values((), "Phase current phasors")
        self.provenance.setText("Calculation provenance will appear here.")

    def display(self, result: ShortCircuitResult, *, project_name: str, bus_name: str) -> None:
        self.phase_table.setSortingEnabled(False)
        self.phase_table.setRowCount(3)
        for index, phase in enumerate(("A", "B", "C")):
            current = result.phase_currents_pu[index]
            voltage = result.phase_voltages_pu[index]
            values = (
                phase,
                f"{abs(current):.10f}",
                f"{math_degrees(cmath.phase(current)):.8f}",
                f"{abs(result.phase_currents_ka[index]):.9f}",
                f"{abs(voltage):.10f}",
                f"{math_degrees(cmath.phase(voltage)):.8f}",
                f"{abs(result.phase_voltages_kv[index]):.9f}",
                f"{current.real:.10f} {'+' if current.imag >= 0 else '−'} j{abs(current.imag):.10f}",
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                else:
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self.phase_table.setItem(index, column, cell)
        self.phase_table.setSortingEnabled(True)

        sequence_values = {
            sequence.value: (
                result.sequence_currents_pu.get(sequence, 0.0j),
                result.sequence_fault_voltages_pu.get(sequence, 0.0j),
                result.driving_point_impedances_pu.get(sequence),
            )
            for sequence in (SequenceType.ZERO, SequenceType.POSITIVE, SequenceType.NEGATIVE)
        }
        self.sequence_table.setSortingEnabled(False)
        self.sequence_table.setRowCount(3)
        for row, sequence in enumerate(("zero", "positive", "negative")):
            current, voltage, impedance = sequence_values[sequence]
            values = (
                sequence,
                f"{abs(current):.10f}",
                f"{math_degrees(cmath.phase(current)):.8f}" if abs(current) > 1e-15 else "—",
                f"{abs(voltage):.10f}",
                f"{math_degrees(cmath.phase(voltage)):.8f}" if abs(voltage) > 1e-15 else "—",
                f"{impedance.real:.8f} + j{impedance.imag:.8f}"
                if impedance is not None
                else "Not calculated",
            )
            for column, value in enumerate(values):
                self.sequence_table.setItem(row, column, QTableWidgetItem(value))
        self.sequence_table.setSortingEnabled(True)
        self.phasor_plot.set_values(tuple(result.phase_currents_pu), "Phase current phasors")
        self.summary.setText(
            f"{project_name}  |  {result.fault_type.value.replace('_', ' ')}  |  "
            f"Bus {bus_name}  |  Base {result.base_power_mva:g} MVA / "
            f"{result.base_voltage_kv:g} kV  |  Maximum phase current "
            f"{max(abs(value) for value in result.phase_currents_ka):.6f} kA"
        )
        self.provenance.setText(
            "Calculation provenance\n"
            "Solver: ShortCircuitSolver (production numerical kernel)\n"
            f"Fault impedance: {result.fault_impedance_pu.real:g} + j{result.fault_impedance_pu.imag:g} p.u.\n"
            "Study type: general symmetrical-components bus-fault analysis; IEC 60909 corrections are not applied."
        )


def math_degrees(value: float) -> float:
    return value * 180.0 / 3.141592653589793
