import os
os.environ["PATH"] += os.pathsep + "/opt/homebrew/bin"

SAFE_APPS = [
    "Code",
    "Google Chrome",
    "OBS Studio",
    "RODE Connect",
    "Talon",
    "Terminal",
    "Slack",
    "System Settings",
]

mask_path = "/Users/trilliumsmith/Downloads/left_mask.png"

nextjsWebsocketURL = "http://localhost:7328/api/obs-scene-safety"

GREEN = (0, 255, 0, 255)
RED = (255, 0, 0, 255)

COLOR_MASK_DANGER = "white"
COLOR_MASK_SAFE = "black"

COLOR_SAFE = GREEN
COLOR_DANGER = RED