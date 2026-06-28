"""Connect Four game logic and AI for Pop Pop's Games."""

import random

ROWS = 6
COLS = 7
PLAYER = "P"
COMPUTER = "C"
LEVELS = ("easy", "medium", "hard")
DEFAULT_LEVEL = "medium"

# Minimax search depth per difficulty. Easy uses random moves (depth unused).
_AI_DEPTH = {"medium": 3, "hard": 5}

# Center-first column order for better alpha-beta pruning.
_COL_ORDER = [3, 2, 4, 1, 5, 0, 6]


def new_game(level=DEFAULT_LEVEL):
    if level not in LEVELS:
        level = DEFAULT_LEVEL
    return {
        "board": [[None] * COLS for _ in range(ROWS)],
        "level": level,
        "over": False,
        "winner": None,         # "P", "C", or "draw"
        "winning_cells": None,  # [[row, col], ...] of the winning four
        "scored": False,
    }


def valid_cols(board):
    """Return column indices that still have at least one empty cell."""
    return [c for c in range(COLS) if board[0][c] is None]


def drop_piece(board, col, piece):
    """Drop piece into col (row 0 = top). Returns the row it landed on."""
    for row in range(ROWS - 1, -1, -1):
        if board[row][col] is None:
            board[row][col] = piece
            return row
    return -1


def _find_winning_cells(board, piece):
    """Return [[row,col],...] for the first 4-in-a-row of piece, or None."""
    for r in range(ROWS):                       # horizontal
        for c in range(COLS - 3):
            cells = [[r, c + i] for i in range(4)]
            if all(board[r2][c2] == piece for r2, c2 in cells):
                return cells
    for r in range(ROWS - 3):                   # vertical
        for c in range(COLS):
            cells = [[r + i, c] for i in range(4)]
            if all(board[r2][c2] == piece for r2, c2 in cells):
                return cells
    for r in range(ROWS - 3):                   # diagonal down-right
        for c in range(COLS - 3):
            cells = [[r + i, c + i] for i in range(4)]
            if all(board[r2][c2] == piece for r2, c2 in cells):
                return cells
    for r in range(ROWS - 3):                   # diagonal down-left
        for c in range(3, COLS):
            cells = [[r + i, c - i] for i in range(4)]
            if all(board[r2][c2] == piece for r2, c2 in cells):
                return cells
    return None


def check_winner(board):
    """Return 'P', 'C', 'draw', or None."""
    for piece in (PLAYER, COMPUTER):
        if _find_winning_cells(board, piece):
            return piece
    if not valid_cols(board):
        return "draw"
    return None


# ---------------------------------------------------------------------------
# Minimax AI
# ---------------------------------------------------------------------------

def _score_window(window, piece):
    opp = COMPUTER if piece == PLAYER else PLAYER
    pc, oc, nc = window.count(piece), window.count(opp), window.count(None)
    if pc == 4:
        return 100
    if pc == 3 and nc == 1:
        return 5
    if oc == 3 and nc == 1:
        return -4
    if pc == 2 and nc == 2:
        return 2
    return 0


def _score_board(board, piece):
    score = [board[r][COLS // 2] for r in range(ROWS)].count(piece) * 3
    for r in range(ROWS):
        for c in range(COLS - 3):
            score += _score_window([board[r][c + i] for i in range(4)], piece)
    for r in range(ROWS - 3):
        for c in range(COLS):
            score += _score_window([board[r + i][c] for i in range(4)], piece)
    for r in range(ROWS - 3):
        for c in range(COLS - 3):
            score += _score_window([board[r + i][c + i] for i in range(4)], piece)
    for r in range(ROWS - 3):
        for c in range(3, COLS):
            score += _score_window([board[r + i][c - i] for i in range(4)], piece)
    return score


def _ordered_valid_cols(board):
    vc = set(valid_cols(board))
    return [c for c in _COL_ORDER if c in vc]


def _minimax(board, depth, alpha, beta, maximizing):
    winner = check_winner(board)
    if winner == COMPUTER:
        return 1000000 + depth
    if winner == PLAYER:
        return -1000000 - depth
    if winner == "draw" or depth == 0:
        return _score_board(board, COMPUTER)
    cols = _ordered_valid_cols(board)
    if maximizing:
        value = float("-inf")
        for col in cols:
            row = drop_piece(board, col, COMPUTER)
            value = max(value, _minimax(board, depth - 1, alpha, beta, False))
            board[row][col] = None
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        return value
    else:
        value = float("inf")
        for col in cols:
            row = drop_piece(board, col, PLAYER)
            value = min(value, _minimax(board, depth - 1, alpha, beta, True))
            board[row][col] = None
            beta = min(beta, value)
            if alpha >= beta:
                break
        return value


def computer_move(board, level):
    """Return the column for the computer's move based on difficulty."""
    cols = _ordered_valid_cols(board)
    if not cols:
        return None
    if level == "easy":
        return random.choice(cols)
    depth = _AI_DEPTH.get(level, 3)
    best_col, best_score = cols[0], float("-inf")
    for col in cols:
        row = drop_piece(board, col, COMPUTER)
        score = _minimax(board, depth - 1, float("-inf"), float("inf"), False)
        board[row][col] = None
        if score > best_score:
            best_score, best_col = score, col
    return best_col


# ---------------------------------------------------------------------------
# Game flow
# ---------------------------------------------------------------------------

def drop(game, col):
    """Apply the player's drop and the computer's response. Mutates game."""
    board = game["board"]
    if game["over"] or col not in valid_cols(board):
        return
    drop_piece(board, col, PLAYER)
    winner = check_winner(board)
    if winner:
        _finish(game, winner)
        return
    comp_col = computer_move(board, game["level"])
    if comp_col is not None:
        drop_piece(board, comp_col, COMPUTER)
        winner = check_winner(board)
        if winner:
            _finish(game, winner)


def _finish(game, winner):
    game["winner"] = winner
    game["over"] = True
    if winner != "draw":
        game["winning_cells"] = _find_winning_cells(game["board"], winner)


def game_state(game):
    return {
        "board": game["board"],
        "level": game["level"],
        "levels": list(LEVELS),
        "over": game["over"],
        "winner": game["winner"],
        "winning_cells": game["winning_cells"],
    }
