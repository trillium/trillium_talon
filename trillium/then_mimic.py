from talon import speech_system, actions, cron

_pending_mimic: list[str] = []


def on_pre_phrase(d):
    global _pending_mimic
    words = d.get("phrase", [])
    if not words:
        return

    word_strings = [str(w) for w in words]
    try:
        then_idx = word_strings.index("then")
    except ValueError:
        return

    remaining = word_strings[then_idx + 1 :]
    if not remaining:
        return

    # Truncate phrase to only include words before "then"
    d["phrase"] = words[:then_idx]
    if "parsed" in d:
        seq = d["parsed"]._sequence
        new_seq = []
        word_count = 0
        for capture in seq:
            capture_words = str(capture).split()
            word_count += len(capture_words)
            if word_count <= then_idx:
                new_seq.append(capture)
            else:
                break
        d["parsed"]._sequence = new_seq

    # Schedule mimic of remaining words after current phrase completes
    _pending_mimic = remaining
    cron.after("50ms", _do_mimic)


def _do_mimic():
    global _pending_mimic
    words = _pending_mimic
    _pending_mimic = []
    if words:
        actions.mimic(" ".join(words))


speech_system.register("pre:phrase", on_pre_phrase)
