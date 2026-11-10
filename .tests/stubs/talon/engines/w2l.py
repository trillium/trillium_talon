"""talon.engines.w2l stubs (wav2letter engine word types).

The production on_phrase/analyze_phrase chain imports these for capture
type discrimination. Only the attributes used by the analyzed code are
provided.
"""


class DecodeWord:
    """A decoded word token from the speech engine."""

    def __init__(self, word=None):
        self.word = word


class WordMeta:
    """Metadata wrapper around a decoded word."""

    def __init__(self, word=None, **kwargs):
        self.word = word
        for k, v in kwargs.items():
            setattr(self, k, v)
