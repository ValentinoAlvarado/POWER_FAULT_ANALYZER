"""Technical PDF report export. reportlab is an optional reporting dependency."""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from power_fault_analyzer.results.result_models import EngineeringStudyReport


class PDFReportExporter:
    """Generate a paginated technical report from normalized engineering results."""

    def export(self, report: EngineeringStudyReport, path: str | Path) -> Path:
        try:
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_LEFT
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except ImportError as exc:
            raise RuntimeError(
                'PDF export requires the optional dependency. Install with: pip install -e ".[reports]"'
            ) from exc

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        document = SimpleDocTemplate(
            str(target),
            pagesize=landscape(A4),
            rightMargin=13 * mm,
            leftMargin=13 * mm,
            topMargin=13 * mm,
            bottomMargin=13 * mm,
            title=report.metadata.study_name,
            author="POWER_FAULT_ANALYZER",
        )
        styles = getSampleStyleSheet()
        styles.add(
            ParagraphStyle(
                name="SmallCell",
                parent=styles["BodyText"],
                fontSize=7,
                leading=8,
                alignment=TA_LEFT,
            )
        )
        styles.add(
            ParagraphStyle(
                name="SectionTitle", parent=styles["Heading2"], spaceBefore=8, spaceAfter=5
            )
        )
        story = [
            Paragraph("POWER_FAULT_ANALYZER", styles["Title"]),
            Paragraph(escape(report.metadata.study_name), styles["Heading1"]),
            Paragraph(
                f"Project: {escape(report.metadata.project_name)} &nbsp;&nbsp; "
                f"Network: {escape(report.metadata.network_name)}",
                styles["BodyText"],
            ),
            Paragraph(
                f"Study ID: {escape(report.metadata.study_id)} &nbsp;&nbsp; "
                f"Generated (UTC): {escape(report.metadata.generated_at_utc)}",
                styles["BodyText"],
            ),
            Paragraph(
                f"Standard edition: {escape(report.metadata.standard_edition or 'Not specified')}",
                styles["BodyText"],
            ),
            Spacer(1, 7 * mm),
        ]

        def add_table(
            title: str, headers: list[str], rows: list[list[object]], widths=None
        ) -> None:
            story.append(Paragraph(escape(title), styles["SectionTitle"]))
            if not rows:
                rows = [["No data supplied for this section."] + [""] * (len(headers) - 1)]
            data = [
                [Paragraph(f"<b>{escape(str(item))}</b>", styles["SmallCell"]) for item in headers]
            ]
            data.extend(
                [
                    [
                        Paragraph(escape("" if value is None else str(value)), styles["SmallCell"])
                        for value in row
                    ]
                    for row in rows
                ]
            )
            table = Table(data, repeatRows=1, colWidths=widths, hAlign="LEFT")
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#203864")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#A6A6A6")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#F2F6FC")],
                        ),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            story.append(table)
            story.append(Spacer(1, 3 * mm))

        add_table(
            "Fault summary",
            [
                "Location",
                "Fault type",
                "Case",
                "Max I phase (kA)",
                "Base U (kV L-L)",
                "c",
                "f (Hz)",
                "t_k (s)",
            ],
            [
                [
                    f.location_name,
                    f.fault_type,
                    f.current_case or "-",
                    f"{f.maximum_phase_current_ka:.6g}",
                    f"{f.base_voltage_kv:.6g}",
                    "" if f.voltage_factor is None else f"{f.voltage_factor:.5g}",
                    "" if f.frequency_hz is None else f"{f.frequency_hz:.5g}",
                    "" if f.fault_duration_s is None else f"{f.fault_duration_s:.5g}",
                ]
                for f in report.faults
            ],
        )
        phase_rows = []
        for fault in report.faults:
            for phase in fault.phase_quantities:
                phase_rows.append(
                    [
                        fault.location_name,
                        phase.phase,
                        f"{phase.current_ka.magnitude:.6g}",
                        f"{phase.current_ka.angle_degrees:.5g}",
                        f"{phase.voltage_kv.magnitude:.6g}",
                        f"{phase.voltage_kv.angle_degrees:.5g}",
                    ]
                )
        add_table(
            "Phase quantities",
            ["Fault location", "Phase", "I (kA)", "I angle (deg)", "V (kV L-N)", "V angle (deg)"],
            phase_rows,
        )

        sequence_rows = []
        for fault in report.faults:
            for sequence in fault.sequence_quantities:
                sequence_rows.append(
                    [
                        fault.location_name,
                        sequence.sequence,
                        ""
                        if sequence.current_pu is None
                        else f"{sequence.current_pu.magnitude:.6g}",
                        ""
                        if sequence.current_pu is None
                        else f"{sequence.current_pu.angle_degrees:.5g}",
                        ""
                        if sequence.voltage_pu is None
                        else f"{sequence.voltage_pu.magnitude:.6g}",
                        ""
                        if sequence.driving_point_impedance_pu is None
                        else f"{sequence.driving_point_impedance_pu.magnitude:.6g}",
                    ]
                )
        add_table(
            "Sequence quantities",
            ["Fault location", "Sequence", "I (pu)", "I angle (deg)", "V (pu)", "Zth (pu)"],
            sequence_rows,
        )

        quantity_rows = []
        for fault in report.faults:
            for quantity in fault.iec_quantities:
                quantity_rows.append(
                    [
                        fault.location_name,
                        quantity.name,
                        "" if quantity.value is None else f"{quantity.value:.7g}",
                        quantity.unit,
                        quantity.status.value,
                        quantity.classification,
                        quantity.method_reference or quantity.reason or "",
                    ]
                )
        add_table(
            "IEC and supplementary quantities",
            ["Fault location", "Quantity", "Value", "Unit", "Status", "Class", "Method / reason"],
            quantity_rows,
        )

        source_rows = [
            [
                item.fault_id,
                item.source_name,
                item.source_family,
                item.domain,
                item.component,
                f"{item.current_ka.magnitude:.6g}",
                f"{item.current_ka.angle_degrees:.5g}",
            ]
            for item in report.source_contributions
        ]
        add_table(
            "Source contributions",
            ["Fault ID", "Source", "Family", "Domain", "Component", "I (kA)", "Angle (deg)"],
            source_rows,
        )

        source_balance_rows = [
            [item.fault_id, item.domain, item.component, f"{item.residual_ka:.6g}", item.method_id]
            for item in report.source_balance_residuals
        ]
        add_table(
            "Source contribution balance residuals",
            ["Fault ID", "Domain", "Component", "Residual (kA)", "Method"],
            source_balance_rows,
        )

        branch_rows = [
            [
                item.branch_name,
                item.equipment_type,
                item.terminal,
                item.bus_name,
                item.phase,
                f"{item.current_ka.magnitude:.6g}",
                f"{item.current_ka.angle_degrees:.5g}",
                item.direction_convention,
            ]
            for item in report.branch_currents
        ]
        add_table(
            "Branch terminal currents",
            ["Branch", "Type", "Terminal", "Bus", "Phase", "I (kA)", "Angle (deg)", "Direction"],
            branch_rows,
        )

        correction_rows = [
            [fault.location_name, factor.name, f"{factor.value:.8g}", factor.provenance]
            for fault in report.faults
            for factor in fault.correction_factors
        ]
        add_table(
            "Applied correction factors",
            ["Fault location", "Factor", "Value", "Provenance"],
            correction_rows,
        )

        diagnostic_rows = [
            [item.severity, item.code, item.message, item.entity_id or ""]
            for item in report.diagnostics
        ]
        add_table("Diagnostics", ["Severity", "Code", "Message", "Entity ID"], diagnostic_rows)

        if report.assumptions:
            story.append(Paragraph("Assumptions", styles["SectionTitle"]))
            story.extend(
                Paragraph(f"- {escape(item)}", styles["BodyText"]) for item in report.assumptions
            )
        if report.limitations:
            story.append(Paragraph("Limitations", styles["SectionTitle"]))
            story.extend(
                Paragraph(f"- {escape(item)}", styles["BodyText"]) for item in report.limitations
            )
        document.build(story)
        return target
