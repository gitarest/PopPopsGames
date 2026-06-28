"""Tests for Connect Four — standard library only (unittest), no deps.

Run:
    python -m unittest test_connectfour
    python test_connectfour.py

Four groups:
  * TestCFGameLogic — pure functions: new_game, drop, check_winner, game_state
  * TestCFAI        — computer_move at easy/medium/hard difficulty
  * TestCFScoring   — cf_apply_score: points, idempotency, persistence
  * TestCFApi       — end-to-end HTTP with cookie-backed sessions
"""

import http.cookiejar
import json
import os
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

import connectfour
import PopPopsGames as server


class ApiClient:
    """A simulated browser: its own cookie jar, hence its own server session."""

    def __init__(self, port):
        self.port = port
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )

    def call(self, path, body=None):
        url = "http://127.0.0.1:%d%s" % (self.port, path)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        with self.opener.open(req) as resp:
            return json.loads(resp.read().decode())


class IsolatedScores(unittest.TestCase):
    """Base class: redirect SCORES to a temp file and start from an empty map."""

    def setUp(self):
        fd, self._path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self._orig_file = server.SCORES_FILE
        self._orig_scores = server.SCORES
        server.SCORES_FILE = self._path
        server.SCORES = {}

    def tearDown(self):
        server.SCORES_FILE = self._orig_file
        server.SCORES = self._orig_scores
        os.unlink(self._path)


def make_board():
    return [[None] * connectfour.COLS for _ in range(connectfour.ROWS)]


class TestCFGameLogic(unittest.TestCase):
    """Pure game logic: new_game, drop_piece, valid_cols, check_winner, game_state."""

    def test_new_game_is_fresh(self):
        g = connectfour.new_game()
        self.assertFalse(g["over"])
        self.assertIsNone(g["winner"])
        self.assertIsNone(g["winning_cells"])
        self.assertFalse(g["scored"])
        for row in g["board"]:
            self.assertEqual(row, [None] * connectfour.COLS)

    def test_new_game_default_level(self):
        g = connectfour.new_game()
        self.assertEqual(g["level"], connectfour.DEFAULT_LEVEL)

    def test_new_game_explicit_level(self):
        self.assertEqual(connectfour.new_game("easy")["level"], "easy")
        self.assertEqual(connectfour.new_game("hard")["level"], "hard")

    def test_new_game_invalid_level_falls_back(self):
        g = connectfour.new_game("impossible")
        self.assertEqual(g["level"], connectfour.DEFAULT_LEVEL)

    def test_drop_piece_falls_to_bottom(self):
        board = make_board()
        row = connectfour.drop_piece(board, 3, "P")
        self.assertEqual(row, connectfour.ROWS - 1)
        self.assertEqual(board[connectfour.ROWS - 1][3], "P")

    def test_drop_piece_stacks(self):
        board = make_board()
        connectfour.drop_piece(board, 3, "P")
        row = connectfour.drop_piece(board, 3, "C")
        self.assertEqual(row, connectfour.ROWS - 2)
        self.assertEqual(board[connectfour.ROWS - 2][3], "C")

    def test_full_column_returns_negative_one(self):
        board = make_board()
        for _ in range(connectfour.ROWS):
            connectfour.drop_piece(board, 0, "P")
        self.assertEqual(connectfour.drop_piece(board, 0, "C"), -1)

    def test_full_column_excluded_from_valid_cols(self):
        board = make_board()
        for _ in range(connectfour.ROWS):
            connectfour.drop_piece(board, 0, "P")
        self.assertNotIn(0, connectfour.valid_cols(board))

    def test_no_winner_on_partial_board(self):
        board = make_board()
        for c in range(3):
            connectfour.drop_piece(board, c, "P")
        self.assertIsNone(connectfour.check_winner(board))

    def test_horizontal_win(self):
        board = make_board()
        for c in range(4):
            connectfour.drop_piece(board, c, "P")
        self.assertEqual(connectfour.check_winner(board), "P")

    def test_vertical_win(self):
        board = make_board()
        for _ in range(4):
            connectfour.drop_piece(board, 2, "C")
        self.assertEqual(connectfour.check_winner(board), "C")

    def test_diagonal_win(self):
        # P at (5,0), (4,1), (3,2), (2,3) — diagonal down-left starting at (2,3)
        board = make_board()
        connectfour.drop_piece(board, 0, "P")               # P at row 5
        connectfour.drop_piece(board, 1, "C")
        connectfour.drop_piece(board, 1, "P")               # P at row 4
        connectfour.drop_piece(board, 2, "C")
        connectfour.drop_piece(board, 2, "C")
        connectfour.drop_piece(board, 2, "P")               # P at row 3
        connectfour.drop_piece(board, 3, "C")
        connectfour.drop_piece(board, 3, "C")
        connectfour.drop_piece(board, 3, "C")
        connectfour.drop_piece(board, 3, "P")               # P at row 2
        self.assertEqual(connectfour.check_winner(board), "P")

    def test_draw_on_full_board_no_winner(self):
        # Checkerboard-shifted pattern: 2P/2C per column offset by 2 per column.
        # This fills all 42 cells without creating any 4-in-a-row.
        board = make_board()
        for c in range(connectfour.COLS):
            offset = (c * 2) % 4
            for r in range(connectfour.ROWS):
                board[r][c] = "P" if (r + offset) % 4 < 2 else "C"
        self.assertFalse(connectfour.valid_cols(board))
        self.assertEqual(connectfour.check_winner(board), "draw")

    def test_game_state_fields(self):
        g = connectfour.new_game()
        st = connectfour.game_state(g)
        for key in ("board", "level", "levels", "over", "winner", "winning_cells"):
            self.assertIn(key, st)

    def test_winning_cells_set_on_game_over(self):
        g = connectfour.new_game("easy")
        board = g["board"]
        for c in range(4):
            connectfour.drop_piece(board, c, "P")
        connectfour._finish(g, "P")
        self.assertIsNotNone(g["winning_cells"])
        self.assertEqual(len(g["winning_cells"]), 4)

    def test_drop_ignored_when_game_over(self):
        g = connectfour.new_game("easy")
        board = g["board"]
        for c in range(4):
            connectfour.drop_piece(board, c, "P")
        connectfour._finish(g, "P")
        connectfour.drop(g, 4)
        # Column 4 must be untouched since drop() returned early
        self.assertTrue(all(board[r][4] is None for r in range(connectfour.ROWS)))


