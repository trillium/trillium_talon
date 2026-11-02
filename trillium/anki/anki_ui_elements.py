"""ui_elements renderer for Anki — registers itself at module load time.

Translates AnkiSession → ui_elements state dict → declarative card UI.
The UI function is module-level so ui_elements_show/hide can key on it.
"""

from talon import actions

from trillium.anki import anki_renderer as _registry
from trillium.anki.anki_state import AnkiSession

# ── State key namespace ───────────────────────────────────────────────────────
# All keys prefixed "anki_" to avoid collisions with other UIs.
_K = {
    "front": "anki_front",
    "back": "anki_back",
    "shown": "anki_answer_shown",
    "deck": "anki_deck",
    "done": "anki_reviewed",
    "total": "anki_total",
    "active": "anki_session_active",
    "error": "anki_error",
}


def _to_state(session: AnkiSession) -> dict:
    return {
        _K["front"]: session.front_text(),
        _K["back"]: session.back_text(),
        _K["shown"]: session.answer_shown,
        _K["deck"]: session.deck or "Anki",
        _K["done"]: session.reviewed,
        _K["total"]: session.total,
        _K["active"]: session.active,
        _K["error"]: session.error,
    }


# ── Palette ───────────────────────────────────────────────────────────────────
_CARD_BG = "0f0f1a"
_BORDER = "2255aa"
_FRONT_C = "eeeeff"
_BACK_C = "aaccbb"
_META_C = "7799bb"
_HINT_C = "555566"
_AGAIN_BG = "5c2020"
_HARD_BG = "5c3d20"
_GOOD_BG = "1e4d33"
_EASY_BG = "1e3d5c"
_ERROR_C = "ff6b6b"
_DONE_C = "44cc66"
_CLOSE_BG = "2a2a3a"


# ── UI function (module-level — stable identity for show/hide keying) ─────────
def _anki_ui():
    screen, window, div, text, button, state = actions.user.ui_elements(
        ["screen", "window", "div", "text", "button", "state"]
    )

    front = state.get(_K["front"], "")
    back = state.get(_K["back"], "")
    shown = state.get(_K["shown"], False)
    deck = state.get(_K["deck"], "Anki")
    done = state.get(_K["done"], 0)
    total = state.get(_K["total"], 0)
    active = state.get(_K["active"], False)
    error = state.get(_K["error"], None)
    selected = state.get("anki_selected", 0)

    def rate(ease):
        actions.user.anki_answer(ease)

    def show_answer():
        actions.user.anki_show_answer()

    def close():
        actions.user.anki_close()

    title = f"{deck}   {done} / {total}"

    # ── Card body ─────────────────────────────────────────────────────────────
    if error:
        body = div(padding=20, gap=14)[
            text(error, font_size=15, color=_ERROR_C, white_space="normal"),
            button(
                "Close",
                on_click=lambda e: close(),
                background_color=_CLOSE_BG,
                border_radius=6,
                padding=8,
                padding_left=16,
                padding_right=16,
            ),
        ]

    elif not active:
        card_label = "card" if done == 1 else "cards"
        body = div(padding=20, gap=14, align_items="center")[
            text(
                f"Done! Reviewed {done} {card_label}.",
                font_size=18,
                color=_DONE_C,
                text_align="center",
            ),
            button(
                "Close",
                on_click=lambda e: close(),
                background_color=_CLOSE_BG,
                border_radius=6,
                padding=8,
                padding_left=16,
                padding_right=16,
            ),
        ]

    else:
        _EASE_DEFS = [
            (1, "Again", _AGAIN_BG, "ff9999"),
            (2, "Hard", _HARD_BG, "ffcc88"),
            (3, "Good", _GOOD_BG, "88dd99"),
            (4, "Easy", _EASY_BG, "88bbff"),
        ]

        def _ease_btn(ease, label, bg, text_c):
            is_sel = selected == ease
            return button(
                label,
                on_click=lambda e, ease=ease: rate(ease),
                background_color=bg,
                border_radius=5,
                border_width=2,
                border_color="ffffffff" if is_sel else bg,
                padding=8,
                padding_left=14,
                padding_right=14,
                color=text_c,
            )

        ease_row = div(flex_direction="column", gap=4)[
            div(flex_direction="row", gap=6)[*[_ease_btn(*d) for d in _EASE_DEFS]],
            (
                text(
                    f'say "pick" to confirm · "rotate" to cycle',
                    font_size=11,
                    color=_HINT_C,
                    font_style="italic",
                )
                if selected
                else None
            ),
        ]

        body = div(padding=20, gap=14)[
            # Front
            div(max_height=240, overflow_y="scroll")[
                text(front, font_size=18, color=_FRONT_C, white_space="normal"),
            ],
            # Separator + back (only when shown)
            div(height=1, background_color=_BORDER) if shown else None,
            (
                div(max_height=200, overflow_y="scroll")[
                    text(back, font_size=15, color=_BACK_C, white_space="normal"),
                ]
                if shown
                else None
            ),
            # Ease row or hint
            (
                ease_row
                if shown
                else text(
                    'say "show answer" to flip',
                    font_size=12,
                    color=_HINT_C,
                    font_style="italic",
                )
            ),
        ]

    return screen(justify_content="center", align_items="center")[
        window(
            title=title,
            width=560,
            background_color=_CARD_BG,
            border_width=1,
            border_color=_BORDER,
            on_close=lambda e: close(),
        )[body]
    ]


# ── Renderer implementation ───────────────────────────────────────────────────
class _UIElementsRenderer:
    def show(self, session: AnkiSession) -> None:
        actions.user.ui_elements_show(
            _anki_ui,
            initial_state=_to_state(session),
        )

    def update(self, session: AnkiSession) -> None:
        actions.user.ui_elements_set_state(_to_state(session))

    def hide(self) -> None:
        if actions.user.ui_elements_is_active(_anki_ui):
            actions.user.ui_elements_hide(_anki_ui)

    def is_active(self) -> bool:
        return actions.user.ui_elements_is_active(_anki_ui)


# Self-register at module load time.
_registry.register(_UIElementsRenderer())
