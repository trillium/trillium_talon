"""Hyprland bridge for Talon (Linux only).

Talon on Hyprland only sees XWayland windows, so its own running-apps list holds just "talon".
This file fills the existing `user.running` list (read by `focus <user.running_applications>` in
trillium_talon/core/windows_and_tabs/window_management.talon) from `hyprctl clients -j`, and
makes `user.switcher_focus` focus the window through Hyprland instead of Talon's own window code.

Nothing in the macbook grammar is changed. Delete this folder to undo.
"""
import glob
import json
import os
import re
import subprocess

from talon import Context, actions, app, cron

ctx = Context()
ctx.matches = r"os: linux"

# Spoken names that differ from what the window class would give.
ALIASES = {
    "google-chrome": ["chrome", "google chrome"],
    "foot": ["terminal", "foot"],
    "org.omarchy.agent": ["agent", "claude"],
    "org.wezfurlong.wezterm": ["wezterm", "terminal"],
    "code": ["code", "vs code", "visual studio code"],
    "discord": ["discord"],
    "handy": ["handy"],
}

_apps = {}  # spoken form -> window class


def _env():
    env = dict(os.environ)
    if not env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        sigs = sorted(glob.glob("/run/user/%d/hypr/*/" % os.getuid()), key=os.path.getmtime)
        if sigs:
            env["HYPRLAND_INSTANCE_SIGNATURE"] = os.path.basename(sigs[-1].rstrip("/"))
    env.setdefault("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid())
    return env


def _clients():
    try:
        out = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, env=_env(), timeout=2)
        return json.loads(out.stdout) if out.returncode == 0 else []
    except Exception:
        return []


def _spoken_forms(cls):
    forms = set(ALIASES.get(cls, []))
    words = re.sub(r"[-_.]+", " ", cls).strip().lower()
    forms.add(words)
    last = re.split(r"[.]", cls)[-1].replace("-", " ").lower()
    if last:
        forms.add(last)
    return {f for f in forms if f and len(f) > 1}


def update_running_list():
    global _apps
    apps = {}
    for c in _clients():
        cls = c.get("class") or ""
        if not cls or cls == "talon":
            continue
        for form in _spoken_forms(cls):
            apps.setdefault(form, cls)
    if apps != _apps:
        _apps = apps
        ctx.lists["user.running"] = dict(apps)


def _focus_class(cls):
    subprocess.Popen(["omarchy", "hyprland", "focus", "app", cls], env=_env(),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@ctx.action_class("user")
class UserActions:
    def switcher_focus(name: str):
        cls = _apps.get(name.lower(), name)
        _focus_class(cls)

    def switcher_focus_app(app):
        _focus_class(getattr(app, "name", str(app)))


def start():
    update_running_list()
    cron.interval("2s", update_running_list)


# Talon may already be past its "ready" event when this file (re)loads, so start right away.
# The os: linux context only gates the actions; this guard keeps the poller from running elsewhere.
if app.platform == "linux":
    start()
