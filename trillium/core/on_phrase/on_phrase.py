"""Central on_phrase orchestrator.

Single registration point for pre:phrase and post:phrase hooks.
Sub-modules export plain functions — they do NOT register their own hooks.
"""

from talon import Module, actions, speech_system
from talon.grammar import Phrase

from .abort.abort import abort_update_phrase
from . import then_mimic
from .analyze_phrase.analyze_phrase import analyze_phrase
from .command_logger.command_logger import log_analyzed_phrase

mod = Module()

mod.setting(
    "analyze_phrase",
    type=bool,
    default=True,
    desc="If true phrase will be analyzed and added to command history",
)


def on_pre_phrase(phrase: Phrase):
    if skip_phrase(phrase):
        return

    is_aborted, text = abort_update_phrase(phrase)

    if not is_aborted:
        then_mimic.on_pre_phrase(phrase)


def on_post_phrase(phrase: Phrase):
    # Then-mimic must run first (fires queued mimics)
    then_mimic.on_post_phrase(phrase)

    if not actions.settings.get("user.analyze_phrase") or skip_phrase(phrase):
        return

    try:
        analyzed = analyze_phrase(phrase)
        log_analyzed_phrase(analyzed)
    except Exception as ex:
        print(f"[on_phrase] analyze/log error: {ex}")


def skip_phrase(phrase: Phrase) -> bool:
    return not phrase.get("phrase") or skip_phrase_in_sleep(phrase)


def skip_phrase_in_sleep(phrase: Phrase) -> bool:
    """Returns true if the rule is <phrase> in sleep mode."""
    return (
        not actions.speech.enabled()
        and len(phrase["parsed"]) == 1
        and phrase["parsed"][0]._name == "___ltphrase_gt__"
    )


speech_system.register("pre:phrase", on_pre_phrase)
speech_system.register("post:phrase", on_post_phrase)
