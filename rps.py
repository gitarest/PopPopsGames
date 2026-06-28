"""Rock Paper Scissors game logic for Pop Pop's Games."""

import random

CHOICES = ("rock", "paper", "scissors")
# Maps each choice to the one it beats.
BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}


def new_game():
    return {
        "player_choice": None,
        "computer_choice": None,
        "result": None,
        "over": False,
        "scored": False,
    }


def play(game, player_choice, _computer_choice=None):
    """Record both choices and determine the result.

    _computer_choice overrides the random pick — used only in tests.
    """
    if game["over"] or player_choice not in CHOICES:
        return
    computer_choice = _computer_choice if _computer_choice in CHOICES else random.choice(CHOICES)
    game["player_choice"] = player_choice
    game["computer_choice"] = computer_choice
    if player_choice == computer_choice:
        game["result"] = "tie"
    elif BEATS[player_choice] == computer_choice:
        game["result"] = "win"
    else:
        game["result"] = "loss"
    game["over"] = True


def game_state(game):
    return {
        "player_choice": game["player_choice"],
        "computer_choice": game["computer_choice"],
        "result": game["result"],
        "over": game["over"],
    }
