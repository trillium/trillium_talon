# Say a Herdr tab's name, then "links" (e.g. "local links", "fixer links",
# "zephyr links") to switch Herdr to that tab and show the URLs seen in it.
# Tab names are the recall herdr_tab_names list; there is no bare "links".
-
^{user.herdr_tab_names} links$: user.links_show_tab(herdr_tab_names)
