"""Tests for recall_overlay_persistent — collision avoidance and mouse click handling."""

import talon

if hasattr(talon, "test_mode"):
    from talon.ui import Rect
    from talon.canvas import MouseEvent

    from plugin.recall.recall_overlay_shared import _pills_overlap
    from plugin.recall import recall_overlay_persistent as rop

    # ── _pills_overlap ────────────────────────────────────────────────

    def test_pills_overlap_identical():
        a = Rect(0, 0, 100, 20)
        assert _pills_overlap(a, a)

    def test_pills_overlap_partial():
        a = Rect(0, 0, 100, 20)
        b = Rect(50, 0, 100, 20)
        assert _pills_overlap(a, b)

    def test_pills_no_overlap_horizontal():
        a = Rect(0, 0, 100, 20)
        b = Rect(105, 0, 100, 20)
        assert not _pills_overlap(a, b)

    def test_pills_no_overlap_vertical():
        a = Rect(0, 0, 100, 20)
        b = Rect(0, 25, 100, 20)
        assert not _pills_overlap(a, b)

    def test_pills_touching_edge_no_overlap():
        a = Rect(0, 0, 100, 20)
        b = Rect(100, 0, 100, 20)
        assert not _pills_overlap(a, b)

    # ── mouse hit test via Rect.contains ─────────────────────────────

    def _make_mouse(x, y, button=0, event="mousedown"):
        return MouseEvent(x=x, y=y, button=button, event=event)

    def test_rect_contains_center():
        r = Rect(10, 10, 100, 20)
        pt = _make_mouse(60, 20).gpos
        assert r.contains(pt)

    def test_rect_not_contains_outside():
        r = Rect(10, 10, 100, 20)
        pt = _make_mouse(5, 20).gpos
        assert not r.contains(pt)

    # ── on_mouse_persistent ───────────────────────────────────────────

    def test_mouse_click_focuses_correct_window():
        focused = []

        class FakeWindow:
            def focus(self):
                focused.append(self)

        win_a = FakeWindow()
        win_b = FakeWindow()

        rop._persistent_hit_targets = [
            (win_a, Rect(0, 0, 80, 20)),
            (win_b, Rect(90, 0, 80, 20)),
        ]

        # Click inside win_b's pill
        e = _make_mouse(x=130, y=10)
        rop.on_mouse_persistent(e)

        assert focused == [win_b]

    def test_mouse_click_miss_focuses_nothing():
        focused = []

        class FakeWindow:
            def focus(self):
                focused.append(self)

        rop._persistent_hit_targets = [
            (FakeWindow(), Rect(0, 0, 80, 20)),
        ]

        e = _make_mouse(x=500, y=500)
        rop.on_mouse_persistent(e)

        assert focused == []

    def test_mouse_right_click_ignored():
        focused = []

        class FakeWindow:
            def focus(self):
                focused.append(self)

        rop._persistent_hit_targets = [
            (FakeWindow(), Rect(0, 0, 80, 20)),
        ]

        e = _make_mouse(x=40, y=10, button=1, event="mousedown")  # right click
        rop.on_mouse_persistent(e)

        assert focused == []
