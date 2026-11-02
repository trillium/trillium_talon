"""Anki review — Talon module and actions.

Rendering is fully delegated to whatever renderer is registered in
anki_renderer. anki_ui_elements.py self-registers at load time.
"""
from talon import Context, Module, actions

from trillium.anki.anki_connect import answer_card, cards_info, due_cards, undo_last
from trillium.anki.anki_state import AnkiSession
from trillium.anki import anki_renderer as _renderer

mod = Module()
mod.tag("anki_active", desc="Anki review overlay is open")
mod.tag("anki_answer_shown", desc="Anki answer side is visible")

_session = AnkiSession()
_ctx = Context()
_selected_ease: int = 0  # mirrors ui_elements "anki_selected" state, readable without get_state



def _sync_tags() -> None:
    tags = []
    if _session.active:
        tags.append("user.anki_active")
        if _session.answer_shown:
            tags.append("user.anki_answer_shown")
    _ctx.tags = tags


def _push(session: AnkiSession) -> None:
    """Push updated session to renderer + sync Talon context tags."""
    r = _renderer.get()
    if r:
        r.update(session)
    _sync_tags()



@mod.action_class
class Actions:
    def anki_start(deck: str = ""):
        """Start an Anki review session (deck name optional)."""
        deck_arg = deck.strip() or None

        try:
            ids = due_cards(deck_arg)
        except RuntimeError as e:
            _session.set_error(str(e))
            ids = []

        if ids and not _session.error:
            try:
                _session.load(cards_info(ids[:50]), deck_arg)
            except RuntimeError as e:
                _session.set_error(str(e))

        if not ids and not _session.error:
            _session.load([], deck_arg)

        r = _renderer.get()
        if r:
            if r.is_active():
                r.update(_session)
            else:
                r.show(_session)

        _sync_tags()

    def anki_show_answer():
        """Reveal the answer side of the current card."""
        if not _session.active:
            return
        _session.show_answer()
        _push(_session)

    def anki_answer(ease: int):
        """Rate current card: 1=Again 2=Hard 3=Good 4=Easy."""
        global _selected_ease
        if not _session.active or not _session.answer_shown:
            return
        card = _session.current_card
        try:
            answer_card(card["cardId"], ease)
        except RuntimeError:
            pass  # advance anyway; Anki will sync on next open
        _session.advance()
        _selected_ease = 0
        actions.user.ui_elements_set_state("anki_selected", 0)
        _push(_session)

    def anki_skip():
        """Skip the current card without rating."""
        global _selected_ease
        if not _session.active:
            return
        _session.advance()
        _selected_ease = 0
        actions.user.ui_elements_set_state("anki_selected", 0)
        _push(_session)

    def anki_select_next():
        """Cycle ease selection forward: Again → Hard → Good → Easy → Again → …"""
        global _selected_ease
        _selected_ease = (_selected_ease % 4) + 1
        actions.user.ui_elements_set_state("anki_selected", _selected_ease)

    def anki_confirm_selected():
        """Rate with the currently highlighted ease, if any."""
        if 1 <= _selected_ease <= 4:
            actions.user.anki_answer(_selected_ease)

    def anki_parrot_enter():
        """Context-sensitive Enter: show answer on front, confirm selection on back."""
        if not _session.active:
            return
        if not _session.answer_shown:
            actions.user.anki_show_answer()
        else:
            actions.user.anki_confirm_selected()

    def anki_undo():
        """Undo the last card rating in Anki."""
        try:
            undo_last()
        except RuntimeError:
            pass

    def anki_close():
        """Close the Anki overlay and clear session state."""
        global _selected_ease
        _session.clear()
        _selected_ease = 0
        r = _renderer.get()
        if r:
            r.hide()
        _ctx.tags = []
