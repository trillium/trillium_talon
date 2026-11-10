from talon import Module, actions

mod = Module()

TAG = "clear_text"

# Stack of deleted text — each destroy pushes, each restore pops
_destroy_stack: list[str] = []


@mod.action_class
class Actions:
    def text_length(text: str) -> int:
        """Return the length of the given text"""
        return len(text)

    def clear_last_dictation():
        """Delete the last dictation utterance by pressing backspace for each character"""
        from ..core.text import phrase_history as ph_module

        history = ph_module.phrase_history
        deleted = history[0] if history else ""
        if deleted:
            _destroy_stack.append(deleted)
        actions.user.clear_last_phrase()
        actions.user.show_follow_on_hints("destroy", deleted)

    def clear_back_to_word(text: str):
        """Delete back to the given word using phrase history as a continuous buffer.

        Concatenates all phrase history entries (oldest first) into one buffer,
        finds the target text (case-insensitive), calculates how many characters
        from the match start to buffer end, presses backspace that many times,
        and trims phrase history accordingly.

        Falls back to character-count deletion if the word isn't found.
        """
        from ..core.text import phrase_history as ph_module

        history = ph_module.phrase_history
        if not history:
            # No history — fall back to character-count deletion
            length = len(text)
            _destroy_stack.append(text)
            print(
                TAG,
                f"clear_back_to_word fallback (no history) text='{text}' length={length}",
            )
            for _ in range(length):
                actions.key("backspace")
            actions.user.show_follow_on_hints("destroy", text)
            return

        # Build continuous buffer: oldest first
        reversed_history = list(reversed(history))
        buffer = "".join(reversed_history)

        # Search case-insensitive for the target text
        buffer_lower = buffer.lower()
        target_lower = text.lower()
        match_pos = buffer_lower.rfind(target_lower)

        if match_pos == -1:
            # Not found — fall back to character-count deletion
            length = len(text)
            _destroy_stack.append(text)
            print(
                TAG,
                f"clear_back_to_word fallback (not found) text='{text}' length={length}",
            )
            for _ in range(length):
                actions.key("backspace")
            actions.user.show_follow_on_hints("destroy", text)
            return

        # Characters from match start to end of buffer
        chars_to_delete = len(buffer) - match_pos
        deleted = buffer[match_pos:]
        _destroy_stack.append(deleted)
        print(
            TAG,
            f"clear_back_to_word text='{text}' match_pos={match_pos} chars_to_delete={chars_to_delete}",
        )

        for _ in range(chars_to_delete):
            actions.key("backspace")

        # Now trim phrase history.
        # We need to remove chars_to_delete characters worth of phrases from the
        # end of the buffer (most recent phrases = index 0 in history).
        remaining_to_trim = chars_to_delete
        while remaining_to_trim > 0 and ph_module.phrase_history:
            most_recent = ph_module.phrase_history[0]
            if len(most_recent) <= remaining_to_trim:
                # Fully consumed — remove it
                remaining_to_trim -= len(most_recent)
                ph_module.phrase_history.pop(0)
            else:
                # Partially consumed — trim from the end
                keep_count = len(most_recent) - remaining_to_trim
                ph_module.phrase_history[0] = most_recent[:keep_count]
                remaining_to_trim = 0

        actions.user.show_follow_on_hints("destroy", deleted)

    def clear_left_by_text(text: str):
        """Delete characters to the left based on the length of the given text"""
        length = len(text)
        print(TAG, f"clear_left text='{text}' length={length}")
        for _ in range(length):
            actions.key("backspace")

    def clear_right_by_text(text: str):
        """Delete characters to the right based on the length of the given text"""
        length = len(text)
        print(TAG, f"clear_right text='{text}' length={length}")
        for _ in range(length):
            actions.key("delete")

    def go_left_by_text(text: str):
        """Move cursor left by the character length of the given text"""
        length = len(text)
        print(TAG, f"go_left text='{text}' length={length}")
        for _ in range(length):
            actions.edit.left()

    def go_right_by_text(text: str):
        """Move cursor right by the character length of the given text"""
        length = len(text)
        print(TAG, f"go_right text='{text}' length={length}")
        for _ in range(length):
            actions.edit.right()

    def restore_destroy():
        """Re-type the text that was deleted by the last destroy command.

        Pops from the stack, so repeated calls unwind multiple destroys.
        """
        if not _destroy_stack:
            print(TAG, "restore_destroy: nothing to restore")
            return
        text = _destroy_stack.pop()
        print(
            TAG,
            f"restore_destroy: restoring {len(text)} chars ({len(_destroy_stack)} remaining in stack)",
        )
        actions.insert(text)
        actions.user.add_phrase_to_history(text)
        # Show hint for next level if stack still has entries
        if _destroy_stack:
            actions.user.show_follow_on_hints("destroy", _destroy_stack[-1])
