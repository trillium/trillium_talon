"""Renderer registry — swap the rendering backend without touching actions.

Usage:
    # In a renderer module (e.g. anki_ui_elements.py), at load time:
    from trillium.anki import anki_renderer as _registry
    _registry.register(MyRenderer())

    # The registered renderer must implement:
    #   show(session: AnkiSession) -> None
    #   update(session: AnkiSession) -> None
    #   hide() -> None
    #   is_active() -> bool
"""

_renderer = None


def register(r) -> None:
    global _renderer
    _renderer = r


def get():
    return _renderer
