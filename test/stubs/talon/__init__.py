"""Talon API stubs for testing.

This module mocks the core Talon runtime so that plugins can be tested
without the Talon application running. Import paths mirror the real Talon API:

    from talon import Module, Context, actions, app, ui, clip, cron
    from talon.canvas import Canvas
    from talon.skia import Paint, Rect
    from talon.types.point import Point2d
    from talon.experimental.parrot import ParrotSystem

Sub-modules:
    talon.canvas        - Canvas overlay API
    talon.screen        - Screen enumeration
    talon.skia          - Skia 2D graphics (Paint, Rect, Path, Canvas)
    talon.types         - Type definitions (Point2d, Rect)
    talon.ui            - Window/screen management, Rect, events
    talon.grammar       - Speech grammar types (Phrase, Capture)
    talon.debug         - Logging/debugging utilities
    talon.experimental  - Experimental APIs (parrot, textarea)
    talon.scripting     - Scripting type introspection
"""

import inspect
from typing import Callable


class RegisteredActionsAccessor:
    def __init__(self, registered_actions, namespace):
        self.registered_actions = registered_actions
        self.namespace = namespace

    def __getattr__(self, name):
        for category in ("test", "module"):
            cat_actions = self.registered_actions[category]
            if self.namespace in cat_actions:
                if name in cat_actions[self.namespace]:
                    return cat_actions[self.namespace][name]

        raise AttributeError(f"Couldn't find action {self.namespace}.{name}")

    def __call__(self, *args, **kwargs):
        # Provide a useful error message if people try something like
        # actions.my_action() when they should do actions.user.my_action()
        raise RuntimeError(f"actions.{self.namespace}() is not an available action")


class Actions:
    """
    Implements something like talon.actions. You can use the register
    function to add in an action definition from your test (e.g. a mock).
    """

    def __init__(self):
        self.registered_actions = {
            "module": {},
            "test": {},
        }

        # Some built in actions
        self.register_module_action("", "key", lambda x: None)
        self.register_module_action("", "insert", lambda x: None)
        self.register_module_action("", "sleep", lambda x: None)
        self.register_module_action("edit", "selected_text", lambda: "test")

    def reset_test_actions(self):
        self.registered_actions["test"] = {}

    def register_module_action(self, namespace: str, name: str, func: Callable):
        """
        Registers an action to the module category. This should
        only be called by importing files containing module definitions.
        It won't be reset between test runs (or test files). Use
        register_test_action and reset_test_actions to temporarily override
        actions.
        """

        self._register_action("module", namespace, name, func)

    def register_test_action(self, namespace: str, name: str, func: Callable):
        """
        Registers the given action, use like:

            actions.register("user.my_action", lambda: None)
        """

        self._register_action("test", namespace, name, func)

    def _register_action(
        self, category: str, namespace: str, name: str, func: Callable
    ):
        if namespace not in self.registered_actions[category]:
            self.registered_actions[category][namespace] = {}

        self.registered_actions[category][namespace][name] = func

    def __getattr__(self, name):
        try:
            # If name exists as a direct property of this class, then
            # use that
            return object.__getattribute__(self, name)
        except AttributeError:
            pass

        try:
            # Else if name is an action like actions.key
            # that has no namespace then return that.
            default_accessor = RegisteredActionsAccessor(self.registered_actions, "")
            return getattr(default_accessor, name)
        except AttributeError:
            # Otherwise treat name as an action namespace
            # (like actions.user).
            return RegisteredActionsAccessor(self.registered_actions, name)


class Module:
    """
    Implements something like the Module class built in to Talon
    """

    def list(self, *args, **kwargs):
        pass

    def setting(self, *args, **kwargs):
        pass

    def capture(self, rule=None):
        def __funcwrapper(func):
            def __inner(*args, **kwargs):
                return func(*args, **kwargs)

            return __inner

        return __funcwrapper

    def tag(self, name, desc=None):
        pass

    def action_class(self, target_class):
        # Register all the methods on the class with our actions implementation
        for name, func in inspect.getmembers(target_class, inspect.isfunction):
            actions.register_module_action("user", name, func)

        return target_class


class Context:
    """
    Implements something like the Context class built in to Talon
    """

    lists = {}
    tags = set()
    settings = {}
    matches = ""

    def action_class(self, path=None):
        def __funcwrapper(clazz):
            return clazz

        return __funcwrapper

    def capture(self, name: str, rule: str = None):
        def __funcwrapper(func):
            def __inner(*args, **kwargs):
                return func(*args, **kwargs)

            return __inner

        return __funcwrapper


class ImgUI:
    """
    Stub out ImgUI so we don't get crashes
    """

    GUI = None

    def open(self):
        def __funcwrapper(func):
            def __inner(*args, **kwargs):
                return func(*args, **kwargs)

            return __inner

        return __funcwrapper


class Settings:
    """Mock talon.settings — global settings accessor.

    In real Talon, settings are declared via Module.setting() and
    read via settings.get("user.my_setting", default).
    """

    _values = {}

    def get(self, name, default=None):
        return self._values.get(name, default)

    def __getitem__(self, name):
        return self._values[name]

    def __contains__(self, name):
        return name in self._values

    # Test helpers

    @classmethod
    def set(cls, name, value):
        """Test helper: set a setting value."""
        cls._values[name] = value

    @classmethod
    def reset(cls):
        """Test helper: clear all settings."""
        cls._values.clear()


