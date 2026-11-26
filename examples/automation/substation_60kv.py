"""Build a 60 kV network using the public PFA scripting API.

Run from the repository root with:
    .venv\\Scripts\\python.exe examples\\automation\\substation_60kv.py
"""

from power_fault_analyzer.scripting import ScriptProject

project = ScriptProject("Substation 60 kV")
bus = project.add_bus("BUS-101", voltage_kv=60.0, x=520.0, y=320.0)
project.add_equivalent_source(
    "GRID-EQUIVALENT",
    bus,
    base_mva=100.0,
    z1_pu=0.08 + 0.24j,
    z2_pu=0.11 + 0.31j,
    z0_pu=0.18 + 0.52j,
    prefault_voltage_pu=1.0 + 0.0j,
    frequency_hz=60.0,
)

project.assert_valid(for_calculation=True)
workspace = project.render()

print(f"Project: {project.name}")
print(f"Buses: {len(workspace.network.buses)}")
print(f"Equipment: {len(workspace.network.equipment)}")
print(f"Explicit terminal connections: {len(workspace.network.connections)}")
print("Workspace built successfully; pass `workspace` to the desktop renderer.")
