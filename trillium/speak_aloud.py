"""
say_text_background - Run '/Users/trilliumsmith/bashrc_dir/public/SAY ' command in the background
"""

import subprocess
from talon import Module, cron

mod = Module()

_say_processes = []


def say_background_process(text):
    """Run /Users/trilliumsmith/bashrc_dir/public/SAY  command in the background (non-blocking) and track process"""

    try:
        proc = subprocess.Popen(["/Users/trilliumsmith/bashrc_dir/public/SAY", text], start_new_session=True)
        _say_processes.append(proc)
    except FileNotFoundError as e:
        try:
            proc = subprocess.Popen(["say", text], start_new_session=True)
            _say_processes.append(proc)
        except Exception as e2:
            return
    except Exception as e:
        return

    # Instead of starting a thread every time, use a timer to periodically clean up
    if not getattr(say_background_process, "_cleanup_scheduled", False):
        say_background_process._cleanup_scheduled = True

        def periodic_cleanup():
            _cleanup_say_processes()
            # Only continue cleanup if there are still processes running
            if len(_say_processes) > 0:
                cron.after("2s", periodic_cleanup)
            else:
                say_background_process._cleanup_scheduled = False

        cron.after("2s", periodic_cleanup)


def _cleanup_say_processes():
    """Check and clean up finished /Users/trilliumsmith/bashrc_dir/public/SAY  processes"""
    global _say_processes
    for proc in _say_processes[:]:
        if proc.poll() is not None:
            proc.wait()
            _say_processes.remove(proc)


def cancel_say_processes():
    """Terminate all running /Users/trilliumsmith/bashrc_dir/public/SAY  processes"""
    global _say_processes
    for proc in _say_processes[:]:
        if proc.poll() is None:
            proc.terminate()
            proc.wait()
        _say_processes.remove(proc)


@mod.action_class
class Actions:
    def speak_aloud(text: str):
        """Run /Users/trilliumsmith/bashrc_dir/public/SAY  with the given text in the background"""
        say_background_process(text)

    def speak_aloud_cancel():
        """Cancel all running /Users/trilliumsmith/bashrc_dir/public/SAY  processes"""
        cancel_say_processes()

# Example usage in Talon REPL:
# from trillium.speak_aloud import Actions
# Actions.speak_aloud("Hello world")
# Actions.speak_aloud_cancel()

