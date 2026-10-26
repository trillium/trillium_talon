settings():
    user.mode_indicator_show = true
    user.mode_indicator_show_mic_name = true
    # Per-subscription quota panel (quota-axi) replaces the Claude-only usage text
    user.mode_indicator_show_usage = false
    user.quota_panel_show = true
    # Opacity (0=transparent, 1=opaque)
    user.mode_indicator_color_alpha = 0.75
    # Gradient brightness (0=darkest, 1=brightest)
    user.mode_indicator_color_gradient = 0.5
    # Colors
    user.mode_indicator_color_text = "EEE"
    user.mode_indicator_color_mute = "000000"
    user.mode_indicator_color_sleep = "3f3f3f"
    user.mode_indicator_color_dictation = "7d6900"
    user.mode_indicator_color_mixed = "1d5837"
    user.mode_indicator_color_command = "314974"
    user.mode_indicator_color_other = "7a7a7d"
    # Weekly usage limit reset: Monday at 5pm Pacific
    user.week_reset_day = 0
    user.week_reset_hour = 17
