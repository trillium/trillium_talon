"""
Recall Terminal (Linux) - Terminal launching via ui.launch

Registers Linux terminal launchers into the shared TERMINAL_LAUNCHERS registry.
"""

from talon import app

if app.platform == "linux":
    from talon import ui

    from .recall_terminal import TERMINAL_LAUNCHERS

    # Linux terminal launch configs: (binary, [arg_templates])
    _LAUNCH_CONFIGS = {
        "Gnome-terminal":   ("gnome-terminal", ["--working-directory={path}"]),
        "Mate-terminal":    ("mate-terminal", ["--working-directory={path}"]),
        "kitty":            ("kitty", ["--directory", "{path}"]),
        "Alacritty":        ("alacritty", ["--working-directory", "{path}"]),
        "foot":             ("foot", ["--working-directory={path}"]),
        "xfce4-terminal":   ("xfce4-terminal", ["--working-directory={path}"]),
        "Terminator":       ("terminator", ["--working-directory={path}"]),
        "Tilix":            ("tilix", ["--working-directory={path}"]),
    }

    def _make_launcher(binary: str, arg_templates: list):
        """Create a launcher callable for a Linux terminal."""
        def launcher(path: str):
            args = [a.format(path=path) for a in arg_templates]
            ui.launch(path=binary, args=args)
        return launcher

    for _app_name, (_binary, _arg_templates) in _LAUNCH_CONFIGS.items():
        TERMINAL_LAUNCHERS[_app_name] = _make_launcher(_binary, _arg_templates)
