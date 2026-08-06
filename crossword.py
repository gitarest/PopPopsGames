"""Kids Crossword game logic for Pop Pop's Games.

Puzzles are hand-authored in crossword_puzzles.py (words + clues + start
positions); this module derives the blocked/active grid, the solution
letters, and standard crossword numbering from those placements, then
tracks the player's own typed letters against that solution.
"""

import random

from crossword_puzzles import PUZZLES_BY_LEVEL, LEVELS, DEFAULT_LEVEL


def _build_grid(puzzle):
    """From word placements, derive the solution grid and each word's cells/number."""
    size = puzzle["size"]
    solution = [[None] * size for _ in range(size)]
    for w in puzzle["words"]:
        r, c, d = w["row"], w["col"], w["dir"]
        for i, ch in enumerate(w["answer"]):
            rr, cc = (r, c + i) if d == "across" else (r + i, c)
            solution[rr][cc] = ch

    starts = sorted({(w["row"], w["col"]) for w in puzzle["words"]})
    number_by_start = {pos: i + 1 for i, pos in enumerate(starts)}

    words = []
    for w in puzzle["words"]:
        r, c, d = w["row"], w["col"], w["dir"]
        cells = [(r, c + i) if d == "across" else (r + i, c) for i in range(len(w["answer"]))]
        words.append({
            "number": number_by_start[(r, c)],
            "dir": d,
            "clue": w["clue"],
            "answer": w["answer"],
            "cells": cells,
        })
    return size, solution, words


def new_game(level=DEFAULT_LEVEL):
    if level not in LEVELS:
        level = DEFAULT_LEVEL
    puzzle = random.choice(PUZZLES_BY_LEVEL[level])
    size, solution, words = _build_grid(puzzle)
    return {
        "level": level,
        "size": size,
        "solution": solution,
        "words": words,
        "player": [[None] * size for _ in range(size)],
        "hints_used": 0,
        "over": False,
        "won": False,
        "scored": False,
    }


def _cell_active(game, row, col):
    if row < 0 or row >= game["size"] or col < 0 or col >= game["size"]:
        return False
    return game["solution"][row][col] is not None


def _word_solved(game, word):
    return all(game["player"][r][c] == game["solution"][r][c] for r, c in word["cells"])


def _check_complete(game):
    size = game["size"]
    solved = all(
        game["player"][r][c] == game["solution"][r][c]
        for r in range(size)
        for c in range(size)
        if game["solution"][r][c] is not None
    )
    if solved:
        game["over"] = True
        game["won"] = True


def set_letter(game, row, col, letter):
    """Player types a letter into an active cell."""
    if game["over"] or not _cell_active(game, row, col):
        return
    letter = (letter or "")[:1].upper()
    if not letter.isalpha():
        return
    game["player"][row][col] = letter
    _check_complete(game)


def clear_letter(game, row, col):
    """Backspace: clear a cell's letter."""
    if game["over"] or not _cell_active(game, row, col):
        return
    game["player"][row][col] = None


def reveal_letter(game, row, col):
    """Hint: fill in the correct letter for a cell; counts against scoring."""
    if game["over"] or not _cell_active(game, row, col):
        return
    game["player"][row][col] = game["solution"][row][col]
    game["hints_used"] += 1
    _check_complete(game)


def game_state(game):
    """Client view: grid cells (blocked/letter/number), across/down clue lists."""
    size = game["size"]
    cell_number = {}
    for w in game["words"]:
        cell_number[w["cells"][0]] = w["number"]

    cells = []
    for r in range(size):
        row_cells = []
        for c in range(size):
            blocked = game["solution"][r][c] is None
            row_cells.append({
                "blocked": blocked,
                "letter": None if blocked else game["player"][r][c],
                "number": cell_number.get((r, c)),
            })
        cells.append(row_cells)

    across, down = [], []
    for w in game["words"]:
        entry = {"number": w["number"], "clue": w["clue"], "solved": _word_solved(game, w)}
        (across if w["dir"] == "across" else down).append(entry)
    across.sort(key=lambda e: e["number"])
    down.sort(key=lambda e: e["number"])

    return {
        "size": size,
        "cells": cells,
        "clues": {"across": across, "down": down},
        "hints_used": game["hints_used"],
        "over": game["over"],
        "won": game["won"],
        "level": game["level"],
        "levels": LEVELS,
    }
