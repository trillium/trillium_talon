"""
Shared utilities for feature modules.

Common functions extracted from grid and clock_letters features.
"""

_LAZY_IMPORTS = {
    'calculate_row_positions': '.layout',
    'calculate_column_positions': '.layout',
    'apply_alpha': '.alpha',
    'set_alpha': '.alpha',
    'get_alpha': '.alpha',
    'safe_index': '.utils',
    'safe_index_or_none': '.utils',
    # Re-exported from core; currently unused but available for feature modules
    'DEFAULT_TEXT_COLOR': '...core.constants',
    'DEFAULT_TEXT_BG_COLOR': '...core.constants',
}

def __getattr__(name):
    if name in _LAZY_IMPORTS:
        from importlib import import_module
        mod = import_module(_LAZY_IMPORTS[name], __name__)
        val = getattr(mod, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
