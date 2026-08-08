"""Battleship game logic for Pop Pop's Games."""

import random

BOARD_SIZE = 10
SHIPS = [
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2),
]

LEVELS = ["easy", "medium", "hard"]
DEFAULT_LEVEL = "easy"
LEVEL_POINTS = {"easy": 1, "medium": 2, "hard": 3}


def _neighbors4(row, col):
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        r, c = row + dr, col + dc
        if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
            yield r, c


def _place_fleet_randomly():
    """Random valid placement of the whole fleet, no overlaps."""
    grid = [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
    ships = []
    for ship_idx, (name, length) in enumerate(SHIPS):
        while True:
            horizontal = random.choice([True, False])
            if horizontal:
                row = random.randint(0, BOARD_SIZE - 1)
                col = random.randint(0, BOARD_SIZE - length)
                cells = [(row, col + i) for i in range(length)]
            else:
                row = random.randint(0, BOARD_SIZE - length)
                col = random.randint(0, BOARD_SIZE - 1)
                cells = [(row + i, col) for i in range(length)]
            if all(grid[r][c] is None for r, c in cells):
                for r, c in cells:
                    grid[r][c] = ship_idx
                ships.append({"name": name, "length": length, "cells": cells, "hits": set()})
                break
    return {"grid": grid, "ships": ships}


def _is_sunk(ship):
    return len(ship["hits"]) >= ship["length"]


def _all_sunk(board):
    return all(_is_sunk(ship) for ship in board["ships"])


def new_game(level=DEFAULT_LEVEL):
    if level not in LEVEL_POINTS:
        level = DEFAULT_LEVEL
    return {
        "level": level,
        "player_board": _place_fleet_randomly(),
        "computer_board": _place_fleet_randomly(),
        "player_shots": {},    # {(r, c): "hit" | "miss"} fired by the player at computer_board
        "computer_shots": {},  # {(r, c): "hit" | "miss"} fired by the computer at player_board
        "ai_targets": [],      # stack of candidate cells queued while hunting a damaged ship
        "first_shot_fired": False,
        "over": False,
        "won": None,
        "scored": False,
    }


def randomize_player_fleet(game):
    """Reroll the player's own fleet layout. Locked once the battle starts."""
    if game["over"] or game["first_shot_fired"]:
        return
    game["player_board"] = _place_fleet_randomly()


def _choose_ai_shot(game):
    shots = game["computer_shots"]
    while game["ai_targets"]:
        r, c = game["ai_targets"].pop()
        if (r, c) not in shots:
            return r, c
    candidates = [(r, c) for r in range(BOARD_SIZE) for c in range(BOARD_SIZE) if (r, c) not in shots]
    if game["level"] == "hard":
        # Every ship is at least 2 cells long, so it must occupy a parity cell —
        # searching only these first finds ships in roughly half the shots.
        parity = [(r, c) for (r, c) in candidates if (r + c) % 2 == 0]
        if parity:
            candidates = parity
    return random.choice(candidates)


def _computer_turn(game):
    board = game["player_board"]
    row, col = _choose_ai_shot(game)
    ship_idx = board["grid"][row][col]
    if ship_idx is not None:
        game["computer_shots"][(row, col)] = "hit"
        ship = board["ships"][ship_idx]
        ship["hits"].add((row, col))
        if _is_sunk(ship):
            game["ai_targets"] = []  # done hunting this ship; simple single-target AI
        elif game["level"] in ("medium", "hard"):
            for nr, nc in _neighbors4(row, col):
                if (nr, nc) not in game["computer_shots"] and (nr, nc) not in game["ai_targets"]:
                    game["ai_targets"].append((nr, nc))
    else:
        game["computer_shots"][(row, col)] = "miss"

    if _all_sunk(board):
        game["over"] = True
        game["won"] = False


def fire(game, row, col):
    """Player fires at the computer's board; the computer immediately fires back."""
    if game["over"]:
        return
    if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
        return
    if (row, col) in game["player_shots"]:
        return

    game["first_shot_fired"] = True
    board = game["computer_board"]
    ship_idx = board["grid"][row][col]
    if ship_idx is not None:
        game["player_shots"][(row, col)] = "hit"
        board["ships"][ship_idx]["hits"].add((row, col))
    else:
        game["player_shots"][(row, col)] = "miss"

    if _all_sunk(board):
        game["over"] = True
        game["won"] = True
        return

    _computer_turn(game)


def _board_view(board, shots, reveal_ships):
    """reveal_ships=True for the player's own board (always visible to them).
    For the enemy board, a ship only becomes visible once it's fully sunk.

    `sunk` is reported separately from `ship` because `ship` means different
    things per board (always true where a ship sits, on the always-visible
    own board) — the client needs an explicit, board-independent signal for
    "this specific cell belongs to a fully-sunk ship" to style a damaged-but-
    afloat hit differently from a sunk one on either board.

    `damaged` marks every cell of a ship that has taken at least one hit but
    isn't sunk yet, so the whole ship can be styled as wounded rather than
    just the individual hit cell — but only on the always-visible own board;
    revealing an enemy ship's *undamaged* cells early (just because one of
    its other cells was hit) would leak position info the player hasn't
    earned by actually hitting those cells."""
    sunk_cells = set()
    damaged_cells = set()
    for ship in board["ships"]:
        if _is_sunk(ship):
            sunk_cells.update(ship["cells"])
        elif ship["hits"]:
            damaged_cells.update(ship["cells"])
    cells = []
    for r in range(BOARD_SIZE):
        row_out = []
        for c in range(BOARD_SIZE):
            has_ship = board["grid"][r][c] is not None
            is_sunk_cell = (r, c) in sunk_cells
            row_out.append({
                "shot": shots.get((r, c)),
                "ship": has_ship and (reveal_ships or is_sunk_cell),
                "sunk": is_sunk_cell,
                "damaged": (r, c) in damaged_cells and reveal_ships,
            })
        cells.append(row_out)
    return cells


def _ship_status(ship):
    if _is_sunk(ship):
        return "sunk"
    if ship["hits"]:
        return "damaged"
    return "intact"


def _fleet_roster(board):
    return [{"name": s["name"], "length": s["length"], "status": _ship_status(s)} for s in board["ships"]]


def game_state(game):
    player_board = game["player_board"]
    computer_board = game["computer_board"]
    return {
        "your_fleet": _board_view(player_board, game["computer_shots"], reveal_ships=True),
        "enemy_waters": _board_view(computer_board, game["player_shots"], reveal_ships=False),
        "ships_remaining": {
            "player": sum(1 for s in player_board["ships"] if not _is_sunk(s)),
            "computer": sum(1 for s in computer_board["ships"] if not _is_sunk(s)),
        },
        "fleets": {
            "player": _fleet_roster(player_board),
            "computer": _fleet_roster(computer_board),
        },
        "board_size": BOARD_SIZE,
        "level": game["level"],
        "levels": LEVELS,
        "first_shot_fired": game["first_shot_fired"],
        "over": game["over"],
        "won": game["won"],
    }
