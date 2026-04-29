mode: all
-
^discord (mute | unmute)$: user.discord_mute()
trillium out$:
    user.discord_mute()

alexa please (mute | unmute) trillium$:
    user.discord_mute()

^zoom (mute | unmute)$:
    user.zoom_mute()

^zoom (toggle video)$:
    user.zoom_toggle_video()

key(cmd-ctrl-alt-shift-z):
    user.zoom_mute()
