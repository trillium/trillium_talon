# Discord Keyboard Navigation Reference

A comprehensive reference of Discord keyboard shortcuts for use with Talon voice
control. Shortcuts are listed with both macOS and Windows/Linux key combinations.

Note: Keyboard shortcuts are only available on the desktop and browser versions
of Discord. Press Ctrl+/ (Windows) or Cmd+/ (Mac) inside Discord to view the
built-in shortcut overlay.

---

## Navigation: Servers

| Action                                  | macOS               | Windows / Linux        |
|-----------------------------------------|---------------------|------------------------|
| Previous server                         | Cmd+Opt+Up          | Ctrl+Alt+Up            |
| Next server                             | Cmd+Opt+Down        | Ctrl+Alt+Down          |
| Toggle between DMs and last server      | Cmd+Opt+Right       | Ctrl+Alt+Right         |

## Navigation: Channels and DMs

| Action                                  | macOS               | Windows / Linux        |
|-----------------------------------------|---------------------|------------------------|
| Previous channel / DM                   | Opt+Up              | Alt+Up                 |
| Next channel / DM                       | Opt+Down            | Alt+Down               |
| Previous unread channel                 | Opt+Shift+Up        | Alt+Shift+Up           |
| Next unread channel                     | Opt+Shift+Down      | Alt+Shift+Down         |
| Previous channel with unread mentions   | Cmd+Opt+Shift+Up    | Ctrl+Alt+Shift+Up      |
| Next channel with unread mentions       | Cmd+Opt+Shift+Down  | Ctrl+Alt+Shift+Down    |
| Jump to oldest unread message           | Shift+PageUp        | Shift+PageUp           |

## Quick Switcher

| Action                                  | macOS               | Windows / Linux        |
|-----------------------------------------|---------------------|------------------------|
| Open quick switcher                     | Cmd+K               | Ctrl+K                 |

Inside the quick switcher, prefix your query to filter results:

- `#` -- search channels
- `@` -- search users
- `!` -- search voice channels
- `*` -- search servers

## Search

| Action                                  | macOS               | Windows / Linux        |
|-----------------------------------------|---------------------|------------------------|
| Search current channel                  | Cmd+F               | Ctrl+F                 |
| Search all channels (server-wide)       | Cmd+Shift+F         | Ctrl+Shift+F           |

## Messages

| Action                                  | macOS               | Windows / Linux        |
|-----------------------------------------|---------------------|------------------------|
| Edit last sent message                  | Up (in empty input) | Up (in empty input)    |
| Scroll chat up                          | PageUp              | PageUp                 |
| Scroll chat down                        | PageDown            | PageDown               |
| Mark channel as read                    | Esc                 | Esc                    |
| Mark server as read                     | Shift+Esc           | Shift+Esc              |

### Message Actions (when a message is focused)

These single-key shortcuts work when a message is selected via keyboard
navigation (arrow keys or Tab to reach the message list):

| Action                                  | Key                 |
|-----------------------------------------|---------------------|
| Edit message                            | E                   |
| Delete message                          | Backspace           |
| Reply to message                        | R                   |
| Pin message                             | P                   |
| Add reaction                            | +                   |
| Quote message                           | Q                   |
| Forward message                         | F                   |
| Copy message text                       | Cmd+C / Ctrl+C      |
| Mark message as unread                  | Opt+Enter / Alt+Enter|

## UI Panels and Pickers

| Action                                  | macOS               | Windows / Linux        |
|-----------------------------------------|---------------------|------------------------|
| Toggle pinned messages                  | Cmd+P               | Ctrl+P                 |
| Toggle inbox / mentions                 | Cmd+I               | Ctrl+I                 |
| Toggle member list                      | Cmd+U               | Ctrl+U                 |
| Open emoji picker                       | Cmd+E               | Ctrl+E                 |
| Open GIF picker                         | Cmd+G               | Ctrl+G                 |
| Open sticker picker                     | Cmd+S               | Ctrl+S                 |
| Upload file                             | Cmd+Shift+U         | Ctrl+Shift+U           |
| Mark top inbox channel read             | Cmd+Shift+E         | Ctrl+Shift+E           |

## Text Formatting

| Action                                  | macOS               | Windows / Linux        |
|-----------------------------------------|---------------------|------------------------|
| Bold                                    | Cmd+B               | Ctrl+B                 |
| Italic                                  | Cmd+I               | Ctrl+I                 |
| Underline                               | Cmd+U               | Ctrl+U                 |

## Voice and Video

| Action                                  | macOS               | Windows / Linux        |
|-----------------------------------------|---------------------|------------------------|
| Toggle mute                             | Cmd+Shift+M         | Ctrl+Shift+M           |
| Toggle deafen                           | Cmd+Shift+D         | Ctrl+Shift+D           |
| Answer incoming call                    | Cmd+Enter           | Ctrl+Enter             |
| Decline incoming call                   | Esc                 | Esc                    |
| Go to current call / voice channel      | Cmd+Opt+A           | Ctrl+Shift+Alt+V       |
| Start call in current DM                | Ctrl+'              | Ctrl+'                 |

## Accessibility and Keyboard-Only Navigation

Discord has a dedicated keyboard navigation mode. When enabled, a blue focus
ring appears around the currently focused element.

| Action                                  | Key                 |
|-----------------------------------------|---------------------|
| Move through interactive elements       | Tab                 |
| Move backwards through elements         | Shift+Tab           |
| Jump to next app section                | F6                  |
| Jump to previous app section            | Shift+F6            |
| Navigate lists (servers, channels, messages) | Arrow Keys     |
| Activate / click focused element        | Enter or Space      |
| Close menu / modal / go back            | Esc                 |

### F6 Section Order

Pressing F6 cycles through four main sections in order:

1. Server list
2. Channel list
3. Messages / chat area
4. Members list or search results (if open)

### Drag and Drop (Servers)

| Action                                  | Key                 |
|-----------------------------------------|---------------------|
| Pick up server to reorder               | Cmd+D / Ctrl+D      |
| Move server while held                  | Arrow Keys          |
| Drop server in new position             | Enter               |

## Application

| Action                                  | macOS               | Windows / Linux        |
|-----------------------------------------|---------------------|------------------------|
| Open user settings                      | Cmd+,               | Ctrl+,                 |
| Show keyboard shortcuts overlay         | Cmd+/               | Ctrl+/                 |
| Create or join a server                 | Cmd+Shift+N         | Ctrl+Shift+N           |
| Create private group DM                 | Cmd+Shift+T         | Ctrl+Shift+T           |
| Show help                               | Cmd+Shift+H         | Ctrl+Shift+H           |

---

## Notes for Talon Integration

The existing Talon voice commands for Discord are defined in the sibling files:

- `discord.talon` -- voice command definitions
- `discord.py` -- cross-platform action declarations
- `discord_mac.py` -- macOS key bindings
- `discord_win.py` -- Windows/Linux key bindings

Several shortcuts listed above are not yet mapped to Talon voice commands,
including:

- Text formatting (Bold, Italic, Underline)
- Search (Cmd/Ctrl+F, Cmd/Ctrl+Shift+F)
- User settings (Cmd/Ctrl+,)
- Create/join server (Cmd/Ctrl+Shift+N)
- Create private group (Cmd/Ctrl+Shift+T)
- F6 section jumping
- Drag-and-drop server reordering
- Message-focused single-key actions (R, Q, +, F, P, E, Backspace)
- Start call in DM (Ctrl+')
- Screen share (Ctrl+Shift+L on Windows)

These represent opportunities to expand the Talon Discord command set.
