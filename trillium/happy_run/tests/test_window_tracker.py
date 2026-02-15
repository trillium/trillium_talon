"""Tests for window_tracker diff logic."""


def diff_ids(before, after):
    """Pure diff logic extracted for testing."""
    return after - before


class TestWindowDiff:
    def test_new_window_detected(self):
        before = {101, 102, 103}
        after = {101, 102, 103, 104}
        assert diff_ids(before, after) == {104}

    def test_no_new_window(self):
        before = {101, 102, 103}
        after = {101, 102, 103}
        assert diff_ids(before, after) == set()

    def test_app_not_running_before(self):
        before = set()
        after = {104}
        assert diff_ids(before, after) == {104}

    def test_multiple_new_windows(self):
        before = {101, 102}
        after = {101, 102, 103, 104}
        assert diff_ids(before, after) == {103, 104}

    def test_window_closed_during_launch(self):
        before = {101, 102, 103}
        after = {101, 103, 104}
        assert diff_ids(before, after) == {104}
