os: mac
-
demo down: user.smooth_scroll_mimic("down")
demo flat down: user.smooth_scroll_demo("down")
demo up: user.smooth_scroll_mimic("up")
demo flat up: user.smooth_scroll_demo("up")
demo farther: user.smooth_scroll_scale(1.25)
demo shorter: user.smooth_scroll_scale(0.8)
demo longer glide: user.smooth_scroll_glide(true)
demo shorter glide: user.smooth_scroll_glide(false)
demo distance <number_small>: user.smooth_scroll_set("pixels", number_small)
demo frames <number_small>: user.smooth_scroll_set("frames", number_small)
demo settings: user.smooth_scroll_show()
demo record: user.smooth_scroll_record(8)
demo replay <number_small>: user.smooth_scroll_replay(number_small)
demo slower: user.smooth_scroll_stretch(1.15)
demo faster: user.smooth_scroll_stretch(0.87)
demo reset: user.smooth_scroll_reset()
demo panel: user.smooth_scroll_panel_show()
demo panel close: user.smooth_scroll_panel_hide()

settings():
    # Defaults. Edit and save, or use the voice commands above (voice-set values
    # win until you say "demo reset").
    user.smooth_scroll_pixels = 11
    user.smooth_scroll_frames = 30
    user.smooth_scroll_frame_ms = 16
    user.smooth_scroll_decay = 0.92
    user.smooth_scroll_min_pixels = 0.5
