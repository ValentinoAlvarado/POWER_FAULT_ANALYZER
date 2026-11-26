# PFA-WORKBENCH-004.2.3.1 — Qt Offscreen Teardown

The property editor acceptance harness creates an in-memory Workbench and marks
it dirty through real commands. Closing it previously invoked the unsaved
project modal prompt, which cannot be answered under Qt offscreen. The harness
now clears its synthetic dirty flag before close, processes events and asserts
that the window actually closes. Production close behavior is unchanged.
