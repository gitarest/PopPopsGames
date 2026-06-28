"""Tests for Rock Paper Scissors — standard library only (unittest), no deps.

Run:
    python -m unittest test_rps
    python test_rps.py

Three groups:
  * TestRPSGameLogic — pure functions: play, game_state, new_game.
  * TestRPSScoring   — rps_apply_score: points, idempotency, persistence.
  * TestRPSApi       — end-to-end HTTP with cookie-backed sessions.
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


class TestRPSGameLogic(unittest.TestCase):
    """Pure functions: rps.play, rps.game_state, rps.new_game."""

    def test_new_game_is_fresh(self):
        g = server.rps_new_game()
        self.assertIsNone(g["player_choice"])
        self.assertIsNone(g["computer_choice"])
        self.assertIsNone(g["result"])
        self.assertFalse(g["over"])
        self.assertFalse(g["scored"])

    def test_play_win(self):
        g = server.rps_new_game()
        server.rps_play(g, "rock", _computer_choice="scissors")
        self.assertEqual(g["result"], "win")
        self.assertTrue(g["over"])

    def test_play_loss(self):
        g = server.rps_new_game()
        server.rps_play(g, "rock", _computer_choice="paper")
        self.assertEqual(g["result"], "loss")

    def test_play_tie(self):
        g = server.rps_new_game()
        server.rps_play(g, "paper", _computer_choice="paper")
        self.assertEqual(g["result"], "tie")

    def test_all_win_combinations(self):
        beats = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
        for player, computer in beats.items():
            g = server.rps_new_game()
            server.rps_play(g, player, _computer_choice=computer)
            self.assertEqual(g["result"], "win", f"{player} should beat {computer}")

    def test_invalid_choice_is_ignored(self):
        g = server.rps_new_game()
        server.rps_play(g, "fire", _computer_choice="rock")
        self.assertFalse(g["over"])
        self.assertIsNone(g["result"])

    def test_play_after_game_over_is_ignored(self):
        g = server.rps_new_game()
        server.rps_play(g, "rock", _computer_choice="scissors")
        server.rps_play(g, "paper", _computer_choice="rock")
        self.assertEqual(g["player_choice"], "rock")

    def test_game_state_fields(self):
        g = server.rps_new_game()
        server.rps_play(g, "scissors", _computer_choice="paper")
        st = server.rps_game_state(g)
        self.assertEqual(st["player_choice"], "scissors")
        self.assertEqual(st["computer_choice"], "paper")
        self.assertEqual(st["result"], "win")
        self.assertTrue(st["over"])


class TestRPSScoring(IsolatedScores):
    """rps_apply_score: points, idempotency, persistence."""

    @staticmethod
    def finished_rps_session(name=None, result="win"):
        sess = server.new_session()
        sess["name"] = name
        sess["rps_game"]["result"] = result
        sess["rps_game"]["over"] = True
        return sess

    def test_win_awards_player_point(self):
        sess = self.finished_rps_session(result="win")
        server.rps_apply_score(sess)
        self.assertEqual(sess["guest_score"]["rps"], {"player": 1, "hangman": 0})

    def test_loss_awards_computer_point(self):
        sess = self.finished_rps_session(result="loss")
        server.rps_apply_score(sess)
        self.assertEqual(sess["guest_score"]["rps"], {"player": 0, "hangman": 1})

    def test_tie_awards_no_points(self):
        sess = self.finished_rps_session(result="tie")
        server.rps_apply_score(sess)
        self.assertEqual(sess["guest_score"]["rps"], {"player": 0, "hangman": 0})

    def test_score_applied_exactly_once(self):
        sess = self.finished_rps_session(result="win")
        server.rps_apply_score(sess)
        server.rps_apply_score(sess)
        self.assertEqual(sess["guest_score"]["rps"]["player"], 1)

    def test_named_score_persists(self):
        sess = self.finished_rps_session(name="Alice", result="win")
        server.rps_apply_score(sess)
        self.assertEqual(server.SCORES["Alice"]["rps"]["player"], 1)


class TestRPSApi(IsolatedScores):
    """End-to-end RPS over HTTP with cookie-backed sessions."""

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
        st = self.client().call("/rps/state")
        for key in ("player_choice", "computer_choice", "result", "over",
                    "score", "name", "names"):
            self.assertIn(key, st)
        self.assertFalse(st["over"])

    def test_play_valid_choice_ends_game(self):
        c = self.client()
        st = c.call("/rps/play", {"choice": "rock"})
        self.assertTrue(st["over"])
        self.assertEqual(st["player_choice"], "rock")
        self.assertIn(st["computer_choice"], ("rock", "paper", "scissors"))
        self.assertIn(st["result"], ("win", "loss", "tie"))

    def test_play_invalid_choice_is_ignored(self):
        c = self.client()
        st = c.call("/rps/play", {"choice": "fire"})
        self.assertFalse(st["over"])

    def test_play_after_game_over_is_ignored(self):
        c = self.client()
        c.call("/rps/play", {"choice": "rock"})
        first = c.call("/rps/state")
        second = c.call("/rps/play", {"choice": "paper"})
        self.assertEqual(second["player_choice"], first["player_choice"])

    def test_new_resets_game(self):
        c = self.client()
        c.call("/rps/play", {"choice": "rock"})
        st = c.call("/rps/new", {})
        self.assertFalse(st["over"])
        self.assertIsNone(st["player_choice"])

    def test_sessions_are_independent(self):
        a, b = self.client(), self.client()
        a.call("/rps/play", {"choice": "rock"})
        self.assertFalse(b.call("/rps/state")["over"])

    def test_score_matches_result(self):
        c = self.client()
        st = c.call("/rps/play", {"choice": "scissors"})
        self.assertTrue(st["over"])
        if st["result"] == "win":
            self.assertEqual(st["score"]["player"], 1)
            self.assertEqual(st["score"]["hangman"], 0)
        elif st["result"] == "loss":
            self.assertEqual(st["score"]["player"], 0)
            self.assertEqual(st["score"]["hangman"], 1)
        else:
            self.assertEqual(st["score"]["player"], 0)
            self.assertEqual(st["score"]["hangman"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
