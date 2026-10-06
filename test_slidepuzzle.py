"""Tests for Slide Puzzle — standard library only, no deps.

Four groups:
  * TestSlidePuzzleGameLogic — pure slidepuzzle.py board helpers. No server.
  * TestSlidePuzzleImages    — per-player picture config + animal fallback.
  * TestSlidePuzzleScoring   — scoring functions + persistence. No network.
  * TestSlidePuzzleApi       — end-to-end HTTP with cookie-backed sessions.
"""

import http.cookiejar
import json
import os
import random
import shutil
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

import PopPopsGames as server
import slidepuzzle


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


class IsolatedImages(unittest.TestCase):
    """Point the picture config and images folder at a temp dir."""

    def setUp(self):
        super().setUp()
        self._tmp = tempfile.mkdtemp()
        self._orig = (slidepuzzle.CONFIG_FILE, slidepuzzle.IMAGES_DIR)
        slidepuzzle.IMAGES_DIR = os.path.join(self._tmp, "images")
        slidepuzzle.CONFIG_FILE = os.path.join(self._tmp, "config.json")
        os.makedirs(os.path.join(slidepuzzle.IMAGES_DIR, "players"))

    def tearDown(self):
        slidepuzzle.CONFIG_FILE, slidepuzzle.IMAGES_DIR = self._orig
        shutil.rmtree(self._tmp)
        super().tearDown()

    def add_image(self, rel):
        path = os.path.join(slidepuzzle.IMAGES_DIR, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"img")

    def write_config(self, players):
        with open(slidepuzzle.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"players": players}, f)


def solve_by_walk(game, path):
    """Undo a recorded random walk to bring a board back to solved."""
    for index in reversed(path):
        slidepuzzle.move(game, index)


def walked_game(level="easy", steps=30, seed=1):
    """A game shuffled by a known sequence of legal single-tile moves from
    solved, plus the blank positions needed to undo it."""
    rng = random.Random(seed)
    game = slidepuzzle.new_game(level)
    n = game["size"]
    game["tiles"] = list(range(n * n))
    undo = []
    prev = None
    for _ in range(steps):
        b = game["tiles"].index(n * n - 1)
        r, c = divmod(b, n)
        options = [i for i, ok in ((b - n, r > 0), (b + n, r < n - 1),
                                   (b - 1, c > 0), (b + 1, c < n - 1))
                   if ok and i != prev]
        pick = rng.choice(options)
        slidepuzzle.move(game, pick)
        undo.append(b)  # sliding the tile now at b back undoes this step
        prev = b
    if slidepuzzle.is_solved(game["tiles"]):
        return walked_game(level, steps, seed + 1)
    game["moves"] = 0
    return game, undo


# ---------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------

