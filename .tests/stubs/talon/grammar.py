"""Talon grammar stubs.

Provides mock types for speech grammar processing:
- Phrase: represents a spoken phrase
- Capture: represents a captured grammar match
- vm: talon.grammar.vm module — VM-level capture types
"""

import sys


class Phrase:
    """A spoken phrase from the speech engine."""

    def __init__(self, words=None):
        self._words = words or []

    def __iter__(self):
        return iter(self._words)

    def __len__(self):
        return len(self._words)

    def __str__(self):
        return " ".join(str(w) for w in self._words)


class Capture:
    """A grammar capture match."""

    def __init__(self, value=None):
        self.value = value

    def __str__(self):
        return str(self.value) if self.value else ""


class VMCapture:
    """VM-level capture."""

    def __init__(self, name=None, data=None, value=None):
        self.name = name
        self.data = data or []
        self.value = value if value is not None else self.data

    def unmapped(self):
        return [str(w) for w in self.data]


class VMListCapture:
    """VM-level list capture."""

    def __init__(self, name=None, value=None):
        self.name = name
        self.value = value


class vm:
    """Namespace mirroring the `talon.grammar.vm` module surface."""

    Phrase = Phrase
    VMCapture = VMCapture
    VMListCapture = VMListCapture


# The production code does `from talon.grammar.vm import ...`. `talon.grammar`
# is a plain module here (not a package), so register the vm submodule in
# sys.modules to make that import resolve against the stubs.
_vm_module = sys.modules.setdefault("talon.grammar.vm", sys.modules.get("talon.grammar.vm"))
if _vm_module is None or not hasattr(_vm_module, "VMCapture"):
    import types

    _vm_module = types.ModuleType("talon.grammar.vm")
    _vm_module.Phrase = Phrase
    _vm_module.VMCapture = VMCapture
    _vm_module.VMListCapture = VMListCapture
    sys.modules["talon.grammar.vm"] = _vm_module
