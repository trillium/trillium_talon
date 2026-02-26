speak clip$:
    user.speak_aloud(clip.text())

cancel:
    user.speak_aloud_cancel()

key(escape:passive):
    user.speak_aloud_cancel()