class TestCFAI(unittest.TestCase):
    """computer_move across difficulty levels."""

    def test_easy_returns_valid_column(self):
        board = make_board()
        col = connectfour.computer_move(board, "easy")
        self.assertIn(col, connectfour.valid_cols(board))

    def test_medium_blocks_imminent_player_win(self):
        # P has 3 in a row at cols 0–2, row 5; medium AI must block at col 3.
        board = make_board()
        for c in range(3):
            connectfour.drop_piece(board, c, "P")
        self.assertEqual(connectfour.computer_move(board, "medium"), 3)

    def test_hard_blocks_imminent_player_win(self):
        board = make_board()
        for c in range(3):
            connectfour.drop_piece(board, c, "P")
        self.assertEqual(connectfour.computer_move(board, "hard"), 3)

    def test_medium_takes_winning_move(self):
        # C has 3 in a row vertically at col 2; AI must win by playing col 2.
        board = make_board()
        for _ in range(3):
            connectfour.drop_piece(board, 2, "C")
        self.assertEqual(connectfour.computer_move(board, "medium"), 2)

    def test_no_valid_col_returns_none(self):
        board = make_board()
        for c in range(connectfour.COLS):
            for _ in range(connectfour.ROWS):
                connectfour.drop_piece(board, c, "P")
        self.assertIsNone(connectfour.computer_move(board, "medium"))


