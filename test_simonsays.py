"""Tests for Simon Says — standard library only, no deps.

Three groups:
  * TestSSGameLogic  — pure simonsays.py helpers. No server.
  * TestSSScoring    — scoring functions + persistence. No network.
  * TestSSApi        — end-to-end HTTP with cookie-backed sessions.
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
import simonsays


class ApiClient:
    """Simulated browser: its own cookie jar = its own server session."""

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

    def sid(self):
        return next((c.value for c in self.jar if c.name == "sid"), None)


class IsolatedScores(unittest.TestCase):
    """Base: redirect SCORES to a temp file, start from an empty map."""

    def setUp(self):
        fd, self._path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self._orig_file   = server.SCORES_FILE
        self._orig_scores = server.SCORES
        server.SCORES_FILE = self._path
        server.SCORES = {}

    def tearDown(self):
        server.SCORES_FILE = self._orig_file
        server.SCORES      = self._orig_scores
        os.unlink(self._path)


# ---------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------

class TestSSGameLogic(unittest.TestCase):

    def test_new_game_defaults(self):
        g = simonsays.new_game()
        self.assertEqual(len(g["sequence"]), 1)
        self.assertIn(g["sequence"][0], simonsays.COLORS)
        self.assertEqual(g["player_index"], 0)
        self.assertEqual(g["phase"], "watch")
        self.assertFalse(g["over"])
        self.assertFalse(g["scored"])
        self.assertEqual(g["level"], "easy")

    def test_new_game_with_level(self):
        self.assertEqual(simonsays.new_game("hard")["level"], "hard")
        self.assertEqual(simonsays.new_game("medium")["level"], "medium")

    def test_new_game_invalid_level_falls_back_to_easy(self):
        self.assertEqual(simonsays.new_game("impossible")["level"], "easy")

    def test_ready_transitions_watch_to_play(self):
        g = simonsays.new_game()
        self.assertEqual(g["phase"], "watch")
        simonsays.ready(g)
        self.assertEqual(g["phase"], "play")

    def test_ready_ignored_when_over(self):
        g = simonsays.new_game()
        g["over"]  = True
        g["phase"] = "over"
        simonsays.ready(g)
        self.assertEqual(g["phase"], "over")

    def test_tap_correct_advances_player_index(self):
        g = simonsays.new_game()
        g["sequence"] = ["red", "blue"]
        g["phase"] = "play"
        simonsays.tap(g, "red")
        self.assertEqual(g["player_index"], 1)
        self.assertEqual(g["phase"], "play")
        self.assertFalse(g["over"])

    def test_tap_completes_round_extends_sequence_and_returns_to_watch(self):
        g = simonsays.new_game()
        g["sequence"] = ["green"]
        g["phase"] = "play"
        simonsays.tap(g, "green")
        self.assertEqual(len(g["sequence"]), 2)
        self.assertEqual(g["player_index"], 0)
        self.assertEqual(g["phase"], "watch")

    def test_tap_wrong_color_ends_game(self):
        g = simonsays.new_game()
        g["sequence"] = ["red"]
        g["phase"] = "play"
        simonsays.tap(g, "blue")
        self.assertTrue(g["over"])
        self.assertEqual(g["phase"], "over")

    def test_tap_ignored_in_watch_phase(self):
        g = simonsays.new_game()
        g["sequence"] = ["red"]
        g["phase"] = "watch"
        simonsays.tap(g, "red")
        self.assertEqual(g["player_index"], 0)
        self.assertFalse(g["over"])

    def test_tap_ignored_after_game_over(self):
        g = simonsays.new_game()
        g["sequence"] = ["red"]
        g["phase"] = "over"
        g["over"]  = True
        simonsays.tap(g, "red")
        self.assertEqual(g["player_index"], 0)

    def test_game_state_fields_and_rounds(self):
        g = simonsays.new_game()
        g["sequence"] = ["red", "blue", "green"]
        st = simonsays.game_state(g)
        self.assertEqual(st["rounds"], 2)
        self.assertIn("level", st)
        self.assertIn("levels", st)
        self.assertEqual(st["levels"], list(simonsays.LEVELS))

    def test_rounds_is_zero_on_first_game(self):
        g = simonsays.new_game()
        self.assertEqual(simonsays.game_state(g)["rounds"], 0)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class TestSSScoring(IsolatedScores):

    def _finished_ss(self, name=None, rounds=3, level="easy"):
        sess = server.new_session()
        sess["name"] = name
        g = simonsays.new_game(level)
        # Simulate completing `rounds` rounds: sequence has rounds+1 colors, player_index=0
        g["sequence"] = [simonsays.COLORS[i % 4] for i in range(rounds + 1)]
        g["player_index"] = 0
        g["phase"] = "over"
        g["over"]  = True
        sess["ss_game"] = g
        return sess

    def test_player_gets_rounds_completed(self):
        sess = self._finished_ss(rounds=5)
        server.ss_apply_score(sess)
        self.assertEqual(sess["guest_score"]["simonsays"]["player"], 5)

    def test_computer_always_gets_one(self):
        sess = self._finished_ss(rounds=0)
        server.ss_apply_score(sess)
        score = sess["guest_score"]["simonsays"]
        self.assertEqual(score["hangman"], 1)
        self.assertEqual(score["player"], 0)

    def test_apply_score_fires_exactly_once(self):
        sess = self._finished_ss(rounds=4)
        server.ss_apply_score(sess)
        server.ss_apply_score(sess)
        self.assertEqual(sess["guest_score"]["simonsays"]["player"], 4)

    def test_best_initializes_and_updates(self):
        sess = self._finished_ss(rounds=3)
        server.ss_apply_score(sess)
        score = sess["guest_score"]["simonsays"]
        self.assertEqual(score["best"], 3)

    def test_best_does_not_decrease(self):
        sess1 = self._finished_ss(name="Kai", rounds=7, level="medium")
        server.ss_apply_score(sess1)
        sess2 = self._finished_ss(name="Kai", rounds=2, level="medium")
        server.ss_apply_score(sess2)
        self.assertEqual(server.SCORES["Kai"]["simonsays"]["best"], 7)

    def test_best_increases_on_new_record(self):
        sess1 = self._finished_ss(name="Kai", rounds=3, level="easy")
        server.ss_apply_score(sess1)
        sess2 = self._finished_ss(name="Kai", rounds=10, level="easy")
        server.ss_apply_score(sess2)
        self.assertEqual(server.SCORES["Kai"]["simonsays"]["best"], 10)

    def test_level_saved_in_named_score(self):
        sess = self._finished_ss(name="Kai", rounds=2, level="hard")
        server.ss_apply_score(sess)
        self.assertEqual(server.SCORES["Kai"]["simonsays"]["level"], "hard")

    def test_guest_score_not_written_to_disk(self):
        server.ss_apply_score(self._finished_ss(name=None, rounds=3))
        self.assertEqual(server.load_scores(), {})

    def test_named_score_persists_to_disk(self):
        sess = self._finished_ss(name="Nia", rounds=5, level="medium")
        server.ss_apply_score(sess)
        loaded = server.load_scores()
        self.assertEqual(loaded["Nia"]["simonsays"]["player"], 5)

    def test_not_yet_over_does_not_score(self):
        sess = server.new_session()
        g = simonsays.new_game()
        g["phase"] = "play"
        sess["ss_game"] = g
        server.ss_apply_score(sess)
        self.assertEqual(sess["guest_score"], {})


# ---------------------------------------------------------------------------
# End-to-end API
# ---------------------------------------------------------------------------

class TestSSApi(IsolatedScores):

    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.HangmanHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls._orig_log = server.HangmanHandler.log_message
        server.HangmanHandler.log_message = lambda *a, **k: None

    @classmethod
    def tearDownClass(cls):
        server.HangmanHandler.log_message = cls._orig_log
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def client(self):
        return ApiClient(self.port)

    def _play_through(self, c, rounds=1):
        """Force a game to a specific round count then lose."""
        for _ in range(rounds):
            st = c.call("/simonsays/state")
            seq = st["sequence"]
            # Signal ready (watch → play)
            st = c.call("/simonsays/ready", {})
            # Tap the whole sequence correctly
            for color in seq:
                st = c.call("/simonsays/tap", {"color": color})
                if st["phase"] == "watch":
                    break
        # Now lose: tap wrong color
        c.call("/simonsays/ready", {})
        wrong_color = next(co for co in simonsays.COLORS
                          if co != server.SESSIONS[c.sid()]["ss_game"]["sequence"][0])
        return c.call("/simonsays/tap", {"color": wrong_color})

    def test_state_returns_expected_fields(self):
        st = self.client().call("/simonsays/state")
        for field in ("sequence", "player_index", "phase", "over", "rounds",
                      "level", "levels", "score", "total_score", "names"):
            self.assertIn(field, st)

    def test_state_score_has_best_and_level(self):
        st = self.client().call("/simonsays/state")
        self.assertIn("best", st["score"])
        self.assertIn("level", st["score"])

    def test_new_game_resets(self):
        c = self.client()
        st = c.call("/simonsays/new", {})
        self.assertEqual(st["phase"], "watch")
        self.assertEqual(len(st["sequence"]), 1)
        self.assertFalse(st["over"])

    def test_new_game_with_level(self):
        c = self.client()
        st = c.call("/simonsays/new", {"level": "hard"})
        self.assertEqual(st["level"], "hard")

    def test_ready_transitions_to_play(self):
        c = self.client()
        c.call("/simonsays/new", {})
        st = c.call("/simonsays/ready", {})
        self.assertEqual(st["phase"], "play")

    def test_tap_in_watch_phase_is_noop(self):
        c = self.client()
        c.call("/simonsays/new", {})
        st_before = c.call("/simonsays/state")
        self.assertEqual(st_before["phase"], "watch")
        st_after = c.call("/simonsays/tap", {"color": "red"})
        self.assertEqual(st_after["phase"], "watch")
        self.assertFalse(st_after["over"])

    def test_correct_tap_advances_index(self):
        c = self.client()
        c.call("/simonsays/new", {})
        color = server.SESSIONS[c.sid()]["ss_game"]["sequence"][0]
        c.call("/simonsays/ready", {})
        st = c.call("/simonsays/tap", {"color": color})
        # Single-color sequence → completes round, returns to watch
        self.assertEqual(st["phase"], "watch")

    def test_wrong_tap_ends_game(self):
        c = self.client()
        c.call("/simonsays/new", {})
        seq = server.SESSIONS[c.sid()]["ss_game"]["sequence"]
        wrong = next(co for co in simonsays.COLORS if co != seq[0])
        c.call("/simonsays/ready", {})
        st = c.call("/simonsays/tap", {"color": wrong})
        self.assertTrue(st["over"])
        self.assertEqual(st["phase"], "over")

    def test_score_increments_after_game_over(self):
        c = self.client()
        c.call("/simonsays/new", {})
        seq = server.SESSIONS[c.sid()]["ss_game"]["sequence"]
        wrong = next(co for co in simonsays.COLORS if co != seq[0])
        c.call("/simonsays/ready", {})
        st = c.call("/simonsays/tap", {"color": wrong})
        self.assertEqual(st["score"]["hangman"], 1)

    def test_named_player_level_restored_on_new_game(self):
        c = self.client()
        c.call("/name", {"name": "Tester"})
        c.call("/simonsays/new", {"level": "hard"})
        # Force a game over so level is saved
        seq = server.SESSIONS[c.sid()]["ss_game"]["sequence"]
        wrong = next(co for co in simonsays.COLORS if co != seq[0])
        c.call("/simonsays/ready", {})
        c.call("/simonsays/tap", {"color": wrong})
        # New game without specifying level → should restore "hard"
        st = c.call("/simonsays/new", {})
        self.assertEqual(st["level"], "hard")

    def test_guest_gets_default_level_not_named_players_saved_level(self):
        # Named player saves "hard"
        named = self.client()
        named.call("/name", {"name": "TesterX"})
        named.call("/simonsays/new", {"level": "hard"})
        seq = server.SESSIONS[named.sid()]["ss_game"]["sequence"]
        wrong = next(co for co in simonsays.COLORS if co != seq[0])
        named.call("/simonsays/ready", {})
        named.call("/simonsays/tap", {"color": wrong})
        # Fresh guest client → should default to easy, not hard
        guest = self.client()
        st = guest.call("/simonsays/new", {})
        self.assertEqual(st["level"], "easy")

    def test_two_clients_are_independent(self):
        a, b = self.client(), self.client()
        a.call("/simonsays/new", {"level": "hard"})
        b_st = b.call("/simonsays/state")
        self.assertEqual(b_st["level"], "easy")


if __name__ == "__main__":
    unittest.main(verbosity=2)
