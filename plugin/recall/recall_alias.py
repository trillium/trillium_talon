"""
Recall Alias - Combine, rename, alias, promote, and pending-finish actions.
"""

from talon import actions
from . import recall_overlay
from . import recall_state
from .recall_state import (
    mod, saved_windows,
    pending_ctx, is_forbidden,
    save_to_disk, update_window_list,
    _cancel_pending,
)


@mod.action_class
class Actions:
    def recall_combine(primary: str, secondary: str):
        """Combine two saved windows: secondary becomes an alias of primary"""
        if primary not in saved_windows or secondary not in saved_windows:
            return
        if primary == secondary:
            return

        # Merge secondary's aliases into primary
        primary_info = saved_windows[primary]
        secondary_info = saved_windows[secondary]

        aliases = primary_info.get("aliases", [])
        # Add the secondary name itself as an alias
        if secondary not in aliases:
            aliases.append(secondary)
        # Also bring over any aliases the secondary had
        for alias in secondary_info.get("aliases", []):
            if alias not in aliases and alias != primary:
                aliases.append(alias)
        primary_info["aliases"] = aliases

        # Merge path if primary doesn't have one
        if not primary_info.get("path") and secondary_info.get("path"):
            primary_info["path"] = secondary_info["path"]

        # Remove secondary entry
        del saved_windows[secondary]

        save_to_disk()
        update_window_list()
        recall_overlay.flash(f'combined: {secondary} -> {primary}')
        print(f'[recall] combined: "{secondary}" is now an alias of "{primary}"')

    def recall_combine_start(primary: str):
        """Start two-step combine: show prompt and wait for second name"""
        if primary not in saved_windows:
            return

        recall_state._pending_mode = "combine"
        recall_state._pending_name = primary
        pending_ctx.tags = ["user.recall_pending_input"]
        recall_overlay.show_prompt(
            f'Combine with "{primary}"',
            "Say the name to merge as an alias...",
        )

    def recall_rename_start(name: str):
        """Start two-step rename: show prompt and wait for new name"""
        if name not in saved_windows:
            return

        recall_state._pending_mode = "rename"
        recall_state._pending_name = name
        pending_ctx.tags = ["user.recall_pending_input"]
        recall_overlay.show_prompt(
            f'Rename "{name}"',
            "Say the new name...",
        )

    def recall_alias_start(name: str):
        """Start two-step alias: show prompt and wait for alias"""
        print(f"[recall] alias_start: name={name!r}, pending_mode={recall_state._pending_mode!r}, pending_name={recall_state._pending_name!r}")

        # If we're already waiting for alias input, treat this as the alias
        if recall_state._pending_mode == "alias" and recall_state._pending_name:
            print(f"[recall] alias_start: already pending — treating {name!r} as alias for {recall_state._pending_name!r}")
            actions.user.recall_pending_finish(name)
            return

        if name not in saved_windows:
            print(f"[recall] alias_start: ABORT — name not found")
            return

        recall_state._pending_mode = "alias"
        recall_state._pending_name = name
        pending_ctx.tags = ["user.recall_pending_input"]
        print(f"[recall] alias_start: tag set, pending_mode={recall_state._pending_mode!r}, pending_name={recall_state._pending_name!r}")
        recall_overlay.show_prompt(
            f'Add alias for "{name}"',
            "Say the alias...",
        )

    def recall_pending_finish(spoken: str):
        """Complete whichever two-step command is pending"""
        print(f"[recall] pending_finish: raw spoken={spoken!r}, type={type(spoken).__name__}")

        # Normalize: <user.raw_prose> gives a Phrase/list, not a str
        if not isinstance(spoken, str):
            spoken = " ".join(str(w) for w in spoken)
        spoken = spoken.strip()

        print(f"[recall] pending_finish: normalized spoken={spoken!r}")

        mode = recall_state._pending_mode
        name = recall_state._pending_name
        print(f"[recall] pending_finish: mode={mode!r}, name={name!r}")
        _cancel_pending()
        recall_overlay.hide_prompt()

        if not mode or not name or not spoken:
            print(f"[recall] pending_finish: ABORT — empty mode/name/spoken")
            return

        print(f"[recall] pending_finish: dispatching mode={mode!r} name={name!r} spoken={spoken!r}")
        if mode == "combine":
            actions.user.recall_combine(name, spoken)
        elif mode == "rename":
            actions.user.recall_rename(name, spoken)
        elif mode == "alias":
            actions.user.add_recall_alias(name, spoken)

    def recall_promote(spoken_name: str):
        """Promote an alias to be the canonical name, demoting the old name to alias"""
        if is_forbidden(spoken_name):
            recall_overlay.flash(f'"{spoken_name}" is a reserved word')
            return

        spoken = spoken_name.lower().strip()

        # Find which canonical entry has this as an alias
        canonical = None
        for name, info in saved_windows.items():
            if name.lower() == spoken:
                # Already canonical, nothing to do
                return
            if spoken in [a.lower() for a in info.get("aliases", [])]:
                canonical = name
                break

        if canonical is None:
            print(f'[recall] promote: "{spoken_name}" is not a known alias')
            return

        info = saved_windows[canonical]

        # Remove the alias from the list
        aliases = info.get("aliases", [])
        aliases = [a for a in aliases if a.lower() != spoken]
        # Add the old canonical name as an alias
        aliases.append(canonical)
        info["aliases"] = aliases

        # Re-key the entry under the new name
        del saved_windows[canonical]
        saved_windows[spoken_name] = info

        save_to_disk()
        update_window_list()
        recall_overlay.flash(f'promoted: {spoken_name} (was {canonical})')
        print(f'[recall] promoted: "{spoken_name}" is now canonical (was alias of "{canonical}")')

    def recall_rename(name: str, new_name: str):
        """Rename a saved window to a completely new name"""
        if is_forbidden(new_name):
            recall_overlay.flash(f'"{new_name}" is a reserved word')
            return

        if name not in saved_windows:
            return

        info = saved_windows[name]
        del saved_windows[name]
        saved_windows[new_name] = info

        save_to_disk()
        update_window_list()
        recall_overlay.flash(f'renamed: {name} -> {new_name}')

    def add_recall_alias(name: str, alias: str):
        """Add an alias spoken form for a saved window"""
        print(f"[recall] add_alias: name={name!r}, alias={alias!r}")
        if is_forbidden(alias):
            print(f"[recall] add_alias: ABORT — forbidden")
            recall_overlay.flash(f'"{alias}" is a reserved word')
            return

        if name not in saved_windows:
            print(f"[recall] add_alias: ABORT — name not in saved_windows")
            return

        aliases = saved_windows[name].get("aliases", [])
        if alias not in aliases:
            aliases.append(alias)
            saved_windows[name]["aliases"] = aliases
            save_to_disk()
            update_window_list()
            recall_overlay.flash(f'alias: {alias} -> {name}')

    def remove_recall_alias(alias: str):
        """Remove an alias from whichever window owns it"""
        spoken = alias.lower().strip()

        for name, info in saved_windows.items():
            aliases = info.get("aliases", [])
            matching = [a for a in aliases if a.lower() == spoken]
            if matching:
                info["aliases"] = [a for a in aliases if a.lower() != spoken]
                save_to_disk()
                update_window_list()
                recall_overlay.flash(f'removed alias: {alias} (was {name})')
                return

        recall_overlay.flash(f'"{alias}" is not an alias')
