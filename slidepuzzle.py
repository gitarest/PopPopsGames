"""Slide Puzzle game logic for Pop Pop's Games.

The board is a flat list of tile ids. Tile id `t` belongs at index `t` in the
solved board; the blank is id `size*size - 1` and belongs in the bottom-right.

Each player can have their own picture (see slidepuzzle_config.json); anyone
without one gets a random animal from static/slidepuzzle/images/animals/.
"""

import json
import os
import random

LEVELS = ["easy", "medium", "hard"]
DEFAULT_LEVEL = "easy"
LEVEL_POINTS = {"easy": 1, "medium": 2, "hard": 3}
LEVEL_SIZES = {"easy": 3, "medium": 4, "hard": 5}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "slidepuzzle_config.json")
IMAGES_DIR = os.path.join(BASE_DIR, "static", "slidepuzzle", "images")
ANIMALS_DIR = os.path.join(IMAGES_DIR, "animals")
IMAGES_URL = "/slidepuzzle/images/"
IMAGE_EXTS = (".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp")


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def animal_images():
    """Sorted URLs of every default animal picture."""
    try:
        files = sorted(f for f in os.listdir(ANIMALS_DIR)
                       if f.lower().endswith(IMAGE_EXTS))
    except OSError:
        return []
    return [IMAGES_URL + "animals/" + f for f in files]


def player_images(name):
    """URLs configured for this player in slidepuzzle_config.json.

    Read on every call so the config can be edited without a restart. A
    player's entry may be one path or a list of paths, relative to
    static/slidepuzzle/images/. Missing files and paths that escape the
    images folder are skipped.
    """
    if not name:
        return []
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            players = json.load(f).get("players", {})
    except (OSError, ValueError, AttributeError):
        return []
    if not isinstance(players, dict):
        return []
    entry = next((v for k, v in players.items()
                  if str(k).strip().lower() == name.strip().lower()), None)
    if isinstance(entry, str):
        entry = [entry]
    if not isinstance(entry, list):
        return []
    urls = []
    for rel in entry:
        if not isinstance(rel, str):
            continue
        full = os.path.normpath(os.path.join(IMAGES_DIR, rel))
        if (full.startswith(IMAGES_DIR + os.sep) and os.path.isfile(full)
                and full.lower().endswith(IMAGE_EXTS)):
            urls.append(IMAGES_URL + os.path.relpath(full, IMAGES_DIR).replace(os.sep, "/"))
    return urls


def pick_image(name=None, avoid=None):
    """The player's own picture if configured, else a random animal.

    `avoid` is the previous image, so New Game shows a different picture
    whenever there's more than one to choose from.
    """
    choices = player_images(name) or animal_images()
    if len(choices) > 1 and avoid in choices:
        choices = [c for c in choices if c != avoid]
    return random.choice(choices) if choices else None


# ---------------------------------------------------------------------------
# Board
# ---------------------------------------------------------------------------

def is_solvable(tiles, size):
    """Standard 15-puzzle parity rule (blank's home is the bottom-right)."""
    blank = size * size - 1
    order = [t for t in tiles if t != blank]
    inversions = sum(1 for i in range(len(order))
                     for j in range(i + 1, len(order)) if order[i] > order[j])
    if size % 2 == 1:
        return inversions % 2 == 0
    blank_row = tiles.index(blank) // size
    return (inversions + blank_row) % 2 == 1


def is_solved(tiles):
    return all(t == i for i, t in enumerate(tiles))


def shuffled_tiles(size):
    """A random, solvable, not-already-solved board."""
    blank = size * size - 1
    while True:
        tiles = list(range(size * size))
        random.shuffle(tiles)
        if not is_solvable(tiles, size):
            # Swapping two non-blank tiles flips the parity.
            a, b = [i for i, t in enumerate(tiles) if t != blank][:2]
            tiles[a], tiles[b] = tiles[b], tiles[a]
        if not is_solved(tiles):
            return tiles


def new_game(level=DEFAULT_LEVEL, image=None):
    if level not in LEVEL_SIZES:
        level = DEFAULT_LEVEL
    size = LEVEL_SIZES[level]
    return {
        "tiles": shuffled_tiles(size),
        "size": size,
        "level": level,
        "image": image,
        "moves": 0,
        "over": False,
        "won": False,
        "gave_up": False,
        "scored": False,
    }