class TestCFScoring(IsolatedScores):
    """cf_apply_score: points, idempotency, persistence."""

    @staticmethod
    def finished_cf_session(name=None, winner="P"):
        sess = server.new_session()
        sess["name"] = name
        sess["cf_game"]["winner"] = winner
        sess["cf_game"]["over"] = True
        return sess

    def test_player_win_awards_player_point(self):
        sess = self.finished_cf_session(winner="P")
        server.cf_apply_score(sess)
        self.assertEqual(sess["guest_score"]["connectfour"], {"player": 1, "hangman": 0})

    def test_computer_win_awards_hangman_point(self):
        sess = self.finished_cf_session(winner="C")
        server.cf_apply_score(sess)
        self.assertEqual(sess["guest_score"]["connectfour"], {"player": 0, "hangman": 1})

    def test_draw_awards_no_points(self):
        sess = self.finished_cf_session(winner="draw")
        server.cf_apply_score(sess)
        self.assertEqual(sess["guest_score"]["connectfour"], {"player": 0, "hangman": 0})

    def test_score_applied_exactly_once(self):
        sess = self.finished_cf_session(winner="P")
        server.cf_apply_score(sess)
        server.cf_apply_score(sess)
        self.assertEqual(sess["guest_score"]["connectfour"]["player"], 1)

    def test_incomplete_game_not_scored(self):
        sess = server.new_session()
        server.cf_apply_score(sess)
        self.assertNotIn("connectfour", sess["guest_score"])

    def test_named_score_persists(self):
        sess = self.finished_cf_session(name="Alice", winner="P")
        server.cf_apply_score(sess)
        self.assertEqual(server.SCORES["Alice"]["connectfour"]["player"], 1)


class TestCFApi(IsolatedScores):
    """End-to-end Connect Four over HTTP with cookie-backed sessions."""

    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.HangmanHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls._orig_log = server.HangmanHandler.log_message
        server.HangmanHandler.log_message = lambda *_: None

    @classmethod
    def tearDownClass(cls):
        server.HangmanHandler.log_message = cls._orig_log
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def client(self):
        return ApiClient(self.port)

    def test_state_returns_expected_fields(self):
        st = self.client().call("/connectfour/state")
        for key in ("board", "level", "levels", "over", "winner",
                    "winning_cells", "score", "name", "names"):
            self.assertIn(key, st)
        self.assertFalse(st["over"])

    def test_board_is_6x7(self):
        st = self.client().call("/connectfour/state")
        self.assertEqual(len(st["board"]), 6)
        self.assertEqual(len(st["board"][0]), 7)

    def test_drop_places_pieces(self):
        c = self.client()
        c.call("/connectfour/new", {"level": "easy"})
        st = c.call("/connectfour/drop", {"col": 3})
        total = sum(1 for row in st["board"] for cell in row if cell is not None)
        self.assertGreaterEqual(total, 1)

    def test_invalid_column_ignored(self):
        c = self.client()
        c.call("/connectfour/new", {"level": "easy"})
        before = c.call("/connectfour/state")["board"]
        after  = c.call("/connectfour/drop", {"col": 99})["board"]
        self.assertEqual(before, after)

    def test_new_resets_board(self):
        c = self.client()
        c.call("/connectfour/new", {"level": "easy"})
        c.call("/connectfour/drop", {"col": 3})
        st = c.call("/connectfour/new", {})
        for row in st["board"]:
            self.assertEqual(row, [None] * 7)
        self.assertFalse(st["over"])

    def test_level_change_takes_effect(self):
        c = self.client()
        st = c.call("/connectfour/new", {"level": "hard"})
        self.assertEqual(st["level"], "hard")

    def test_sessions_are_independent(self):
        a, b = self.client(), self.client()
        a.call("/connectfour/new", {"level": "easy"})
        a.call("/connectfour/drop", {"col": 3})
        st_b = b.call("/connectfour/state")
        total = sum(1 for row in st_b["board"] for cell in row if cell is not None)
        self.assertEqual(total, 0)

    def test_score_fields_present(self):
        c = self.client()
        st = c.call("/connectfour/state")
        self.assertIn("player", st["score"])
        self.assertIn("hangman", st["score"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
