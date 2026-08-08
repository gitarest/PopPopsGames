"""Tests for Battleship — standard library only, no deps.

Three groups:
  * TestBattleshipGameLogic — pure battleship.py helpers. No server.
  * TestBattleshipScoring   — scoring functions + persistence. No network.
  * TestBattleshipApi       — end-to-end HTTP with cookie-backed sessions.
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
import battleship


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


def win_game(game):
    """Fire at every cell of the computer's fleet to force a player win,
    bypassing the computer's return fire by restoring player_shots state
    directly isn't needed — we just fire until over, since the computer's
    return shots landing on the player's board can't make the player lose
    faster than finishing the computer's fleet in the same loop."""
    board = game["computer_board"]
    ship_cells = [cell for ship in board["ships"] for cell in ship["cells"]]
    for r, c in ship_cells:
        if game["over"]:
            break
        battleship.fire(game, r, c)


def sink_all_player_ships_directly(game):
    """Bypass turn order and mark every player ship cell as hit, for testing
    the loss/scoring path without depending on computer AI randomness."""
    board = game["player_board"]
    for ship in board["ships"]:
        for r, c in ship["cells"]:
            ship["hits"].add((r, c))
            game["computer_shots"][(r, c)] = "hit"
    if battleship._all_sunk(board):
        game["over"] = True
        game["won"] = False


# ---------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------

