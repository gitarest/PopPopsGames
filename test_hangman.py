"""Tests for Hangman — standard library only (unittest), no deps.

Run:
    python -m unittest test_hangman
    python test_hangman.py            # same thing, with verbose output

Three groups:
  * TestGameLogic  — pure helpers (masking, flags, level points). No server.
  * TestScoring    — Player-vs-Hangman scoring + persistence. No network.
  * TestHangmanApi — end-to-end HTTP with cookie-backed sessions.

Every test that could persist a score redirects server.SCORES_FILE to a
temp file so the real scores.json is never touched.
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


def make_game(word, guessed=(), wrong=0, level="medium"):
    """A game dict shaped like server.new_game(), with a chosen word."""
    return {
        "word": word.upper(),
        "guessed": [c.upper() for c in guessed],
        "wrong": wrong,
        "level": level,
        "scored": False,
    }


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

    def sid(self):
        return next((c.value for c in self.jar if c.name == "sid"), None)


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

    @staticmethod
    def finished_session(name=None, level="medium", won=True):
        sess = server.new_session()
        sess["name"] = name
        game = make_game("PROGRAMMER", level=level)
        if won:
            game["guessed"] = list(set("PROGRAMMER"))
        else:
            game["guessed"] = ["B"]
            game["wrong"] = server.MAX_WRONG
        sess["game"] = game
        return sess


class TestGameLogic(unittest.TestCase):
    """Pure functions: no server, no network."""

    def test_level_points_scale_with_difficulty(self):
        self.assertEqual(
            [server.level_points(l) for l in ["easy", "medium", "hard", "expert"]],
            [1, 2, 3, 4],
        )

    def test_new_game_unknown_level_falls_back_to_default(self):
        self.assertEqual(server.new_game("bogus")["level"], server.DEFAULT_LEVEL)

    def test_new_game_picks_word_from_requested_level(self):
        g = server.new_game("medium")
        self.assertEqual(g["level"], "medium")
        self.assertIn(g["word"], [w.upper() for w in server.WORDS_BY_LEVEL["medium"]])

    def test_masking_hides_unguessed_and_word_until_over(self):
        st = server.game_state(make_game("CAT", guessed=["C"]))
        self.assertEqual(st["masked"], ["C", "_", "_"])
        self.assertFalse(st["over"])
        self.assertIsNone(st["word"])

    def test_win_reveals_word_and_sets_flags(self):
        st = server.game_state(make_game("CAT", guessed=["C", "A", "T"]))
        self.assertTrue(st["won"])
        self.assertTrue(st["over"])
        self.assertFalse(st["lost"])
        self.assertEqual(st["word"], "CAT")

    def test_loss_at_max_wrong(self):
        st = server.game_state(make_game("CAT", guessed=["X"], wrong=server.MAX_WRONG))
        self.assertTrue(st["lost"])
        self.assertTrue(st["over"])
        self.assertFalse(st["won"])


class TestScoring(IsolatedScores):
    def test_guest_win_awards_player_points_by_level(self):
        sess = self.finished_session(level="medium", won=True)
        server.apply_score(sess)
        self.assertEqual(sess["guest_score"]["hangman"], {"player": 2, "hangman": 0})

    def test_loss_awards_hangman_one_point(self):
        sess = self.finished_session(won=False)
        server.apply_score(sess)
        self.assertEqual(sess["guest_score"]["hangman"], {"player": 0, "hangman": 1})

    def test_score_is_applied_exactly_once(self):
        sess = self.finished_session(level="easy", won=True)
        server.apply_score(sess)
        server.apply_score(sess)
        self.assertEqual(sess["guest_score"]["hangman"]["player"], 1)

    def test_named_score_persists_and_reloads_from_disk(self):
        sess = self.finished_session(name="Alice", level="hard", won=True)
        server.apply_score(sess)
        self.assertEqual(server.SCORES["Alice"]["hangman"]["player"], 3)
        self.assertEqual(server.load_scores()["Alice"]["hangman"]["player"], 3)

    def test_guest_score_is_never_written_to_disk(self):
        server.apply_score(self.finished_session(name=None, won=True))
        self.assertEqual(server.load_scores(), {})

    def test_build_payload_lists_known_names_sorted(self):
        for n in ["Cara", "Alice", "Bob"]:
            server.apply_score(self.finished_session(name=n, won=True))
        payload = server.build_payload(server.new_session())
        self.assertEqual(payload["names"], ["Alice", "Bob", "Cara"])

    def test_normalize_name_title_cases_and_trims(self):
        self.assertEqual(server.normalize_name("  hUNTer "), "Hunter")
        self.assertEqual(server.normalize_name("mary jane"), "Mary Jane")
        self.assertEqual(server.normalize_name(""), "")

    def test_load_scores_merges_case_only_duplicates(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(
                {"Hunter": {"player": 1, "hangman": 2},
                 "hunter": {"player": 3, "hangman": 4}}, f,
            )
        loaded = server.load_scores()
        self.assertEqual(list(loaded), ["Hunter"])
        self.assertEqual(loaded["Hunter"]["hangman"], {"player": 4, "hangman": 6})


class TestHangmanApi(IsolatedScores):
    """End-to-end over HTTP, with cookie-backed sessions like a real browser."""

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

    def current_word(self, c):
        return server.SESSIONS[c.sid()]["game"]["word"]

    def win(self, c, level="medium", name=None):
        if name is not None:
            c.call("/name", {"name": name})
        c.call("/new", {"level": level})
        last = None
        for letter in sorted(set(self.current_word(c))):
            last = c.call("/guess", {"letter": letter})
        return last

    def test_state_defaults_to_configured_level(self):
        st = self.client().call("/state")
        self.assertEqual(st["level"], server.DEFAULT_LEVEL)
        self.assertEqual(st["score"], {"player": 0, "hangman": 0})

    def test_new_without_level_keeps_current_level(self):
        c = self.client()
        c.call("/new", {"level": "hard"})
        self.assertEqual(c.call("/new", {})["level"], "hard")

    def test_new_with_invalid_level_falls_back(self):
        self.assertEqual(
            self.client().call("/new", {"level": "impossible"})["level"],
            server.DEFAULT_LEVEL,
        )

    def test_guess_validation_and_dedup(self):
        c = self.client()
        c.call("/new", {"level": "medium"})
        word = set(self.current_word(c))
        wrong = next(ch for ch in "QWERTYUIOPASDFGHJKLZXCVBNM" if ch not in word)
        self.assertEqual(c.call("/guess", {"letter": wrong.lower()})["wrong"], 1)
        self.assertEqual(c.call("/guess", {"letter": wrong.lower()})["wrong"], 1)
        self.assertEqual(c.call("/guess", {"letter": "1"})["wrong"], 1)

    def test_guesses_after_game_over_are_ignored(self):
        c = self.client()
        self.win(c)
        before = c.call("/state")
        after = c.call("/guess", {"letter": "Z"})
        self.assertTrue(before["over"])
        self.assertEqual(after["wrong"], before["wrong"])
        self.assertEqual(after["score"], before["score"])

    def test_sessions_are_independent_across_cookies(self):
        a, b = self.client(), self.client()
        a.call("/new", {"level": "hard"})
        self.assertEqual(b.call("/state")["level"], server.DEFAULT_LEVEL)

    def test_named_vs_guest_scores_are_separate(self):
        c = self.client()
        st = self.win(c, level="medium", name="Alice")
        self.assertEqual(st["name"], "Alice")
        self.assertEqual(st["score"]["player"], 2)
        guest = c.call("/name", {"name": ""})
        self.assertIsNone(guest["name"])
        self.assertEqual(guest["score"], {"player": 0, "hangman": 0})

    def test_named_score_visible_to_a_fresh_client(self):
        self.win(self.client(), name="Bob")
        self.assertIn("Bob", self.client().call("/state")["names"])

    def test_name_is_title_cased_on_set(self):
        self.assertEqual(self.client().call("/name", {"name": "hUNTER"})["name"], "Hunter")

    def test_same_name_different_casing_is_one_player(self):
        self.win(self.client(), name="hunter")
        self.win(self.client(), name="HUNTER")
        names = self.client().call("/state")["names"]
        self.assertEqual(names.count("Hunter"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
