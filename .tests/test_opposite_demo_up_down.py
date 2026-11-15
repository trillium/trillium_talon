"""'demo up' and 'demo down' are registered as opposites of each other."""

from trillium.plugin.repeater.opposite_mappings import OPPOSITES


def test_demo_up_and_down_point_at_each_other():
    assert OPPOSITES["demo up"]["trigger"] == "demo down"
    assert OPPOSITES["demo down"]["trigger"] == "demo up"


def test_demo_opposite_actions_undo_the_phrase():
    assert OPPOSITES["demo up"]["action"] == ("user", "smooth_scroll_mimic", ("down",))
    assert OPPOSITES["demo down"]["action"] == ("user", "smooth_scroll_mimic", ("up",))
