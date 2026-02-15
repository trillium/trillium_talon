from talon import Context, Module, actions

mod = Module()
apps = mod.apps
apps.zoom = "app.bundle: com.hnc.Zoom"
apps.zoom = "app.name: Zoom"
apps.zoom = "app.name: Zoom.exe"
apps.zoom = """
tag: browser
browser.host: zoom.com
"""

ctx = Context()
ctx.matches = r"""
app: zoom.us
"""

@mod.action_class
class zoom_actions:
    def zoom_mute():
        """Toggle mute"""
    
    def zoom_toggle_video():
        """Toggle zoom video"""

