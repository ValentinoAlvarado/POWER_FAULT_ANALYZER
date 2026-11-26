"""Regression tests for the centralized PFA workbench design system."""

from __future__ import annotations

import pytest

from power_fault_analyzer.interfaces.desktop.workbench.design_system import (
    DARK_PALETTE,
    LIGHT_PALETTE,
    palette_for_theme,
    stylesheet_for_theme,
)


def test_dark_palette_defines_dark_shell_and_neutral_engineering_canvas() -> None:
    palette = palette_for_theme("dark")

    assert palette == DARK_PALETTE
    assert palette.window == "#151C25"
    assert palette.panel == "#1E2936"
    assert palette.canvas == "#F4F7FA"
    assert palette.canvas_grid_minor != palette.canvas_grid_major


def test_light_palette_remains_available_for_user_preference() -> None:
    palette = palette_for_theme("light")

    assert palette == LIGHT_PALETTE
    assert palette.window == "#F3F5F8"
    assert palette.canvas == "#FFFFFF"


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_stylesheet_resolves_every_semantic_token(theme: str) -> None:
    stylesheet = stylesheet_for_theme(theme)

    assert "QDockWidget::title" in stylesheet
    assert "QDockWidget > QWidget" in stylesheet
    assert "QWidget#WorkbenchPanelContent" in stylesheet
    assert "QToolBar#EngineeringCommandBar" in stylesheet
    assert "min-height: 32px" in stylesheet
    assert "padding: 2px 5px" in stylesheet
    assert "QLabel#CommandSectionLabel" in stylesheet
    assert "QTreeWidget::item:selected" in stylesheet
    assert "QLineEdit:focus" in stylesheet
    assert "QSplitter::handle:hover" in stylesheet
    assert "@" not in stylesheet


def test_unknown_theme_is_rejected_instead_of_silently_falling_back() -> None:
    with pytest.raises(ValueError, match="theme must be 'dark' or 'light'"):
        palette_for_theme("system")
