"""Tic-Tac-Toe game logic and minimax AI for Pop Pop's Games."""

import random

# All eight winning lines for a 3×3 board (indexed 0-8, row-major).
TTT_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
]


def new_game(level="easy"):
    """Return a fresh TTT game dict."""
    if level not in ("easy", "expert"):
        level = "expert"
    return {"board": [None] * 9, "over": False, "winner": None, "scored": False, "level": level}


def check_winner(board):
    """Return 'X', 'O', 'draw', or None."""
    for a, b, c in TTT_LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    if all(x is not None for x in board):
        return "draw"
    return None


def _minimax(board, is_maximizing):
    """Standard minimax. O maximizes, X minimizes."""
    winner = check_winner(board)
    if winner == "O":    return 1
    if winner == "X":    return -1
    if winner == "draw": return 0
    scores = []
    for i in range(9):
        if board[i] is None:
            board[i] = "O" if is_maximizing else "X"
            scores.append(_minimax(board, not is_maximizing))
            board[i] = None
    return max(scores) if is_maximizing else min(scores)


def random_move(board):
    """Return a random empty cell index, or None if the board is full."""
    empties = [i for i in range(9) if board[i] is None]
    return random.choice(empties) if empties else None


def best_move(board):
    """Return the index of the best cell for the computer (O), or None."""
    best_score, move = float("-inf"), None
    for i in range(9):
        if board[i] is None:
            board[i] = "O"
            score = _minimax(board, False)
            board[i] = None
            if score > best_score:
                best_score, move = score, i
    return move


def game_state(game):
    """Build the client view of a TTT game, including the winning line."""
    winning_line = None
    if game["winner"] and game["winner"] != "draw":
        b = game["board"]
        for combo in TTT_LINES:
            if b[combo[0]] == b[combo[1]] == b[combo[2]] == game["winner"]:
                winning_line = list(combo)
                break
    return {
        "board": game["board"],
        "over": game["over"],
        "winner": game["winner"],
        "winning_line": winning_line,
        "level": game.get("level", "expert"),
        "levels": ["easy", "expert"],
    }
