"""Tests for Matchstick Equation — standard library only, no deps.

Three groups:
  * TestMatchstickGameLogic — pure matchstick.py helpers. No server.
  * TestMatchstickScoring   — scoring functions + persistence. No network.
  * TestMatchstickApi       — end-to-end HTTP with cookie-backed sessions.
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
import matchstick as ms


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


def find_fix(slots):
    """Brute-force search for a single stick-move that makes the equation true."""
    positions = ms._moveable_positions(slots)
    for si, sseg in positions:
        if sseg not in slots[si]["segments"]:
            continue
        for di, dseg in positions:
            if si == di and sseg == dseg:
                continue
            if dseg in slots[di]["segments"]:
                continue
            trial = [dict(s) for s in slots]
            src_new = set(slots[si]["segments"])
            src_new.discard(sseg)
            dst_new = set(slots[di]["segments"] if di != si else src_new)
            dst_new.add(dseg)
            trial[si] = {**slots[si], "segments": src_new}
            trial[di] = {**trial[di], "segments": dst_new}
            if ms._equation_true(trial):
                return (si, sseg, di, dseg)
    return None


# ---------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------

class TestMatchstickGameLogic(unittest.TestCase):

    def test_digit_segment_counts_match_real_matchsticks(self):
        expected = {"0": 6, "1": 2, "2": 5, "3": 5, "4": 4,
                    "5": 5, "6": 6, "7": 3, "8": 7, "9": 6}
        for digit, count in expected.items():
            self.assertEqual(len(ms.DIGIT_SEGMENTS[digit]), count)

    def test_new_game_defaults(self):
        g = ms.new_game()
        self.assertEqual(g["level"], ms.DEFAULT_LEVEL)
        self.assertEqual(g["par_moves"], 1)
        self.assertEqual(g["moves_used"], 0)
        self.assertFalse(g["over"])
        self.assertFalse(g["won"])
        self.assertFalse(g["scored"])

    def test_new_game_invalid_level_falls_back(self):
        g = ms.new_game("impossible")
        self.assertEqual(g["level"], ms.DEFAULT_LEVEL)

    def test_generated_puzzles_start_false_and_have_a_fix(self):
        for level in ms.LEVELS:
            for _ in range(15):
                g = ms.new_game(level)
                self.assertFalse(ms._equation_true(g["slots"]))
                self.assertIsNotNone(find_fix(g["slots"]))

    def test_move_stick_basic_pickup_and_place(self):
        g = ms.new_game("easy")
        positions = ms._moveable_positions(g["slots"])
        lit = [(i, s) for i, s in positions if s in g["slots"][i]["segments"]]
        unlit = [(i, s) for i, s in positions if s not in g["slots"][i]["segments"]]
        si, sseg = lit[0]
        di, dseg = unlit[0]
        ms.move_stick(g, si, sseg, di, dseg)
        self.assertNotIn(sseg, g["slots"][si]["segments"])
        self.assertIn(dseg, g["slots"][di]["segments"])
        self.assertEqual(g["moves_used"], 1)

    def test_move_stick_same_slot_reshape(self):
        # 0 = {a,b,c,d,e,f}; moving e -> g turns it into 9 = {a,b,c,d,f,g}.
        g = ms.new_game("easy")
        g["slots"][0] = {"kind": "digit", "segments": set("abcdef")}
        ms.move_stick(g, 0, "e", 0, "g")
        self.assertEqual(g["slots"][0]["segments"], set("abcdfg"))
        self.assertEqual(ms._decode_slot(g["slots"][0]), "9")

    def test_move_stick_invalid_segment_key_ignored(self):
        g = ms.new_game("easy")
        before = g["moves_used"]
        ms.move_stick(g, 0, "z", 1, "a")
        self.assertEqual(g["moves_used"], before)

    def test_move_stick_into_equals_slot_ignored(self):
        g = ms.new_game("easy")
        equals_idx = next(i for i, s in enumerate(g["slots"]) if s["kind"] == "equals")
        digit_idx = next(i for i, s in enumerate(g["slots"]) if s["kind"] == "digit")
        lit_seg = next(iter(g["slots"][digit_idx]["segments"]))
        before = g["moves_used"]
        ms.move_stick(g, digit_idx, lit_seg, equals_idx, "a")
        self.assertEqual(g["moves_used"], before)

    def test_move_stick_onto_already_lit_destination_ignored(self):
        g = ms.new_game("easy")
        d1 = next(i for i, s in enumerate(g["slots"]) if s["kind"] == "digit")
        d2 = next(i for i, s in enumerate(g["slots"]) if s["kind"] == "digit" and i != d1)
        seg1 = next(iter(g["slots"][d1]["segments"]))
        seg2 = next(iter(g["slots"][d2]["segments"]))
        before = g["moves_used"]
        ms.move_stick(g, d1, seg1, d2, seg2)  # seg2 already lit at d2
        self.assertEqual(g["moves_used"], before)

    def test_move_stick_noop_after_over(self):
        g = ms.new_game("easy")
        fix = find_fix(g["slots"])
        ms.move_stick(g, *fix)
        self.assertTrue(g["over"])
        moves_at_win = g["moves_used"]
        ms.move_stick(g, 0, "a", 1, "b")
        self.assertEqual(g["moves_used"], moves_at_win)

    def test_solving_sets_won_and_over(self):
        g = ms.new_game("medium")
        fix = find_fix(g["slots"])
        ms.move_stick(g, *fix)
        self.assertTrue(g["over"])
        self.assertTrue(g["won"])
        self.assertEqual(g["moves_used"], 1)

    def test_reset_restores_original_slots_and_zeroes_moves(self):
        g = ms.new_game("easy")
        # Make a few moves without necessarily solving it.
        positions = ms._moveable_positions(g["slots"])
        lit = [(i, s) for i, s in positions if s in g["slots"][i]["segments"]]
        unlit = [(i, s) for i, s in positions if s not in g["slots"][i]["segments"]]
        ms.move_stick(g, lit[0][0], lit[0][1], unlit[0][0], unlit[0][1])
        self.assertGreater(g["moves_used"], 0)

        ms.reset_puzzle(g)
        self.assertEqual(g["moves_used"], 0)
        self.assertFalse(g["over"])
        self.assertFalse(g["won"])
        self.assertEqual(g["slots"], g["original_slots"])

    def test_reset_after_solving_allows_resolving_same_puzzle(self):
        g = ms.new_game("easy")
        fix = find_fix(g["slots"])
        ms.move_stick(g, *fix)
        self.assertTrue(g["over"])

        ms.reset_puzzle(g)
        self.assertFalse(g["over"])
        self.assertFalse(ms._equation_true(g["slots"]))

        ms.move_stick(g, *fix)
        self.assertTrue(g["over"])
        self.assertTrue(g["won"])
        self.assertEqual(g["moves_used"], 1)

    def test_reset_does_not_mutate_original_slots(self):
        g = ms.new_game("easy")
        fix = find_fix(g["slots"])
        ms.move_stick(g, *fix)
        snapshot = ms._copy_slots(g["original_slots"])
        ms.reset_puzzle(g)
        ms.move_stick(g, *fix)  # solve it again after reset
        self.assertEqual(g["original_slots"], snapshot)

    def test_reset_does_not_reopen_scoring(self):
        # A puzzle that's already been scored shouldn't score again after
        # being reset and re-solved (no point-farming via reset).
        g = ms.new_game("easy")
        fix = find_fix(g["slots"])
        ms.move_stick(g, *fix)
        g["scored"] = True  # simulate PopPopsGames.ms_apply_score having run
        ms.reset_puzzle(g)
        self.assertTrue(g["scored"])
        ms.move_stick(g, *fix)
        self.assertTrue(g["over"])
        self.assertTrue(g["scored"])  # still true — apply_score would no-op

    def test_give_up_reveals_and_sets_over_without_winning(self):
        g = ms.new_game("easy")
        ms.give_up(g)
        self.assertTrue(g["over"])
        self.assertFalse(g["won"])
        self.assertTrue(g["gave_up"])
        self.assertEqual(g["moves_used"], 0)
        self.assertEqual(g["slots"], g["original_slots"])

    def test_give_up_locks_further_moves(self):
        g = ms.new_game("easy")
        ms.give_up(g)
        before = ms._copy_slots(g["slots"])
        ms.move_stick(g, *g["solution"][0])
        self.assertEqual(g["slots"], before)

    def test_give_up_exposes_solution_in_game_state(self):
        g = ms.new_game("medium")
        ms.give_up(g)
        st = ms.game_state(g)
        self.assertTrue(st["gave_up"])
        self.assertIsNotNone(st["original_slots"])
        self.assertIsNotNone(st["solution"])

    def test_reset_after_give_up_clears_gave_up(self):
        g = ms.new_game("easy")
        ms.give_up(g)
        ms.reset_puzzle(g)
        self.assertFalse(g["gave_up"])
        self.assertFalse(g["over"])

    def test_game_state_includes_expected_fields(self):
        st = ms.game_state(ms.new_game())
        for field in ("slots", "moves_used", "par_moves", "over", "won", "level",
                      "levels", "original_slots", "solution"):
            self.assertIn(field, st)

    def test_solution_and_original_hidden_before_over(self):
        st = ms.game_state(ms.new_game())
        self.assertIsNone(st["original_slots"])
        self.assertIsNone(st["solution"])

    def test_solution_and_original_revealed_after_over(self):
        g = ms.new_game("easy")
        fix = find_fix(g["slots"])
        ms.move_stick(g, *fix)
        st = ms.game_state(g)
        self.assertIsNotNone(st["original_slots"])
        self.assertIsNotNone(st["solution"])

    def test_stored_solution_actually_solves_the_original(self):
        for level in ms.LEVELS:
            for _ in range(10):
                g = ms.new_game(level)
                self.assertEqual(len(g["solution"]), 1)
                trial = ms._copy_slots(g["slots"])
                fi, fs, ti, ts = g["solution"][0]
                trial[fi]["segments"].discard(fs)
                trial[ti]["segments"].add(ts)
                self.assertTrue(ms._equation_true(trial))

    def test_original_slots_unaffected_by_gameplay(self):
        g = ms.new_game("easy")
        snapshot = ms._copy_slots(g["original_slots"])
        fix = find_fix(g["slots"])
        ms.move_stick(g, *fix)
        self.assertEqual(g["original_slots"], snapshot)


# ---------------------------------------------------------------------------
# "Solve One For Me" — minimum-moves solver
# ---------------------------------------------------------------------------

def apply_moves(slots, moves):
    trial = ms._copy_slots(slots)
    for fi, fs, ti, ts in moves:
        trial[fi]["segments"].discard(fs)
        trial[ti]["segments"].add(ts)
    return trial


class TestMatchstickSolver(unittest.TestCase):

    def test_parse_valid_equation_variants(self):
        for text in ("3-3=1", "3 - 3 = 1", "  3-3=1  ", "3- 3 =1"):
            self.assertEqual(ms.parse_custom_equation(text), ("3", "-", "3", "1"))

    def test_parse_preserves_leading_zeros(self):
        self.assertEqual(ms.parse_custom_equation("03-3=1"), ("03", "-", "3", "1"))

    def test_parse_rejects_bad_format(self):
        for text in ("", "hello", "3+3", "3+3+3=9", "3*3=9", "3 - = 1", "-3+3=0"):
            with self.assertRaises(ValueError):
                ms.parse_custom_equation(text)

    def test_parse_rejects_too_many_digits(self):
        with self.assertRaises(ValueError):
            ms.parse_custom_equation("1234-1=1233")

    def test_solve_already_correct_needs_zero_moves(self):
        original_slots, moves, moves_needed = ms.solve_custom_equation("6+4=10")
        self.assertEqual(moves_needed, 0)
        self.assertEqual(moves, [])

    def test_solve_known_case_needs_one_move(self):
        # 3-3=1 is false; turning the second '3' into '2' (3-2=1) is a single
        # stick move and no cheaper fix exists (0 moves is impossible since
        # 3-3=1 is false as written).
        original_slots, moves, moves_needed = ms.solve_custom_equation("3 - 3 = 1")
        self.assertEqual(moves_needed, 1)
        self.assertEqual(len(moves), 1)
        self.assertTrue(ms._equation_true(apply_moves(original_slots, moves)))

    def test_solve_result_actually_solves_equation(self):
        for text in ("3-3=1", "8-3=1", "1+1=3", "9-1=1", "2+2=5"):
            result = ms.solve_custom_equation(text)
            self.assertIsNotNone(result, text)
            original_slots, moves, moves_needed = result
            self.assertEqual(len(moves), moves_needed)
            solved = apply_moves(original_slots, moves)
            self.assertTrue(ms._equation_true(solved), f"{text} -> moves {moves} did not solve it")

    def test_solve_moves_needed_matches_move_list_length(self):
        for text in ("12-7=3", "45+10=99", "7-7=7"):
            original_slots, moves, moves_needed = ms.solve_custom_equation(text)
            self.assertEqual(len(moves), moves_needed)

    def test_solve_preserves_total_stick_budget(self):
        original_slots, moves, moves_needed = ms.solve_custom_equation("3-3=1")
        solved = apply_moves(original_slots, moves)
        self.assertEqual(len(ms._segment_set(original_slots)), len(ms._segment_set(solved)))

    def test_solve_can_flip_operator(self):
        # "1-2=9" is false; the cheapest fix (verified empirically) flips the
        # operator to '+' and changes the result's '9' to '3' (1-2=9 -> 1+2=3)
        # — exactly one stick moves from the result's extra segment into the
        # operator's missing one.
        original_slots, moves, moves_needed = ms.solve_custom_equation("1-2=9")
        self.assertEqual(moves_needed, 1)
        solved = apply_moves(original_slots, moves)
        self.assertTrue(ms._equation_true(solved))
        chars = [ms._decode_slot(s) for s in solved]
        self.assertEqual("".join(chars), "1+2=3")


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class TestMatchstickScoring(IsolatedScores):

    def _finished_session(self, name=None, level="easy", moves_used=1):
        sess = server.new_session()
        sess["name"] = name
        g = ms.new_game(level)
        g["over"] = True
        g["won"] = True
        g["moves_used"] = moves_used
        sess["ms_game"] = g
        return sess

    def test_par_move_awards_level_points(self):
        sess = self._finished_session(level="hard", moves_used=1)
        server.ms_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["matchstick"]["player"], ms.LEVEL_POINTS["hard"])
        self.assertEqual(server.SCORES["Guest"]["matchstick"]["hangman"], 0)

    def test_over_par_awards_computer_point(self):
        sess = self._finished_session(moves_used=3)
        server.ms_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["matchstick"]["hangman"], 1)
        self.assertEqual(server.SCORES["Guest"]["matchstick"]["player"], 0)

    def test_apply_score_fires_once(self):
        sess = self._finished_session(level="medium", moves_used=1)
        server.ms_apply_score(sess)
        server.ms_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["matchstick"]["player"], ms.LEVEL_POINTS["medium"])

    def test_not_over_does_not_score(self):
        sess = server.new_session()
        server.ms_apply_score(sess)
        self.assertNotIn("matchstick", server.SCORES.get("Guest", {}))

    def test_guest_score_written_to_db(self):
        sess = self._finished_session(level="easy", moves_used=1)
        server.ms_apply_score(sess)
        loaded = server.load_scores()
        self.assertIn("Guest", loaded)
        self.assertEqual(loaded["Guest"]["matchstick"]["player"], ms.LEVEL_POINTS["easy"])

    def test_named_score_persists(self):
        sess = self._finished_session(name="Nia", level="hard", moves_used=1)
        server.ms_apply_score(sess)
        self.assertEqual(server.load_scores()["Nia"]["matchstick"]["player"], ms.LEVEL_POINTS["hard"])

    def test_give_up_always_awards_computer_point(self):
        sess = server.new_session()
        ms.give_up(sess["ms_game"])
        server.ms_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["matchstick"]["hangman"], 1)
        self.assertEqual(server.SCORES["Guest"]["matchstick"]["player"], 0)

    def test_give_up_then_replaying_solution_does_not_score_again(self):
        # The anti-exploit case: give up (scores as a loss), then manually
        # replay the exact revealed solution — this must NOT also earn a
        # player point, since `scored` is already set from the give-up.
        sess = server.new_session()
        game = sess["ms_game"]
        ms.give_up(game)
        server.ms_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["matchstick"]["hangman"], 1)

        solution = game["solution"]
        ms.reset_puzzle(game)  # gave_up cleared, but scored stays True
        for fi, fs, ti, ts in solution:
            ms.move_stick(game, fi, fs, ti, ts)
        self.assertTrue(game["over"])
        self.assertTrue(game["won"])
        server.ms_apply_score(sess)  # should no-op: already scored
        self.assertEqual(server.SCORES["Guest"]["matchstick"]["player"], 0)
        self.assertEqual(server.SCORES["Guest"]["matchstick"]["hangman"], 1)


# ---------------------------------------------------------------------------
# End-to-end API
# ---------------------------------------------------------------------------

class TestMatchstickApi(IsolatedScores):

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
        st = self.client().call("/matchstick/state")
        for f in ("slots", "moves_used", "par_moves", "over", "won",
                  "level", "levels", "score", "total_score", "names"):
            self.assertIn(f, st)

    def test_new_game_resets(self):
        c = self.client()
        st = c.call("/matchstick/new", {"level": "hard"})
        self.assertEqual(st["level"], "hard")
        self.assertEqual(st["moves_used"], 0)
        self.assertFalse(st["over"])

    def test_new_without_level_keeps_current_level(self):
        c = self.client()
        c.call("/matchstick/new", {"level": "hard"})
        self.assertEqual(c.call("/matchstick/new", {})["level"], "hard")

    def test_move_via_api_changes_state(self):
        c = self.client()
        c.call("/matchstick/new", {"level": "easy"})
        game = server.SESSIONS[c.sid()]["ms_game"]
        positions = ms._moveable_positions(game["slots"])
        si, sseg = next((i, s) for i, s in positions if s in game["slots"][i]["segments"])
        di, dseg = next((i, s) for i, s in positions if s not in game["slots"][i]["segments"])
        st = c.call("/matchstick/move", {"from_index": si, "from_seg": sseg, "to_index": di, "to_seg": dseg})
        self.assertNotIn(sseg, st["slots"][si]["segments"])
        self.assertIn(dseg, st["slots"][di]["segments"])

    def test_reset_via_api_restores_original_and_zeroes_moves(self):
        c = self.client()
        st = c.call("/matchstick/new", {"level": "easy"})
        original_slots_snapshot = server.SESSIONS[c.sid()]["ms_game"]["original_slots"]
        positions = ms._moveable_positions(server.SESSIONS[c.sid()]["ms_game"]["slots"])
        game = server.SESSIONS[c.sid()]["ms_game"]
        si, sseg = next((i, s) for i, s in positions if s in game["slots"][i]["segments"])
        di, dseg = next((i, s) for i, s in positions if s not in game["slots"][i]["segments"])
        c.call("/matchstick/move", {"from_index": si, "from_seg": sseg, "to_index": di, "to_seg": dseg})

        st = c.call("/matchstick/reset", {})
        self.assertEqual(st["moves_used"], 0)
        self.assertFalse(st["over"])
        self.assertEqual(server.SESSIONS[c.sid()]["ms_game"]["slots"], original_slots_snapshot)

    def test_reset_then_resolve_scores_only_once(self):
        c = self.client()
        c.call("/matchstick/new", {"level": "easy"})
        game = server.SESSIONS[c.sid()]["ms_game"]
        fix = find_fix(game["slots"])
        si, sseg, di, dseg = fix
        c.call("/matchstick/move", {"from_index": si, "from_seg": sseg, "to_index": di, "to_seg": dseg})
        self.assertEqual(server.SCORES["Guest"]["matchstick"]["player"], ms.LEVEL_POINTS["easy"])

        c.call("/matchstick/reset", {})
        st = c.call("/matchstick/move", {"from_index": si, "from_seg": sseg, "to_index": di, "to_seg": dseg})
        self.assertTrue(st["over"])
        # Score unchanged — resetting and resolving the same puzzle doesn't score again.
        self.assertEqual(server.SCORES["Guest"]["matchstick"]["player"], ms.LEVEL_POINTS["easy"])

    def test_solving_within_par_scores_player(self):
        c = self.client()
        c.call("/matchstick/new", {"level": "easy"})
        game = server.SESSIONS[c.sid()]["ms_game"]
        fix = find_fix(game["slots"])
        self.assertIsNotNone(fix)
        si, sseg, di, dseg = fix
        st = c.call("/matchstick/move", {"from_index": si, "from_seg": sseg, "to_index": di, "to_seg": dseg})
        self.assertTrue(st["over"])
        self.assertTrue(st["won"])
        self.assertEqual(st["score"]["player"], ms.LEVEL_POINTS["easy"])
        self.assertEqual(st["score"]["hangman"], 0)

    def test_show_me_data_hidden_until_solved_then_revealed(self):
        c = self.client()
        st = c.call("/matchstick/new", {"level": "easy"})
        self.assertIsNone(st["original_slots"])
        self.assertIsNone(st["solution"])

        game = server.SESSIONS[c.sid()]["ms_game"]
        fix = find_fix(game["slots"])
        si, sseg, di, dseg = fix
        st = c.call("/matchstick/move", {"from_index": si, "from_seg": sseg, "to_index": di, "to_seg": dseg})
        self.assertIsNotNone(st["original_slots"])
        self.assertIsNotNone(st["solution"])
        self.assertEqual(len(st["solution"]), 1)
        for key in ("from_index", "from_seg", "to_index", "to_seg"):
            self.assertIn(key, st["solution"][0])

    def test_solve_endpoint_success(self):
        c = self.client()
        data = c.call("/matchstick/solve", {"equation": "3 - 3 = 1"})
        self.assertTrue(data["ok"])
        self.assertEqual(data["moves_needed"], 1)
        self.assertEqual(len(data["solution"]), 1)
        self.assertIsNotNone(data["original_slots"])

    def test_solve_endpoint_already_correct(self):
        c = self.client()
        data = c.call("/matchstick/solve", {"equation": "6+4=10"})
        self.assertTrue(data["ok"])
        self.assertEqual(data["moves_needed"], 0)
        self.assertEqual(data["solution"], [])

    def test_solve_endpoint_bad_input(self):
        c = self.client()
        data = c.call("/matchstick/solve", {"equation": "not an equation"})
        self.assertFalse(data["ok"])
        self.assertIn("error", data)

    def test_solve_endpoint_does_not_touch_current_game(self):
        c = self.client()
        st_before = c.call("/matchstick/new", {"level": "easy"})
        c.call("/matchstick/solve", {"equation": "3-3=1"})
        st_after = c.call("/matchstick/state")
        self.assertEqual(st_before["slots"], st_after["slots"])
        self.assertEqual(st_after["moves_used"], 0)

    def test_give_up_via_api_reveals_solution_and_scores_computer(self):
        c = self.client()
        c.call("/matchstick/new", {"level": "easy"})
        st = c.call("/matchstick/give_up", {})
        self.assertTrue(st["over"])
        self.assertFalse(st["won"])
        self.assertTrue(st["gave_up"])
        self.assertIsNotNone(st["original_slots"])
        self.assertIsNotNone(st["solution"])
        self.assertEqual(st["score"]["hangman"], 1)
        self.assertEqual(st["score"]["player"], 0)

    def test_give_up_then_reset_clears_gave_up_flag(self):
        c = self.client()
        c.call("/matchstick/new", {"level": "easy"})
        c.call("/matchstick/give_up", {})
        st = c.call("/matchstick/reset", {})
        self.assertFalse(st["gave_up"])
        self.assertFalse(st["over"])

    def test_sessions_are_independent(self):
        a, b = self.client(), self.client()
        a.call("/matchstick/new", {"level": "hard"})
        self.assertEqual(b.call("/matchstick/state")["level"], ms.DEFAULT_LEVEL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
