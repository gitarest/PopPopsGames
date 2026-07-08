"""Wordle game logic for Pop Pop's Games."""

import random
from words_wordle import WORDS
from words_wordle_valid import VALID_GUESSES

MAX_GUESSES = 6
WORD_LENGTH = 5

_VALID = set(WORDS) | set(VALID_GUESSES)


def new_game():
    return {
        "word":          random.choice(WORDS),
        "guesses":       [],   # [{"word": "CRANE", "result": ["correct","absent",...]}]
        "phase":         "play",   # "play" | "won" | "lost"
        "over":          False,
        "scored":        False,
        "start_logged":  False,
        "invalid_guess": False,
    }


def guess(game, word):
    """Submit a guess. Returns False if the word is not in the valid word list."""
    game["invalid_guess"] = False
    if game["over"] or game["phase"] != "play":
        return True
    word = word.upper().strip()
    if len(word) != WORD_LENGTH or not word.isalpha():
        return True
    if word not in _VALID:
        game["invalid_guess"] = True
        return False
    result = _score_guess(word, game["word"])
    game["guesses"].append({"word": word, "result": result})
    if all(r == "correct" for r in result):
        game["phase"] = "won"
        game["over"]  = True
    elif len(game["guesses"]) >= MAX_GUESSES:
        game["phase"] = "lost"
        game["over"]  = True
    return True


def _score_guess(guess_word, answer):
    result = ["absent"] * WORD_LENGTH
    remaining = {}
    # First pass: mark correct positions
    for i, (g, a) in enumerate(zip(guess_word, answer)):
        if g == a:
            result[i] = "correct"
        else:
            remaining[a] = remaining.get(a, 0) + 1
    # Second pass: mark present (right letter, wrong position)
    for i, g in enumerate(guess_word):
        if result[i] == "correct":
            continue
        if remaining.get(g, 0) > 0:
            result[i] = "present"
            remaining[g] -= 1
    return result


def game_state(game):
    # Build per-letter keyboard state: best state seen for each letter
    letter_states = {}
    priority = {"correct": 3, "present": 2, "absent": 1}
    for g in game["guesses"]:
        for letter, state in zip(g["word"], g["result"]):
            if priority.get(state, 0) > priority.get(letter_states.get(letter), 0):
                letter_states[letter] = state
    return {
        "guesses":       game["guesses"],
        "phase":         game["phase"],
        "over":          game["over"],
        "word":          game["word"] if game["over"] else None,
        "attempts":      len(game["guesses"]),
        "max_guesses":   MAX_GUESSES,
        "letter_states": letter_states,
        "invalid_guess": game.get("invalid_guess", False),
    }
