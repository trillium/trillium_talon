"""Anki session state — no Talon imports."""
import html.parser
import re


_SUPPRESS_TAGS = {"style", "script"}
_BLOCK_TAGS    = {"br", "div", "p", "li", "tr"}


class _TextExtractor(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._suppress = 0  # nesting depth inside style/script

    def handle_data(self, data: str):
        if not self._suppress:
            self._parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in _SUPPRESS_TAGS:
            self._suppress += 1
        elif tag in _BLOCK_TAGS and not self._suppress:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SUPPRESS_TAGS and self._suppress:
            self._suppress -= 1

    def result(self) -> str:
        text = "".join(self._parts)
        return re.sub(r"\n{3,}", "\n\n", text).strip()


def strip_html(s: str) -> str:
    ex = _TextExtractor()
    try:
        ex.feed(s)
        return ex.result()
    except Exception:
        return re.sub(r"<[^>]+>", "", s).strip()


EASE_LABELS = {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}
EASE_COLORS = {
    1: "ff6b6bff",
    2: "ffaa44ff",
    3: "44cc66ff",
    4: "5ab5f0ff",
}


class AnkiSession:
    def __init__(self):
        self._cards: list[dict] = []
        self._index: int = 0
        self._answer_shown: bool = False
        self._deck: str | None = None
        self._reviewed: int = 0
        self._error: str | None = None

    # ── Read-only properties ──────────────────────────────────────

    @property
    def active(self) -> bool:
        return self._index < len(self._cards)

    @property
    def current_card(self) -> dict | None:
        return self._cards[self._index] if self.active else None

    @property
    def answer_shown(self) -> bool:
        return self._answer_shown

    @property
    def deck(self) -> str | None:
        return self._deck

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def remaining(self) -> int:
        return max(0, len(self._cards) - self._index)

    @property
    def reviewed(self) -> int:
        return self._reviewed

    @property
    def total(self) -> int:
        return len(self._cards)

    def front_text(self) -> str:
        card = self.current_card
        return strip_html(card.get("question", "")) if card else ""

    def back_text(self) -> str:
        card = self.current_card
        if not card:
            return ""
        answer = card.get("answer", "")
        # Anki embeds front+back separated by <hr id=answer>
        split = re.split(r'<hr[^>]*id=["\']?answer["\']?[^>]*/?\s*>', answer, maxsplit=1)
        return strip_html(split[1]) if len(split) > 1 else strip_html(answer)

    # ── Mutations ─────────────────────────────────────────────────

    def load(self, cards: list[dict], deck: str | None = None):
        self._cards = cards
        self._index = 0
        self._answer_shown = False
        self._deck = deck
        self._reviewed = 0
        self._error = None

    def set_error(self, msg: str):
        self._error = msg
        self._cards = []

    def show_answer(self):
        self._answer_shown = True

    def advance(self):
        self._index += 1
        self._answer_shown = False
        self._reviewed += 1

    def clear(self):
        self.__init__()
