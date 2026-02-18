#!/usr/bin/env python3
"""
Analyze command logs to find misrecognition correction patterns.

Scans ~/.talon/recordings/commands/ for sequences like:
  dictation -> destroy/clear_left -> dictation
where both dictation phrases are short and similar enough to suggest
the user was correcting a misrecognition rather than changing their mind.
"""

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

COMMANDS_DIR = Path.home() / ".talon" / "recordings" / "commands"

# Max seconds between events in a correction sequence
MAX_GAP_SECONDS = 15

# Max words in a dictation phrase to consider (long phrases are conversation, not corrections)
MAX_PHRASE_WORDS = 5

# Max ratio of word counts between before/after (they should be similar length)
MAX_LENGTH_RATIO = 3.0


def is_correction(trigger):
    """Check if a command trigger is a correction/undo action."""
    t = trigger.lower().strip()
    for prefix in ["destroy", "clear left", "scratch", "undo", "nope"]:
        if t == prefix or t.startswith(prefix + " "):
            return True
    return False


def is_dictation(trigger):
    """Check if a command trigger is dictation/text insertion."""
    t = trigger.strip()
    # Explicit dictation triggers
    if t in {
        "{user.prose_formatter} <user.prose>",
        "<user.raw_prose>",
        "<user.text>",
        "<user.prose>",
    }:
        return True
    # Recall directed dictation
    if "<user.raw_prose>" in t or "<user.prose>" in t:
        return True
    return False


def extract_dictated_text(record):
    """Pull the actual dictated words from a command record."""
    phrase = record.get("phrase", {})
    words = phrase.get("words", [])
    if words and isinstance(words[0], str):
        raw = words[0] if len(words) == 1 else " ".join(words)
    else:
        raw = phrase.get("text", "") or ""

    # Remove known command prefixes (prose formatters)
    for prefix in ["say ", "sentence ", "title ", "word ", "NOOP "]:
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break

    return raw.strip().lower()


def word_count(text):
    return len(text.split()) if text else 0


