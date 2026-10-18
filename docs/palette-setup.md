# Add a device to the palette

The palette is a web page served by the Mac running Talon. Any phone, tablet or laptop on
the tailnet can use it; nothing is installed and no token is needed.

1. Open `http://mini0:7399/` in the device's browser (the tailnet must be up on it).
2. Add it to the home screen: iOS Safari **Share → Add to Home Screen**; Android Chrome
   **⋮ → Add to Home screen**.
3. Search for a command, tap it to run it on the Mac. A command with a slot opens a small
   form first.

Reads and `/execute` are open on the tailnet by default on mini0, so there is nothing to
paste or sign in to. The tailnet is the security boundary; see `docs/palette-feed.md`.

## First-run guide

The first visit shows a short block: what the page is (the voice commands active on the
Mac right now) and one search tip (type a few letters in order: "pbnow" finds "playback
now"). **Got it** hides it, and so does your first successful run.

## "engine_inactive"

The page shows the hint `engine_inactive` when Talon is running but has no speech engine
attached, so a tap could not do anything. Nothing is wrong with the page. Start or attach
the speech engine on the Mac, then tap the command again. Searching still works while the
engine is off.

## Recents and favorites

- **Recent** lists the last 10 commands you ran successfully, newest first. Running one
  again moves it to the top. Tap an entry to run it again.
- **Favorites** are commands you starred with the ☆ on a result row. They sit above the
  results; tap the ★ to remove one.
- Both live in the browser's `localStorage` on that device, per browser: they are not
  synced, and a phone's Safari tab and its home-screen app are separate stores. Clearing
  site data or using a private window loses them. If storage is unavailable, the page
  still works and simply remembers nothing.
