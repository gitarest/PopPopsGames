"""Tests for Wordle — standard library only, no deps.

Three groups:
  * TestWLGameLogic  — pure wordle.py helpers. No server.
  * TestWLScoring    — scoring functions + persistence. No network.
  * TestWLApi        — end-to-end HTTP with cookie-backed sessions.
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
import wordle


class ApiClient:
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
    def setUp(self):
        fd, self._db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._orig_db     = server.DB_FILE
        self._orig_scores = server.SCORES
        server.DB_FILE = self._db_path
        server.init_db()
        server.SCORES = {}

    def tearDown(self):
        server.DB_FILE = self._orig_db
        server.SCORES  = self._orig_scores
        os.unlink(self._db_path)


# ---------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------

class TestWLGameLogic(unittest.TestCase):

    def test_new_game_defaults(self):
        g = wordle.new_game()
        self.assertEqual(g["phase"], "play")
        self.assertEqual(g["guesses"], [])
        self.assertFalse(g["over"])
        self.assertFalse(g["scored"])
        self.assertIn(g["word"], wordle.WORDS)

    def test_correct_guess_wins(self):
        g = wordle.new_game()
        wordle.guess(g, g["word"])
        self.assertEqual(g["phase"], "won")
        self.assertTrue(g["over"])
        self.assertEqual(len(g["guesses"]), 1)

    def test_wrong_guess_continues(self):
        g = wordle.new_game()
        g["word"] = "CRANE"
        wordle.guess(g, "BLAST")
        self.assertEqual(g["phase"], "play")
        self.assertFalse(g["over"])

    def test_six_wrong_guesses_loses(self):
        g = wordle.new_game()
        g["word"] = "CRANE"
        for _ in range(6):
            wordle.guess(g, "BLAST")
        self.assertEqual(g["phase"], "lost")
        self.assertTrue(g["over"])
        self.assertEqual(len(g["guesses"]), 6)

    def test_guess_ignored_after_game_over(self):
        g = wordle.new_game()
        wordle.guess(g, g["word"])
        wordle.guess(g, g["word"])
        self.assertEqual(len(g["guesses"]), 1)

    def test_score_all_correct(self):
        result = wordle._score_guess("CRANE", "CRANE")
        self.assertEqual(result, ["correct"] * 5)

    def test_score_all_absent(self):
        result = wordle._score_guess("BBBBB", "CRANE")
        self.assertEqual(result, ["absent"] * 5)

    def test_score_present(self):
        result = wordle._score_guess("RXXXX", "CRANE")
        self.assertEqual(result[0], "present")

    def test_score_duplicate_letter_handling(self):
        # KEEPS vs ABBEY: only one E in ABBEY, so first E is present, second absent
        result = wordle._score_guess("KEEPS", "ABBEY")
        e_results = [result[i] for i, c in enumerate("KEEPS") if c == "E"]
        self.assertIn("present", e_results)
        self.assertIn("absent", e_results)

    def test_game_state_hides_word_in_play(self):
        g = wordle.new_game()
        st = wordle.game_state(g)
        self.assertIsNone(st["word"])

    def test_game_state_reveals_word_on_loss(self):
        g = wordle.new_game()
        g["word"] = "CRANE"
        for _ in range(6):
            wordle.guess(g, "BLAST")
        st = wordle.game_state(g)
        self.assertEqual(st["word"], "CRANE")

    def test_game_state_letter_states_correct_beats_present(self):
        g = wordle.new_game()
        g["word"] = "CRANE"
        # Inject a guess where C is present (wrong position) directly — avoids needing
        # a valid dict word for the intermediate state; only game_state() logic is under test.
        g["guesses"].append({"word": "SCONE", "result": wordle._score_guess("SCONE", "CRANE")})
        # Second guess: C is correct (right position)
        wordle.guess(g, "CRANE")
        st = wordle.game_state(g)
        self.assertEqual(st["letter_states"].get("C"), "correct")

    def test_word_not_in_list_rejected(self):
        g = wordle.new_game()
        result = wordle.guess(g, "CHEND")
        self.assertFalse(result)
        self.assertTrue(g["invalid_guess"])
        self.assertEqual(len(g["guesses"]), 0)

    def test_valid_word_clears_invalid_flag(self):
        g = wordle.new_game()
        g["word"] = "CRANE"
        wordle.guess(g, "CHEND")
        self.assertTrue(g["invalid_guess"])
        wordle.guess(g, "BLAST")
        self.assertFalse(g["invalid_guess"])
        self.assertEqual(len(g["guesses"]), 1)

    def test_invalid_guess_too_short(self):
        g = wordle.new_game()
        wordle.guess(g, "AB")
        self.assertEqual(len(g["guesses"]), 0)

    def test_invalid_guess_non_alpha(self):
        g = wordle.new_game()
        wordle.guess(g, "AB123")
        self.assertEqual(len(g["guesses"]), 0)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class TestWLScoring(IsolatedScores):

    def _make_won(self, name=None, attempts=1):
        sess = server.new_session()
        sess["name"] = name
        g = wordle.new_game()
        g["word"] = "CRANE"
        g["phase"] = "won"
        g["over"]  = True
        # Simulate `attempts` guesses
        g["guesses"] = [{"word": "CRANE", "result": ["correct"]*5}]
        if attempts > 1:
            extra = [{"word": "BLAST", "result": ["absent"]*5}] * (attempts - 1)
            g["guesses"] = extra + g["guesses"]
        sess["wl_game"] = g
        return sess

    def _make_lost(self, name=None):
        sess = server.new_session()
        sess["name"] = name
        g = wordle.new_game()
        g["word"]   = "CRANE"
        g["phase"]  = "lost"
        g["over"]   = True
        g["guesses"] = [{"word": "BLAST", "result": ["absent"]*5}] * 6
        sess["wl_game"] = g
        return sess

    def test_win_one_guess_gives_six_points(self):
        sess = self._make_won(attempts=1)
        server.wl_apply_score(sess)
        self.assertEqual(sess["guest_score"]["wordle"]["player"], 6)

    def test_win_six_guesses_gives_one_point(self):
        sess = self._make_won(attempts=6)
        server.wl_apply_score(sess)
        self.assertEqual(sess["guest_score"]["wordle"]["player"], 1)

    def test_loss_gives_computer_one_point(self):
        sess = self._make_lost()
        server.wl_apply_score(sess)
        self.assertEqual(sess["guest_score"]["wordle"]["hangman"], 1)
        self.assertEqual(sess["guest_score"]["wordle"]["player"], 0)

    def test_apply_score_fires_once(self):
        sess = self._make_won(attempts=1)
        server.wl_apply_score(sess)
        server.wl_apply_score(sess)
        self.assertEqual(sess["guest_score"]["wordle"]["player"], 6)

    def test_not_over_does_not_score(self):
        sess = server.new_session()
        server.wl_apply_score(sess)
        self.assertEqual(sess["guest_score"], {})

    def test_named_player_score_persists(self):
        sess = self._make_won(name="Ada", attempts=3)
        server.wl_apply_score(sess)
        loaded = server.load_scores()
        self.assertEqual(loaded["Ada"]["wordle"]["player"], 4)  # 7-3=4


# ---------------------------------------------------------------------------
# End-to-end API
# ---------------------------------------------------------------------------

class TestWLApi(IsolatedScores):

    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.HangmanHandler)
        cls.port  = cls.httpd.server_address[1]
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

    def test_state_returns_expected_fields(self):
        st = self.client().call("/wordle/state")
        for f in ("guesses", "phase", "over", "word", "attempts",
                  "max_guesses", "letter_states", "invalid_guess",
                  "score", "total_score", "names"):
            self.assertIn(f, st)

    def test_new_game_resets(self):
        c = self.client()
        st = c.call("/wordle/new", {})
        self.assertEqual(st["phase"], "play")
        self.assertEqual(st["guesses"], [])
        self.assertEqual(st["attempts"], 0)

    def test_correct_guess_wins(self):
        c = self.client()
        c.call("/wordle/new", {})
        word = server.SESSIONS[c.sid()]["wl_game"]["word"]
        st = c.call("/wordle/guess", {"word": word})
        self.assertEqual(st["phase"], "won")

    def test_six_wrong_guesses_loses(self):
        c = self.client()
        c.call("/wordle/new", {})
        g = server.SESSIONS[c.sid()]["wl_game"]
        correct = g["word"]
        wrong = next(w for w in wordle.WORDS if w != correct)
        for _ in range(6):
            c.call("/wordle/guess", {"word": wrong})
        st = c.call("/wordle/state")
        self.assertEqual(st["phase"], "lost")

    def test_invalid_word_rejected_via_api(self):
        c = self.client()
        c.call("/wordle/new", {})
        st = c.call("/wordle/guess", {"word": "CHEND"})
        self.assertTrue(st["invalid_guess"])
        self.assertEqual(st["attempts"], 0)

    def test_score_increments_after_win(self):
        c = self.client()
        c.call("/wordle/new", {})
        word = server.SESSIONS[c.sid()]["wl_game"]["word"]
        st = c.call("/wordle/guess", {"word": word})
        self.assertGreater(st["score"]["player"], 0)

    def test_two_clients_independent(self):
        a, b = self.client(), self.client()
        a.call("/wordle/state")
        ga = server.SESSIONS[a.sid()]["wl_game"]
        ga["word"] = "CRANE"
        st_b = b.call("/wordle/state")
        self.assertNotEqual(st_b.get("word"), "CRANE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
