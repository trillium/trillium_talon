import os
from talon import actions

TALON_HOME = os.getcwd()

def rename_recordings():
    recordings_folder = TALON_HOME + "/recordings"
    
    if not os.path.exists(recordings_folder):
        actions.user.hud_add_log("error", "No recordings have been made yet!")
        return
    
    files = os.listdir(recordings_folder)

    for file in files:
        if file.endswith(".flac"):
            os.rename(recordings_folder + "/" + file, recordings_folder + "/" + file.replace(" ", "_").replace("-", "_").replace(":", "_"))
    actions.user.hud_add_log("info", "Renamed recordings")