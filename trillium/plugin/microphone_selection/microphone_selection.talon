settings():
    # Comma-separated mic names (or substrings) to hide from the overlay.
    # Example: "BlackHole, ZoomAudioDevice, CADefaultDeviceAggregate"
    user.microphone_excluded = ""

^microphone (show | list)$: user.microphone_selection_toggle()
^microphone close$: user.microphone_selection_hide()
^microphone (pick | choose) <user.overlay_select>$: user.microphone_select(overlay_select)
^microphone exclude <user.overlay_select>$: user.microphone_exclude(overlay_select)
^microphone include <user.overlay_select>$: user.microphone_include(overlay_select)
^microphone exclude reset$: user.microphone_exclude_reset()