class Registry:
    """Mock Talon registry — tracks all loaded modules, contexts, actions, lists.

    In real Talon, registry provides introspection over everything loaded.
    """

    lists = {}
    tags = set()
    commands = {}
    contexts = []
    decls = type("decls", (), {"lists": {}, "tags": set()})()

    def __init__(self):
        self._callbacks = {}

    def register(self, event, callback):
        self._callbacks.setdefault(event, []).append(callback)

    def unregister(self, event, callback):
        if event in self._callbacks:
            self._callbacks[event] = [
                cb for cb in self._callbacks[event] if cb != callback
            ]


class Resource:
    """
    Implements something like the talon resource system
    """

    def open(self, path: str, mode: str = "r"):
        return open(path, mode, encoding="utf-8")

    def watch(self, path: str):
        return lambda f: f


class App:
    """
    Implements something like the talon app variable
    """

    platform = "mac"

    @staticmethod
    def notify(title="", body="", sound=False):
        """Show a notification. Noop in tests."""
        pass

    @staticmethod
    def register(event, callback):
        """Register app event callback (launch, ready, etc.)."""
        pass

    @staticmethod
    def unregister(event, callback):
        """Unregister app event callback."""
        pass


class Clip:
    """Mock clipboard API.

    Usage:
        clip.set_text("hello")
        text = clip.text()
    """

    _text = ""
    _image = None

    @classmethod
    def text(cls):
        return cls._text

    @classmethod
    def set_text(cls, text):
        cls._text = text

    @classmethod
    def image(cls):
        return cls._image

    @classmethod
    def set_image(cls, image):
        cls._image = image

    @classmethod
    def clear(cls):
        cls._text = ""
        cls._image = None

    # Context manager for clipboard revert
    def __enter__(self):
        self._saved_text = self._text
        return self

    def __exit__(self, *args):
        type(self)._text = self._saved_text


class Cron:
    """Mock cron (timer) API.

    Usage:
        job = cron.interval("500ms", callback)
        cron.cancel(job)
    """

    _jobs = []
    _next_id = 0

    @classmethod
    def interval(cls, period, callback):
        """Schedule repeating callback. Returns job handle."""
        cls._next_id += 1
        job = cls._next_id
        cls._jobs.append({"id": job, "type": "interval", "callback": callback})
        return job

    @classmethod
    def after(cls, delay, callback):
        """Schedule one-shot callback. Returns job handle."""
        cls._next_id += 1
        job = cls._next_id
        cls._jobs.append({"id": job, "type": "after", "callback": callback})
        return job

    @classmethod
    def cancel(cls, job):
        """Cancel a scheduled job."""
        cls._jobs = [j for j in cls._jobs if j["id"] != job]

    # Test helpers

    @classmethod
    def trigger(cls, job_id=None):
        """Test helper: fire a job's callback. If no id, fires all."""
        for j in cls._jobs:
            if job_id is None or j["id"] == job_id:
                j["callback"]()

    @classmethod
    def reset(cls):
        """Test helper: cancel all jobs."""
        cls._jobs.clear()
        cls._next_id = 0


class Ctrl:
    """Mock keyboard/mouse control API."""

    @staticmethod
    def mouse_click(button=0, hold=None, times=1):
        pass

    @staticmethod
    def mouse_scroll(x=0, y=0):
        pass

    @staticmethod
    def mouse_move(x, y):
        pass

    @staticmethod
    def key_press(key, modifiers=None):
        pass


class Noise:
    """Mock noise detection API (hiss, pop).

    This is the simpler noise API. For advanced noise detection,
    see talon.experimental.parrot.
    """

    _callbacks = {}

    @classmethod
    def register(cls, noise_name, callback):
        cls._callbacks.setdefault(noise_name, []).append(callback)

    @classmethod
    def unregister(cls, noise_name, callback):
        if noise_name in cls._callbacks:
            cls._callbacks[noise_name] = [
                cb for cb in cls._callbacks[noise_name] if cb != callback
            ]

    # Test helpers

    @classmethod
    def simulate(cls, noise_name, active=True):
        """Test helper: simulate a noise event."""
        for cb in cls._callbacks.get(noise_name, []):
            cb(active)

    @classmethod
    def reset(cls):
        cls._callbacks.clear()


class Scope:
    """Mock scope — provides current context state (modes, tags, etc.)."""

    _data = {}

    @classmethod
    def get(cls, key, default=None):
        return cls._data.get(key, default)

    @classmethod
    def update(cls, data):
        cls._data.update(data)

    @classmethod
    def reset(cls):
        cls._data.clear()


class Fs:
    """Mock filesystem watcher."""

    _callbacks = {}

    @classmethod
    def watch(cls, path, callback):
        cls._callbacks[path] = callback

    @classmethod
    def unwatch(cls, path, callback=None):
        cls._callbacks.pop(path, None)

    # Test helper
    @classmethod
    def simulate_change(cls, path, flags=None):
        """Test helper: simulate a file change event."""
        if path in cls._callbacks:
            cls._callbacks[path](path, flags or set())


# Module-level singletons
actions = Actions()
app = App
clip = Clip()
cron = Cron
ctrl = Ctrl
imgui = ImgUI()
noise = Noise
scope = Scope
settings = Settings()
resource = Resource()
registry = Registry()
fs = Fs

# Indicate to test files that they should load since we're running in test mode
test_mode = True
