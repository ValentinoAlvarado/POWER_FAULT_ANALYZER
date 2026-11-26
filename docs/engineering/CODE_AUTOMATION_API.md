# Python network-authoring API (initial release)

POWER_FAULT_ANALYZER exposes `power_fault_analyzer.scripting.ScriptProject` for
programmatic construction of the same domain `Network` and `NetworkWorkspace`
objects used by the desktop workbench.

```python
from power_fault_analyzer.scripting import ScriptProject

project = ScriptProject("Substation 60 kV")
bus = project.add_bus("BUS-101", voltage_kv=60.0, x=520, y=320)
project.add_equivalent_source(
    "GRID-EQUIVALENT", bus,
    base_mva=100.0,
    z1_pu=0.08 + 0.24j,
    z2_pu=0.11 + 0.31j,
    z0_pu=0.18 + 0.52j,
)
project.assert_valid(for_calculation=True)
workspace = project.render()
```

`add_equivalent_source` requires independent positive-, negative- and zero-
sequence impedances. It does not infer sequence values, source strength, or
connectivity. Terminal-to-bus connectivity is created explicitly through the
domain aggregate. Coordinates are presentation metadata and do not affect
network topology or electrical calculations.

Run the included example from the repository root:

```powershell
.\.venv\Scripts\python.exe examples\automation\substation_60kv.py
```

This initial API covers buses and explicit Thevenin-equivalent sources. It is
not yet a general-purpose scripting IDE, does not execute arbitrary scripts
inside the desktop workbench, and does not claim to export or render a diagram
from a headless Python process. Those require the next UI/application-service
integration increment.
