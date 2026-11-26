"""Electrical equivalent models supported for line-like branches."""

from enum import StrEnum


class LineModelKind(StrEnum):
    """Model used to represent a line in each symmetrical-component network."""

    SERIES_ONLY = "series_only"
    NOMINAL_PI = "nominal_pi"
