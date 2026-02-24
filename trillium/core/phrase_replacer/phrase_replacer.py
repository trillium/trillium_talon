"""
Unified phrase replacement system.

Single CSV file to fix misrecognitions across the entire Talon pipeline:

1. SYMBOL — injects alternate spoken forms into punctuation_dict and
   symbol_key_dict so they work in both command and dictation grammars.
   e.g. "christa mark" → "?" everywhere

2. WORD — injects into the PhraseReplacer used by dictate.replace_words
   so corrections apply to <phrase> captures in dictation.
   e.g. "jason" → "JSON" in dictated text

3. COMMAND — injects into the vocabulary list so alternate spoken forms
   are available in {user.vocabulary} captures (<user.text>, <user.prose>).
   e.g. "new cleft" → "nuke left"

All types also get a pre:phrase hook for subtitle/logging correction.

Edit: phrase_replacements.csv
Format: type,replacement,original
"""

import sys
from talon import Module, Context, speech_system, app
from talon.grammar import Phrase
from pathlib import Path

mod = Module()
ctx = Context()

REPLACEMENTS_FILE = Path(__file__).parent / "phrase_replacements.csv"

# Pre:phrase index for display/logging correction
_phrase_index = {}


def _find_module(suffix):
    """Find a loaded Talon module by path suffix."""
    for name, module in sys.modules.items():
        if hasattr(module, "__file__") and module.__file__ and module.__file__.endswith(suffix):
            return module
    return None


def _load_replacements():
    """Load CSV and inject replacements into the appropriate systems."""
    global _phrase_index
    _phrase_index = {}

    if not REPLACEMENTS_FILE.exists():
        print("[phrase_replacer] No replacements file found")
        return

    symbol_entries = []  # (character, spoken_form)
    word_entries = []    # (replacement, original)
    command_entries = [] # (replacement, original)

    for line in REPLACEMENTS_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("Type"):
            continue
        parts = line.split(",", 2)
        if len(parts) != 3:
            continue
        entry_type, replacement, original = (p.strip() for p in parts)
        if not entry_type or not replacement or not original:
            continue

        if entry_type == "symbol":
            symbol_entries.append((replacement, original))
        elif entry_type == "word":
            word_entries.append((replacement, original))
        elif entry_type == "command":
            command_entries.append((replacement, original))

    # --- 1. SYMBOL: inject into punctuation + symbol_key grammars ---
    if symbol_entries:
        try:
            symbols_mod = _find_module("core/keys/symbols.py")
            keys_mod = _find_module("core/keys/keys.py")

            if symbols_mod and keys_mod:
                for character, spoken_form in symbol_entries:
                    symbols_mod.punctuation_dict[spoken_form] = character
                    symbols_mod.symbol_key_dict[spoken_form] = character

                # Reassign ctx.lists to trigger Talon grammar update
                keys_mod.ctx.lists["user.punctuation"] = dict(symbols_mod.punctuation_dict)
                keys_mod.ctx.lists["user.symbol_key"] = dict(symbols_mod.symbol_key_dict)
                print(f"[phrase_replacer] Injected {len(symbol_entries)} symbol forms")
            else:
                print("[phrase_replacer] Could not find symbols/keys modules")
        except Exception as e:
            print(f"[phrase_replacer] Symbol injection failed: {e}")

    # --- 2. WORD: inject into dictate.replace_words pipeline ---
    if word_entries:
        try:
            vocab_mod = _find_module("core/vocabulary/vocabulary.py")

            if vocab_mod:
                for replacement, original in word_entries:
                    vocab_mod.phrases_to_replace[original.lower()] = replacement

                vocab_mod.phrase_replacer.update(vocab_mod.phrases_to_replace)
                print(f"[phrase_replacer] Injected {len(word_entries)} word replacements")
            else:
                print("[phrase_replacer] Could not find vocabulary module")
        except Exception as e:
            print(f"[phrase_replacer] Word injection failed: {e}")

    # --- 3. COMMAND: inject into vocabulary list ---
    if command_entries:
        try:
            vocab_additions = {}
            for replacement, original in command_entries:
                vocab_additions[original.lower()] = replacement

            ctx.lists["user.vocabulary"] = vocab_additions
            print(f"[phrase_replacer] Injected {len(command_entries)} command forms")
        except Exception as e:
            print(f"[phrase_replacer] Command injection failed: {e}")

    # --- Build pre:phrase index for ALL entries (subtitles/logging) ---
    raw_index = {}
    all_entries = (
        [(orig.lower(), repl.lower()) for repl, orig in symbol_entries]
        + [(orig.lower(), repl.lower()) for repl, orig in word_entries]
        + [(orig.lower(), repl.lower()) for repl, orig in command_entries]
    )
    for original, replacement in all_entries:
        orig_words = original.split()
        repl_words = replacement.split()
        first = orig_words[0]
        rest = tuple(orig_words[1:])
        n_extra = len(rest)
        raw_index.setdefault(first, {}).setdefault(n_extra, {})[rest] = repl_words

    _phrase_index = {
        first: sorted(by_len.items(), key=lambda x: -x[0])
        for first, by_len in raw_index.items()
    }

    total = len(symbol_entries) + len(word_entries) + len(command_entries)
    print(f"[phrase_replacer] Loaded {total} total replacements")


def _replace_words(words):
    """Apply replacements to a list of words."""
    output = []
    i = 0
    while i < len(words):
        word = str(words[i]).lower()
        matched = False
        for n_extra, phrases in _phrase_index.get(word, []):
            if i + n_extra < len(words):
                rest = tuple(str(w).lower() for w in words[i + 1 : i + 1 + n_extra])
                if rest in phrases:
                    output.extend(phrases[rest])
                    i += 1 + n_extra
                    matched = True
                    break
        if not matched:
            output.append(words[i])
            i += 1
    return output


def pre_phrase(phrase: Phrase):
    """Replace words in phrase for display/logging/subtitle purposes."""
    if not _phrase_index:
        return
    words = phrase.get("phrase")
    if not words:
        return
    new_words = _replace_words(words)
    if len(new_words) != len(words) or any(
        str(a).lower() != str(b).lower() for a, b in zip(new_words, words)
    ):
        phrase["phrase"] = new_words


def on_ready():
    _load_replacements()


speech_system.register("pre:phrase", pre_phrase)
app.register("ready", on_ready)
