"""Windows Qt smoke test for the PFA-DESIGN-003 canonical engineering canvas."""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from examples.canonical_model_scenarios import (
    build_double_bus_substation,
    build_multibus_network,
    build_single_bus_substation,
)
from power_fault_analyzer.diagram.model_projection import project_network_to_diagram
from power_fault_analyzer.interfaces.desktop.workbench.network_canvas import NetworkCanvasView

OUTPUT = ROOT / "outputs" / "pfa_design_003_6_qt"
OUTPUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    cases = (
        ("01_single_bus", build_single_bus_substation),
        ("02_double_bus", build_double_bus_substation),
        ("03_multibus", build_multibus_network),
    )
    for name, builder in cases:
        canvas = NetworkCanvasView()
        canvas.resize(1440, 1000)
        workspace = builder()
        document = project_network_to_diagram(workspace)
        canvas.set_workspace(workspace)
        canvas.set_grid_visible(False)
        if len(canvas._junction_items) != len(workspace.network.connections):
            raise RuntimeError(
                f"{name}: Qt junction marker count does not match canonical terminal connections."
            )

        # The interactive canvas must render the exact canonical route. In the
        # automatic layout, tap and terminal share one normal lane, so this is
        # exactly one straight segment (moveTo + lineTo), never three collinear
        # path elements retained from redundant construction waypoints.
        canonical_conductors = {
            str(item.terminal_id): item for item in document.conductors
        }
        for terminal_id, link in canvas._conductor_items.items():
            path = link.path()
            expected = canonical_conductors[terminal_id].points
            if path.elementCount() != len(expected):
                raise RuntimeError(
                    f"{name}: Qt path {terminal_id} differs from canonical route "
                    f"(Qt elements={path.elementCount()}, canonical points={len(expected)})."
                )
            actual = [path.elementAt(index) for index in range(path.elementCount())]
            if any(abs(item.x - point.x) > 0.5 or abs(item.y - point.y) > 0.5
                   for item, point in zip(actual, expected, strict=True)):
                raise RuntimeError(f"{name}: Qt route {terminal_id} does not match canonical SVG/PDF geometry.")
            if path.elementCount() != 2:
                raise RuntimeError(
                    f"{name}: default route {terminal_id} is not a single straight segment "
                    f"(elements={path.elementCount()})."
                )
            start, end = path.elementAt(0), path.elementAt(path.elementCount() - 1)
            bus_id = canvas._terminal_route_specs[terminal_id][0]
            bus = next(item for item in document.buses if str(item.bus_id) == str(bus_id))
            if abs(bus.orientation_deg % 180.0) < 1e-6:
                if abs(start.x - end.x) > 0.5:
                    raise RuntimeError(f"{name}: default route {terminal_id} is not perpendicular to its horizontal busbar.")
            elif abs(start.y - end.y) > 0.5:
                raise RuntimeError(f"{name}: default route {terminal_id} is not perpendicular to its vertical busbar.")

        # Each canonical terminal must own a distinct tap on its bus.  Both
        # ends of every terminal drop must meet a horizontal bus/pin normally.
        bus_by_id = {str(item.bus_id): item for item in document.buses}
        taps_by_bus = {}
        for conductor in document.conductors:
            taps_by_bus.setdefault(str(conductor.bus_id), []).append(conductor.points[0])
            if len(conductor.points) >= 2:
                first, second = conductor.points[:2]
                last, terminal = conductor.points[-2:]
                bus = bus_by_id[str(conductor.bus_id)]
                if (
                    abs(bus.orientation_deg % 180.0) < 1e-6
                    and (abs(first.x - second.x) > 0.5 or abs(last.x - terminal.x) > 0.5)
                ):
                        raise RuntimeError(
                            f"{name}: terminal {conductor.terminal_id} is not routed perpendicular to its busbar."
                        )
        for bus_id, taps in taps_by_bus.items():
            unique = {(round(point.x, 3), round(point.y, 3)) for point in taps}
            if len(unique) != len(taps):
                raise RuntimeError(f"{name}: duplicate canonical bay taps on bus {bus_id}.")

        # Move one bus by one grid interval and verify the reserved tap positions
        # remain distinct and follow the moved bar without snapping to one point.
        terminal_id, route_spec = next(iter(canvas._terminal_route_specs.items()))
        bus_id = route_spec[0]
        bus_item = canvas._bus_items[str(bus_id)]
        original_bus_pos = QPointF(bus_item.pos())
        original_marker_pos = QPointF(canvas._junction_items[terminal_id].pos())
        marker_positions_before = {
            key: QPointF(item.pos()) for key, item in canvas._junction_items.items()
            if canvas._terminal_route_specs[key][0] == bus_id
        }
        bus_item.setPos(original_bus_pos + QPointF(20.0, 20.0))
        app.processEvents()
        marker_positions_after = {
            key: QPointF(canvas._junction_items[key].pos()) for key in marker_positions_before
        }
        moved_marker_pos = marker_positions_after[terminal_id]
        if (abs((moved_marker_pos.x() - original_marker_pos.x()) - 20.0) > 0.5
                or abs((moved_marker_pos.y() - original_marker_pos.y()) - 20.0) > 0.5):
            raise RuntimeError(f"{name}: junction marker did not follow the moved bus tap.")
        for key in marker_positions_before:
            path = canvas._conductor_items[key].path()
            elements = [path.elementAt(index) for index in range(path.elementCount())]
            points = [(item.x, item.y) for item in elements]
            if any(abs(x1 - x2) > 0.5 and abs(y1 - y2) > 0.5
                   for (x1, y1), (x2, y2) in itertools.pairwise(points)):
                raise RuntimeError(f"{name}: dragged conductor {key} is not orthogonal.")
            if len(points) >= 2:
                bus_id = canvas._terminal_route_specs[key][0]
                bus = next(item for item in document.buses if str(item.bus_id) == str(bus_id))
                if abs(bus.orientation_deg % 180.0) < 1e-6:
                    if (abs(points[0][0] - points[1][0]) > 0.5
                            or abs(points[-1][0] - points[-2][0]) > 0.5):
                        raise RuntimeError(f"{name}: dragged conductor {key} lost perpendicular bus/pin approach.")
                elif (abs(points[0][1] - points[1][1]) > 0.5
                      or abs(points[-1][1] - points[-2][1]) > 0.5):
                    raise RuntimeError(f"{name}: dragged conductor {key} lost perpendicular bus/pin approach.")
            route_length = sum(abs(x2 - x1) + abs(y2 - y1)
                               for (x1, y1), (x2, y2) in zip(points, points[1:]))
            direct_length = abs(points[-1][0] - points[0][0]) + abs(points[-1][1] - points[0][1])
            if abs(route_length - direct_length) > 0.5:
                raise RuntimeError(
                    f"{name}: dragged conductor {key} does not attain the Manhattan lower bound. "
                    f"route={route_length:.3f}, lower_bound={direct_length:.3f}."
                )
        after_unique = {
            (round(point.x(), 3), round(point.y(), 3))
            for point in marker_positions_after.values()
        }
        if len(after_unique) != len(marker_positions_after):
            raise RuntimeError(f"{name}: bus drag collapsed distinct bay taps.")
        bus_item.setPos(original_bus_pos)
        app.processEvents()
        if (canvas._junction_items[terminal_id].pos() - original_marker_pos).manhattanLength() > 0.5:
            raise RuntimeError(f"{name}: junction marker did not restore with its bus.")
        canvas.show()
        app.processEvents()
        bounds = canvas.scene().itemsBoundingRect().adjusted(-80, -80, 80, 80)
        canvas.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
        app.processEvents()
        target = OUTPUT / f"{name}.png"
        if not canvas.viewport().grab().save(str(target), "PNG"):
            raise RuntimeError(f"Could not save Qt viewport screenshot: {target}")
        print(
            f"PASS {name}: {target} "
            f"(junctions={len(canvas._junction_items)}, buses={len(canvas._bus_items)}, "
            f"equipment={len(canvas._source_items) + len(canvas._equipment_items) + len(canvas._branch_items)}, "
            "straight-default-routes=PASS, shortest-orthogonal-drag=PASS, "
            "perpendicular-bays=PASS, unique-taps=PASS, tap-drag=PASS)"
        )
        canvas.prepare_for_shutdown()
        canvas.close()
        app.processEvents()
    print("PFA-DESIGN-003.6 canonical/Qt route parity and shortest-route Qt smoke test passed for all three canonical Network models.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
