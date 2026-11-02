# CapsLock-alone fires F19 (via Karabiner); this routes it to herdr's ctrl+b prefix.
# herdr is not a standalone macOS app (runs in WezTerm), so app: can't match it;
# user.herder_panel is the focus signal (see herder_panel.py).
mode: all
tag: user.herder_panel
-
key(f19): key(ctrl-b)
