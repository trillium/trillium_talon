"""Example: Testing cron (timer) based plugins.

This demonstrates how to test plugins that use talon.cron for scheduling.
Pattern: Register callbacks, use trigger() to fire them manually in tests.

Applicable to: repeaters, pollers, debounce handlers, auto-dismiss UIs
"""

import talon

if hasattr(talon, "test_mode"):
    from talon import cron

    # --- Simulated production code ---

    class Poller:
        """Polls at an interval, tracking state changes."""

        def __init__(self, check_fn):
            self.check_fn = check_fn
            self.last_value = None
            self.changes = []
            self._job = None

        def start(self):
            self._job = cron.interval("500ms", self._tick)

        def stop(self):
            if self._job:
                cron.cancel(self._job)
                self._job = None

        def _tick(self):
            current = self.check_fn()
            if current != self.last_value:
                self.changes.append((self.last_value, current))
                self.last_value = current

    class AutoDismiss:
        """Shows something, then auto-dismisses after a delay."""

        def __init__(self, dismiss_fn):
            self.dismiss_fn = dismiss_fn
            self._job = None
            self.visible = False

        def show(self, duration_ms=3000):
            self.visible = True
            if self._job:
                cron.cancel(self._job)
            self._job = cron.after(f"{duration_ms}ms", self._dismiss)

        def _dismiss(self):
            self.visible = False
            self._job = None
            self.dismiss_fn()

    # --- Tests ---

    def setup_function():
        talon.Cron.reset()

    def teardown_function():
        talon.Cron.reset()

    def test_poller_detects_changes():
        values = iter(["A", "A", "B", "B", "C"])
        poller = Poller(lambda: next(values))
        poller.start()

        # Simulate 5 ticks
        for _ in range(5):
            cron.trigger(poller._job)

        assert poller.changes == [(None, "A"), ("A", "B"), ("B", "C")]

    def test_poller_stop_cancels_job():
        poller = Poller(lambda: "X")
        poller.start()

        assert len(talon.Cron._jobs) == 1
        poller.stop()
        assert len(talon.Cron._jobs) == 0

    def test_auto_dismiss():
        dismissed = []
        ad = AutoDismiss(lambda: dismissed.append(True))

        ad.show(duration_ms=1000)
        assert ad.visible is True

        # Trigger the after() callback
        cron.trigger(ad._job)

        assert ad.visible is False
        assert len(dismissed) == 1

    def test_auto_dismiss_reshow_resets_timer():
        dismissed = []
        ad = AutoDismiss(lambda: dismissed.append(True))

        ad.show()
        first_job = ad._job

        ad.show()  # re-show cancels previous timer
        second_job = ad._job

        assert first_job != second_job
        assert ad.visible is True