def move(game, index):
    """Slide toward the blank. Clicking any tile in the blank's row or column
    slides every tile between them; each tile that moves counts as one move."""
    if game["over"]:
        return
    size = game["size"]
    tiles = game["tiles"]
    if not (isinstance(index, int) and 0 <= index < size * size):
        return
    b = tiles.index(size * size - 1)
    if index == b:
        return
    if index // size == b // size:
        step = 1 if index > b else -1
    elif index % size == b % size:
        step = size if index > b else -size
    else:
        return
    while b != index:
        tiles[b] = tiles[b + step]
        b += step
        game["moves"] += 1
    tiles[index] = size * size - 1
    if is_solved(tiles):
        game["over"] = True
        game["won"] = True


# ---------------------------------------------------------------------------
# Solver (for Give Up)
# ---------------------------------------------------------------------------

def _neighbors(i, size, region):
    r, c = divmod(i, size)
    for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
        if 0 <= nr < size and 0 <= nc < size and nr * size + nc in region:
            yield nr * size + nc


def _place(tiles, size, region, targets):
    """Shortest click sequence that brings each tile id in `targets` to its
    home cell, moving only within `region`. Other tiles are interchangeable
    here, so the search state is just the blank plus the target tiles."""
    blank = size * size - 1
    start = (tiles.index(blank),) + tuple(tiles.index(t) for t in targets)
    if start[1:] == tuple(targets):
        return []
    parent = {start: None}
    queue = [start]
    for state in queue:
        b = state[0]
        for nb in _neighbors(b, size, region):
            nxt = (nb,) + tuple(b if p == nb else p for p in state[1:])
            if nxt in parent:
                continue
            parent[nxt] = state
            if nxt[1:] == tuple(targets):
                path = []
                while parent[nxt] is not None:
                    path.append(nxt[0])
                    nxt = parent[nxt]
                return path[::-1]
            queue.append(nxt)
    raise ValueError("unreachable placement")


def _solve_3x3(tiles, size, region):
    """A* (Manhattan distance) over the final 3x3 corner — an optimal finish."""
    import heapq
    blank = size * size - 1
    cells = sorted(region)

    def h(state):
        total = 0
        for cell, t in zip(cells, state):
            if t != blank:
                total += abs(cell // size - t // size) + abs(cell % size - t % size)
        return total

    start = tuple(tiles[c] for c in cells)
    goal = tuple(cells)
    parent = {start: (None, None)}
    cost = {start: 0}
    heap = [(h(start), 0, start)]
    while heap:
        _, g, state = heapq.heappop(heap)
        if state == goal:
            path = []
            while parent[state][0] is not None:
                state, clicked = parent[state]
                path.append(clicked)
            return path[::-1]
        if g > cost[state]:
            continue
        bi = state.index(blank)
        for nb in _neighbors(cells[bi], size, region):
            ni = cells.index(nb)
            lst = list(state)
            lst[bi], lst[ni] = lst[ni], lst[bi]
            nxt = tuple(lst)
            if g + 1 < cost.get(nxt, 1 << 30):
                cost[nxt] = g + 1
                parent[nxt] = (state, nb)
                heapq.heappush(heap, (g + 1 + h(nxt), g + 1, nxt))
    raise ValueError("unsolvable board")


def solve(tiles, size):
    """Click sequence (cell indexes, one tile per click) that solves the board.

    Like a person would: finish the top row, then the left column, shrinking
    the puzzle until a 3x3 corner is left, then solve that optimally. The last
    two tiles of each row/column are placed together so the first can't get
    stuck in the corner.
    """
    tiles = list(tiles)
    path = []

    def run(clicks):
        b = tiles.index(size * size - 1)
        for i in clicks:
            tiles[b], tiles[i] = tiles[i], tiles[b]
            b = i
        path.extend(clicks)

    region = set(range(size * size))
    top = 0
    while size - top > 3:
        row = [top * size + c for c in range(top, size)]
        col = [r * size + top for r in range(top + 1, size)]
        for line in (row, col):
            for t in line[:-2]:
                run(_place(tiles, size, region, [t]))
                region.discard(t)
            run(_place(tiles, size, region, line[-2:]))
            region -= set(line[-2:])
        top += 1
    run(_solve_3x3(tiles, size, region))
    return path


def give_up(game):
    """End the game as a loss. `solution` holds the clicks that solve the
    board as it was, so the page can play them out."""
    if game["over"]:
        return
    game["solution"] = solve(game["tiles"], game["size"])
    game["tiles"] = list(range(game["size"] ** 2))
    game["over"] = True
    game["gave_up"] = True


def game_state(game):
    return {
        "tiles": list(game["tiles"]),
        "size": game["size"],
        "level": game["level"],
        "levels": LEVELS,
        "image": game["image"],
        "moves": game["moves"],
        "over": game["over"],
        "won": game["won"],
        "gave_up": game["gave_up"],
        "solution": game.get("solution"),
    }
