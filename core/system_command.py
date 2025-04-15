import os
import subprocess

from talon import Module
from security import safe_command

mod = Module()


@mod.action_class
class Actions:
    def system_command(cmd: str):
        """execute a command on the system"""
        os.system(cmd)

    def system_command_nb(cmd: str):
        """execute a command on the system without blocking"""
        safe_command.run(subprocess.Popen, cmd, shell=True)
