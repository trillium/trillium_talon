"""
Geometric calculations for the mouse clock system.

This module provides pure mathematical functions for angle conversions,
averaging, and coordinate transformations used in mouse positioning.
"""

_LAZY_IMPORTS = {
    # clock
    'letter_to_position': '.clock',
    'letter_to_clock_angle': '.clock',
    # averaging
    'calculate_mean': '.averaging',
    'average_clock_angles': '.averaging',
    # coordinates
    'move_in_direction': '.coordinates',
}

def __getattr__(name):
    if name in _LAZY_IMPORTS:
        from importlib import import_module
        mod = import_module(_LAZY_IMPORTS[name], __name__)
        val = getattr(mod, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = list(_LAZY_IMPORTS.keys())