class TestBattleshipGameLogic(unittest.TestCase):

    def test_new_game_defaults(self):
        g = battleship.new_game()
        self.assertEqual(g["level"], battleship.DEFAULT_LEVEL)
        self.assertFalse(g["over"])
        self.assertIsNone(g["won"])
        self.assertFalse(g["scored"])
        self.assertFalse(g["first_shot_fired"])

    def test_new_game_invalid_level_falls_back(self):
        g = battleship.new_game("impossible")
        self.assertEqual(g["level"], battleship.DEFAULT_LEVEL)

    def test_fleet_has_no_overlaps_and_correct_cell_count(self):
        for _ in range(50):
            board = battleship._place_fleet_randomly()
            all_cells = [cell for ship in board["ships"] for cell in ship["cells"]]
            self.assertEqual(len(all_cells), len(set(all_cells)))
            expected_total = sum(length for _, length in battleship.SHIPS)
            self.assertEqual(len(all_cells), expected_total)
            for r, c in all_cells:
                self.assertIsNotNone(board["grid"][r][c])

    def test_fleet_ships_stay_in_bounds(self):
        for _ in range(50):
            board = battleship._place_fleet_randomly()
            for ship in board["ships"]:
                for r, c in ship["cells"]:
                    self.assertTrue(0 <= r < battleship.BOARD_SIZE)
                    self.assertTrue(0 <= c < battleship.BOARD_SIZE)

    def test_fire_hit_registers_on_computer_board(self):
        g = battleship.new_game("easy")
        r, c = g["computer_board"]["ships"][0]["cells"][0]
        battleship.fire(g, r, c)
        self.assertEqual(g["player_shots"][(r, c)], "hit")

    def test_fire_miss_registers(self):
        g = battleship.new_game("easy")
        ship_cells = {cell for ship in g["computer_board"]["ships"] for cell in ship["cells"]}
        empty = next((r, c) for r in range(battleship.BOARD_SIZE) for c in range(battleship.BOARD_SIZE)
                     if (r, c) not in ship_cells)
        battleship.fire(g, *empty)
        self.assertEqual(g["player_shots"][empty], "miss")

    def test_fire_marks_first_shot_fired(self):
        g = battleship.new_game("easy")
        battleship.fire(g, 0, 0)
        self.assertTrue(g["first_shot_fired"])

    def test_fire_out_of_bounds_is_noop(self):
        g = battleship.new_game("easy")
        battleship.fire(g, -1, 0)
        battleship.fire(g, 0, 999)
        self.assertFalse(g["first_shot_fired"])

    def test_fire_same_cell_twice_is_noop(self):
        g = battleship.new_game("easy")
        battleship.fire(g, 0, 0)
        shots_before = dict(g["player_shots"])
        battleship.fire(g, 0, 0)
        self.assertEqual(g["player_shots"], shots_before)

    def test_fire_triggers_computer_return_shot(self):
        g = battleship.new_game("easy")
        battleship.fire(g, 0, 0)
        if not g["over"]:
            self.assertEqual(len(g["computer_shots"]), 1)

    def test_sinking_all_computer_ships_wins(self):
        g = battleship.new_game("easy")
        win_game(g)
        self.assertTrue(g["over"])
        self.assertTrue(g["won"])

    def test_winning_skips_final_computer_turn(self):
        # The computer should not get to fire back after the player's
        # winning shot -- game is already over.
        g = battleship.new_game("easy")
        win_game(g)
        computer_shots_after_win = len(g["computer_shots"])
        battleship.fire(g, 0, 0)  # no-op since over
        self.assertEqual(len(g["computer_shots"]), computer_shots_after_win)

    def test_losing_all_player_ships_loses(self):
        g = battleship.new_game("easy")
        sink_all_player_ships_directly(g)
        self.assertTrue(g["over"])
        self.assertFalse(g["won"])

    def test_fire_after_over_is_noop(self):
        g = battleship.new_game("easy")
        win_game(g)
        shots_before = dict(g["player_shots"])
        battleship.fire(g, 5, 5)
        self.assertEqual(g["player_shots"], shots_before)

    def test_medium_ai_hunts_after_hit(self):
        # Force a known layout: place a 2-cell ship at (0,0)-(0,1) directly,
        # then have the computer's first shot land on it and verify the
        # follow-up target queue points at an orthogonal neighbor.
        g = battleship.new_game("medium")
        g["player_board"] = {
            "grid": [[None] * battleship.BOARD_SIZE for _ in range(battleship.BOARD_SIZE)],
            "ships": [{"name": "Destroyer", "length": 2, "cells": [(0, 0), (0, 1)], "hits": set()}],
        }
        g["player_board"]["grid"][0][0] = 0
        g["player_board"]["grid"][0][1] = 0
        g["ai_targets"] = [(0, 0)]
        battleship._computer_turn(g)
        self.assertEqual(g["computer_shots"][(0, 0)], "hit")
        self.assertIn((0, 1), g["ai_targets"])

    def test_easy_ai_does_not_queue_hunt_targets(self):
        g = battleship.new_game("easy")
        g["player_board"] = {
            "grid": [[None] * battleship.BOARD_SIZE for _ in range(battleship.BOARD_SIZE)],
            "ships": [{"name": "Destroyer", "length": 2, "cells": [(0, 0), (0, 1)], "hits": set()}],
        }
        g["player_board"]["grid"][0][0] = 0
        g["player_board"]["grid"][0][1] = 0
        g["ai_targets"] = [(0, 0)]
        battleship._computer_turn(g)
        self.assertEqual(g["ai_targets"], [])

    def test_randomize_before_first_shot_changes_layout_possible(self):
        g = battleship.new_game("easy")
        original = g["player_board"]
        battleship.randomize_player_fleet(g)
        self.assertIsNotNone(g["player_board"])
        # Not asserting inequality (a reroll could coincidentally match),
        # just that it doesn't crash and produces a valid fresh board.
        all_cells = [cell for ship in g["player_board"]["ships"] for cell in ship["cells"]]
        self.assertEqual(len(all_cells), len(set(all_cells)))

    def test_randomize_after_first_shot_is_noop(self):
        g = battleship.new_game("easy")
        battleship.fire(g, 0, 0)
        board_before = g["player_board"]
        battleship.randomize_player_fleet(g)
        self.assertIs(g["player_board"], board_before)

    def test_randomize_after_over_is_noop(self):
        g = battleship.new_game("easy")
        win_game(g)
        board_before = g["player_board"]
        battleship.randomize_player_fleet(g)
        self.assertIs(g["player_board"], board_before)

    def test_game_state_hides_unsunk_enemy_ships(self):
        g = battleship.new_game("easy")
        st = battleship.game_state(g)
        self.assertTrue(all(not cell["ship"] for row in st["enemy_waters"] for cell in row))

    def test_game_state_reveals_own_ships(self):
        g = battleship.new_game("easy")
        st = battleship.game_state(g)
        ship_cell_count = sum(1 for row in st["your_fleet"] for cell in row if cell["ship"])
        expected = sum(length for _, length in battleship.SHIPS)
        self.assertEqual(ship_cell_count, expected)

    def test_own_ship_hit_but_not_sunk_is_not_marked_sunk(self):
        g = battleship.new_game("easy")
        ship = next(s for s in g["player_board"]["ships"] if s["length"] > 1)
        r, c = ship["cells"][0]
        ship["hits"].add((r, c))
        g["computer_shots"][(r, c)] = "hit"
        st = battleship.game_state(g)
        self.assertFalse(st["your_fleet"][r][c]["sunk"])
        self.assertTrue(st["your_fleet"][r][c]["ship"])

    def test_own_ship_fully_sunk_is_marked_sunk(self):
        g = battleship.new_game("easy")
        ship = g["player_board"]["ships"][0]
        for r, c in ship["cells"]:
            ship["hits"].add((r, c))
            g["computer_shots"][(r, c)] = "hit"
        st = battleship.game_state(g)
        for r, c in ship["cells"]:
            self.assertTrue(st["your_fleet"][r][c]["sunk"])

    def test_game_state_reveals_sunk_enemy_ship(self):
        g = battleship.new_game("easy")
        ship = g["computer_board"]["ships"][0]
        for r, c in ship["cells"]:
            battleship.fire(g, r, c)
            if g["over"]:
                break
        st = battleship.game_state(g)
        for r, c in ship["cells"]:
            self.assertTrue(st["enemy_waters"][r][c]["ship"])

    def test_game_state_includes_expected_fields(self):
        st = battleship.game_state(battleship.new_game())
        for field in ("your_fleet", "enemy_waters", "ships_remaining", "fleets",
                      "board_size", "level", "levels", "first_shot_fired", "over", "won"):
            self.assertIn(field, st)

    def test_fleet_roster_includes_names_and_lengths(self):
        st = battleship.game_state(battleship.new_game())
        for side in ("player", "computer"):
            names = {s["name"] for s in st["fleets"][side]}
            self.assertEqual(names, {name for name, _ in battleship.SHIPS})
            for ship in st["fleets"][side]:
                self.assertEqual(ship["status"], "intact")

    def test_fleet_roster_status_transitions(self):
        g = battleship.new_game("easy")
        ship = g["computer_board"]["ships"][0]  # every ship is length >= 2
        r, c = ship["cells"][0]
        battleship.fire(g, r, c)
        st = battleship.game_state(g)
        status = next(s["status"] for s in st["fleets"]["computer"] if s["name"] == ship["name"])
        self.assertEqual(status, "damaged")

        for r, c in ship["cells"][1:]:
            battleship.fire(g, r, c)
        st = battleship.game_state(g)
        status = next(s["status"] for s in st["fleets"]["computer"] if s["name"] == ship["name"])
        self.assertEqual(status, "sunk")

    def test_ships_remaining_starts_at_fleet_size(self):
        st = battleship.game_state(battleship.new_game())
        self.assertEqual(st["ships_remaining"]["player"], len(battleship.SHIPS))
        self.assertEqual(st["ships_remaining"]["computer"], len(battleship.SHIPS))


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class TestBattleshipScoring(IsolatedScores):

    def _finished_session(self, name=None, level="easy", won=True):
        sess = server.new_session()
        sess["name"] = name
        g = battleship.new_game(level)
        g["over"] = True
        g["won"] = won
        sess["bs_game"] = g
        return sess

    def test_win_awards_level_points(self):
        sess = self._finished_session(level="hard", won=True)
        server.bs_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["battleship"]["player"], battleship.LEVEL_POINTS["hard"])
        self.assertEqual(server.SCORES["Guest"]["battleship"]["hangman"], 0)

    def test_loss_awards_computer_point(self):
        sess = self._finished_session(won=False)
        server.bs_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["battleship"]["hangman"], 1)
        self.assertEqual(server.SCORES["Guest"]["battleship"]["player"], 0)

    def test_apply_score_fires_once(self):
        sess = self._finished_session(level="medium", won=True)
        server.bs_apply_score(sess)
        server.bs_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["battleship"]["player"], battleship.LEVEL_POINTS["medium"])

    def test_not_over_does_not_score(self):
        sess = server.new_session()
        server.bs_apply_score(sess)
        self.assertNotIn("battleship", server.SCORES.get("Guest", {}))

    def test_guest_score_written_to_db(self):
        sess = self._finished_session(level="easy", won=True)
        server.bs_apply_score(sess)
        loaded = server.load_scores()
        self.assertIn("Guest", loaded)
        self.assertEqual(loaded["Guest"]["battleship"]["player"], battleship.LEVEL_POINTS["easy"])

    def test_named_score_persists(self):
        sess = self._finished_session(name="Nia", level="hard", won=True)
        server.bs_apply_score(sess)
        self.assertEqual(server.load_scores()["Nia"]["battleship"]["player"], battleship.LEVEL_POINTS["hard"])


