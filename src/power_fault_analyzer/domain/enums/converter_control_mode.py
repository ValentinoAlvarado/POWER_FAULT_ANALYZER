"""Converter control classifications relevant to fault contribution models."""

from enum import StrEnum


class ConverterControlMode(StrEnum):
    GRID_FOLLOWING = "grid_following"
    GRID_FORMING = "grid_forming"
    OTHER = "other"


class ConverterCurrentPriority(StrEnum):
    ACTIVE = "active"
    REACTIVE = "reactive"
    BALANCED = "balanced"
    USER_DEFINED = "user_defined"
