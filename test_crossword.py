"""Tests for the Kids Crossword — standard library only, no deps.

Three groups:
  * TestCrosswordGameLogic — pure crossword.py helpers. No server.
  * TestCrosswordScoring   — scoring functions + persistence. No network.
  * TestCrosswordApi       — end-to-end HTTP with cookie-backed sessions.
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
import crossword
from crossword_puzzles import PUZZLES_BY_LEVEL


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


def solve_all(game):
    """Fill every active cell with its correct letter."""
    for r in range(game["size"]):
        for c in range(game["size"]):
            sol = game["solution"][r][c]
            if sol is not None:
                crossword.set_letter(game, r, c, sol)


# ---------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------

class TestCrosswordGameLogic(unittest.TestCase):

    def test_new_game_defaults(self):
        g = crossword.new_game()
        self.assertEqual(g["level"], crossword.DEFAULT_LEVEL)
        self.assertEqual(g["hints_used"], 0)
        self.assertFalse(g["over"])
        self.assertFalse(g["won"])
        self.assertFalse(g["scored"])
        self.assertTrue(all(cell is None for row in g["player"] for cell in row))

    def test_new_game_invalid_level_falls_back(self):
        g = crossword.new_game("impossible")
        self.assertEqual(g["level"], crossword.DEFAULT_LEVEL)

    def test_build_grid_numbering_shared_start_cell(self):
        # Easy puzzle 0: APPLE(across) and ANT(down) both start at (1,0) —
        # that cell should get exactly one number, shared by both clues.
        puzzle = PUZZLES_BY_LEVEL["easy"][0]
        size, solution, words = crossword._build_grid(puzzle)
        apple = next(w for w in words if w["answer"] == "APPLE")
        ant   = next(w for w in words if w["answer"] == "ANT")
        egg   = next(w for w in words if w["answer"] == "EGG")
        self.assertEqual(apple["number"], ant["number"])
        self.assertNotEqual(apple["number"], egg["number"])

    def test_build_grid_blocked_cells_exist(self):
        puzzle = PUZZLES_BY_LEVEL["easy"][0]
        size, solution, words = crossword._build_grid(puzzle)
        blocked_count = sum(1 for row in solution for cell in row if cell is None)
        active_count = size * size - blocked_count
        self.assertGreater(blocked_count, 0)
        # APPLE(5)+ANT(3)+EGG(3)-1 shared + SHEEP(5)+SUN(3)+PIG(3)-1 shared = 18
        self.assertEqual(active_count, 18)

    def test_set_letter_on_active_cell(self):
        g = crossword.new_game("easy")
        r, c = g["words"][0]["cells"][0]
        crossword.set_letter(g, r, c, g["solution"][r][c])
        self.assertEqual(g["player"][r][c], g["solution"][r][c])

    def test_set_letter_on_blocked_cell_is_noop(self):
        g = crossword.new_game("easy")
        # (3,0) is the buffer row separating the two stacked blocks — always blocked
        crossword.set_letter(g, 3, 0, "Z")
        self.assertIsNone(g["player"][3][0])

    def test_set_letter_lowercase_normalized_to_upper(self):
        g = crossword.new_game("easy")
        r, c = g["words"][0]["cells"][0]
        crossword.set_letter(g, r, c, g["solution"][r][c].lower())
        self.assertEqual(g["player"][r][c], g["solution"][r][c])

    def test_set_letter_invalid_char_ignored(self):
        g = crossword.new_game("easy")
        r, c = g["words"][0]["cells"][0]
        crossword.set_letter(g, r, c, "5")
        self.assertIsNone(g["player"][r][c])

    def test_clear_letter(self):
        g = crossword.new_game("easy")
        r, c = g["words"][0]["cells"][0]
        crossword.set_letter(g, r, c, g["solution"][r][c])
        crossword.clear_letter(g, r, c)
        self.assertIsNone(g["player"][r][c])

    def test_clear_letter_on_blocked_cell_is_noop(self):
        g = crossword.new_game("easy")
        crossword.clear_letter(g, 3, 0)
        self.assertIsNone(g["player"][3][0])

    def test_reveal_letter_fills_correct_and_counts_hint(self):
        g = crossword.new_game("easy")
        r, c = g["words"][0]["cells"][0]
        crossword.reveal_letter(g, r, c)
        self.assertEqual(g["player"][r][c], g["solution"][r][c])
        self.assertEqual(g["hints_used"], 1)

    def test_reveal_letter_on_blocked_cell_is_noop(self):
        g = crossword.new_game("easy")
        crossword.reveal_letter(g, 3, 0)
        self.assertEqual(g["hints_used"], 0)

    def test_word_solved_reflected_in_game_state(self):
        g = crossword.new_game("easy")
        word = g["words"][0]
        for r, c in word["cells"]:
            crossword.set_letter(g, r, c, g["solution"][r][c])
        st = crossword.game_state(g)
        all_clues = st["clues"]["across"] + st["clues"]["down"]
        solved_clue = next(cl for cl in all_clues if cl["number"] == word["number"] and cl["clue"] == word["clue"])
        self.assertTrue(solved_clue["solved"])

    def test_full_completion_sets_over_and_won(self):
        g = crossword.new_game("easy")
        solve_all(g)
        self.assertTrue(g["over"])
        self.assertTrue(g["won"])

    def test_partial_completion_not_over(self):
        g = crossword.new_game("easy")
        r, c = g["words"][0]["cells"][0]
        crossword.set_letter(g, r, c, g["solution"][r][c])
        self.assertFalse(g["over"])

    def test_set_letter_noop_after_over(self):
        g = crossword.new_game("easy")
        solve_all(g)
        r, c = g["words"][0]["cells"][0]
        crossword.clear_letter(g, r, c)  # should be ignored once over
        self.assertEqual(g["player"][r][c], g["solution"][r][c])

    def test_game_state_includes_expected_fields(self):
        st = crossword.game_state(crossword.new_game())
        for field in ("size", "cells", "clues", "hints_used", "over", "won", "level", "levels"):
            self.assertIn(field, st)

    def test_game_state_blocked_cells_have_no_letter(self):
        st = crossword.game_state(crossword.new_game("easy"))
        self.assertIsNone(st["cells"][3][0]["letter"])
        self.assertTrue(st["cells"][3][0]["blocked"])


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class TestCrosswordScoring(IsolatedScores):

    def _finished_session(self, name=None, level="easy", hints_used=0):
        sess = server.new_session()
        sess["name"] = name
        g = crossword.new_game(level)
        g["over"] = True
        g["won"] = True
        g["hints_used"] = hints_used
        sess["cw_game"] = g
        return sess

    def test_no_hints_awards_level_points(self):
        sess = self._finished_session(level="hard", hints_used=0)
        server.cw_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["crossword"]["player"], server.level_points("hard"))
        self.assertEqual(server.SCORES["Guest"]["crossword"]["hangman"], 0)

    def test_hints_used_awards_computer_point(self):
        sess = self._finished_session(hints_used=2)
        server.cw_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["crossword"]["hangman"], 1)
        self.assertEqual(server.SCORES["Guest"]["crossword"]["player"], 0)

    def test_apply_score_fires_once(self):
        sess = self._finished_session(level="medium", hints_used=0)
        server.cw_apply_score(sess)
        server.cw_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["crossword"]["player"], server.level_points("medium"))

    def test_not_over_does_not_score(self):
        sess = server.new_session()
        server.cw_apply_score(sess)
        self.assertNotIn("crossword", server.SCORES.get("Guest", {}))

    def test_guest_score_written_to_db(self):
        sess = self._finished_session(level="easy", hints_used=0)
        server.cw_apply_score(sess)
        loaded = server.load_scores()
        self.assertIn("Guest", loaded)
        self.assertEqual(loaded["Guest"]["crossword"]["player"], server.level_points("easy"))

    def test_named_score_persists(self):
        sess = self._finished_session(name="Nia", level="hard", hints_used=0)
        server.cw_apply_score(sess)
        self.assertEqual(server.load_scores()["Nia"]["crossword"]["player"], server.level_points("hard"))


# ---------------------------------------------------------------------------
# End-to-end API
# ---------------------------------------------------------------------------

class TestCrosswordApi(IsolatedScores):

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
        st = self.client().call("/crossword/state")
        for f in ("size", "cells", "clues", "hints_used", "over", "won",
                  "level", "levels", "score", "total_score", "names"):
            self.assertIn(f, st)

    def test_new_game_resets(self):
        c = self.client()
        st = c.call("/crossword/new", {"level": "hard"})
        self.assertEqual(st["level"], "hard")
        self.assertFalse(st["over"])
        self.assertEqual(st["hints_used"], 0)

    def test_new_without_level_keeps_current_level(self):
        c = self.client()
        c.call("/crossword/new", {"level": "hard"})
        self.assertEqual(c.call("/crossword/new", {})["level"], "hard")

    def test_letter_and_clear_round_trip(self):
        c = self.client()
        c.call("/crossword/new", {"level": "easy"})
        game = server.SESSIONS[c.sid()]["cw_game"]
        r, cc = game["words"][0]["cells"][0]
        letter = game["solution"][r][cc]
        st = c.call("/crossword/letter", {"row": r, "col": cc, "letter": letter})
        self.assertEqual(st["cells"][r][cc]["letter"], letter)
        st = c.call("/crossword/clear", {"row": r, "col": cc})
        self.assertIsNone(st["cells"][r][cc]["letter"])

    def test_reveal_increments_hints(self):
        c = self.client()
        c.call("/crossword/new", {"level": "easy"})
        game = server.SESSIONS[c.sid()]["cw_game"]
        r, cc = game["words"][0]["cells"][0]
        st = c.call("/crossword/reveal", {"row": r, "col": cc})
        self.assertEqual(st["hints_used"], 1)
        self.assertEqual(st["cells"][r][cc]["letter"], game["solution"][r][cc])

    def test_completing_puzzle_without_hints_scores_player(self):
        c = self.client()
        c.call("/crossword/new", {"level": "easy"})
        game = server.SESSIONS[c.sid()]["cw_game"]
        st = None
        for r in range(game["size"]):
            for col in range(game["size"]):
                sol = game["solution"][r][col]
                if sol is not None:
                    st = c.call("/crossword/letter", {"row": r, "col": col, "letter": sol})
        self.assertTrue(st["over"])
        self.assertTrue(st["won"])
        self.assertEqual(st["score"]["player"], server.level_points("easy"))
        self.assertEqual(st["score"]["hangman"], 0)

    def test_sessions_are_independent(self):
        a, b = self.client(), self.client()
        a.call("/crossword/new", {"level": "hard"})
        self.assertEqual(b.call("/crossword/state")["level"], crossword.DEFAULT_LEVEL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
