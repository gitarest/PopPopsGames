"""Tetris game logic for Pop Pop's Games.

Server-authoritative gravity: the server tracks wall-clock time (`last_drop`)
so pieces keep falling even if the client never calls in — `_apply_gravity`
is invoked at the top of every handler and reconciles however much real time
has passed since the last drop.
"""

import random
import time

COLS = 10
ROWS = 20

LEVELS = ["easy", "medium", "hard"]      # difficulty = starting speed
DEFAULT_LEVEL = "medium"

START_SPEED_MS = {"easy": 800, "medium": 500, "hard": 300}
MIN_SPEED_MS = 100
LINES_PER_LEVEL_UP = 10
SPEED_MULT_PER_LEVEL = 0.9               # interval shrinks (speeds up) each level-up

PIECES = {
    "I": {"size": 4, "color": "#22d3ee", "rotations": [
        [(1, 0), (1, 1), (1, 2), (1, 3)],
        [(0, 2), (1, 2), (2, 2), (3, 2)],
        [(2, 0), (2, 1), (2, 2), (2, 3)],
        [(0, 1), (1, 1), (2, 1), (3, 1)],
    ]},
    "O": {"size": 2, "color": "#facc15", "rotations": [
        [(0, 0), (0, 1), (1, 0), (1, 1)],
        [(0, 0), (0, 1), (1, 0), (1, 1)],
        [(0, 0), (0, 1), (1, 0), (1, 1)],
        [(0, 0), (0, 1), (1, 0), (1, 1)],
    ]},
    "T": {"size": 3, "color": "#a855f7", "rotations": [
        [(0, 1), (1, 0), (1, 1), (1, 2)],
        [(0, 1), (1, 1), (1, 2), (2, 1)],
        [(1, 0), (1, 1), (1, 2), (2, 1)],
        [(0, 1), (1, 0), (1, 1), (2, 1)],
    ]},
    "S": {"size": 3, "color": "#4ade80", "rotations": [
        [(0, 1), (0, 2), (1, 0), (1, 1)],
        [(0, 1), (1, 1), (1, 2), (2, 2)],
        [(1, 1), (1, 2), (2, 0), (2, 1)],
        [(0, 0), (1, 0), (1, 1), (2, 1)],
    ]},
    "Z": {"size": 3, "color": "#f87171", "rotations": [
        [(0, 0), (0, 1), (1, 1), (1, 2)],
        [(0, 2), (1, 1), (1, 2), (2, 1)],
        [(1, 0), (1, 1), (2, 1), (2, 2)],
        [(0, 1), (1, 0), (1, 1), (2, 0)],
    ]},
    "J": {"size": 3, "color": "#3b82f6", "rotations": [
        [(0, 0), (1, 0), (1, 1), (1, 2)],
        [(0, 1), (0, 2), (1, 1), (2, 1)],
        [(1, 0), (1, 1), (1, 2), (2, 2)],
        [(0, 1), (1, 1), (2, 0), (2, 1)],
    ]},
    "L": {"size": 3, "color": "#fb923c", "rotations": [
        [(0, 2), (1, 0), (1, 1), (1, 2)],
        [(0, 1), (1, 1), (2, 1), (2, 2)],
        [(1, 0), (1, 1), (1, 2), (2, 0)],
        [(0, 0), (0, 1), (1, 1), (2, 1)],
    ]},
}
PIECE_TYPES = list(PIECES.keys())


def _spawn_col(piece_type):
    return (COLS - PIECES[piece_type]["size"]) // 2


def _speed_for(level_num, level):
    base = START_SPEED_MS.get(level, START_SPEED_MS[DEFAULT_LEVEL])
    interval = base * (SPEED_MULT_PER_LEVEL ** (level_num - 1))
    return max(MIN_SPEED_MS, int(interval))


def new_game(level=DEFAULT_LEVEL):
    if level not in LEVELS:
        level = DEFAULT_LEVEL
    first_type = random.choice(PIECE_TYPES)
    return {
        "board": [[None] * COLS for _ in range(ROWS)],
        "piece_type": first_type,
        "rotation": 0,
        "row": 0,
        "col": _spawn_col(first_type),
        "next_type": random.choice(PIECE_TYPES),
        "lines": 0,
        "level_num": 1,
        "level": level,
        "drop_interval": _speed_for(1, level),
        "last_drop": time.monotonic(),
        "over": False,
        "scored": False,
    }