# ---------------------------------------------------------------------------
# End-to-end API
# ---------------------------------------------------------------------------

class TestBattleshipApi(IsolatedScores):

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
        st = self.client().call("/battleship/state")
        for f in ("your_fleet", "enemy_waters", "ships_remaining", "fleets",
                  "board_size", "level", "levels", "over", "won", "score", "total_score", "names"):
            self.assertIn(f, st)

    def test_new_game_resets(self):
        c = self.client()
        st = c.call("/battleship/new", {"level": "hard"})
        self.assertEqual(st["level"], "hard")
        self.assertFalse(st["over"])
        self.assertFalse(st["first_shot_fired"])

    def test_new_without_level_keeps_current_level(self):
        c = self.client()
        c.call("/battleship/new", {"level": "hard"})
        self.assertEqual(c.call("/battleship/new", {})["level"], "hard")

    def test_fire_returns_updated_state(self):
        c = self.client()
        c.call("/battleship/new", {"level": "easy"})
        st = c.call("/battleship/fire", {"row": 0, "col": 0})
        self.assertTrue(st["first_shot_fired"])

    def test_randomize_round_trip(self):
        c = self.client()
        c.call("/battleship/new", {"level": "easy"})
        st = c.call("/battleship/randomize", {})
        ship_cell_count = sum(1 for row in st["your_fleet"] for cell in row if cell["ship"])
        self.assertEqual(ship_cell_count, sum(length for _, length in battleship.SHIPS))

    def test_randomize_locked_after_first_shot(self):
        c = self.client()
        c.call("/battleship/new", {"level": "easy"})
        c.call("/battleship/fire", {"row": 0, "col": 0})
        game = server.SESSIONS[c.sid()]["bs_game"]
        board_before = game["player_board"]
        c.call("/battleship/randomize", {})
        self.assertIs(game["player_board"], board_before)

    def test_winning_awards_player_point(self):
        c = self.client()
        c.call("/battleship/new", {"level": "easy"})
        game = server.SESSIONS[c.sid()]["bs_game"]
        ship_cells = [cell for ship in game["computer_board"]["ships"] for cell in ship["cells"]]
        st = None
        for r, col in ship_cells:
            st = c.call("/battleship/fire", {"row": r, "col": col})
            if st["over"]:
                break
        self.assertTrue(st["over"])
        self.assertTrue(st["won"])
        self.assertEqual(st["score"]["player"], battleship.LEVEL_POINTS["easy"])
        self.assertEqual(st["score"]["hangman"], 0)

    def test_sessions_are_independent(self):
        a, b = self.client(), self.client()
        a.call("/battleship/new", {"level": "hard"})
        self.assertEqual(b.call("/battleship/state")["level"], battleship.DEFAULT_LEVEL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
