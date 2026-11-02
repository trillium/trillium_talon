# Go to — unified addressing across herdr + Parlay. See goto.py.
# "go to muse" focuses BOTH the herdr pane and (once the select-tab patch lands)
# the Parlay tab. Reuses the herder plugin's live agent list.
#
# NOTE: prototype loads globally; scope to terminal/panel context once happy.

go to {user.herder_targets}$:
    user.goto_surface(herder_targets)
