"""The real TalonBackend over a stub Talon registry, in both live CommandImpl shapes.

Talon 0.4.0 (115.0) on mini0 has `CommandImpl(ctx, rule, script, experiments)`: no `trigger`, no
`lineno`, and the registry is a real one we cannot import here. Later builds
(0.4.0-1561-9c3d) answer both directly. `/state` and `/commands` must answer 200 for either shape,
and the two shapes must produce byte-identical commands — same ids, slots and `commands_rev` — or the
phone's cached ids churn on every host it talks to. Evidence for the equivalence: task-ykd7c.
"""

import types

import pytest

from talon import registry, scope

from trillium.palette_feed import palette_feed
from trillium.palette_feed import serialize
from trillium.palette_feed.api import Config, PaletteApi
from trillium.palette_feed.limits import RateLimiter

TOKEN = "t" * 43
AUTH = {"Authorization": f"Bearer {TOKEN}"}

PARROT_CONTEXT = "user.trillium_talon.trillium.plugin.parrot.parrot_always.talon"

# (rule, context, lineno) — the third value is what the newer build calls `lineno` and what 0.4.0
# exposes as `script.start_line`. The parrot row is live evidence: both builds serve `00de4484b8`.
SPEC = [
    ("parrot on", PARROT_CONTEXT, 4, ()),
    ("tab {user.tab_action}", "user.trillium_talon.core.tabs.talon", 2, (1, 0)),
    ("say <user.text>", "user.trillium_talon.core.say.talon", 9, ()),
    # Two impls for one rule: `shadowed` folds them into one entry.
    ("nuke left", "user.trillium_talon.trillium.rapid_delete.talon", 12, ()),
    ("nuke left", "user.trillium_talon.plugin.rapid_delete.talon", 3, ()),
]

PARROT_ID = "00de4484b8"


class _Rule:
    def __init__(self, text):
        self.rule = text


class _Script:
    def __init__(self, start_line):
        self.start_line = start_line
        self.filename = "user/x.talon"
        self.code = "pass"


class _Ctx:
    def __init__(self, path, score=()):
        self.path = path
        self._match = "<talon.scripting.match.MatchAny object at 0x10abc0000>"
        if score:
            self._active_scores = score


class Impl040:
    """Talon 0.4.0 (mini0): ctx/rule/script/experiments — no `trigger`, no `lineno`."""

    def __init__(self, ctx, rule, start_line):
        self.ctx = ctx
        self.rule = _Rule(rule)
        self.script = _Script(start_line)
        self.experiments = set()


class ImplRefactored:
    """0.4.0-1561-9c3d: CommandImpl(ScriptImpl) with `trigger` and `lineno`."""

    def __init__(self, ctx, rule, lineno):
        self.ctx = ctx
        self.rule = _Rule(rule)
        self.script = _Script(lineno)
        self.trigger = rule
        self.lineno = lineno
        self.experiments = set()


def _groups(shape):
    """One group per unique rule text, the way registry.commands presents them."""
    groups: dict[str, list] = {}
    for rule, ctx, lineno, score in SPEC:
        groups.setdefault(rule, []).append(shape(_Ctx(ctx, score), rule, lineno))
    return list(groups.values())


@pytest.fixture
def serve(monkeypatch):
    """Return a factory: build a PaletteApi over TalonBackend with a registry holding `groups`."""

    def build(groups):
        monkeypatch.setattr(
            palette_feed,
            "registry",
            types.SimpleNamespace(
                commands={"g%d" % i: g for i, g in enumerate(groups)},
                lists={"user.tab_action": [{"open": "open", "close": "close"}]},
                tags=frozenset({"user.parrot_on"}),
            ),
        )
        monkeypatch.setattr(palette_feed, "RawImpl", serialize.RawImpl, raising=False)
        return PaletteApi(
            TOKEN, palette_feed.TalonBackend(), RateLimiter(100, 1.0), Config()
        )

    return build


@pytest.fixture
def stable_scope():
    scope.reset()
    scope.update(
        {
            "app": {"name": "WezTerm", "bundle": "com.github.wez.wezterm"},
            "mode": ["command", "all"],
        }
    )
    yield scope
    scope.reset()


def test_the_0_4_0_fixture_really_lacks_trigger_and_lineno():
    """Without this the equivalence below could pass by accident on a newer-shaped object."""
    (group,) = _groups(Impl040)[:1]
    (impl,) = group
    assert not hasattr(impl, "trigger")
    assert not hasattr(impl, "lineno")
    assert not hasattr(impl.ctx, "_active_scores")


def test_the_unpatched_expression_would_fail_on_the_0_4_0_shape():
    """The defect task-ykd7c fixes: reading `.trigger`/`.lineno` directly is what 500'd mini0."""
    (group,) = _groups(Impl040)[:1]
    (impl,) = group
    with pytest.raises(AttributeError, match="trigger"):
        impl.trigger
    with pytest.raises(AttributeError, match="lineno"):
        impl.lineno


def test_commands_and_state_answer_for_the_0_4_0_shape(serve, stable_scope):
    api = serve(_groups(Impl040))
    assert api.handle("GET", "/commands", AUTH).status == 200
    assert api.handle("GET", "/state", AUTH).status == 200
    assert api.handle("GET", "/lists/user.tab_action", AUTH).status == 200


def test_both_shapes_serve_identical_commands_and_state(serve, stable_scope):
    old = serve(_groups(Impl040))
    new = serve(_groups(ImplRefactored))

    old_commands = old.handle("GET", "/commands", AUTH)
    new_commands = new.handle("GET", "/commands", AUTH)
    assert old_commands.status == new_commands.status == 200
    # ids, slots, shadowed and commands_rev all come out the same from the fallback.
    assert old_commands.body == new_commands.body

    old_state = old.handle("GET", "/state", AUTH)
    new_state = new.handle("GET", "/state", AUTH)
    assert old_state.status == new_state.status == 200
    assert old_state.body["commands_rev"] == new_state.body["commands_rev"]
    assert old_state.body["rev"] == new_state.body["rev"]
    assert old_state.body["tags"] == new_state.body["tags"] == ["user.parrot_on"]
    assert old_state.body["app"]["name"] == "WezTerm"


def test_the_0_4_0_shape_reproduces_the_live_id_and_slots(serve, stable_scope):
    api = serve(_groups(Impl040))
    body = api.handle("GET", "/commands", AUTH).body
    by_rule = {c["rule"]: c for c in body["commands"]}
    assert by_rule["parrot on"]["id"] == PARROT_ID
    assert by_rule["parrot on"]["lineno"] == 4
    assert by_rule["tab {user.tab_action}"]["slots"] == [
        {"name": "user.tab_action", "type": "list", "n": 2}
    ]
    assert by_rule["say <user.text>"]["kind"] == "capture"
    assert by_rule["nuke left"]["shadowed"] == 1
    assert body["count"] == 4


def test_the_etag_is_a_validator_for_the_0_4_0_shape(serve, stable_scope):
    api = serve(_groups(Impl040))
    first = api.handle("GET", "/commands", AUTH)
    assert first.headers["ETag"] == f'"{first.body["commands_rev"]}"'
    assert (
        api.handle("GET", f'/commands?rev={first.body["commands_rev"]}', AUTH).status
        == 304
    )
