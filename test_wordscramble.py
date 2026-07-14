"""Tests for Word Scramble — standard library only, no deps.

Three groups:
  * TestWSGameLogic  — pure wordscramble.py helpers. No server.
  * TestWSScoring    — scoring functions + persistence. No network.
  * TestWSApi        — end-to-end HTTP with cookie-backed sessions.
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
import wordscramble


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


def make_game(word, level="medium"):
    """A game dict shaped like wordscramble.new_game(), with a chosen word (already scrambled)."""
    letters = list(word.upper())
    return {
        "word": word.upper(),
        "letters": letters,
        "tile_state": ["pool"] * len(letters),
        "answer_order": [],
        "wrong": 0,
        "wrong_flag": False,
        "won": False,
        "over": False,
        "level": level,
        "scored": False,
    }


# ---------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------

class TestWSGameLogic(unittest.TestCase):

    def test_new_game_defaults(self):
        g = wordscramble.new_game()
        self.assertEqual(len(g["letters"]), len(g["word"]))
        self.assertEqual(g["tile_state"], ["pool"] * len(g["word"]))
        self.assertEqual(g["answer_order"], [])
        self.assertEqual(g["wrong"], 0)
        self.assertFalse(g["wrong_flag"])
        self.assertFalse(g["won"])
        self.assertFalse(g["over"])
        self.assertFalse(g["scored"])

    def test_new_game_picks_word_from_requested_level(self):
        g = wordscramble.new_game("medium")
        self.assertEqual(g["level"], "medium")
        self.assertIn(g["word"], [w.upper() for w in server.WORDS_BY_LEVEL["medium"]])

    def test_new_game_invalid_level_falls_back(self):
        g = wordscramble.new_game("impossible")
        self.assertEqual(g["level"], server.DEFAULT_LEVEL)

    def test_letters_are_a_permutation_of_word(self):
        g = wordscramble.new_game()
        self.assertEqual(sorted(g["letters"]), sorted(g["word"]))

    def test_scramble_actually_shuffles_when_possible(self):
        # Run several times to confirm it's not returning the identity order.
        shuffled_at_least_once = False
        for _ in range(20):
            g = wordscramble.new_game()
            if len(set(g["word"])) > 1 and "".join(g["letters"]) != g["word"]:
                shuffled_at_least_once = True
                break
        self.assertTrue(shuffled_at_least_once)

    def test_scramble_never_equals_original_when_letters_differ(self):
        for _ in range(20):
            g = wordscramble.new_game()
            if len(set(g["word"])) > 1:
                self.assertNotEqual("".join(g["letters"]), g["word"])

    def test_place_moves_tile_to_answer(self):
        g = make_game("CAT")
        wordscramble.place(g, 0)
        self.assertEqual(g["tile_state"][0], "answer")
        self.assertEqual(g["answer_order"], [0])

    def test_place_ignored_on_non_pool_tile(self):
        g = make_game("CAT")
        wordscramble.place(g, 0)
        wordscramble.place(g, 0)
        self.assertEqual(g["answer_order"], [0])

    def test_place_out_of_range_ignored(self):
        g = make_game("CAT")
        wordscramble.place(g, 99)
        self.assertEqual(g["answer_order"], [])

    def test_remove_moves_tile_back_to_pool(self):
        g = make_game("CAT")
        wordscramble.place(g, 0)
        wordscramble.remove(g, 0)
        self.assertEqual(g["tile_state"][0], "pool")
        self.assertEqual(g["answer_order"], [])

    def test_remove_ignored_on_pool_tile(self):
        g = make_game("CAT")
        wordscramble.remove(g, 0)
        self.assertEqual(g["answer_order"], [])

    def test_correct_full_arrangement_wins(self):
        g = make_game("CAT")
        wordscramble.place(g, 0)  # C
        wordscramble.place(g, 1)  # A
        wordscramble.place(g, 2)  # T
        self.assertTrue(g["won"])
        self.assertTrue(g["over"])
        self.assertEqual(g["wrong"], 0)

    def test_wrong_full_arrangement_sets_wrong_flag(self):
        g = make_game("CAT")
        wordscramble.place(g, 1)  # A
        wordscramble.place(g, 0)  # C
        wordscramble.place(g, 2)  # T -> "ACT" != "CAT"
        self.assertTrue(g["wrong_flag"])
        self.assertEqual(g["wrong"], 1)
        self.assertFalse(g["over"])
        self.assertFalse(g["won"])

    def test_remove_ignored_while_wrong_flag_active(self):
        g = make_game("CAT")
        wordscramble.place(g, 1)
        wordscramble.place(g, 0)
        wordscramble.place(g, 2)  # triggers wrong_flag ("ACT" != "CAT")
        self.assertTrue(g["wrong_flag"])
        wordscramble.remove(g, 0)
        self.assertEqual(g["tile_state"][0], "answer")
        self.assertTrue(g["wrong_flag"])

    def test_clear_wrong_resets_tiles_to_pool(self):
        g = make_game("CAT")
        wordscramble.place(g, 1)
        wordscramble.place(g, 0)
        wordscramble.place(g, 2)  # triggers wrong_flag
        wordscramble.clear_wrong(g)
        self.assertFalse(g["wrong_flag"])
        self.assertEqual(g["tile_state"], ["pool", "pool", "pool"])
        self.assertEqual(g["answer_order"], [])

    def test_clear_wrong_noop_when_no_wrong_flag(self):
        g = make_game("CAT")
        wordscramble.place(g, 0)
        wordscramble.clear_wrong(g)
        self.assertEqual(g["tile_state"][0], "answer")

    def test_max_wrong_ends_game_as_loss(self):
        g = make_game("CAT")
        for _ in range(wordscramble.MAX_WRONG):
            wordscramble.place(g, 1)
            wordscramble.place(g, 0)
            wordscramble.place(g, 2)  # wrong arrangement "ACT"
            wordscramble.clear_wrong(g)
        self.assertTrue(g["over"])
        self.assertFalse(g["won"])
        self.assertEqual(g["wrong"], wordscramble.MAX_WRONG)

    def test_place_and_remove_ignored_after_game_over(self):
        g = make_game("CAT")
        wordscramble.place(g, 0)
        wordscramble.place(g, 1)
        wordscramble.place(g, 2)
        self.assertTrue(g["over"])
        wordscramble.remove(g, 0)
        self.assertEqual(g["tile_state"][0], "answer")

    def test_game_state_hides_word_until_over(self):
        g = make_game("CAT")
        st = wordscramble.game_state(g)
        self.assertIsNone(st["word"])
        self.assertFalse(st["over"])

    def test_game_state_reveals_word_on_win(self):
        g = make_game("CAT")
        wordscramble.place(g, 0)
        wordscramble.place(g, 1)
        wordscramble.place(g, 2)
        st = wordscramble.game_state(g)
        self.assertEqual(st["word"], "CAT")
        self.assertTrue(st["won"])
        self.assertFalse(st["lost"])

    def test_game_state_includes_expected_fields(self):
        st = wordscramble.game_state(make_game("CAT"))
        for field in ("letters", "tile_state", "answer_order", "wrong", "max_wrong",
                      "wrong_flag", "won", "lost", "over", "word", "level", "levels"):
            self.assertIn(field, st)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class TestWSScoring(IsolatedScores):

    def _finished_session(self, name=None, level="medium", won=True):
        sess = server.new_session()
        sess["name"] = name
        g = make_game("CAT", level=level)
        if won:
            g["won"] = True
            g["over"] = True
        else:
            g["wrong"] = wordscramble.MAX_WRONG
            g["over"] = True
        sess["ws_game"] = g
        return sess

    def test_win_awards_level_points(self):
        sess = self._finished_session(level="hard", won=True)
        server.ws_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["wordscramble"]["player"], server.level_points("hard"))
        self.assertEqual(server.SCORES["Guest"]["wordscramble"]["hangman"], 0)

    def test_loss_awards_computer_one_point(self):
        sess = self._finished_session(won=False)
        server.ws_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["wordscramble"]["hangman"], 1)
        self.assertEqual(server.SCORES["Guest"]["wordscramble"]["player"], 0)

    def test_apply_score_fires_once(self):
        sess = self._finished_session(level="easy", won=True)
        server.ws_apply_score(sess)
        server.ws_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["wordscramble"]["player"], server.level_points("easy"))

    def test_not_over_does_not_score(self):
        sess = server.new_session()
        server.ws_apply_score(sess)
        self.assertNotIn("wordscramble", server.SCORES.get("Guest", {}))

    def test_guest_score_written_to_db(self):
        sess = self._finished_session(level="medium", won=True)
        server.ws_apply_score(sess)
        loaded = server.load_scores()
        self.assertIn("Guest", loaded)
        self.assertEqual(loaded["Guest"]["wordscramble"]["player"], server.level_points("medium"))

    def test_named_score_persists(self):
        sess = self._finished_session(name="Nia", level="expert", won=True)
        server.ws_apply_score(sess)
        self.assertEqual(server.SCORES["Nia"]["wordscramble"]["player"], server.level_points("expert"))
        self.assertEqual(server.load_scores()["Nia"]["wordscramble"]["player"], server.level_points("expert"))


# ---------------------------------------------------------------------------
# End-to-end API
# ---------------------------------------------------------------------------

class TestWSApi(IsolatedScores):

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
        st = self.client().call("/wordscramble/state")
        for f in ("letters", "tile_state", "answer_order", "wrong", "max_wrong",
                  "wrong_flag", "won", "lost", "over", "word", "level", "levels",
                  "score", "total_score", "names"):
            self.assertIn(f, st)

    def test_new_game_resets(self):
        c = self.client()
        st = c.call("/wordscramble/new", {"level": "hard"})
        self.assertEqual(st["level"], "hard")
        self.assertEqual(st["answer_order"], [])
        self.assertFalse(st["over"])

    def test_new_without_level_keeps_current_level(self):
        c = self.client()
        c.call("/wordscramble/new", {"level": "hard"})
        self.assertEqual(c.call("/wordscramble/new", {})["level"], "hard")

    def test_place_and_remove_round_trip(self):
        c = self.client()
        c.call("/wordscramble/new", {})
        st = c.call("/wordscramble/place", {"index": 0})
        self.assertEqual(st["tile_state"][0], "answer")
        st = c.call("/wordscramble/remove", {"index": 0})
        self.assertEqual(st["tile_state"][0], "pool")

    def test_full_correct_arrangement_wins(self):
        c = self.client()
        c.call("/wordscramble/new", {})
        word = server.SESSIONS[c.sid()]["ws_game"]["word"]
        letters = server.SESSIONS[c.sid()]["ws_game"]["letters"]
        st = None
        for target_letter in word:
            idx = next(i for i, (l, s) in enumerate(zip(letters, ["pool"] * len(letters)))
                       if l == target_letter and server.SESSIONS[c.sid()]["ws_game"]["tile_state"][i] == "pool")
            st = c.call("/wordscramble/place", {"index": idx})
        self.assertTrue(st["won"])
        self.assertTrue(st["over"])
        self.assertEqual(st["word"], word)

    def test_score_increments_after_win(self):
        c = self.client()
        c.call("/wordscramble/new", {"level": "easy"})
        g = server.SESSIONS[c.sid()]["ws_game"]
        word = g["word"]
        for target_letter in word:
            idx = next(i for i, l in enumerate(g["letters"]) if l == target_letter and g["tile_state"][i] == "pool")
            st = c.call("/wordscramble/place", {"index": idx})
        self.assertEqual(st["score"]["player"], server.level_points("easy"))

    def test_sessions_are_independent(self):
        a, b = self.client(), self.client()
        a.call("/wordscramble/new", {"level": "hard"})
        self.assertEqual(b.call("/wordscramble/state")["level"], server.DEFAULT_LEVEL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
