"""Minesweeper game logic for Pop Pop's Games."""

import random

LEVELS = ["easy", "medium", "hard"]
DEFAULT_LEVEL = "easy"
LEVEL_POINTS = {"easy": 1, "medium": 2, "hard": 3}
LEVEL_CONFIG = {
    "easy":   {"rows": 8,  "cols": 8,  "mines": 8},
    "medium": {"rows": 10, "cols": 10, "mines": 18},
    "hard":   {"rows": 12, "cols": 12, "mines": 30},
}


def _neighbors(row, col, rows, cols):
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            r, c = row + dr, col + dc
            if 0 <= r < rows and 0 <= c < cols:
                yield r, c


def new_game(level=DEFAULT_LEVEL):
    if level not in LEVEL_CONFIG:
        level = DEFAULT_LEVEL
    cfg = LEVEL_CONFIG[level]
    rows, cols = cfg["rows"], cfg["cols"]
    board = [[{"mine": False, "flagged": False, "revealed": False, "count": 0}
              for _ in range(cols)] for _ in range(rows)]
    return {
        "board": board,
        "rows": rows,
        "cols": cols,
        "mines_total": cfg["mines"],
        "level": level,
        "mines_placed": False,
        "revealed_safe": 0,
        "over": False,
        "won": False,
        "scored": False,
        "hit": None,
    }


def _place_mines(game, safe_row, safe_col):
    """Place mines avoiding the first-clicked cell and its neighbors, so the
    opening click never immediately loses the game."""
    rows, cols = game["rows"], game["cols"]
    safe_zone = {(safe_row, safe_col)} | set(_neighbors(safe_row, safe_col, rows, cols))
    candidates = [(r, c) for r in range(rows) for c in range(cols) if (r, c) not in safe_zone]
    mines = set(random.sample(candidates, game["mines_total"]))
    board = game["board"]
    for r, c in mines:
        board[r][c]["mine"] = True
    for r in range(rows):
        for c in range(cols):
            if not board[r][c]["mine"]:
                board[r][c]["count"] = sum(1 for nr, nc in _neighbors(r, c, rows, cols) if board[nr][nc]["mine"])
    game["mines_placed"] = True


def _reveal_all(game):
    for row in game["board"]:
        for cell in row:
            cell["revealed"] = True


def _flood_reveal(game, row, col):
    """Reveal (row, col) and cascade outward through connected zero-count
    cells, stopping at flagged cells and numbered borders."""
    board = game["board"]
    rows, cols = game["rows"], game["cols"]
    stack = [(row, col)]
    while stack:
        r, c = stack.pop()
        cell = board[r][c]
        if cell["revealed"] or cell["flagged"]:
            continue
        cell["revealed"] = True
        game["revealed_safe"] += 1
        if cell["count"] == 0:
            for nr, nc in _neighbors(r, c, rows, cols):
                if not board[nr][nc]["revealed"] and not board[nr][nc]["flagged"]:
                    stack.append((nr, nc))


def reveal(game, row, col):
    if game["over"]:
        return
    rows, cols = game["rows"], game["cols"]
    if not (0 <= row < rows and 0 <= col < cols):
        return
    cell = game["board"][row][col]
    if cell["revealed"] or cell["flagged"]:
        return

    if not game["mines_placed"]:
        _place_mines(game, row, col)

    if cell["mine"]:
        cell["revealed"] = True
        game["over"] = True
        game["won"] = False
        game["hit"] = [row, col]
        _reveal_all(game)
        return

    _flood_reveal(game, row, col)

    total_safe = rows * cols - game["mines_total"]
    if game["revealed_safe"] >= total_safe:
        game["over"] = True
        game["won"] = True
        for board_row in game["board"]:
            for c in board_row:
                if c["mine"]:
                    c["flagged"] = True
        _reveal_all(game)


def flag(game, row, col):
    if game["over"]:
        return
    rows, cols = game["rows"], game["cols"]
    if not (0 <= row < rows and 0 <= col < cols):
        return
    cell = game["board"][row][col]
    if cell["revealed"]:
        return
    cell["flagged"] = not cell["flagged"]


def game_state(game):
    flags_used = 0
    cells = []
    for row in game["board"]:
        out_row = []
        for cell in row:
            flagged = cell["flagged"]
            if flagged:
                flags_used += 1
            revealed = cell["revealed"]
            out_row.append({
                "revealed": revealed,
                "flagged": flagged,
                "mine": cell["mine"] if revealed else None,
                "count": cell["count"] if (revealed and not cell["mine"]) else None,
                "wrong_flag": game["over"] and flagged and not cell["mine"],
            })
        cells.append(out_row)
    return {
        "cells": cells,
        "rows": game["rows"],
        "cols": game["cols"],
        "mines_total": game["mines_total"],
        "flags_used": flags_used,
        "level": game["level"],
        "levels": LEVELS,
        "over": game["over"],
        "won": game["won"],
        "hit": game["hit"],
    }
