# PFA Code & Automation Studio 001

This patch adds an embedded Python authoring tab to the Engineering Workbench.
It uses the existing `power_fault_analyzer.scripting.ScriptProject` API and
hands the resulting `NetworkWorkspace` to the existing desktop network canvas.

## Apply

Extract the ZIP at the repository root, preserving the `src/` directory tree.

## Use

1. Start the desktop application.
2. Open **Code & Automation** in the central workspace tabs.
3. Edit the starter Python script.
4. Select **Validate script** for structural validation, or **Build diagram**
   to replace the active network workspace and render it in **Network Design**.
5. Save the project using the normal Workbench Save command.

A script must create a `ScriptProject` named `project`. It may set `workspace`
by calling `project.render()`. The API currently supports AC buses and explicit
three-sequence Thevenin-equivalent sources as documented in
`docs/engineering/CODE_AUTOMATION_API.md`.

## Security and limitations

Scripts execute in-process with the current user's permissions. This is not a
sandbox. Only run scripts you trust. Long-running scripts can block the GUI;
keep scripts short. This increment does not provide a general-purpose IDE,
syntax highlighting, LSP/autocomplete, asynchronous execution, arbitrary
component coverage, or a separate scripting permission model.

The current API's `assert_valid()` performs structural validation. It does not
certify engineering data, prove IEC compliance, or imply that a numerical study
is ready to run.

## Verification

The source package was checked with `compileall` and the available regression
suite: 577 passed, 4 skipped. This build environment did not have PySide6, so
Qt runtime/visual verification remains required on the target Windows setup.
