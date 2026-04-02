settings():
    # Adjust the scale of the imgui
    imgui.scale = 1.3
    imgui.dark_mode = true

    # Disable subtitles (large text display after commands)
    user.subtitles_show = false

    # If `true`, automatically show the picker GUI when the file manager has focus
    user.file_manager_auto_show_pickers = false

    # Set the number of command lines to display per help page
    user.help_max_command_lines_per_page = 50

    # Set the number of contexts to display per help page
    user.help_max_contexts_per_page = 20

    # Set the scroll amount for continuous scroll/gaze scroll
    user.mouse_continuous_scroll_amount = 80

    # If `true`, stop continuous scroll/gaze scroll with a pop
    user.mouse_enable_pop_stops_scroll = true

    # Choose how pop click should work in 'control mouse' mode
    # 0 = off
    # 1 = on with eyetracker but not zoom mouse mode
    # 2 = on but not with zoom mouse mode
    user.mouse_enable_pop_click = 0

    # If `true`, use a hissing noise to scroll continuously
    user.mouse_enable_hiss_scroll = false

    # When enabled, the 'Scroll Mouse' GUI will not be shown.
    user.mouse_hide_mouse_gui = false

    # If `true`, hide the cursor when enabling zoom mouse
    user.mouse_wake_hides_cursor = false

    # The amount to scroll up/down (equivalent to mouse wheel on Windows by default)
    user.mouse_wheel_down_amount = 120

    # Reverse scroll direction to compensate for OS-level natural scrolling
    user.mouse_wheel_reverse_direction = true

    # Set the amount to scroll left/right
    user.mouse_wheel_horizontal_amount = 40

    # If `true`, start mouse grid numbering on the bottom left (vs. top left)
    user.grids_put_one_bottom_left = true

    # Set the default number of command history lines to display
    user.command_history_display = 10

    # Set the total number of command history lines to display
    user.command_history_size = 50

    # Uncomment to add a directory (relative to the Talon user dir) with additional
    # .snippet files. Changing this setting requires a restart of Talon.
    # user.snippets_dir = "snippets"

    # Uncomment to insert text longer than 10 characters (customizable) by pasting from
    # the clipboard. This is often faster than typing.
    # user.paste_to_insert_threshold = 10

    # Uncomment to enable context-sensitive dictation. This determines how to format
    # (capitalize, space) dictation-mode speech by selecting & copying surrounding text
    # before inserting. This can be slow and may not work in some applications. You may
    # wish to enable this on a per-application basis.
    # user.context_sensitive_dictation = true

    # Choose how to resize windows moved across physical screens (eg. via `snap next`).
    # Default is 'proportional', which preserves window size : screen size ratio.
    # 'size aware' keeps absolute window size the same, except full-height or
    # -width windows are resized to stay full-height/width.
    # user.window_snap_screen = "size aware"

    # Twitch chat integration
    user.twitch_channel = "trilliumsmith"
    user.twitch_bot_username = "trilliumsmith"

    # Gaze OCR text overlay colors
    user.ocr_light_background_debug_color = "FF4444"
    user.ocr_dark_background_debug_color = "00AA00"

    # Mouse grid border setting
    user.grid_narrow_expansion = 25

# Uncomment to enable the curse yes/curse no commands (show/hide mouse cursor).
# See issue #688 for more detail: https://github.com/talonhub/community/issues/688
tag(): user.mouse_cursor_commands_enable

# Uncomment the below to enable support for saying numbers without a prefix.
# By default you need to say "numb one" to write "1". If you uncomment this,
# you can say "one" to write "1".
tag(): user.unprefixed_numbers
