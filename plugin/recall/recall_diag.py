"""Recall Diagnostics - diagnostic actions for debugging pill/click behavior.

Usage: call actions.user.recall_diag() from REPL or voice command.
Remove this file when debugging is complete.
"""

from talon import Module, ui
from talon.canvas import Canvas
from talon.ui import Rect

from .recall_overlay_shared import _get_saved_windows

mod = Module()


def _check_click_chain(name: str) -> str:
    """Verify the full click-to-focus chain for a pill name.
    Returns a status string describing what would happen on click."""
    saved_windows, find_window_by_id = _get_saved_windows()
    info = saved_windows.get(name)
    if not info:
        return f"BROKEN: '{name}' not in saved_windows"
    wid = info.get("id")
    if wid is None:
        return f"BROKEN: saved_windows['{name}'] has id=None (window closed?)"
    w = find_window_by_id(wid)
    if w is None:
        return f"BROKEN: find_window_by_id({wid}) returned None (window gone)"
    try:
        app = w.app.name
        title = w.title[:40]
    except Exception as e:
        return f"BROKEN: window {wid} exists but can't read properties: {e}"
    try:
        _ = w.rect
    except Exception:
        return f"BROKEN: window {wid} exists but rect inaccessible"
    return f"OK -> {app}: {title}"


@mod.action_class
class Actions:
    def recall_diag():
        """Full diagnostic: alignment, blocks_mouse, handler chain, focus target."""
        from .recall_overlay_persistent import (
            _pill_hit_rects, _click_canvases,
            _persistent_canvas, _persistent_window,
        )

        print("\n=== RECALL PILL DIAGNOSTICS ===")
        print(f"Render canvas: {'ALIVE' if _persistent_canvas else 'DEAD'}")
        print(f"Active window: {_persistent_window}")
        print(f"Pills cached: {len(_pill_hit_rects)}")
        print(f"Click canvases: {len(_click_canvases)}")

        if not _pill_hit_rects:
            print("No pills — is persistent highlight active?")
            print("=== END ===\n")
            return

        count_mismatch = len(_pill_hit_rects) != len(_click_canvases)
        if count_mismatch:
            print(f"!! COUNT MISMATCH: {len(_pill_hit_rects)} pills vs {len(_click_canvases)} canvases")

        print("\n--- Per-pill status ---")
        for i, (name, pill) in enumerate(_pill_hit_rects):
            checks = []

            # 1. Click canvas exists?
            if i < len(_click_canvases):
                cc = _click_canvases[i]

                # 2. blocks_mouse enabled?
                if cc.blocks_mouse:
                    checks.append("blocks_mouse=YES")
                else:
                    checks.append("blocks_mouse=NO !! won't receive clicks")

                # 3. Position aligned?
                cr = cc.rect
                dx = abs(cr.x - pill.x)
                dy = abs(cr.y - pill.y)
                if dx < 2 and dy < 2:
                    checks.append("pos=ALIGNED")
                else:
                    checks.append(f"pos=MISALIGNED dx={cr.x-pill.x:.0f} dy={cr.y-pill.y:.0f}")

                # 4. Size matched?
                dw = abs(cr.width - pill.width)
                dh = abs(cr.height - pill.height)
                if dw < 2 and dh < 2:
                    checks.append("size=OK")
                else:
                    checks.append(f"size=OFF dw={cr.width-pill.width:.0f} dh={cr.height-pill.height:.0f}")
            else:
                checks.append("canvas=MISSING")

            # 5. Click handler resolves to a focusable window?
            chain_status = _check_click_chain(name)
            checks.append(f"chain={chain_status}")

            status = " | ".join(checks)
            will_work = (
                i < len(_click_canvases)
                and _click_canvases[i].blocks_mouse
                and dx < 2 and dy < 2
                and "OK ->" in chain_status
            )
            verdict = "PASS" if will_work else "FAIL"

            print(f"  [{verdict}] {name:12s} {status}")

        # Screen info
        s = ui.main_screen()
        print(f"\nScreen: {s.rect}")
        print(f"Visible: {s.visible_rect}")
        print("=== END DIAGNOSTICS ===\n")
