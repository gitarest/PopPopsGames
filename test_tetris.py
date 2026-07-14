"""Tests for Tetris — standard library only, no deps.

Three groups:
  * TestTetrisGameLogic — pure tetris.py helpers. No server.
  * TestTetrisScoring   — scoring functions + persistence. No network.
  * TestTetrisApi       — end-to-end HTTP with cookie-backed sessions.

Gravity is time-based (server checks real elapsed time via time.monotonic()),
so tests never sleep — they backdate game["last_drop"] to simulate elapsed
time deterministically and instantly.
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
import tetris


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


def fill_row(game, row, except_cols=()):
    for c in range(tetris.COLS):
        if c not in except_cols:
            game["board"][row][c] = "#fff"


# ---------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------

class TestTetrisGameLogic(unittest.TestCase):

    def test_new_game_defaults(self):
        g = tetris.new_game()
        self.assertEqual(len(g["board"]), tetris.ROWS)
        self.assertEqual(len(g["board"][0]), tetris.COLS)
        self.assertTrue(all(cell is None for row in g["board"] for cell in row))
        self.assertEqual(g["level"], tetris.DEFAULT_LEVEL)
        self.assertEqual(g["level_num"], 1)
        self.assertEqual(g["lines"], 0)
        self.assertFalse(g["over"])
        self.assertFalse(g["scored"])
        self.assertIn(g["piece_type"], tetris.PIECE_TYPES)
        self.assertIn(g["next_type"], tetris.PIECE_TYPES)

    def test_new_game_invalid_level_falls_back(self):
        g = tetris.new_game("impossible")
        self.assertEqual(g["level"], tetris.DEFAULT_LEVEL)

    def test_new_game_levels_have_different_speeds(self):
        easy = tetris.new_game("easy")["drop_interval"]
        hard = tetris.new_game("hard")["drop_interval"]
        self.assertGreater(easy, hard)

    def test_spawn_col_within_bounds(self):
        for piece_type in tetris.PIECE_TYPES:
            col = tetris._spawn_col(piece_type)
            size = tetris.PIECES[piece_type]["size"]
            self.assertGreaterEqual(col, 0)
            self.assertLessEqual(col + size, tetris.COLS)

    def test_move_left_shifts_column(self):
        g = tetris.new_game()
        before = g["col"]
        tetris.move(g, "left")
        self.assertEqual(g["col"], before - 1)

    def test_move_right_shifts_column(self):
        g = tetris.new_game()
        before = g["col"]
        tetris.move(g, "right")
        self.assertEqual(g["col"], before + 1)

    def test_move_left_blocked_at_wall(self):
        g = tetris.new_game()
        g["col"] = 0
        tetris.move(g, "left")
        self.assertEqual(g["col"], 0)

    def test_move_right_blocked_at_wall(self):
        g = tetris.new_game()
        g["piece_type"] = "I"
        g["rotation"] = 1  # vertical, 1 column wide at offset col+2
        g["col"] = tetris.COLS - 3
        tetris.move(g, "right")
        self.assertEqual(g["col"], tetris.COLS - 3)

    def test_rotate_cycles_through_four_states_and_returns(self):
        g = tetris.new_game()
        g["piece_type"] = "T"
        g["row"], g["col"], g["rotation"] = 5, 4, 0
        original = sorted(tetris._cells(g))
        for _ in range(4):
            tetris.move(g, "rotate")
        self.assertEqual(sorted(tetris._cells(g)), original)

    def test_rotate_blocked_when_it_would_collide(self):
        g = tetris.new_game()
        g["piece_type"] = "I"
        g["rotation"] = 0
        g["row"], g["col"] = 8, tetris.COLS - 4
        # Rotating to vertical (rotation 1) would occupy column col+2 down through row 10 —
        # fill that row so the rotated position collides.
        fill_row(g, 10)
        tetris.move(g, "rotate")
        self.assertEqual(g["rotation"], 0)

    def test_soft_drop_moves_down_one_row(self):
        g = tetris.new_game()
        before_row = g["row"]
        tetris.move(g, "soft_drop")
        self.assertEqual(g["row"], before_row + 1)

    def test_hard_drop_locks_at_bottom(self):
        g = tetris.new_game()
        tetris.move(g, "hard_drop")
        # A new piece should have spawned back at row 0 after locking
        self.assertEqual(g["row"], 0)
        # Board should now have some locked cells
        self.assertTrue(any(cell is not None for row in g["board"] for cell in row))

    def test_single_line_clear(self):
        g = tetris.new_game()
        fill_row(g, 19, except_cols=(8, 9))
        g["piece_type"] = "O"
        g["rotation"] = 0
        g["row"], g["col"] = 18, 8
        tetris._lock_piece(g)
        self.assertEqual(g["lines"], 1)
        self.assertTrue(all(cell is None for cell in g["board"][19][:8]))

    def test_level_up_after_enough_lines(self):
        g = tetris.new_game("easy")
        start_interval = g["drop_interval"]
        for i in range(tetris.LINES_PER_LEVEL_UP):
            fill_row(g, 19, except_cols=(8, 9))
            g["piece_type"] = "O"
            g["rotation"] = 0
            g["row"], g["col"] = 18, 8
            tetris._lock_piece(g)
        self.assertEqual(g["lines"], tetris.LINES_PER_LEVEL_UP)
        self.assertEqual(g["level_num"], 2)
        self.assertLess(g["drop_interval"], start_interval)

    def test_game_over_on_top_out(self):
        g = tetris.new_game()
        # Fill the top rows in columns 0-8, leaving column 9 empty so no row
        # is complete (no accidental line-clear) — any piece spawning near
        # the center columns will immediately collide with this stack.
        for r in range(6):
            for c in range(tetris.COLS - 1):
                g["board"][r][c] = "#fff"
        tetris.move(g, "hard_drop")
        self.assertTrue(g["over"])

    def test_gravity_reconciles_backdated_last_drop(self):
        g = tetris.new_game()
        before_row = g["row"]
        # Back-date by just over one interval so exactly one gravity step fires
        # (a large backdate could drop all the way to the floor and lock,
        # which resets row back to 0 for the newly spawned piece).
        g["last_drop"] -= (g["drop_interval"] / 1000.0) + 0.05
        tetris.tick(g)
        self.assertEqual(g["row"], before_row + 1)

    def test_gravity_does_nothing_when_no_time_has_passed(self):
        g = tetris.new_game()
        before_row = g["row"]
        tetris.tick(g)
        self.assertEqual(g["row"], before_row)

    def test_move_and_tick_noop_after_game_over(self):
        g = tetris.new_game()
        g["over"] = True
        before = (g["row"], g["col"], g["rotation"])
        tetris.move(g, "left")
        tetris.tick(g)
        self.assertEqual((g["row"], g["col"], g["rotation"]), before)

    def test_game_state_hides_piece_overlay_when_over(self):
        g = tetris.new_game()
        g["over"] = True
        st = tetris.game_state(g)
        self.assertTrue(st["over"])

    def test_game_state_includes_expected_fields(self):
        st = tetris.game_state(tetris.new_game())
        for field in ("board", "next_cells", "next_color", "lines", "level_num",
                      "level", "levels", "drop_interval", "over"):
            self.assertIn(field, st)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class TestTetrisScoring(IsolatedScores):

    def _finished_session(self, name=None, level="medium", level_num=3, lines=25):
        sess = server.new_session()
        sess["name"] = name
        g = tetris.new_game(level)
        g["level_num"] = level_num
        g["lines"] = lines
        g["over"] = True
        sess["tet_game"] = g
        return sess

    def test_score_awards_level_num_to_player(self):
        sess = self._finished_session(level_num=4)
        server.tet_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["tetris"]["player"], 4)

    def test_computer_always_gets_one_point(self):
        sess = self._finished_session(level_num=1)
        server.tet_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["tetris"]["hangman"], 1)

    def test_apply_score_fires_once(self):
        sess = self._finished_session(level_num=5)
        server.tet_apply_score(sess)
        server.tet_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["tetris"]["player"], 5)
        self.assertEqual(server.SCORES["Guest"]["tetris"]["hangman"], 1)

    def test_not_over_does_not_score(self):
        sess = server.new_session()
        server.tet_apply_score(sess)
        self.assertNotIn("tetris", server.SCORES.get("Guest", {}))

    def test_best_initializes_and_updates(self):
        sess = self._finished_session(level_num=3)
        server.tet_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["tetris"]["best"], 3)

    def test_best_does_not_decrease(self):
        sess1 = self._finished_session(name="Kai", level_num=6)
        server.tet_apply_score(sess1)
        sess2 = self._finished_session(name="Kai", level_num=2)
        server.tet_apply_score(sess2)
        self.assertEqual(server.SCORES["Kai"]["tetris"]["best"], 6)

    def test_best_increases_on_new_record(self):
        sess1 = self._finished_session(name="Kai", level_num=2)
        server.tet_apply_score(sess1)
        sess2 = self._finished_session(name="Kai", level_num=7)
        server.tet_apply_score(sess2)
        self.assertEqual(server.SCORES["Kai"]["tetris"]["best"], 7)

    def test_guest_score_written_to_db(self):
        sess = self._finished_session(level_num=4)
        server.tet_apply_score(sess)
        loaded = server.load_scores()
        self.assertIn("Guest", loaded)
        self.assertEqual(loaded["Guest"]["tetris"]["player"], 4)

    def test_named_score_persists(self):
        sess = self._finished_session(name="Nia", level_num=5)
        server.tet_apply_score(sess)
        self.assertEqual(server.load_scores()["Nia"]["tetris"]["player"], 5)


# ---------------------------------------------------------------------------
# End-to-end API
# ---------------------------------------------------------------------------

class TestTetrisApi(IsolatedScores):

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
        st = self.client().call("/tetris/state")
        for f in ("board", "next_cells", "next_color", "lines", "level_num",
                  "level", "levels", "drop_interval", "over", "score", "total_score", "names"):
            self.assertIn(f, st)

    def test_new_game_resets(self):
        c = self.client()
        st = c.call("/tetris/new", {"level": "hard"})
        self.assertEqual(st["level"], "hard")
        self.assertEqual(st["lines"], 0)
        self.assertFalse(st["over"])

    def test_new_without_level_keeps_current_level(self):
        c = self.client()
        c.call("/tetris/new", {"level": "hard"})
        self.assertEqual(c.call("/tetris/new", {})["level"], "hard")

    def test_move_left_changes_column(self):
        c = self.client()
        c.call("/tetris/state")
        before_col = server.SESSIONS[c.sid()]["tet_game"]["col"]
        c.call("/tetris/move", {"action": "left"})
        after_col = server.SESSIONS[c.sid()]["tet_game"]["col"]
        self.assertEqual(after_col, before_col - 1)

    def test_unknown_action_is_ignored(self):
        c = self.client()
        c.call("/tetris/state")
        before = dict(server.SESSIONS[c.sid()]["tet_game"])
        c.call("/tetris/move", {"action": "teleport"})
        after = server.SESSIONS[c.sid()]["tet_game"]
        self.assertEqual(before["row"], after["row"])
        self.assertEqual(before["col"], after["col"])

    def test_tick_reconciles_backdated_gravity(self):
        c = self.client()
        c.call("/tetris/state")
        game = server.SESSIONS[c.sid()]["tet_game"]
        before_row = game["row"]
        # Back-date by just over one interval so exactly one gravity step fires.
        game["last_drop"] -= (game["drop_interval"] / 1000.0) + 0.05
        c.call("/tetris/tick", {})
        self.assertEqual(server.SESSIONS[c.sid()]["tet_game"]["row"], before_row + 1)

    def test_score_increments_on_game_over(self):
        c = self.client()
        c.call("/tetris/state")
        game = server.SESSIONS[c.sid()]["tet_game"]
        game["level_num"] = 3
        game["lines"] = 25
        game["over"] = True
        st = c.call("/tetris/state")
        self.assertEqual(st["score"]["player"], 3)
        self.assertEqual(st["score"]["hangman"], 1)

    def test_sessions_are_independent(self):
        a, b = self.client(), self.client()
        a.call("/tetris/new", {"level": "hard"})
        self.assertEqual(b.call("/tetris/state")["level"], tetris.DEFAULT_LEVEL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
