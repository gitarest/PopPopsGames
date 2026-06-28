"""Tests for Tic-Tac-Toe — standard library only (unittest), no deps.

Run:
    python -m unittest test_tictactoe
    python test_tictactoe.py

Four groups:
  * TestTTTGameLogic — pure functions: check_winner, game_state, new_game.
  * TestTTTAI        — best_move correctness and unbeatable-AI property.
  * TestTTTScoring   — ttt_apply_score: points, idempotency, persistence.
  * TestTTTApi       — end-to-end HTTP with cookie-backed sessions.
"""

import http.cookiejar
import json
import os
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

import PopPopsGames as server


def make_ttt_game(board, over=False, winner=None):
    """A TTT game dict with a custom board state."""
    return {"board": list(board), "over": over, "winner": winner, "scored": False}


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


class TestTTTGameLogic(unittest.TestCase):
    """Pure functions: check_winner, game_state, new_ttt_game."""

    def test_new_game_is_empty(self):
        g = server.new_ttt_game()
        self.assertEqual(g["board"], [None] * 9)
        self.assertFalse(g["over"])
        self.assertIsNone(g["winner"])
        self.assertFalse(g["scored"])

    def test_check_winner_x_wins_row(self):
        board = ["X", "X", "X", None, None, None, None, None, None]
        self.assertEqual(server.ttt_check_winner(board), "X")

    def test_check_winner_o_wins_column(self):
        board = ["O", "X", None, "O", "X", None, "O", None, None]
        self.assertEqual(server.ttt_check_winner(board), "O")

    def test_check_winner_x_wins_diagonal(self):
        board = ["X", "O", None, None, "X", "O", None, None, "X"]
        self.assertEqual(server.ttt_check_winner(board), "X")

    def test_check_winner_draw_on_full_board(self):
        board = ["X", "O", "X", "O", "X", "O", "O", "X", "O"]
        self.assertEqual(server.ttt_check_winner(board), "draw")

    def test_check_winner_none_when_incomplete(self):
        self.assertIsNone(server.ttt_check_winner([None] * 9))

    def test_game_state_includes_winning_line(self):
        g = make_ttt_game(["X", "X", "X", "O", "O", None, None, None, None],
                          over=True, winner="X")
        self.assertEqual(server.ttt_state(g)["winning_line"], [0, 1, 2])

    def test_game_state_no_winning_line_for_draw(self):
        board = ["X", "O", "X", "O", "X", "O", "O", "X", "O"]
        g = make_ttt_game(board, over=True, winner="draw")
        self.assertIsNone(server.ttt_state(g)["winning_line"])

    def test_game_state_no_winning_line_while_in_progress(self):
        self.assertIsNone(server.ttt_state(make_ttt_game([None] * 9))["winning_line"])


class TestTTTAI(unittest.TestCase):
    """best_move correctness."""

    def test_best_move_returns_none_on_full_board(self):
        board = ["X", "O", "X", "O", "X", "O", "O", "X", "O"]
        self.assertIsNone(server.ttt_best_move(board))

    def test_best_move_takes_immediate_win(self):
        board = ["O", "X", None, "O", "X", None, None, None, None]
        self.assertEqual(server.ttt_best_move(board), 6)

    def test_best_move_blocks_x_win(self):
        board = ["X", "X", None, None, "O", None, None, None, None]
        self.assertEqual(server.ttt_best_move(board), 2)

    def test_ai_never_loses(self):
        """O never loses against a variety of X move-order strategies."""
        strategies = [
            [0, 1, 2, 3, 4, 5, 6, 7, 8],
            [4, 0, 2, 6, 8, 1, 3, 5, 7],
            [2, 0, 6, 8, 4, 1, 3, 5, 7],
            [1, 3, 5, 7, 0, 2, 4, 6, 8],
            [8, 7, 6, 5, 4, 3, 2, 1, 0],
        ]
        for strategy in strategies:
            board = [None] * 9
            winner = None
            while winner is None and any(c is None for c in board):
                for cell in strategy:
                    if board[cell] is None:
                        board[cell] = "X"
                        break
                winner = server.ttt_check_winner(board)
                if winner:
                    break
                ai = server.ttt_best_move(board)
                if ai is None:
                    break
                board[ai] = "O"
                winner = server.ttt_check_winner(board)
            self.assertNotEqual(winner, "X",
                                f"AI lost to strategy {strategy}: {board}")


