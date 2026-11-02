# Crew — voice verb+target orchestration over herdr + firstmate.
#   Focus:   "herder muse"
#   Send:    "herder muse say deploy the branch bravely"
#   Rotate:  "herder next working"  /  "herder next"
#   Refresh: "herder refresh"

# Focus an agent pane by name (bare verb = focus).
herder <user.herder_targets>$:
    user.herder_focus(herder_targets)

# Send prose to an agent pane. End with an ender (bravely/lap) to also submit.
herder <user.herder_targets> say <user.text>$:
    user.herder_send(herder_targets, text)

herder <user.herder_targets> say <user.text> {user.dictation_ender}$:
    user.herder_send(herder_targets, text)
    user.herder_submit(herder_targets)

# Cycle focus through the fleet by status.
herder [next] working$:
    user.herder_rotate("working")
herder [next] idle$:
    user.herder_rotate("idle")
herder [next] blocked$:
    user.herder_rotate("blocked")
herder next$:
    user.herder_rotate("all")

# Re-pull the sayable agent list from live herdr state.
herder refresh$:
    user.herder_refresh_targets()
