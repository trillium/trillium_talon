"""
Core mouse clock logic, independent of Talon.

This module contains the core business logic for the mouse clock system,
including configuration, geometry calculations, and mouse positioning.
"""

_LAZY_IMPORTS = {
    'RadiusAnimator': '.animation',
    'exponential_lerp_factor': '.animation',
    'flip_letter_to_opposite': '.voice_parsing',
    'parse_voice_inputs': '.voice_parsing',
    'MouseClockCore': '.mouse_clock',
}

def __getattr__(name):
    if name in _LAZY_IMPORTS:
        from importlib import import_module
        mod = import_module(_LAZY_IMPORTS[name], __name__)
        val = getattr(mod, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