class TestTTTScoring(IsolatedScores):
    """ttt_apply_score: points, idempotency, persistence."""

    @staticmethod
    def finished_ttt_session(name=None, winner="O"):
        sess = server.new_session()
        sess["name"] = name
        sess["ttt_game"]["over"] = True
        sess["ttt_game"]["winner"] = winner
        return sess

    def test_o_win_awards_hangman_point(self):
        sess = self.finished_ttt_session(winner="O")
        server.ttt_apply_score(sess)
        self.assertEqual(sess["guest_score"]["tictactoe"], {"player": 0, "hangman": 1})

    def test_x_win_awards_player_point(self):
        sess = self.finished_ttt_session(winner="X")
        server.ttt_apply_score(sess)
        self.assertEqual(sess["guest_score"]["tictactoe"], {"player": 1, "hangman": 0})

    def test_draw_awards_no_points(self):
        sess = self.finished_ttt_session(winner="draw")
        server.ttt_apply_score(sess)
        self.assertEqual(sess["guest_score"]["tictactoe"], {"player": 0, "hangman": 0})

    def test_score_applied_exactly_once(self):
        sess = self.finished_ttt_session(winner="O")
        server.ttt_apply_score(sess)
        server.ttt_apply_score(sess)
        self.assertEqual(sess["guest_score"]["tictactoe"]["hangman"], 1)

    def test_named_score_persists(self):
        sess = self.finished_ttt_session(name="Alice", winner="O")
        server.ttt_apply_score(sess)
        self.assertEqual(server.SCORES["Alice"]["tictactoe"]["hangman"], 1)


class TestTTTApi(IsolatedScores):
    """End-to-end TTT over HTTP with cookie-backed sessions."""

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

    def play_to_end(self, c):
        state = c.call("/ttt/state")
        while not state["over"]:
            cell = next(i for i, v in enumerate(state["board"]) if v is None)
            state = c.call("/ttt/move", {"cell": cell})
        return state

    def test_state_returns_expected_fields(self):
        st = self.client().call("/ttt/state")
        for key in ("board", "over", "winner", "winning_line", "score", "name", "names"):
            self.assertIn(key, st)
        self.assertEqual(st["board"], [None] * 9)
        self.assertFalse(st["over"])

    def test_valid_move_updates_board_and_o_responds(self):
        c = self.client()
        st = c.call("/ttt/move", {"cell": 0})
        self.assertEqual(st["board"][0], "X")
        self.assertEqual(sum(1 for v in st["board"] if v is not None), 2)

    def test_move_into_occupied_cell_is_ignored(self):
        c = self.client()
        c.call("/ttt/move", {"cell": 4})
        st = c.call("/ttt/move", {"cell": 4})
        self.assertEqual(sum(1 for v in st["board"] if v is not None), 2)

    def test_move_after_game_over_is_ignored(self):
        c = self.client()
        final = self.play_to_end(c)
        self.assertTrue(final["over"])
        after = c.call("/ttt/move", {"cell": next(
            (i for i, v in enumerate(final["board"]) if v is None), 0
        )})
        self.assertEqual(after["board"], final["board"])

    def test_new_resets_board(self):
        c = self.client()
        c.call("/ttt/move", {"cell": 0})
        st = c.call("/ttt/new", {})
        self.assertEqual(st["board"], [None] * 9)
        self.assertFalse(st["over"])

    def test_sessions_are_independent(self):
        a, b = self.client(), self.client()
        a.call("/ttt/move", {"cell": 0})
        self.assertEqual(b.call("/ttt/state")["board"], [None] * 9)

    def test_draw_awards_no_points(self):
        c = self.client()
        final = self.play_to_end(c)
        self.assertNotEqual(final["winner"], "X")
        if final["winner"] == "draw":
            self.assertEqual(final["score"], {"player": 0, "hangman": 0})


if __name__ == "__main__":
    unittest.main(verbosity=2)
