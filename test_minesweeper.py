"""Tests for Minesweeper — standard library only, no deps.

Three groups:
  * TestMinesweeperGameLogic — pure minesweeper.py helpers. No server.
  * TestMinesweeperScoring   — scoring functions + persistence. No network.
  * TestMinesweeperApi       — end-to-end HTTP with cookie-backed sessions.
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
import minesweeper


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


def reveal_safe_cell(game):
    """Reveal any single safe (non-mine) cell, placing mines first if needed."""
    if not game["mines_placed"]:
        minesweeper.reveal(game, 0, 0)
        return
    for r in range(game["rows"]):
        for c in range(game["cols"]):
            if not game["board"][r][c]["mine"]:
                minesweeper.reveal(game, r, c)
                return


def win_game(game):
    """Reveal every safe cell to force a win, without ever touching a mine."""
    minesweeper.reveal(game, 0, 0)  # places mines away from (0,0)
    for r in range(game["rows"]):
        for c in range(game["cols"]):
            if not game["board"][r][c]["mine"]:
                minesweeper.reveal(game, r, c)


def lose_game(game):
    """Force mines to be placed, then reveal a known mine to lose immediately."""
    minesweeper.reveal(game, 0, 0)
    for r in range(game["rows"]):
        for c in range(game["cols"]):
            if game["board"][r][c]["mine"]:
                minesweeper.reveal(game, r, c)
                return


# ---------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------

class TestMinesweeperGameLogic(unittest.TestCase):

    def test_new_game_defaults(self):
        g = minesweeper.new_game()
        self.assertEqual(g["level"], minesweeper.DEFAULT_LEVEL)
        self.assertFalse(g["mines_placed"])
        self.assertFalse(g["over"])
        self.assertFalse(g["won"])
        self.assertFalse(g["scored"])
        self.assertTrue(all(not cell["revealed"] for row in g["board"] for cell in row))

    def test_new_game_invalid_level_falls_back(self):
        g = minesweeper.new_game("impossible")
        self.assertEqual(g["level"], minesweeper.DEFAULT_LEVEL)

    def test_level_sizes_and_mine_counts(self):
        for level, cfg in minesweeper.LEVEL_CONFIG.items():
            g = minesweeper.new_game(level)
            self.assertEqual(g["rows"], cfg["rows"])
            self.assertEqual(g["cols"], cfg["cols"])
            self.assertEqual(g["mines_total"], cfg["mines"])

    def test_first_click_never_a_mine(self):
        # Run many trials since mine placement is random.
        for _ in range(200):
            g = minesweeper.new_game("easy")
            minesweeper.reveal(g, 3, 3)
            self.assertFalse(g["board"][3][3]["mine"])
            self.assertTrue(g["board"][3][3]["revealed"])

    def test_first_click_neighbors_also_safe(self):
        for _ in range(200):
            g = minesweeper.new_game("easy")
            minesweeper.reveal(g, 4, 4)
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    self.assertFalse(g["board"][4 + dr][4 + dc]["mine"])

    def test_mine_count_matches_level_config(self):
        g = minesweeper.new_game("medium")
        minesweeper.reveal(g, 0, 0)
        total_mines = sum(1 for row in g["board"] for cell in row if cell["mine"])
        self.assertEqual(total_mines, minesweeper.LEVEL_CONFIG["medium"]["mines"])

    def test_adjacent_counts_correct(self):
        g = minesweeper.new_game("easy")
        minesweeper.reveal(g, 0, 0)
        for r in range(g["rows"]):
            for c in range(g["cols"]):
                cell = g["board"][r][c]
                if cell["mine"]:
                    continue
                expected = sum(
                    1 for nr, nc in minesweeper._neighbors(r, c, g["rows"], g["cols"])
                    if g["board"][nr][nc]["mine"]
                )
                self.assertEqual(cell["count"], expected)

    def test_reveal_mine_ends_game_as_loss(self):
        g = minesweeper.new_game("easy")
        lose_game(g)
        self.assertTrue(g["over"])
        self.assertFalse(g["won"])
        self.assertIsNotNone(g["hit"])

    def test_losing_reveals_entire_board(self):
        g = minesweeper.new_game("easy")
        lose_game(g)
        self.assertTrue(all(cell["revealed"] for row in g["board"] for cell in row))

    def test_reveal_all_safe_cells_wins(self):
        g = minesweeper.new_game("easy")
        win_game(g)
        self.assertTrue(g["over"])
        self.assertTrue(g["won"])

    def test_win_auto_flags_all_mines(self):
        g = minesweeper.new_game("easy")
        win_game(g)
        for row in g["board"]:
            for cell in row:
                if cell["mine"]:
                    self.assertTrue(cell["flagged"])

    def test_flood_reveal_opens_zero_region(self):
        g = minesweeper.new_game("easy")
        minesweeper.reveal(g, 0, 0)
        # The first-click safe zone guarantees (0,0) and its 8 neighbors are
        # mine-free; if (0,0) itself is a zero, flood fill should open more
        # than just the single clicked cell.
        if g["board"][0][0]["count"] == 0:
            revealed = sum(1 for row in g["board"] for cell in row if cell["revealed"])
            self.assertGreater(revealed, 1)

    def test_reveal_out_of_bounds_is_noop(self):
        g = minesweeper.new_game("easy")
        minesweeper.reveal(g, -1, 0)
        minesweeper.reveal(g, 0, 999)
        self.assertFalse(g["over"])

    def test_reveal_after_over_is_noop(self):
        g = minesweeper.new_game("easy")
        lose_game(g)
        hit_before = g["hit"]
        minesweeper.reveal(g, 0, 0)
        self.assertEqual(g["hit"], hit_before)

    def test_flag_toggles(self):
        g = minesweeper.new_game("easy")
        minesweeper.flag(g, 2, 2)
        self.assertTrue(g["board"][2][2]["flagged"])
        minesweeper.flag(g, 2, 2)
        self.assertFalse(g["board"][2][2]["flagged"])

    def test_flag_on_revealed_cell_is_noop(self):
        g = minesweeper.new_game("easy")
        reveal_safe_cell(g)
        r, c = next((r, c) for r in range(g["rows"]) for c in range(g["cols"])
                    if g["board"][r][c]["revealed"])
        minesweeper.flag(g, r, c)
        self.assertFalse(g["board"][r][c]["flagged"])

    def test_flagged_cell_cannot_be_revealed(self):
        g = minesweeper.new_game("easy")
        minesweeper.flag(g, 5, 5)
        minesweeper.reveal(g, 5, 5)
        self.assertFalse(g["board"][5][5]["revealed"])

    def test_flag_after_over_is_noop(self):
        g = minesweeper.new_game("easy")
        lose_game(g)
        minesweeper.flag(g, 0, 0)
        # (0,0) was revealed by _reveal_all on loss, so flagging must no-op.
        self.assertFalse(g["board"][0][0]["flagged"])

    def test_game_state_hides_mine_and_count_before_reveal(self):
        g = minesweeper.new_game("easy")
        st = minesweeper.game_state(g)
        for row in st["cells"]:
            for cell in row:
                self.assertIsNone(cell["mine"])
                self.assertIsNone(cell["count"])

    def test_game_state_wrong_flag_only_after_over(self):
        g = minesweeper.new_game("easy")
        minesweeper.reveal(g, 0, 0)
        # Flag a cell known to be safe.
        r, c = next((r, c) for r in range(g["rows"]) for c in range(g["cols"])
                    if not g["board"][r][c]["mine"] and not g["board"][r][c]["revealed"])
        minesweeper.flag(g, r, c)
        st = minesweeper.game_state(g)
        self.assertFalse(st["cells"][r][c]["wrong_flag"])  # not over yet
        lose_game(g)
        st = minesweeper.game_state(g)
        self.assertTrue(st["cells"][r][c]["wrong_flag"])

    def test_game_state_includes_expected_fields(self):
        st = minesweeper.game_state(minesweeper.new_game())
        for field in ("cells", "rows", "cols", "mines_total", "flags_used",
                      "level", "levels", "over", "won", "hit"):
            self.assertIn(field, st)

    def test_game_state_flags_used_count(self):
        g = minesweeper.new_game("easy")
        minesweeper.flag(g, 0, 0)
        minesweeper.flag(g, 1, 1)
        st = minesweeper.game_state(g)
        self.assertEqual(st["flags_used"], 2)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class TestMinesweeperScoring(IsolatedScores):

    def _finished_session(self, name=None, level="easy", won=True):
        sess = server.new_session()
        sess["name"] = name
        g = minesweeper.new_game(level)
        g["over"] = True
        g["won"] = won
        sess["mw_game"] = g
        return sess

    def test_win_awards_level_points(self):
        sess = self._finished_session(level="hard", won=True)
        server.mw_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["minesweeper"]["player"], minesweeper.LEVEL_POINTS["hard"])
        self.assertEqual(server.SCORES["Guest"]["minesweeper"]["hangman"], 0)

    def test_loss_awards_computer_point(self):
        sess = self._finished_session(won=False)
        server.mw_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["minesweeper"]["hangman"], 1)
        self.assertEqual(server.SCORES["Guest"]["minesweeper"]["player"], 0)

    def test_apply_score_fires_once(self):
        sess = self._finished_session(level="medium", won=True)
        server.mw_apply_score(sess)
        server.mw_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["minesweeper"]["player"], minesweeper.LEVEL_POINTS["medium"])

    def test_not_over_does_not_score(self):
        sess = server.new_session()
        server.mw_apply_score(sess)
        self.assertNotIn("minesweeper", server.SCORES.get("Guest", {}))

    def test_guest_score_written_to_db(self):
        sess = self._finished_session(level="easy", won=True)
        server.mw_apply_score(sess)
        loaded = server.load_scores()
        self.assertIn("Guest", loaded)
        self.assertEqual(loaded["Guest"]["minesweeper"]["player"], minesweeper.LEVEL_POINTS["easy"])

    def test_named_score_persists(self):
        sess = self._finished_session(name="Nia", level="hard", won=True)
        server.mw_apply_score(sess)
        self.assertEqual(server.load_scores()["Nia"]["minesweeper"]["player"], minesweeper.LEVEL_POINTS["hard"])


# ---------------------------------------------------------------------------
# End-to-end API
# ---------------------------------------------------------------------------

class TestMinesweeperApi(IsolatedScores):

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
        st = self.client().call("/minesweeper/state")
        for f in ("cells", "rows", "cols", "mines_total", "flags_used",
                  "level", "levels", "over", "won", "score", "total_score", "names"):
            self.assertIn(f, st)

    def test_new_game_resets(self):
        c = self.client()
        st = c.call("/minesweeper/new", {"level": "hard"})
        self.assertEqual(st["level"], "hard")
        self.assertFalse(st["over"])
        self.assertEqual(st["rows"], minesweeper.LEVEL_CONFIG["hard"]["rows"])

    def test_new_without_level_keeps_current_level(self):
        c = self.client()
        c.call("/minesweeper/new", {"level": "hard"})
        self.assertEqual(c.call("/minesweeper/new", {})["level"], "hard")

    def test_reveal_first_click_never_mine(self):
        c = self.client()
        c.call("/minesweeper/new", {"level": "easy"})
        st = c.call("/minesweeper/reveal", {"row": 3, "col": 3})
        self.assertTrue(st["cells"][3][3]["revealed"])
        self.assertFalse(st["cells"][3][3]["mine"])

    def test_flag_round_trip(self):
        c = self.client()
        c.call("/minesweeper/new", {"level": "easy"})
        st = c.call("/minesweeper/flag", {"row": 1, "col": 1})
        self.assertTrue(st["cells"][1][1]["flagged"])
        self.assertEqual(st["flags_used"], 1)
        st = c.call("/minesweeper/flag", {"row": 1, "col": 1})
        self.assertFalse(st["cells"][1][1]["flagged"])
        self.assertEqual(st["flags_used"], 0)

    def test_winning_awards_player_point(self):
        c = self.client()
        c.call("/minesweeper/new", {"level": "easy"})
        game = server.SESSIONS[c.sid()]["mw_game"]
        st = c.call("/minesweeper/reveal", {"row": 0, "col": 0})
        while not st["over"]:
            game = server.SESSIONS[c.sid()]["mw_game"]
            r, col = next(
                (r, col) for r in range(game["rows"]) for col in range(game["cols"])
                if not game["board"][r][col]["mine"] and not game["board"][r][col]["revealed"]
            )
            st = c.call("/minesweeper/reveal", {"row": r, "col": col})
        self.assertTrue(st["won"])
        self.assertEqual(st["score"]["player"], minesweeper.LEVEL_POINTS["easy"])
        self.assertEqual(st["score"]["hangman"], 0)

    def test_losing_awards_computer_point(self):
        c = self.client()
        c.call("/minesweeper/new", {"level": "easy"})
        c.call("/minesweeper/reveal", {"row": 0, "col": 0})
        game = server.SESSIONS[c.sid()]["mw_game"]
        r, col = next((r, col) for r in range(game["rows"]) for col in range(game["cols"])
                      if game["board"][r][col]["mine"])
        st = c.call("/minesweeper/reveal", {"row": r, "col": col})
        self.assertTrue(st["over"])
        self.assertFalse(st["won"])
        self.assertEqual(st["score"]["hangman"], 1)
        self.assertEqual(st["score"]["player"], 0)

    def test_sessions_are_independent(self):
        a, b = self.client(), self.client()
        a.call("/minesweeper/new", {"level": "hard"})
        self.assertEqual(b.call("/minesweeper/state")["level"], minesweeper.DEFAULT_LEVEL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
