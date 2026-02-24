from talon import actions, clip, Context, Module

mod = Module()
ctx = Context()

@mod.action_class
class Actions:
    def add_angle_bracket_to_clipboard():
        '''Adds "> " before every line break and to front of text'''
        text = clip.text()
        newText = text.replace("\n","\n> ")
        if newText[:1] != "> ":
            newText = "> " + newText
        clip.set_text(newText)