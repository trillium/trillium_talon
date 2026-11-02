# Stow — one-utterance capture / fetch across the brain federation stores.
# See stow.py. The spoken store name is translated to the real CLI by
# brain_store.talon-list, so you never voice "bd" / "beads" / "federated bead store".

# Capture a thought to a store (fire-and-forget + notification).
stow <user.brain_store> <user.text>$:
    user.store_capture(brain_store, user.text)

# Search a store; results appear in the focused terminal.
fetch <user.brain_store> <user.text>$:
    user.store_fetch(brain_store, user.text)
