"""Phone emission receiver: accepts a phone-computed acoustic emission (TPE1) and feeds
Talon's own W2lEngine decoder in place of its encoder.

Nothing here registers with `speech_system`, opens a socket, or changes a setting; callers
hand a `W2lEngine` (a private one, for now) to `PhoneReceiver`. See docs/phone-receiver.md.
"""
