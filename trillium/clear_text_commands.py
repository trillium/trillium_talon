from talon import Module, actions

mod = Module()

TAG = "clear_text"


@mod.action_class
class Actions:
    def text_length(text: str) -> int:
        """Return the length of the given text"""
        return len(text)

    def clear_last_dictation():
        """Delete the last dictation utterance by pressing backspace for each character"""
        actions.user.clear_last_phrase()

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
