"""
Canvas drawing and rendering utilities for the mouse clock.

This module handles all visual rendering of the mouse clock, including
concentric rings, dots, clock letters, and edge-distance visualization.
"""

_LAZY_IMPORTS = {
    # utils
    'get_screen_dimensions': '.utils',
    'setup_paint': '.utils',
    'calculate_ring_radius': '.utils',
    'calculate_clock_position': '.utils',
    # rings
    'draw_concentric_rings': '.rings',
    'draw_clock_position_dots': '.rings',
    # edge
    'calculate_edge_distance': '.edge',
    'draw_edge_distance_dots': '.edge',
    # clock
    'draw_clock_letters': '.clock',
    'draw_mouse_clock': '.clock',
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
