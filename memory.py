"""Memory Match game logic for Pop Pop's Games."""

import random

THEMES = {
    "farm": ["🐄", "🐖", "🐔", "🐑", "🐎", "🐐", "🐓", "🐇", "🦆", "🐴"],
    "zoo":  ["🦁", "🐯", "🐘", "🦒", "🦓", "🦍", "🦏", "🐆", "🦛", "🦘"],
}
DEFAULT_THEME = "farm"

PAR = {"easy": 30, "medium": 25, "hard": 20}
LEVELS = list(PAR.keys())
DEFAULT_LEVEL = "medium"


def _has_adjacent_pair(emoji_list, cols=4):
    """Return True if any matching pair sits directly next to each other (4-directional)."""
    positions = {}
    for i, emoji in enumerate(emoji_list):
        positions.setdefault(emoji, []).append(i)
    for locs in positions.values():
        a, b = locs
        ra, ca = divmod(a, cols)
        rb, cb = divmod(b, cols)
        if abs(ra - rb) + abs(ca - cb) == 1:
            return True
    return False


def new_game(theme=DEFAULT_THEME, level=DEFAULT_LEVEL):
    if theme not in THEMES:
        theme = DEFAULT_THEME
    if level not in PAR:
        level = DEFAULT_LEVEL
    emoji_list = THEMES[theme] * 2
    for _ in range(200):
        random.shuffle(emoji_list)
        if not _has_adjacent_pair(emoji_list):
            break
    return {
        "cards":    [{"emoji": e, "state": "hidden"} for e in emoji_list],
        "theme":    theme,
        "level":    level,
        "par":      PAR[level],
        "flipped":  [],      # indices of currently revealed (not yet matched) cards, max 2
        "matched":  0,       # number of matched pairs found
        "moves":    0,       # pair attempts (incremented on 2nd flip)
        "mismatch": False,   # True when 2 revealed cards don't match
        "over":     False,
        "scored":   False,
    }


def flip(game, index):
    """Flip a card face-up. Handles match detection and mismatch flagging."""
    if game["over"] or game["mismatch"]:
        return
    cards = game["cards"]
    if index < 0 or index >= len(cards):
        return
    if cards[index]["state"] != "hidden":
        return

    cards[index]["state"] = "revealed"
    game["flipped"].append(index)

    if len(game["flipped"]) == 2:
        game["moves"] += 1
        i, j = game["flipped"]
        if cards[i]["emoji"] == cards[j]["emoji"]:
            cards[i]["state"] = "matched"
            cards[j]["state"] = "matched"
            game["flipped"] = []
            game["matched"] += 1
            if game["matched"] == len(THEMES[game["theme"]]):
                game["over"] = True
        else:
            game["mismatch"] = True


def clear_mismatch(game):
    """Flip mismatched pair back to hidden. Called by client after showing them briefly."""
    if not game["mismatch"]:
        return
    for i in game["flipped"]:
        game["cards"][i]["state"] = "hidden"
    game["flipped"] = []
    game["mismatch"] = False


def game_state(game):
    """Return client-visible game state. Hidden cards have emoji=None."""
    return {
        "cards":    [{"emoji": c["emoji"] if c["state"] != "hidden" else None,
                      "state": c["state"]}
                     for c in game["cards"]],
        "theme":    game["theme"],
        "themes":   list(THEMES.keys()),
        "level":    game["level"],
        "levels":   LEVELS,
        "matched":  game["matched"],
        "moves":    game["moves"],
        "mismatch": game["mismatch"],
        "over":     game["over"],
        "par":      game["par"],
    }
