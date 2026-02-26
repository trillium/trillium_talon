"""
Shared utility functions for feature modules.
"""

from typing import List, TypeVar, Optional

T = TypeVar('T')


def safe_index(
    items: List[T],
    value: T,
    default: int = 0,
    case_insensitive: bool = True
) -> int:
    """
    Find index of value in list, returning default if not found.

    Args:
        items: List to search
        value: Value to find
        default: Index to return if not found (default 0)
        case_insensitive: If True and value is str, compare lowercase

    Returns:
        Index of value or default
    """
    search_value = value.lower() if case_insensitive and isinstance(value, str) else value

    try:
        if case_insensitive and isinstance(value, str):
            # Search in lowercase list
            return [x.lower() if isinstance(x, str) else x for x in items].index(search_value)
        return items.index(search_value)
    except ValueError:
        return default


def safe_index_or_none(
    items: List[T],
    value: T,
    case_insensitive: bool = True
) -> Optional[int]:
    """
    Find index of value in list, returning None if not found.

    Args:
        items: List to search
        value: Value to find
        case_insensitive: If True and value is str, compare lowercase

    Returns:
        Index of value or None
    """
    result = safe_index(items, value, default=-1, case_insensitive=case_insensitive)
    return result if result >= 0 else None