class TestSlidePuzzleGameLogic(unittest.TestCase):

    def test_new_game_defaults(self):
        g = slidepuzzle.new_game()
        self.assertEqual(g["level"], slidepuzzle.DEFAULT_LEVEL)
        self.assertEqual(g["size"], 3)
        self.assertEqual(g["moves"], 0)
        self.assertFalse(g["over"])
        self.assertFalse(g["won"])
        self.assertFalse(g["scored"])

    def test_invalid_level_falls_back(self):
        self.assertEqual(slidepuzzle.new_game("impossible")["level"], slidepuzzle.DEFAULT_LEVEL)

    def test_level_sizes(self):
        for level, size in slidepuzzle.LEVEL_SIZES.items():
            g = slidepuzzle.new_game(level)
            self.assertEqual(g["size"], size)
            self.assertEqual(sorted(g["tiles"]), list(range(size * size)))

    def test_new_boards_are_solvable_and_unsolved(self):
        for level, size in slidepuzzle.LEVEL_SIZES.items():
            for _ in range(200):
                tiles = slidepuzzle.new_game(level)["tiles"]
                self.assertTrue(slidepuzzle.is_solvable(tiles, size))
                self.assertFalse(slidepuzzle.is_solved(tiles))

    def test_solvability_rule_matches_reachable_boards(self):
        # Boards reached by legal moves are solvable; swapping two tiles of
        # such a board makes it unsolvable — for odd and even sizes.
        for level in slidepuzzle.LEVELS:
            for seed in range(20):
                g, _ = walked_game(level, steps=60, seed=seed)
                n = g["size"]
                self.assertTrue(slidepuzzle.is_solvable(g["tiles"], n))
                bad = list(g["tiles"])
                a, b = [i for i, t in enumerate(bad) if t != n * n - 1][:2]
                bad[a], bad[b] = bad[b], bad[a]
                self.assertFalse(slidepuzzle.is_solvable(bad, n))

    def test_adjacent_move_swaps_with_blank(self):
        g = slidepuzzle.new_game("easy")
        g["tiles"] = [0, 1, 2, 3, 4, 5, 6, 8, 7]   # blank at 7
        slidepuzzle.move(g, 8)
        self.assertEqual(g["tiles"], list(range(9)))
        self.assertEqual(g["moves"], 1)
        self.assertTrue(g["over"])
        self.assertTrue(g["won"])

    def test_non_line_move_is_ignored(self):
        g = slidepuzzle.new_game("easy")
        g["tiles"] = [8, 1, 2, 3, 4, 5, 6, 7, 0]   # blank at 0
        slidepuzzle.move(g, 4)                     # diagonal
        self.assertEqual(g["tiles"], [8, 1, 2, 3, 4, 5, 6, 7, 0])
        self.assertEqual(g["moves"], 0)

    def test_row_slide_moves_several_tiles(self):
        g = slidepuzzle.new_game("easy")
        g["tiles"] = [8, 0, 1, 2, 3, 4, 5, 6, 7]   # blank at 0
        slidepuzzle.move(g, 2)
        self.assertEqual(g["tiles"][:3], [0, 1, 8])
        self.assertEqual(g["moves"], 2)

    def test_column_slide_moves_several_tiles(self):
        g = slidepuzzle.new_game("easy")
        g["tiles"] = [0, 1, 8, 3, 4, 2, 6, 7, 5]   # blank at 2, col 2 = 8,2,5
        slidepuzzle.move(g, 8)
        self.assertEqual(g["tiles"], list(range(9)))
        self.assertEqual(g["moves"], 2)
        self.assertTrue(g["won"])

    def test_clicking_blank_or_out_of_range_is_ignored(self):
        g = slidepuzzle.new_game("easy")
        before = list(g["tiles"])
        slidepuzzle.move(g, g["tiles"].index(8))
        slidepuzzle.move(g, -1)
        slidepuzzle.move(g, 9)
        slidepuzzle.move(g, "3")
        self.assertEqual(g["tiles"], before)
        self.assertEqual(g["moves"], 0)

    def test_undoing_walk_solves(self):
        for level in slidepuzzle.LEVELS:
            g, undo = walked_game(level, steps=40)
            solve_by_walk(g, undo)
            self.assertTrue(g["won"], level)
            self.assertEqual(g["moves"], len(undo))

    def test_moves_ignored_after_win(self):
        g, undo = walked_game("easy")
        solve_by_walk(g, undo)
        moves = g["moves"]
        slidepuzzle.move(g, 7)
        self.assertEqual(g["moves"], moves)
        self.assertEqual(g["tiles"], list(range(9)))

    def test_give_up_ends_as_loss_with_picture_complete(self):
        g = slidepuzzle.new_game("medium")
        slidepuzzle.give_up(g)
        self.assertTrue(g["over"])
        self.assertFalse(g["won"])
        self.assertTrue(g["gave_up"])
        self.assertEqual(g["tiles"], list(range(16)))

    def test_solver_solves_random_boards(self):
        for level in slidepuzzle.LEVELS:
            for _ in range(25):
                g = slidepuzzle.new_game(level)
                for index in slidepuzzle.solve(g["tiles"], g["size"]):
                    before = g["moves"]
                    slidepuzzle.move(g, index)
                    self.assertEqual(g["moves"], before + 1)  # one tile per click
                self.assertTrue(g["won"], level)

    def test_solver_is_optimal_on_easy(self):
        # Board one move from solved — the 3x3 search should take exactly one.
        self.assertEqual(slidepuzzle.solve([0, 1, 2, 3, 4, 5, 6, 8, 7], 3), [8])
        self.assertEqual(slidepuzzle.solve(list(range(9)), 3), [])

    def test_give_up_records_solution_for_original_board(self):
        for level in slidepuzzle.LEVELS:
            g = slidepuzzle.new_game(level)
            replay = slidepuzzle.new_game(level)
            replay["tiles"] = list(g["tiles"])
            slidepuzzle.give_up(g)
            self.assertTrue(g["solution"])
            for index in g["solution"]:
                slidepuzzle.move(replay, index)
            self.assertTrue(replay["won"])
            self.assertEqual(slidepuzzle.game_state(g)["solution"], g["solution"])

    def test_give_up_after_win_does_nothing(self):
        g, undo = walked_game("easy")
        solve_by_walk(g, undo)
        slidepuzzle.give_up(g)
        self.assertTrue(g["won"])
        self.assertFalse(g["gave_up"])

    def test_game_state_shape(self):
        st = slidepuzzle.game_state(slidepuzzle.new_game("hard", "/x.svg"))
        for f in ("tiles", "size", "level", "levels", "image", "moves", "over", "won", "gave_up"):
            self.assertIn(f, st)
        self.assertEqual(st["image"], "/x.svg")


# ---------------------------------------------------------------------------
# Pictures
# ---------------------------------------------------------------------------

