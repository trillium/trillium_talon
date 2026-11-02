"""AnkiConnect HTTP client — no Talon imports, pure stdlib."""
import json
import urllib.request
import urllib.error

ANKI_CONNECT_URL = "http://localhost:8765"
VERSION = 6


def _invoke(action: str, **params):
    payload = json.dumps(
        {"action": action, "version": VERSION, "params": params}
    ).encode()
    try:
        req = urllib.request.Request(ANKI_CONNECT_URL, payload)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
    except urllib.error.URLError as e:
        raise RuntimeError(f"AnkiConnect unreachable — is Anki running? ({e})") from e
    if data.get("error"):
        raise RuntimeError(f"AnkiConnect: {data['error']}")
    return data["result"]


def due_cards(deck: str | None = None) -> list[int]:
    q = "(is:due is:review) or (is:due is:new)"
    if deck:
        q = f'deck:"{deck}" ({q})'
    return _invoke("findCards", query=q)


def cards_info(card_ids: list[int]) -> list[dict]:
    return _invoke("cardsInfo", cards=card_ids)


def answer_card(card_id: int, ease: int):
    """ease: 1=Again, 2=Hard, 3=Good, 4=Easy."""
    _invoke("answerCards", answers=[{"cardId": card_id, "ease": ease}])


def undo_last():
    _invoke("undo")


def deck_names() -> list[str]:
    return _invoke("deckNames")
