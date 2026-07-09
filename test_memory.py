"""Tests for Memory Match — standard library only, no deps.

Three groups:
  * TestMemoryGameLogic — pure memory.py helpers. No server.
  * TestMemoryScoring   — scoring functions + persistence. No network.
  * TestMemoryApi       — end-to-end HTTP with cookie-backed sessions.
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
import memory


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

class TestMemoryGameLogic(unittest.TestCase):

    def test_new_game_defaults(self):
        g = memory.new_game()
        self.assertEqual(len(g["cards"]), 20)
        self.assertEqual(g["theme"], memory.DEFAULT_THEME)
        self.assertEqual(g["level"], memory.DEFAULT_LEVEL)
        self.assertEqual(g["par"],   memory.PAR[memory.DEFAULT_LEVEL])
        self.assertEqual(g["matched"], 0)
        self.assertEqual(g["moves"], 0)
        self.assertFalse(g["mismatch"])
        self.assertFalse(g["over"])
        self.assertFalse(g["scored"])

    def test_new_game_all_cards_hidden(self):
        g = memory.new_game()
        self.assertTrue(all(c["state"] == "hidden" for c in g["cards"]))

    def test_new_game_ten_pairs(self):
        g = memory.new_game()
        from collections import Counter
        counts = Counter(c["emoji"] for c in g["cards"])
        self.assertTrue(all(v == 2 for v in counts.values()))
        self.assertEqual(len(counts), 10)

    def test_new_game_zoo_theme(self):
        g = memory.new_game("zoo")
        self.assertEqual(g["theme"], "zoo")
        emojis = {c["emoji"] for c in g["cards"]}
        self.assertTrue(emojis.issubset(set(memory.THEMES["zoo"])))

    def test_new_game_invalid_theme_falls_back(self):
        g = memory.new_game("dragons")
        self.assertEqual(g["theme"], memory.DEFAULT_THEME)

    def test_no_adjacent_matching_pairs(self):
        for _ in range(20):
            g = memory.new_game()
            emojis = [c["emoji"] for c in g["cards"]]
            self.assertFalse(memory._has_adjacent_pair(emojis))

    def test_new_game_levels(self):
        self.assertEqual(memory.new_game(level="easy")["par"],   memory.PAR["easy"])
        self.assertEqual(memory.new_game(level="medium")["par"], memory.PAR["medium"])
        self.assertEqual(memory.new_game(level="hard")["par"],   memory.PAR["hard"])

    def test_new_game_invalid_level_falls_back(self):
        g = memory.new_game(level="extreme")
        self.assertEqual(g["level"], memory.DEFAULT_LEVEL)

    def test_first_flip_reveals_card(self):
        g = memory.new_game()
        memory.flip(g, 0)
        self.assertEqual(g["cards"][0]["state"], "revealed")
        self.assertEqual(g["flipped"], [0])
        self.assertFalse(g["mismatch"])
        self.assertEqual(g["moves"], 0)

    def test_second_flip_matching_marks_matched(self):
        g = memory.new_game()
        # Find a pair
        emoji = g["cards"][0]["emoji"]
        partner = next(i for i, c in enumerate(g["cards"]) if c["emoji"] == emoji and i != 0)
        memory.flip(g, 0)
        memory.flip(g, partner)
        self.assertEqual(g["cards"][0]["state"], "matched")
        self.assertEqual(g["cards"][partner]["state"], "matched")
        self.assertEqual(g["matched"], 1)
        self.assertEqual(g["moves"], 1)
        self.assertFalse(g["mismatch"])
        self.assertEqual(g["flipped"], [])

    def test_second_flip_nonmatching_sets_mismatch(self):
        g = memory.new_game()
        # Find two cards with different emoji
        emoji0 = g["cards"][0]["emoji"]
        other = next(i for i, c in enumerate(g["cards"]) if c["emoji"] != emoji0)
        memory.flip(g, 0)
        memory.flip(g, other)
        self.assertTrue(g["mismatch"])
        self.assertEqual(g["moves"], 1)
        self.assertEqual(g["cards"][0]["state"], "revealed")
        self.assertEqual(g["cards"][other]["state"], "revealed")

    def test_flip_ignored_when_mismatch_active(self):
        g = memory.new_game()
        emoji0 = g["cards"][0]["emoji"]
        other = next(i for i, c in enumerate(g["cards"]) if c["emoji"] != emoji0)
        memory.flip(g, 0)
        memory.flip(g, other)
        self.assertTrue(g["mismatch"])
        third = next(i for i, c in enumerate(g["cards"]) if c["state"] == "hidden")
        memory.flip(g, third)
        self.assertEqual(g["cards"][third]["state"], "hidden")

    def test_flip_ignored_on_already_revealed_card(self):
        g = memory.new_game()
        memory.flip(g, 0)
        memory.flip(g, 0)  # flip same card again
        self.assertEqual(g["flipped"], [0])

    def test_clear_mismatch_hides_both_cards(self):
        g = memory.new_game()
        emoji0 = g["cards"][0]["emoji"]
        other = next(i for i, c in enumerate(g["cards"]) if c["emoji"] != emoji0)
        memory.flip(g, 0)
        memory.flip(g, other)
        memory.clear_mismatch(g)
        self.assertFalse(g["mismatch"])
        self.assertEqual(g["flipped"], [])
        self.assertEqual(g["cards"][0]["state"], "hidden")
        self.assertEqual(g["cards"][other]["state"], "hidden")

    def test_clear_mismatch_noop_when_no_mismatch(self):
        g = memory.new_game()
        memory.flip(g, 0)
        memory.clear_mismatch(g)  # no mismatch — should do nothing
        self.assertEqual(g["cards"][0]["state"], "revealed")

    def test_game_over_when_all_pairs_matched(self):
        g = memory.new_game()
        # Flip all matching pairs
        seen = set()
        for i, card in enumerate(g["cards"]):
            if i in seen:
                continue
            partner = next(j for j, c in enumerate(g["cards"]) if c["emoji"] == card["emoji"] and j != i)
            memory.flip(g, i)
            memory.flip(g, partner)
            seen.add(i)
            seen.add(partner)
        self.assertTrue(g["over"])
        self.assertEqual(g["matched"], 10)

    def test_game_state_hides_emoji_for_hidden_cards(self):
        g = memory.new_game()
        st = memory.game_state(g)
        self.assertTrue(all(c["emoji"] is None for c in st["cards"]))

    def test_game_state_reveals_emoji_for_non_hidden(self):
        g = memory.new_game()
        memory.flip(g, 0)
        st = memory.game_state(g)
        self.assertIsNotNone(st["cards"][0]["emoji"])

    def test_game_state_includes_expected_fields(self):
        st = memory.game_state(memory.new_game())
        for field in ("cards", "theme", "themes", "level", "levels", "matched", "moves", "mismatch", "over", "par"):
            self.assertIn(field, st)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class TestMemoryScoring(IsolatedScores):

    def _finished_game(self, name=None, moves=10):
        sess = server.new_session()
        sess["name"] = name
        g = memory.new_game()
        # Simulate a completed game
        for c in g["cards"]:
            c["state"] = "matched"
        g["matched"] = 10
        g["moves"]   = moves
        g["over"]    = True
        g["flipped"] = []
        g["mismatch"] = False
        sess["memory_game"] = g
        return sess

    def test_under_par_awards_player_point(self):
        sess = self._finished_game(moves=15)
        server.memory_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["memory"]["player"], 1)
        self.assertEqual(server.SCORES["Guest"]["memory"]["hangman"], 0)

    def test_at_par_awards_player_point(self):
        par = sess = self._finished_game(moves=memory.PAR["medium"])
        server.memory_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["memory"]["player"], 1)

    def test_over_par_awards_computer_point(self):
        sess = self._finished_game(moves=memory.PAR["medium"] + 1)
        server.memory_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["memory"]["hangman"], 1)
        self.assertEqual(server.SCORES["Guest"]["memory"]["player"], 0)

    def test_easy_par_is_higher(self):
        sess = self._finished_game(moves=28)
        sess["memory_game"]["level"] = "easy"
        sess["memory_game"]["par"]   = memory.PAR["easy"]
        server.memory_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["memory"]["player"], 1)

    def test_apply_score_fires_once(self):
        sess = self._finished_game(moves=10)
        server.memory_apply_score(sess)
        server.memory_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["memory"]["player"], 1)

    def test_not_over_does_not_score(self):
        sess = server.new_session()
        server.memory_apply_score(sess)
        self.assertNotIn("memory", server.SCORES.get("Guest", {}))

    def test_guest_score_written_to_db(self):
        sess = self._finished_game(moves=10)
        server.memory_apply_score(sess)
        loaded = server.load_scores()
        self.assertIn("Guest", loaded)
        self.assertEqual(loaded["Guest"]["memory"]["player"], 1)

    def test_named_score_persists(self):
        sess = self._finished_game(name="Ada", moves=10)
        server.memory_apply_score(sess)
        self.assertEqual(server.SCORES["Ada"]["memory"]["player"], 1)
        self.assertEqual(server.load_scores()["Ada"]["memory"]["player"], 1)


# ---------------------------------------------------------------------------
# End-to-end API
# ---------------------------------------------------------------------------

class TestMemoryApi(IsolatedScores):

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
        st = self.client().call("/memory/state")
        for f in ("cards", "theme", "themes", "level", "levels", "matched", "moves",
                  "mismatch", "over", "par", "score", "total_score", "names"):
            self.assertIn(f, st)

    def test_initial_board_has_20_hidden_cards(self):
        st = self.client().call("/memory/state")
        self.assertEqual(len(st["cards"]), 20)
        self.assertTrue(all(c["state"] == "hidden" for c in st["cards"]))

    def test_flip_reveals_a_card(self):
        c = self.client()
        st = c.call("/memory/flip", {"index": 0})
        self.assertEqual(st["cards"][0]["state"], "revealed")
        self.assertIsNotNone(st["cards"][0]["emoji"])

    def test_matching_pair_marks_matched(self):
        c = self.client()
        c.call("/memory/state")
        g = server.SESSIONS[c.sid()]["memory_game"]
        emoji = g["cards"][0]["emoji"]
        partner = next(i for i, card in enumerate(g["cards"]) if card["emoji"] == emoji and i != 0)
        c.call("/memory/flip", {"index": 0})
        st = c.call("/memory/flip", {"index": partner})
        self.assertEqual(st["matched"], 1)
        self.assertFalse(st["mismatch"])

    def test_mismatch_sets_flag(self):
        c = self.client()
        c.call("/memory/state")
        g = server.SESSIONS[c.sid()]["memory_game"]
        emoji0 = g["cards"][0]["emoji"]
        other = next(i for i, card in enumerate(g["cards"]) if card["emoji"] != emoji0)
        c.call("/memory/flip", {"index": 0})
        st = c.call("/memory/flip", {"index": other})
        self.assertTrue(st["mismatch"])

    def test_clear_resets_mismatch(self):
        c = self.client()
        c.call("/memory/state")
        g = server.SESSIONS[c.sid()]["memory_game"]
        emoji0 = g["cards"][0]["emoji"]
        other = next(i for i, card in enumerate(g["cards"]) if card["emoji"] != emoji0)
        c.call("/memory/flip", {"index": 0})
        c.call("/memory/flip", {"index": other})
        st = c.call("/memory/clear", {})
        self.assertFalse(st["mismatch"])
        self.assertEqual(st["cards"][0]["state"], "hidden")

    def test_new_game_resets_board(self):
        c = self.client()
        c.call("/memory/flip", {"index": 0})
        st = c.call("/memory/new", {})
        self.assertEqual(st["moves"], 0)
        self.assertEqual(st["matched"], 0)
        self.assertTrue(all(card["state"] == "hidden" for card in st["cards"]))

    def test_new_game_with_zoo_theme(self):
        c = self.client()
        st = c.call("/memory/new", {"theme": "zoo"})
        self.assertEqual(st["theme"], "zoo")

    def test_theme_toggle_starts_new_game(self):
        c = self.client()
        c.call("/memory/flip", {"index": 0})
        st = c.call("/memory/new", {"theme": "zoo"})
        self.assertEqual(st["theme"], "zoo")
        self.assertEqual(st["moves"], 0)

    def test_level_toggle_changes_par(self):
        c = self.client()
        st = c.call("/memory/new", {"level": "easy"})
        self.assertEqual(st["level"], "easy")
        self.assertEqual(st["par"], memory.PAR["easy"])
        st = c.call("/memory/new", {"level": "hard"})
        self.assertEqual(st["level"], "hard")
        self.assertEqual(st["par"], memory.PAR["hard"])

    def test_score_increments_on_win(self):
        c = self.client()
        c.call("/memory/state")
        g = server.SESSIONS[c.sid()]["memory_game"]
        # Force all cards matched under par
        for card in g["cards"]:
            card["state"] = "matched"
        g["matched"] = 10
        g["moves"]   = 5
        g["over"]    = True
        g["flipped"] = []
        g["mismatch"] = False
        st = c.call("/memory/state")
        self.assertEqual(st["score"]["player"], 1)

    def test_two_clients_are_independent(self):
        a, b = self.client(), self.client()
        a.call("/memory/flip", {"index": 0})
        st_b = b.call("/memory/state")
        self.assertEqual(st_b["cards"][0]["state"], "hidden")


if __name__ == "__main__":
    unittest.main(verbosity=2)