class TestSlidePuzzleImages(IsolatedImages):

    def test_ships_five_animals(self):
        self.assertGreaterEqual(len(slidepuzzle.animal_images()), 5)
        for url in slidepuzzle.animal_images():
            self.assertTrue(url.startswith("/slidepuzzle/images/animals/"))

    def test_guest_gets_an_animal(self):
        self.assertIn(slidepuzzle.pick_image(None), slidepuzzle.animal_images())

    def test_unconfigured_player_gets_an_animal(self):
        self.write_config({"Nia": "players/nia.jpg"})
        self.add_image("players/nia.jpg")
        self.assertIn(slidepuzzle.pick_image("Leo"), slidepuzzle.animal_images())

    def test_configured_player_gets_their_picture(self):
        self.write_config({"Nia": "players/nia.jpg"})
        self.add_image("players/nia.jpg")
        self.assertEqual(slidepuzzle.pick_image("Nia"), "/slidepuzzle/images/players/nia.jpg")

    def test_name_match_ignores_case(self):
        self.write_config({"nia": "players/nia.jpg"})
        self.add_image("players/nia.jpg")
        self.assertEqual(slidepuzzle.pick_image("Nia"), "/slidepuzzle/images/players/nia.jpg")

    def test_list_of_pictures_picks_one(self):
        self.write_config({"Nia": ["players/a.png", "players/b.png"]})
        self.add_image("players/a.png")
        self.add_image("players/b.png")
        seen = {slidepuzzle.pick_image("Nia") for _ in range(50)}
        self.assertEqual(seen, {"/slidepuzzle/images/players/a.png",
                                "/slidepuzzle/images/players/b.png"})

    def test_avoid_gives_a_different_picture(self):
        animals = slidepuzzle.animal_images()
        for _ in range(30):
            self.assertNotEqual(slidepuzzle.pick_image(None, avoid=animals[0]), animals[0])

    def test_single_picture_repeats_rather_than_falling_back(self):
        self.write_config({"Nia": "players/nia.jpg"})
        self.add_image("players/nia.jpg")
        url = "/slidepuzzle/images/players/nia.jpg"
        self.assertEqual(slidepuzzle.pick_image("Nia", avoid=url), url)

    def test_missing_file_falls_back_to_animal(self):
        self.write_config({"Nia": "players/missing.jpg"})
        self.assertIn(slidepuzzle.pick_image("Nia"), slidepuzzle.animal_images())

    def test_path_escaping_images_dir_is_rejected(self):
        with open(os.path.join(self._tmp, "secret.jpg"), "wb") as f:
            f.write(b"x")
        self.write_config({"Nia": "../secret.jpg"})
        self.assertIn(slidepuzzle.pick_image("Nia"), slidepuzzle.animal_images())

    def test_non_image_file_is_rejected(self):
        self.write_config({"Nia": "players/notes.txt"})
        self.add_image("players/notes.txt")
        self.assertIn(slidepuzzle.pick_image("Nia"), slidepuzzle.animal_images())

    def test_missing_or_broken_config_falls_back(self):
        self.assertIn(slidepuzzle.pick_image("Nia"), slidepuzzle.animal_images())
        with open(slidepuzzle.CONFIG_FILE, "w") as f:
            f.write("{not json")
        self.assertIn(slidepuzzle.pick_image("Nia"), slidepuzzle.animal_images())
        with open(slidepuzzle.CONFIG_FILE, "w") as f:
            f.write("[1, 2]")
        self.assertIn(slidepuzzle.pick_image("Nia"), slidepuzzle.animal_images())

    def test_shipped_config_is_valid_json(self):
        with open(self._orig[0], encoding="utf-8") as f:
            self.assertIsInstance(json.load(f)["players"], dict)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class TestSlidePuzzleScoring(IsolatedScores):

    def _finished_session(self, name=None, level="easy", won=True):
        sess = server.new_session()
        sess["name"] = name
        g, undo = walked_game(level)
        if won:
            solve_by_walk(g, undo)
        else:
            slidepuzzle.give_up(g)
        sess["sp_game"] = g
        return sess

    def test_win_awards_level_points(self):
        for level in slidepuzzle.LEVELS:
            server.SCORES = {}
            sess = self._finished_session(level=level)
            server.sp_apply_score(sess)
            self.assertEqual(server.SCORES["Guest"]["slidepuzzle"]["player"],
                             slidepuzzle.LEVEL_POINTS[level])

    def test_give_up_awards_computer_point(self):
        sess = self._finished_session(won=False)
        server.sp_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["slidepuzzle"], {"player": 0, "hangman": 1})

    def test_apply_score_fires_once(self):
        sess = self._finished_session(level="medium")
        server.sp_apply_score(sess)
        server.sp_apply_score(sess)
        self.assertEqual(server.SCORES["Guest"]["slidepuzzle"]["player"], 2)

    def test_not_over_does_not_score(self):
        sess = server.new_session()
        sess["sp_game"] = slidepuzzle.new_game()
        server.sp_apply_score(sess)
        self.assertNotIn("slidepuzzle", server.SCORES.get("Guest", {}))

    def test_named_score_persists(self):
        sess = self._finished_session(name="Nia", level="hard")
        server.sp_apply_score(sess)
        self.assertEqual(server.load_scores()["Nia"]["slidepuzzle"]["player"], 3)

    def test_counts_in_total_score(self):
        sess = self._finished_session(name="Nia")
        server.sp_apply_score(sess)
        self.assertEqual(server.total_score(sess)["player"], 1)


