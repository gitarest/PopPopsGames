"""Simon Says game logic for Pop Pop's Games."""

import random

COLORS = ("red", "blue", "green", "yellow")
LEVELS = ("easy", "medium", "hard")


def new_game(level="easy"):
    if level not in LEVELS:
        level = "easy"
    return {
        "sequence":     [random.choice(COLORS)],
        "player_index": 0,
        "phase":        "watch",   # "watch" | "play" | "over"
        "over":         False,
        "scored":       False,
        "start_logged": False,
        "level":        level,
    }


def ready(game):
    """Transition watch → play (called after client finishes the animation)."""
    if game["phase"] == "watch" and not game["over"]:
        game["phase"] = "play"


def early_click(game):
    """Player clicked during the between-round pause — treat as a loss."""
    if game["phase"] == "watch" and not game["over"]:
        game["phase"] = "over"
        game["over"]  = True


def tap(game, color):
    """Process one player tap. Ignored if not in play phase or game is over."""
    if game["over"] or game["phase"] != "play" or color not in COLORS:
        return
    if color != game["sequence"][game["player_index"]]:
        game["phase"] = "over"
        game["over"]  = True
        return
    game["player_index"] += 1
    if game["player_index"] == len(game["sequence"]):
        game["sequence"].append(random.choice(COLORS))
        game["player_index"] = 0
        game["phase"] = "watch"


def game_state(game):
    return {
        "sequence":     game["sequence"],
        "player_index": game["player_index"],
        "phase":        game["phase"],
        "over":         game["over"],
        "rounds":       len(game["sequence"]) - 1,
        "level":        game.get("level", "easy"),
        "levels":       list(LEVELS),
    }
