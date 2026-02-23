"""Disable auto-capitalization when dictating in terminals."""

from talon import Context, actions

ctx = Context()
ctx.matches = r"""
tag: terminal
"""


@ctx.action_class("user")
class UserActions:
    def dictation_insert(text: str, auto_cap: bool = True):
        """In terminals, never auto-capitalize dictated text."""
        actions.next(text, auto_cap=False)
