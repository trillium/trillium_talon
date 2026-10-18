"""Talon only honors a setting that was declared, so the feed's settings must be.

A `<name>.talon` `settings():` block is an assignment, and Talon drops an assignment whose
setting has no matching `Module.setting` declaration — the log says "settings skipped
because they have no matching declaration", `settings.get` keeps returning the default, and
the feed silently stays on loopback. That is exactly what happened to
`user.palette_feed_bind` / `user.palette_feed_open_reads` (task-ncz8l): the values in
`trillium/settings.talon` were inert.

`trillium/palette_feed/palette_feed.py` is the one module that imports Talon, so this test
imports it a second time under a recorder and checks the declarations `options.resolve`
depends on. The background is task-ncz8l; the live evidence is the deploy that needed a
by-hand patch on both hosts.
"""

import importlib.util
import os

import pytest
from talon import Module

from trillium.palette_feed import options

MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "trillium",
    "palette_feed",
    "palette_feed.py",
)

# What each declaration must say, keyed by the bare name Talon stores the `user.` prefix in.
EXPECTED = {
    "palette_feed_bind": (str, options.DEFAULT_BIND),
    "palette_feed_open_reads": (bool, options.DEFAULT_OPEN_READS),
    "palette_feed_open_execute": (bool, options.DEFAULT_OPEN_EXECUTE),
}


@pytest.fixture
def declared(monkeypatch):
    """Import palette_feed.py with `Module.setting` recording instead of dropping."""
    calls = []

    def record(self, name, **kwargs):
        calls.append((name, kwargs))

    monkeypatch.setattr(Module, "setting", record)
    # A package-qualified name so the module's relative imports still resolve.
    spec = importlib.util.spec_from_file_location(
        "trillium.palette_feed._settings_probe", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert calls, "palette_feed.py declared no settings at all"
    return module, {name: kwargs for name, kwargs in calls}


def test_every_setting_the_feed_reads_is_declared(declared):
    _, by_name = declared
    assert set(by_name) == set(EXPECTED), (
        "options reads "
        f"{sorted(options.SETTINGS)}; palette_feed.py declares {sorted(by_name)}"
    )


def test_the_declarations_match_the_defaults_the_feed_uses(declared):
    _, by_name = declared
    for name, (kind, default) in EXPECTED.items():
        assert by_name[name]["type"] is kind, f"{name} is declared with the wrong type"
        assert (
            by_name[name]["default"] == default
        ), f"{name} default disagrees with options"


def test_each_declaration_is_documented(declared):
    """A setting nobody can find in the Talon settings list is a setting nobody uses."""
    _, by_name = declared
    for name, kwargs in by_name.items():
        assert kwargs.get("desc"), f"{name} has no description"
        assert (
            len(kwargs["desc"]) > 20
        ), f"{name}'s description is too thin to be useful"


def test_the_declared_names_are_the_ones_options_resolves(declared):
    """`user.x` on the reading side and `x` at the declaration are the same setting."""
    _, by_name = declared
    for name in by_name:
        assert f"user.{name}" in options.SETTINGS


def test_a_talon_style_assignment_reaches_options(declared):
    """The end that broke: a declared setting's value must survive into Options."""
    _, by_name = declared
    values = {
        f"user.{name}": ("100.64.0.1" if name == "palette_feed_bind" else True)
        for name in by_name
    }
    opts = options.resolve({}, lambda name, default=None: values.get(name, default))
    assert opts.bind == "100.64.0.1" and opts.open_reads and opts.open_execute
    assert opts.allow_non_loopback
