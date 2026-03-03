"""Talon scripting types stubs."""


class ListTypeFull:
    """Full list type used in registry introspection."""

    def __init__(self, name="", description=""):
        self.name = name
        self.description = description