def _cells(game, piece_type=None, rotation=None, row=None, col=None):
    piece_type = game["piece_type"] if piece_type is None else piece_type
    rotation = game["rotation"] if rotation is None else rotation
    row = game["row"] if row is None else row
    col = game["col"] if col is None else col
    offsets = PIECES[piece_type]["rotations"][rotation]
    return [(row + dr, col + dc) for dr, dc in offsets]


def _collides(game, piece_type=None, rotation=None, row=None, col=None):
    for r, c in _cells(game, piece_type, rotation, row, col):
        if c < 0 or c >= COLS or r < 0 or r >= ROWS:
            return True
        if game["board"][r][c] is not None:
            return True
    return False


def _clear_lines(game):
    board = game["board"]
    remaining = [row for row in board if any(cell is None for cell in row)]
    cleared = ROWS - len(remaining)
    if cleared:
        game["board"] = [[None] * COLS for _ in range(cleared)] + remaining
        game["lines"] += cleared
        new_level_num = 1 + game["lines"] // LINES_PER_LEVEL_UP
        if new_level_num != game["level_num"]:
            game["level_num"] = new_level_num
            game["drop_interval"] = _speed_for(new_level_num, game["level"])
    return cleared


def _lock_piece(game):
    color = PIECES[game["piece_type"]]["color"]
    for r, c in _cells(game):
        game["board"][r][c] = color
    _clear_lines(game)

    game["piece_type"] = game["next_type"]
    game["next_type"] = random.choice(PIECE_TYPES)
    game["rotation"] = 0
    game["row"] = 0
    game["col"] = _spawn_col(game["piece_type"])
    game["last_drop"] = time.monotonic()
    if _collides(game):
        game["over"] = True


def _step_down(game):
    """Move the piece down one row, or lock it if it can't. Returns True if it locked."""
    if not _collides(game, row=game["row"] + 1):
        game["row"] += 1
        return False
    _lock_piece(game)
    return True


def _apply_gravity(game):
    """Reconcile however much real time has passed since the last drop."""
    if game["over"]:
        return
    now = time.monotonic()
    while not game["over"]:
        interval = game["drop_interval"] / 1000.0
        if now - game["last_drop"] < interval:
            break
        locked = _step_down(game)
        if locked:
            break  # freshly spawned piece starts its own full interval
        game["last_drop"] += interval


def move(game, action):
    """action: left | right | rotate | soft_drop | hard_drop"""
    _apply_gravity(game)
    if game["over"]:
        return

    if action == "left":
        if not _collides(game, col=game["col"] - 1):
            game["col"] -= 1
    elif action == "right":
        if not _collides(game, col=game["col"] + 1):
            game["col"] += 1
    elif action == "rotate":
        new_rotation = (game["rotation"] + 1) % 4
        if not _collides(game, rotation=new_rotation):
            game["rotation"] = new_rotation
    elif action == "soft_drop":
        _step_down(game)
        game["last_drop"] = time.monotonic()
    elif action == "hard_drop":
        while not _collides(game, row=game["row"] + 1):
            game["row"] += 1
        _lock_piece(game)


def tick(game):
    """Heartbeat: just reconciles gravity."""
    _apply_gravity(game)


def game_state(game):
    """Client view: board with the falling piece merged in, next-piece preview, stats."""
    board = [row[:] for row in game["board"]]
    if not game["over"]:
        color = PIECES[game["piece_type"]]["color"]
        for r, c in _cells(game):
            if 0 <= r < ROWS and 0 <= c < COLS:
                board[r][c] = color

    next_type = game["next_type"]
    return {
        "board": board,
        "next_cells": [list(cell) for cell in PIECES[next_type]["rotations"][0]],
        "next_color": PIECES[next_type]["color"],
        "lines": game["lines"],
        "level_num": game["level_num"],
        "level": game["level"],
        "levels": LEVELS,
        "drop_interval": game["drop_interval"],
        "over": game["over"],
    }
