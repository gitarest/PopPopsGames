"""Tests for Blackjack — standard library only, no deps.

Three groups:
  * TestBJGameLogic  — pure blackjack.py helpers. No server.
  * TestBJScoring    — scoring functions + persistence. No network.
  * TestBJApi        — end-to-end HTTP with cookie-backed sessions.
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
import blackjack


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

class TestBJGameLogic(unittest.TestCase):

    def test_new_deck_has_52_cards(self):
        g = blackjack.new_game()
        # Fresh game with no hands dealt yet
        self.assertEqual(len(g["deck"]), 52)

    def test_new_game_phase_is_deal(self):
        g = blackjack.new_game()
        self.assertEqual(g["phase"], "deal")
        self.assertFalse(g["over"])

    def test_deal_removes_4_cards(self):
        g = blackjack.new_game()
        blackjack.deal(g)
        self.assertEqual(len(g["deck"]), 48)
        self.assertEqual(len(g["player_hand"]), 2)
        self.assertEqual(len(g["dealer_hand"]), 2)

    def test_deal_phase_player_when_no_blackjack(self):
        g = blackjack.new_game()
        # Force no blackjack by making sure the hand can't be 21
        # (inject a known deck — hardest to guarantee, so we just test statistically)
        # Instead: set a known hand
        g["deck"] = [{"rank": "2", "suit": "♠"}] * 52
        blackjack.deal(g)
        self.assertEqual(g["phase"], "player")

    def test_deal_transitions_to_deck_over_when_deck_too_small(self):
        g = blackjack.new_game()
        g["deck"] = [{"rank": "2", "suit": "♠"}] * 3
        blackjack.deal(g)
        self.assertEqual(g["phase"], "deck_over")
        self.assertTrue(g["over"])

    def test_hit_adds_card(self):
        g = blackjack.new_game()
        g["deck"] = [{"rank": "5", "suit": "♥"}] * 10
        blackjack.deal(g)
        before = len(g["player_hand"])
        blackjack.hit(g)
        self.assertEqual(len(g["player_hand"]), before + 1)

    def test_hit_bust_ends_round(self):
        g = blackjack.new_game()
        g["phase"] = "player"
        g["player_hand"] = [{"rank": "K", "suit": "♠"}, {"rank": "K", "suit": "♥"}]
        g["dealer_hand"] = [{"rank": "5", "suit": "♠"}, {"rank": "6", "suit": "♣"}]
        g["deck"] = [{"rank": "5", "suit": "♦"}]
        blackjack.hit(g)
        self.assertEqual(g["phase"], "round_over")
        self.assertEqual(g["round_result"], "player_bust")
        self.assertEqual(g["computer_wins"], 1)

    def test_hit_to_21_auto_stands(self):
        g = blackjack.new_game()
        g["phase"] = "player"
        g["player_hand"] = [{"rank": "K", "suit": "♠"}, {"rank": "5", "suit": "♥"}]  # 15
        g["dealer_hand"] = [{"rank": "K", "suit": "♦"}, {"rank": "7", "suit": "♣"}]  # 17
        g["deck"] = [{"rank": "6", "suit": "♦"}]  # player hits to 21
        blackjack.hit(g)
        self.assertEqual(g["phase"], "round_over")
        self.assertEqual(g["round_result"], "player_higher")  # 21 beats 17

    def test_hit_ignored_when_not_player_phase(self):
        g = blackjack.new_game()
        g["phase"] = "round_over"
        g["player_hand"] = [{"rank": "5", "suit": "♠"}]
        g["deck"] = [{"rank": "2", "suit": "♥"}]
        blackjack.hit(g)
        self.assertEqual(len(g["player_hand"]), 1)

    def test_stand_dealer_plays_to_17(self):
        g = blackjack.new_game()
        g["phase"] = "player"
        g["player_hand"] = [{"rank": "K", "suit": "♠"}, {"rank": "8", "suit": "♥"}]  # 18
        g["dealer_hand"] = [{"rank": "6", "suit": "♠"}, {"rank": "7", "suit": "♣"}]  # 13 → must hit
        g["deck"] = [{"rank": "4", "suit": "♦"}]  # dealer draws to 17
        blackjack.stand(g)
        self.assertEqual(g["phase"], "round_over")
        from blackjack import _hand_value
        self.assertGreaterEqual(_hand_value(g["dealer_hand"]), 17)

    def test_stand_player_higher_wins(self):
        g = blackjack.new_game()
        g["phase"] = "player"
        g["player_hand"] = [{"rank": "K", "suit": "♠"}, {"rank": "9", "suit": "♥"}]  # 19
        g["dealer_hand"] = [{"rank": "K", "suit": "♦"}, {"rank": "8", "suit": "♣"}]  # 18
        g["deck"] = []
        blackjack.stand(g)
        self.assertEqual(g["round_result"], "player_higher")
        self.assertEqual(g["player_wins"], 1)

    def test_stand_dealer_bust_player_wins(self):
        g = blackjack.new_game()
        g["phase"] = "player"
        g["player_hand"] = [{"rank": "8", "suit": "♠"}, {"rank": "7", "suit": "♥"}]  # 15
        g["dealer_hand"] = [{"rank": "K", "suit": "♦"}, {"rank": "6", "suit": "♣"}]  # 16
        g["deck"] = [{"rank": "K", "suit": "♠"}]  # dealer draws, 26 = bust
        blackjack.stand(g)
        self.assertEqual(g["round_result"], "dealer_bust")
        self.assertEqual(g["player_wins"], 1)

    def test_stand_push(self):
        g = blackjack.new_game()
        g["phase"] = "player"
        g["player_hand"] = [{"rank": "K", "suit": "♠"}, {"rank": "8", "suit": "♥"}]  # 18
        g["dealer_hand"] = [{"rank": "K", "suit": "♦"}, {"rank": "8", "suit": "♣"}]  # 18
        g["deck"] = []
        blackjack.stand(g)
        self.assertEqual(g["round_result"], "push")
        self.assertEqual(g["ties"], 1)

    def test_player_blackjack_on_deal(self):
        g = blackjack.new_game()
        g["deck"] = [
            {"rank": "2", "suit": "♠"},  # dealer card 2
            {"rank": "2", "suit": "♥"},  # dealer card 1
            {"rank": "K", "suit": "♦"},  # player card 2
            {"rank": "A", "suit": "♣"},  # player card 1
        ]
        blackjack.deal(g)
        self.assertEqual(g["round_result"], "player_blackjack")
        self.assertEqual(g["player_wins"], 1)
        self.assertEqual(g["phase"], "round_over")

    def test_ace_counts_as_1_to_avoid_bust(self):
        from blackjack import _hand_value
        hand = [{"rank": "A", "suit": "♠"}, {"rank": "K", "suit": "♥"}, {"rank": "5", "suit": "♦"}]
        self.assertEqual(_hand_value(hand), 16)  # A+K+5: 11+10+5=26 → A becomes 1 → 16

    def test_game_state_hides_dealer_hole_card_during_player_turn(self):
        g = blackjack.new_game()
        g["deck"] = [{"rank": "2", "suit": "♠"}] * 10
        blackjack.deal(g)
        if g["phase"] == "player":
            st = blackjack.game_state(g)
            self.assertEqual(st["dealer_hand"][1]["rank"], "?")
            self.assertIsNone(st["dealer_value"])

    def test_game_state_reveals_dealer_after_round_over(self):
        g = blackjack.new_game()
        g["phase"] = "round_over"
        g["player_hand"] = [{"rank": "K", "suit": "♠"}, {"rank": "8", "suit": "♥"}]
        g["dealer_hand"] = [{"rank": "5", "suit": "♦"}, {"rank": "Q", "suit": "♣"}]
        st = blackjack.game_state(g)
        self.assertEqual(st["dealer_hand"][1]["rank"], "Q")
        self.assertEqual(st["dealer_value"], 15)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class TestBJScoring(IsolatedScores):

    def _make_deck_over(self, name=None, player_wins=3, computer_wins=1):
        sess = server.new_session()
        sess["name"] = name
        g = blackjack.new_game()
        g["player_wins"]   = player_wins
        g["computer_wins"] = computer_wins
        g["phase"] = "deck_over"
        g["over"]  = True
        sess["bj_game"] = g
        return sess

    def test_player_wins_deck_scores_player(self):
        sess = self._make_deck_over(player_wins=4, computer_wins=2)
        server.bj_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["blackjack"]["player"], 1)
        self.assertEqual(server.SCORES["Guest"]["blackjack"]["hangman"], 0)

    def test_computer_wins_deck_scores_computer(self):
        sess = self._make_deck_over(player_wins=2, computer_wins=5)
        server.bj_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["blackjack"]["hangman"], 1)
        self.assertEqual(server.SCORES["Guest"]["blackjack"]["player"], 0)

    def test_tied_deck_scores_neither(self):
        sess = self._make_deck_over(player_wins=3, computer_wins=3)
        server.bj_apply_score(sess)
        score = server.SCORES["Guest"]["blackjack"]
        self.assertEqual(score["player"], 0)
        self.assertEqual(score["hangman"], 0)

    def test_apply_score_fires_once(self):
        sess = self._make_deck_over(player_wins=3, computer_wins=1)
        server.bj_apply_score(sess)
        server.bj_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["blackjack"]["player"], 1)

    def test_not_over_does_not_score(self):
        sess = server.new_session()
        g = blackjack.new_game()
        g["phase"] = "player"
        sess["bj_game"] = g
        server.bj_apply_score(sess)
        self.assertNotIn("blackjack", server.SCORES.get("Guest", {}))

    def test_named_player_score_persists(self):
        sess = self._make_deck_over(name="Kai", player_wins=4, computer_wins=1)
        server.bj_apply_score(sess)
        loaded = server.load_scores()
        self.assertEqual(loaded["Kai"]["blackjack"]["player"], 1)

    def test_guest_score_written_to_db(self):
        sess = self._make_deck_over(player_wins=3, computer_wins=1)
        server.bj_apply_score(sess)
        loaded = server.load_scores()
        self.assertIn("Guest", loaded)
        self.assertEqual(loaded["Guest"]["blackjack"]["player"], 1)


# ---------------------------------------------------------------------------
# End-to-end API
# ---------------------------------------------------------------------------

class TestBJApi(IsolatedScores):

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
        st = self.client().call("/blackjack/state")
        for f in ("player_hand", "dealer_hand", "player_value", "dealer_value",
                  "phase", "player_wins", "computer_wins", "ties",
                  "round_result", "cards_remaining", "over",
                  "score", "total_score", "names"):
            self.assertIn(f, st)

    def test_initial_state_is_player_or_round_over(self):
        st = self.client().call("/blackjack/state")
        self.assertIn(st["phase"], ("player", "round_over"))

    def test_new_deals_fresh_deck(self):
        c = self.client()
        c.call("/blackjack/state")
        st = c.call("/blackjack/new", {})
        # tally carries over intentionally — just verify a fresh 52-card deck was shuffled
        self.assertGreater(st["cards_remaining"], 44)
        self.assertIn(st["phase"], ("player", "round_over"))

    def test_hit_adds_card(self):
        c = self.client()
        c.call("/blackjack/new", {})
        g = server.SESSIONS[c.sid()]["bj_game"]
        g["phase"] = "player"
        before = len(g["player_hand"])
        g["deck"].append({"rank": "3", "suit": "♠"})
        st = c.call("/blackjack/hit", {})
        self.assertGreaterEqual(len(st["player_hand"]), before)

    def test_stand_transitions_to_round_over(self):
        c = self.client()
        c.call("/blackjack/new", {})
        g = server.SESSIONS[c.sid()]["bj_game"]
        g["phase"] = "player"
        g["player_hand"] = [{"rank": "K", "suit": "♠"}, {"rank": "9", "suit": "♥"}]
        g["dealer_hand"] = [{"rank": "6", "suit": "♦"}, {"rank": "7", "suit": "♣"}]
        g["deck"] = [{"rank": "4", "suit": "♠"}]  # dealer draws to 17
        st = c.call("/blackjack/stand", {})
        self.assertEqual(st["phase"], "round_over")
        self.assertIsNotNone(st["round_result"])

    def test_deal_next_hand(self):
        c = self.client()
        c.call("/blackjack/new", {})
        g = server.SESSIONS[c.sid()]["bj_game"]
        g["phase"]      = "round_over"
        g["round_result"] = "player_higher"
        g["player_wins"] = 1
        st = c.call("/blackjack/deal", {})
        self.assertIn(st["phase"], ("player", "round_over"))

    def test_score_increments_when_deck_exhausted(self):
        c = self.client()
        c.call("/blackjack/new", {})
        g = server.SESSIONS[c.sid()]["bj_game"]
        g["deck"]         = []
        g["player_wins"]  = 5
        g["computer_wins"] = 2
        g["phase"] = "deck_over"
        g["over"]  = True
        st = c.call("/blackjack/state")
        self.assertEqual(st["score"]["player"], 1)

    def test_two_clients_independent(self):
        a, b = self.client(), self.client()
        a.call("/blackjack/state")  # establish session
        ga = server.SESSIONS[a.sid()]["bj_game"]
        ga["player_wins"] = 10
        st_b = b.call("/blackjack/state")
        self.assertEqual(st_b["player_wins"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
