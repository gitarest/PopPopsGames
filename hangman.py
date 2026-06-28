"""Hangman game logic for Pop Pop's Games."""

import random

from words import DEFAULT_LEVEL, LEVELS, WORDS_BY_LEVEL

MAX_WRONG = 6  # coupled to the 6-part SVG drawing


def new_game(level=DEFAULT_LEVEL):
    """Return a fresh Hangman game dict with a word drawn from the given level."""
    if level not in WORDS_BY_LEVEL:
        level = DEFAULT_LEVEL
    return {
        "word": random.choice(WORDS_BY_LEVEL[level]).upper(),
        "guessed": [],
        "wrong": 0,
        "level": level,
        "scored": False,
    }


def game_state(game):
    """Build the JSON-serialisable client view of a Hangman game."""
    word = game["word"]
    guessed = game["guessed"]
    wrong = game["wrong"]

    won = all(c in guessed for c in word)
    lost = wrong >= MAX_WRONG
    over = won or lost

    return {
        "masked": [c if c in guessed else "_" for c in word],
        "guessed": sorted(guessed),
        "wrong": wrong,
        "max_wrong": MAX_WRONG,
        "won": won,
        "lost": lost,
        "over": over,
        "word": word if over else None,
        "level": game["level"],
        "levels": LEVELS,
    }


def level_points(level):
    """Points awarded for winning at this difficulty (easy=1 … expert=4)."""
    return LEVELS.index(level) + 1
