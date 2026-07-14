"""Word Scramble game logic for Pop Pop's Games."""

import random

from words import DEFAULT_LEVEL, LEVELS, WORDS_BY_LEVEL

MAX_WRONG = 5


def _scramble(word):
    letters = list(word)
    if len(set(letters)) == 1:
        return letters
    scrambled = letters[:]
    while scrambled == letters:
        random.shuffle(scrambled)
    return scrambled


def new_game(level=DEFAULT_LEVEL):
    """Return a fresh Word Scramble game dict with a word drawn from the given level."""
    if level not in WORDS_BY_LEVEL:
        level = DEFAULT_LEVEL
    word = random.choice(WORDS_BY_LEVEL[level]).upper()
    letters = _scramble(word)
    return {
        "word": word,
        "letters": letters,                    # fixed tile letters, indexed by position
        "tile_state": ["pool"] * len(letters),  # "pool" or "answer" per tile index
        "answer_order": [],                     # tile indices in the order placed
        "wrong": 0,
        "wrong_flag": False,   # True after a full wrong arrangement, until cleared
        "won": False,
        "over": False,
        "level": level,
        "scored": False,
    }


def place(game, index):
    """Move a pool tile into the next answer slot."""
    if game["over"] or game["wrong_flag"]:
        return
    if index < 0 or index >= len(game["letters"]):
        return
    if game["tile_state"][index] != "pool":
        return

    game["tile_state"][index] = "answer"
    game["answer_order"].append(index)

    if len(game["answer_order"]) == len(game["letters"]):
        guess = "".join(game["letters"][i] for i in game["answer_order"])
        if guess == game["word"]:
            game["won"] = True
            game["over"] = True
        else:
            game["wrong"] += 1
            if game["wrong"] >= MAX_WRONG:
                game["over"] = True
            else:
                game["wrong_flag"] = True


def remove(game, index):
    """Move an answer tile back to the pool."""
    if game["over"] or game["wrong_flag"]:
        return
    if index < 0 or index >= len(game["letters"]):
        return
    if game["tile_state"][index] != "answer":
        return

    game["tile_state"][index] = "pool"
    game["answer_order"].remove(index)


def clear_wrong(game):
    """Return all tiles to the pool after a wrong arrangement was shown."""
    if not game["wrong_flag"]:
        return
    game["tile_state"] = ["pool"] * len(game["letters"])
    game["answer_order"] = []
    game["wrong_flag"] = False


def game_state(game):
    """Build the JSON-serialisable client view of a Word Scramble game."""
    over = game["over"]
    return {
        "letters": game["letters"],
        "tile_state": game["tile_state"],
        "answer_order": game["answer_order"],
        "wrong": game["wrong"],
        "max_wrong": MAX_WRONG,
        "wrong_flag": game["wrong_flag"],
        "won": game["won"],
        "lost": over and not game["won"],
        "over": over,
        "word": game["word"] if over else None,
        "level": game["level"],
        "levels": LEVELS,
    }
