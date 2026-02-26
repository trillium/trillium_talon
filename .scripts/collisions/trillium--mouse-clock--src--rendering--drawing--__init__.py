"""
Basic shape drawing primitives for overlay systems.

Provides a consistent API for drawing lines, circles, rectangles, dots,
crosses, and text on Talon canvas objects.
"""

_LAZY_IMPORTS = {
    # primitives
    'draw_line': '.primitives',
    'draw_circle': '.primitives',
    'draw_rect': '.primitives',
    'draw_dot': '.primitives',
    'draw_cross': '.primitives',
    'draw_text': '.primitives',
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
