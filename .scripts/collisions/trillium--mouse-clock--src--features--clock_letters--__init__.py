"""Clock letters overlay feature."""

_LAZY_IMPORTS = {
    'draw_clock_letters_overlay': '.render',
    'get_clock_letters_target': '.targeting',
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
