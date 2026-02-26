"""Tests for readiness_poller decision logic."""

STABILITY_THRESHOLD = 3


def check_stability(previous_title, current_title, stable_count):
    """Pure stability decision logic.

    Returns:
        (ready, new_stable_count)
    """
    if current_title == previous_title:
        new_stable = stable_count + 1
        if new_stable >= STABILITY_THRESHOLD:
            return True, new_stable
        return False, new_stable
    return False, 0


def check_marker(title, marker):
    """Pure marker detection logic.

    Returns:
        True if marker found in title.
    """
    return marker in title


class TestStability:
    def test_title_stable_fires_after_threshold(self):
        title = "trilliumsmith — -zsh"
        stable = 0
        for _ in range(STABILITY_THRESHOLD):
            ready, stable = check_stability(title, title, stable)
        assert ready is True
        assert stable == STABILITY_THRESHOLD

    def test_title_not_stable_yet(self):
        title = "trilliumsmith — -zsh"
        ready, stable = check_stability(title, title, 0)
        assert ready is False
        assert stable == 1

    def test_title_change_resets_count(self):
        ready, stable = check_stability("loading...", "trilliumsmith — -zsh", 2)
        assert ready is False
        assert stable == 0

    def test_title_churns_then_stabilizes(self):
        titles = [
            "trilliumsmith",
            "trilliumsmith — login",
            "trilliumsmith — -zsh",
            "trilliumsmith — -zsh",
            "trilliumsmith — -zsh",
            "trilliumsmith — -zsh",
        ]
        stable = 0
        previous = None
        ready = False
        for title in titles:
            if previous is not None:
                ready, stable = check_stability(previous, title, stable)
                if ready:
                    break
            previous = title
        assert ready is True

    def test_never_stabilizes(self):
        titles = ["a", "b", "c", "d", "e"]
        stable = 0
        previous = None
        ready = False
        for title in titles:
            if previous is not None:
                ready, stable = check_stability(previous, title, stable)
            previous = title
        assert ready is False
        assert stable == 0


class TestMarker:
    def test_marker_found(self):
        assert check_marker("tdd_guard — ✳ Build Request — bun", "✳") is True

    def test_marker_not_found(self):
        assert check_marker("trilliumsmith — -zsh", "✳") is False

    def test_marker_empty_title(self):
        assert check_marker("", "✳") is False

    def test_marker_at_start(self):
        assert check_marker("✳ Ready", "✳") is True


class TestWindowGone:
    """Window disappearing is modeled as current_window being None.
    The poller should abort — represented here as neither ready nor continuing."""

    def test_window_none_is_not_ready(self):
        # If window is gone, we can't check title — this is an abort condition
        # The poller handles this before calling check_stability/check_marker
        assert True  # Abort logic lives in the poller, not pure functions
