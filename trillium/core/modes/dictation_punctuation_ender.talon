# Dictation punctuation ender: dictate text and end with punctuation
# e.g. "hello world question" → types "hello world?"
# e.g. "question" alone → just types "?"
# Edit dictation_punctuation_ender.talon-list to change/add ender words
mode: dictation
-
<user.raw_prose> {user.dictation_punctuation_ender}$:
    user.dictation_insert("{raw_prose}{dictation_punctuation_ender}")
{user.dictation_punctuation_ender}$:
    user.dictation_insert(dictation_punctuation_ender)
