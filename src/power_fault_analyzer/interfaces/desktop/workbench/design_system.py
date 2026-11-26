"""Centralized visual tokens and Qt stylesheet for the PFA engineering workbench.

The application shell uses a dark technical theme while the SLD remains a neutral
engineering-paper surface. This separation preserves drawing contrast until every
electrical graphics primitive has a theme-aware renderer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkbenchPalette:
    """Semantic colors shared by widgets, icons and the engineering canvas."""

    key: str
    window: str
    panel: str
    panel_elevated: str
    canvas: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_pressed: str
    selection: str
    selection_text: str
    input: str
    input_border: str
    hover: str
    disabled: str
    success: str
    warning: str
    error: str
    canvas_grid_minor: str
    canvas_grid_major: str
    icon: str


DARK_PALETTE = WorkbenchPalette(
    key="dark",
    window="#151C25",
    panel="#1E2936",
    panel_elevated="#263442",
    canvas="#F4F7FA",
    border="#354556",
    border_strong="#4A5D70",
    text="#E5EDF4",
    text_muted="#A5B4C3",
    accent="#35A7C7",
    accent_hover="#4BBAD8",
    accent_pressed="#247F9A",
    selection="#244B60",
    selection_text="#F5FAFC",
    input="#111B26",
    input_border="#485B6F",
    hover="#304254",
    disabled="#738395",
    success="#4DB68E",
    warning="#D9A441",
    error="#E06B6B",
    canvas_grid_minor="#E6EBF0",
    canvas_grid_major="#CFD8E2",
    icon="#DCE6EF",
)

LIGHT_PALETTE = WorkbenchPalette(
    key="light",
    window="#F3F5F8",
    panel="#FFFFFF",
    panel_elevated="#F8FAFC",
    canvas="#FFFFFF",
    border="#E1E6EC",
    border_strong="#C7D0DA",
    text="#1D2939",
    text_muted="#667085",
    accent="#1D6A83",
    accent_hover="#24516F",
    accent_pressed="#17465A",
    selection="#DCEAF4",
    selection_text="#173A57",
    input="#FFFFFF",
    input_border="#D0D5DD",
    hover="#EEF3F7",
    disabled="#98A2B3",
    success="#16845B",
    warning="#946200",
    error="#C33D3D",
    canvas_grid_minor="#F0F3F6",
    canvas_grid_major="#DCE3EA",
    icon="#344054",
)


def palette_for_theme(theme: str) -> WorkbenchPalette:
    """Return a semantic palette for 'dark' or 'light'; reject unknown themes."""
    key = str(theme).strip().casefold()
    if key == "dark":
        return DARK_PALETTE
    if key == "light":
        return LIGHT_PALETTE
    raise ValueError("theme must be 'dark' or 'light'.")


_STYLESHEET = """
QWidget {
    color: @text@;
    font-family: "Segoe UI";
    font-size: 10pt;
}
QMainWindow {
    background: @window@;
}
QMenuBar {
    background: @panel@;
    color: @text@;
    border-bottom: 1px solid @border@;
    padding: 3px 8px;
}
QMenuBar::item {
    background: transparent;
    padding: 7px 11px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background: @hover@;
}
QMenu {
    background: @panel_elevated@;
    color: @text@;
    border: 1px solid @border_strong@;
    padding: 5px;
}
QMenu::item {
    padding: 8px 30px 8px 24px;
    border-radius: 4px;
}
QMenu::item:selected {
    background: @selection@;
    color: @selection_text@;
}
QToolBar#EngineeringCommandBar {
    background: @panel@;
    border: 0;
    border-bottom: 1px solid @border@;
    spacing: 5px;
    padding: 7px 10px;
}
QToolButton {
    color: @text@;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 7px 9px;
}
QToolButton:hover {
    background: @hover@;
    border-color: @border_strong@;
}
QToolButton:pressed, QToolButton:checked {
    background: @selection@;
    border-color: @accent@;
    color: @selection_text@;
}
QToolBar::separator {
    background: @border@;
    width: 1px;
    margin: 5px 7px;
}
QDockWidget {
    color: @text@;
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}
QDockWidget::title {
    background: @panel_elevated@;
    color: @text@;
    padding: 9px 10px;
    border-bottom: 1px solid @border@;
    font-weight: 600;
}
QFrame[workbenchPanel="true"] {
    background: @panel@;
    border: 1px solid @border@;
}
QFrame#DiagramDocumentBar {
    background: @panel@;
    border: 0;
    border-bottom: 1px solid @border@;
}
QTreeWidget, QTableWidget, QTableView, QPlainTextEdit, QTabWidget::pane {
    background: @input@;
    color: @text@;
    border: 1px solid @border@;
    selection-background-color: @selection@;
    selection-color: @selection_text@;
    alternate-background-color: @panel_elevated@;
    outline: 0;
}
QTreeWidget {
    border: 0;
}
QTreeWidget::item, QTableWidget::item {
    padding: 5px 4px;
    border: 0;
}
QTreeWidget::item:hover, QTableWidget::item:hover {
    background: @hover@;
}
QTreeWidget::item:selected, QTableWidget::item:selected {
    background: @selection@;
    color: @selection_text@;
}
QHeaderView::section {
    background: @panel_elevated@;
    color: @text_muted@;
    padding: 8px 9px;
    border: 0;
    border-bottom: 1px solid @border@;
    font-weight: 600;
}
QTabWidget::pane {
    background: @panel@;
    border: 1px solid @border@;
    top: -1px;
}
QTabBar::tab {
    background: @panel_elevated@;
    color: @text_muted@;
    padding: 10px 15px;
    margin-right: 2px;
    border: 0;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    background: @panel@;
    color: @text@;
    border-bottom: 2px solid @accent@;
    font-weight: 600;
}
QTabBar::tab:hover:!selected {
    background: @hover@;
    color: @text@;
}
QPushButton {
    background: @panel_elevated@;
    color: @text@;
    border: 1px solid @border_strong@;
    border-radius: 5px;
    padding: 8px 12px;
    min-height: 20px;
}
QPushButton:hover {
    background: @hover@;
    border-color: @accent@;
}
QPushButton:pressed {
    background: @accent_pressed@;
}
QPushButton:disabled, QToolButton:disabled {
    color: @disabled@;
    border-color: @border@;
}
QPushButton#PrimaryAction {
    background: @accent@;
    color: #FFFFFF;
    border: 1px solid @accent@;
    font-weight: 600;
}
QPushButton#PrimaryAction:hover {
    background: @accent_hover@;
    border-color: @accent_hover@;
}
QPushButton#SecondaryAction {
    background: transparent;
    color: @text@;
    border-color: @border_strong@;
}
QPushButton#EquipmentTile {
    background: @panel_elevated@;
    color: @text@;
    border: 1px solid @border@;
    border-radius: 7px;
    font-weight: 600;
    padding: 12px;
    text-align: left;
}
QPushButton#EquipmentTile:hover {
    background: @hover@;
    border-color: @accent@;
}
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    background: @input@;
    color: @text@;
    border: 1px solid @input_border@;
    border-radius: 5px;
    padding: 7px 9px;
    selection-background-color: @selection@;
    selection-color: @selection_text@;
    min-height: 20px;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid @accent@;
}
QComboBox QAbstractItemView {
    background: @panel_elevated@;
    color: @text@;
    selection-background-color: @selection@;
    selection-color: @selection_text@;
    border: 1px solid @border_strong@;
}
QCheckBox, QRadioButton {
    color: @text@;
    spacing: 8px;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 15px;
    height: 15px;
}
QStatusBar {
    background: @panel@;
    color: @text_muted@;
    border-top: 1px solid @border@;
}
QProgressBar {
    background: @panel_elevated@;
    color: @text@;
    border: 1px solid @border@;
    border-radius: 4px;
    text-align: center;
}
QProgressBar::chunk {
    background: @accent@;
    border-radius: 3px;
}
QScrollBar:vertical {
    background: @panel@;
    width: 12px;
    margin: 2px;
}
QScrollBar:horizontal {
    background: @panel@;
    height: 12px;
    margin: 2px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: @border_strong@;
    border-radius: 5px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::handle:hover {
    background: @disabled@;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
    border: none;
}
QSplitter::handle {
    background: @border@;
}
QSplitter::handle:hover {
    background: @accent@;
}
QSplitter::handle:horizontal {
    width: 7px;
    margin: 0 1px;
}
QSplitter::handle:vertical {
    height: 7px;
    margin: 1px 0;
}
QToolTip {
    background: @panel_elevated@;
    color: @text@;
    border: 1px solid @border_strong@;
    padding: 6px 8px;
}
QLabel#DiagramEyebrow, QLabel#SectionEyebrow, QLabel#WorkbenchPanelHeading {
    color: @text_muted@;
    font-size: 9pt;
    font-weight: 700;
}
QLabel#DiagramTitle {
    color: @text@;
    font-size: 11pt;
    font-weight: 650;
}
QLabel#DiagramSummary {
    color: @text_muted@;
    font-size: 9pt;
    font-weight: 600;
}
QToolButton#DiagramToggle {
    background: @panel_elevated@;
    color: @text@;
    border: 1px solid @border@;
    border-radius: 5px;
    padding: 7px 10px;
}
QToolButton#DiagramToggle:checked {
    background: @selection@;
    color: @selection_text@;
    border-color: @accent@;
}
QPushButton#DiagramFitButton {
    background: @accent@;
    color: #FFFFFF;
    border-color: @accent@;
    font-weight: 600;
}
QLineEdit#ProjectTreeSearch {
    background: @input@;
}
QLabel#CanvasWelcomeTitle {
    color: @text@;
    font-size: 20pt;
    font-weight: 600;
}
QLabel#CanvasWelcomeDescription {
    color: @text_muted@;
    font-size: 10pt;
}
QLabel#CanvasWelcomeHint {
    color: @text_muted@;
    font-size: 9pt;
}
QFrame#CanvasWelcomeCard, QFrame#SymbolPreviewFrame {
    background: @panel_elevated@;
    border: 1px solid @border@;
    border-radius: 9px;
}
QLabel#CandidateStatus {
    background: @panel_elevated@;
    color: @warning@;
    border: 1px solid @warning@;
    border-radius: 4px;
    padding: 4px 7px;
    font-size: 8pt;
    font-weight: 700;
}
QLabel#QETProvenanceDetails {
    background: @input@;
    color: @text_muted@;
    border: 1px solid @border@;
    border-radius: 5px;
    padding: 8px;
    font-size: 9pt;
}
QLabel#QETLibraryStatus {
    color: @text_muted@;
    font-size: 9pt;
}
QToolButton#ProvenanceToggle {
    color: @text_muted@;
    text-align: left;
    padding: 5px 3px;
}
"""

_TOKEN_NAMES = tuple(WorkbenchPalette.__dataclass_fields__)


def stylesheet_for_theme(theme: str) -> str:
    """Build the complete Qt stylesheet from the semantic palette."""
    palette = palette_for_theme(theme)
    stylesheet = _STYLESHEET
    for name in _TOKEN_NAMES:
        stylesheet = stylesheet.replace(f"@{name}@", str(getattr(palette, name)))
    unresolved = [token for token in ("@text@", "@panel@", "@accent@", "@canvas@") if token in stylesheet]
    if unresolved:
        raise RuntimeError(f"Unresolved workbench theme tokens: {', '.join(unresolved)}")
    return stylesheet