def similarity(a, b):
    """Simple word overlap similarity between two phrases."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    overlap = words_a & words_b
    return len(overlap) / max(len(words_a), len(words_b))


def similar_enough(heard, meant):
    """Check if two phrases are plausibly a misrecognition pair.

    Either they share words (partial misrecognition) or they're both
    short enough that one could be a garbled version of the other.
    """
    wc_h = word_count(heard)
    wc_m = word_count(meant)

    # Both must be short
    if wc_h > MAX_PHRASE_WORDS or wc_m > MAX_PHRASE_WORDS:
        return False

    # Length ratio check — "hello" -> "hello world" is fine,
    # "hello" -> "the quick brown fox" is not
    if wc_h > 0 and wc_m > 0:
        ratio = max(wc_h, wc_m) / min(wc_h, wc_m)
        if ratio > MAX_LENGTH_RATIO:
            return False

    # If they share any words, likely a partial correction
    if similarity(heard, meant) > 0:
        return True

    # Both single words — could be phonetic confusion
    if wc_h <= 2 and wc_m <= 2:
        return True

    # Short phrases of similar length
    if abs(wc_h - wc_m) <= 1 and wc_h <= 3:
        return True

    return False


def get_window_id(record):
    return record.get("context", {}).get("window", {}).get("id")


def load_all_commands():
    """Load all command log files, sorted by timestamp."""
    records = []
    for f in COMMANDS_DIR.iterdir():
        if f.suffix != ".json":
            continue
        try:
            with open(f) as fh:
                data = json.load(fh)
            data["_ts"] = datetime.fromisoformat(data["timestamp"])
            records.append(data)
        except Exception:
            continue
    records.sort(key=lambda r: r["_ts"])
    return records


def find_correction_sequences(records):
    """Find dictation -> correction -> dictation sequences."""
    sequences = []
    i = 0
    while i < len(records) - 2:
        r1 = records[i]
        trigger1 = r1.get("command", {}).get("trigger", "")

        if not is_dictation(trigger1):
            i += 1
            continue

        window1 = get_window_id(r1)

        # Look ahead for a correction within MAX_GAP_SECONDS
        j = i + 1
        found = False
        while j < len(records):
            gap = (records[j]["_ts"] - r1["_ts"]).total_seconds()
            if gap > MAX_GAP_SECONDS:
                break

            r2 = records[j]
            trigger2 = r2.get("command", {}).get("trigger", "")

            if is_correction(trigger2):
                # Must be same window
                if get_window_id(r2) != window1:
                    j += 1
                    continue

                # Look for re-dictation after the correction
                k = j + 1
                while k < len(records):
                    gap2 = (records[k]["_ts"] - r2["_ts"]).total_seconds()
                    if gap2 > MAX_GAP_SECONDS:
                        break

                    r3 = records[k]
                    trigger3 = r3.get("command", {}).get("trigger", "")

                    if is_dictation(trigger3) and get_window_id(r3) == window1:
                        text_before = extract_dictated_text(r1)
                        text_after = extract_dictated_text(r3)

                        if (text_before and text_after
                                and text_before != text_after
                                and similar_enough(text_before, text_after)):
                            sequences.append({
                                "heard": text_before,
                                "meant": text_after,
                                "correction_cmd": trigger2,
                                "timestamp": r1["_ts"].isoformat(),
                                "app": r1.get("context", {}).get("app", {}).get("name", ""),
                                "window": r1.get("context", {}).get("window", {}).get("title", ""),
                            })
                        i = k
                        found = True
                        break

                    elif is_correction(trigger3):
                        # Multiple corrections in a row, keep looking
                        k += 1
                        continue
                    else:
                        break
                break

            elif is_dictation(trigger2):
                # New dictation without correction — not a correction sequence
                break
            else:
                # Some other command — skip and keep looking
                j += 1
                continue

        if not found:
            i += 1
        else:
            i += 1

    return sequences


def main():
    print(f"Loading commands from {COMMANDS_DIR}...")
    records = load_all_commands()
    print(f"Loaded {len(records)} command records")

    print(f"\nScanning for correction sequences...")
    print(f"  max gap: {MAX_GAP_SECONDS}s, max phrase words: {MAX_PHRASE_WORDS}")
    print(f"  requiring: same window, similar phrase length, short phrases")
    sequences = find_correction_sequences(records)
    print(f"Found {len(sequences)} correction sequences\n")

    if not sequences:
        print("No correction patterns found.")
        return

    # Tally correction pairs
    pair_counter = Counter()
    pair_examples = {}
    for seq in sequences:
        pair = (seq["heard"], seq["meant"])
        pair_counter[pair] += 1
        if pair not in pair_examples:
            pair_examples[pair] = seq

    # Report
    print("=" * 70)
    print("CORRECTION PATTERNS (most frequent first)")
    print("=" * 70)

    for (heard, meant), count in pair_counter.most_common(50):
        example = pair_examples[(heard, meant)]
        print(f"\n  [{count}x] \"{heard}\" -> \"{meant}\"")
        print(f"         via: {example['correction_cmd']}")
        print(f"         app: {example['app']}  window: {example['window'][:50]}")

    # Suggest words_to_replace entries
    repeats = [(h, m, c) for (h, m), c in pair_counter.most_common() if c >= 2]
    if repeats:
        print("\n" + "=" * 70)
        print("SUGGESTED words_to_replace.csv ENTRIES")
        print("=" * 70)
        for heard, meant, count in repeats:
            print(f"  {meant},{heard}    # {count}x")

    print(f"\n--- Summary ---")
    print(f"Total commands: {len(records)}")
    print(f"Correction sequences: {len(sequences)}")
    print(f"Unique pairs: {len(pair_counter)}")
    print(f"Repeating pairs (2+): {len(repeats) if repeats else 0}")


if __name__ == "__main__":
    main()