# ---------------------------------------------------------------------------
# End-to-end API
# ---------------------------------------------------------------------------

class TestSlidePuzzleApi(IsolatedImages, IsolatedScores):

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
        st = self.client().call("/slidepuzzle/state")
        for f in ("tiles", "size", "level", "levels", "image", "moves", "over",
                  "won", "gave_up", "score", "total_score", "names"):
            self.assertIn(f, st)
        self.assertIn(st["image"], slidepuzzle.animal_images())

    def test_new_game_sets_level(self):
        c = self.client()
        st = c.call("/slidepuzzle/new", {"level": "hard"})
        self.assertEqual(st["level"], "hard")
        self.assertEqual(len(st["tiles"]), 25)
        self.assertEqual(c.call("/slidepuzzle/new", {})["level"], "hard")

    def test_new_game_changes_picture(self):
        c = self.client()
        first = c.call("/slidepuzzle/state")["image"]
        self.assertNotEqual(c.call("/slidepuzzle/new", {})["image"], first)

    def test_move_and_win_awards_points(self):
        c = self.client()
        c.call("/slidepuzzle/new", {"level": "easy"})
        g, undo = walked_game("easy")
        server.SESSIONS[c.sid()]["sp_game"]["tiles"] = g["tiles"]
        for index in reversed(undo):
            st = c.call("/slidepuzzle/move", {"index": index})
        self.assertTrue(st["won"])
        self.assertEqual(st["moves"], len(undo))
        self.assertEqual(st["score"], {"player": 1, "hangman": 0})

    def test_bad_move_payload_is_ignored(self):
        c = self.client()
        before = c.call("/slidepuzzle/state")
        st = c.call("/slidepuzzle/move", {"index": "nope"})
        self.assertEqual(st["tiles"], before["tiles"])
        self.assertEqual(st["moves"], 0)

    def test_give_up_awards_computer_point(self):
        c = self.client()
        c.call("/slidepuzzle/state")
        st = c.call("/slidepuzzle/give_up", {})
        self.assertTrue(st["over"])
        self.assertTrue(st["gave_up"])
        self.assertEqual(st["score"], {"player": 0, "hangman": 1})
        self.assertIsInstance(st["solution"], list)
        st = c.call("/slidepuzzle/give_up", {})
        self.assertEqual(st["score"]["hangman"], 1)

    def test_player_picture_swaps_in_before_first_move(self):
        self.write_config({"Nia": "players/nia.jpg"})
        self.add_image("players/nia.jpg")
        c = self.client()
        self.assertIn(c.call("/slidepuzzle/state")["image"], slidepuzzle.animal_images())
        c.call("/name", {"name": "nia"})
        self.assertEqual(c.call("/slidepuzzle/state")["image"],
                         "/slidepuzzle/images/players/nia.jpg")

    def test_picture_kept_once_puzzle_started(self):
        self.write_config({"Nia": "players/nia.jpg"})
        self.add_image("players/nia.jpg")
        c = self.client()
        st = c.call("/slidepuzzle/state")
        b = st["tiles"].index(8)
        neighbour = b + 1 if b % 3 < 2 else b - 1
        st = c.call("/slidepuzzle/move", {"index": neighbour})
        c.call("/name", {"name": "Nia"})
        self.assertEqual(c.call("/slidepuzzle/state")["image"], st["image"])
        self.assertEqual(c.call("/slidepuzzle/new", {})["image"],
                         "/slidepuzzle/images/players/nia.jpg")

    def test_page_and_animal_images_are_served(self):
        with urllib.request.urlopen("http://127.0.0.1:%d/slidepuzzle/" % self.port) as r:
            self.assertIn(b"Slide Puzzle", r.read())
        url = slidepuzzle.animal_images()[0]
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (self.port, url)) as r:
            self.assertEqual(r.headers["Content-Type"], "image/svg+xml")

    def test_sessions_are_independent(self):
        a, b = self.client(), self.client()
        a.call("/slidepuzzle/new", {"level": "hard"})
        self.assertEqual(b.call("/slidepuzzle/state")["level"], slidepuzzle.DEFAULT_LEVEL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
