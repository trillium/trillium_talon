"""
Talon captures and actions for mouse clock voice commands.

This module defines the Talon captures that extract clock face letters,
colors, and ordinal multipliers from voice input.
"""

from typing import Any
from talon import Context, Module
from ..core.logger import log_debug

mod = Module()
ctx = Context()

mod.list("clock_face", desc="Clock face positions (a-l)")
mod.list("color", desc="Colors for mouse clock navigation")
mod.list("mouse", desc="The word mouse")
mod.list("line_style", desc="Line styles (solid, dashed, dotted)")
mod.list("direction", desc="Directional offsets (top, bottom, left, right)")
ctx.lists["user.mouse"] = ["mouse"]


@mod.capture(rule="{user.clock_face}")
def clock_face(match) -> str:
    """Capture a single clock face letter"""
    log_debug(f"[clock_face] {match.clock_face}")
    return match.clock_face


@mod.capture(rule="{user.color}")
def color(match) -> str:
    """Capture a color"""
    return match.color


@mod.capture(rule="{user.mouse}")
def mouse(match) -> str:
    """Capture the word mouse"""
    return match.mouse


@mod.capture(rule="{user.line_style}")
def line_style(match) -> str:
    """Capture a line style (solid, dashed, dotted)"""
    return match.line_style


@mod.capture(rule="[{user.line_style}] ({user.clock_face} | {user.color}) [{user.direction}]")
def styled_target(match) -> str:
    """Capture an optional line style, a letter or color, and optional direction.

    Returns format: "[style:][target][@direction]"
    Examples:
        "air" -> "a"
        "red" -> "red"
        "air top" -> "a@top"
        "red left" -> "red@left"
        "dash air" -> "dashed:a"
        "dash air top" -> "dashed:a@top"
    """
    parts = list(match)

    # Determine what we have based on parts count and types
    style = None
    target = None
    direction = None

    for part in parts:
        part_str = str(part)
        if part_str in ('solid', 'dashed', 'dotted'):
            style = part_str
        elif part_str in ('top', 'bottom', 'left', 'right'):
            direction = part_str
        else:
            target = part_str

    result = ""
    if style:
        result = f"{style}:{target}"
    else:
        result = target or ""

    if direction:
        result = f"{result}@{direction}"

    return result


@mod.capture(rule="<user.styled_target>+ [dash]")
def letters_colors(match) -> list[str]:
    """Capture any number of styled targets, with optional 'dash' suffix for targeting.

    Each target is optionally preceded by a line style.
    'dash' at the end targets the dash separator after the last color.
    Example: "dash air red" -> ["dashed:a", "red"] (line style)
    Example: "air red dash" -> ["a", "red", "dash"] (dash targeting)
    """
    result = list(match.styled_target_list)
    # Check if 'dash' was captured at the end (for dash targeting)
    try:
        if match.dash:
            result.append("dash")
    except AttributeError:
        pass
    return result
