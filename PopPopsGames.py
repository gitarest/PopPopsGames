"""Pop Pop's Games — HTTP server and session/scoring layer.

Runs Hangman and Tic-Tac-Toe via a pure-stdlib ThreadingHTTPServer.
Game logic lives in hangman.py and tictactoe.py; this file owns routing,
sessions, scoring, and persistence.

Run:  python PopPopsGames.py
Open: http://localhost:8000
"""

import json
import os
import string
import uuid
from datetime import datetime, timezone, timedelta
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from zoneinfo import ZoneInfo as _ZI
    _DENVER_TZ = _ZI("America/Denver")
except Exception:
    _DENVER_TZ = None

# Game modules — import under their original names so tests and handler code
# that reference these symbols continue to work without changes.
from hangman import game_state, level_points, new_game, MAX_WRONG          # noqa: F401
from tictactoe import (
    new_game as new_ttt_game,
    game_state as ttt_state,
    check_winner as ttt_check_winner,
    best_move as ttt_best_move,
)
from rps import (
    new_game as rps_new_game,
    game_state as rps_game_state,
    play as rps_play,
)
from connectfour import (
    new_game as cf_new_game,
    game_state as cf_game_state,
    drop as cf_drop,
)
from words import DEFAULT_LEVEL, LEVELS, WORDS_BY_LEVEL                    # noqa: F401

HOST = "0.0.0.0"
PORT = 8000
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

SESSIONS = {}

# Named scores, persisted to disk.
# {name: {game_key: {"player": int, "hangman": int}}}
SCORES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scores.json")
LOG_FILE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "events.log")


def _denver_now():
    utc = datetime.now(timezone.utc)
    if _DENVER_TZ is not None:
        dt = utc.astimezone(_DENVER_TZ)
        return dt.strftime("%Y-%m-%d %H:%M:%S ") + dt.tzname()
    dt = utc + timedelta(hours=-7)
    return dt.strftime("%Y-%m-%d %H:%M:%S MST")


def log_event(ip, player, game, event):
    """Append one line to events.log: timestamp | ip | player | game | event."""
    label = player or "Guest"
    line = f"{_denver_now()} | {ip or 'unknown'} | {label} | {game} | {event}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css":  "text/css; charset=utf-8",
    ".js":   "application/javascript; charset=utf-8",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif":  "image/gif",
    ".ico":  "image/x-icon",
}


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def normalize_name(name):
    """Canonical form: trimmed, capped at 20 chars, Title Cased."""
    return name.strip()[:20].title()


def load_scores():
    """Load and return the name→score map, migrating old flat format if needed.

    Old format: {name: {"player": N, "hangman": N}}
    New format: {name: {"hangman": {"player": N, "hangman": N}, ...}}
    Old entries are migrated to the "hangman" game key.
    """
    try:
        with open(SCORES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    result = {}
    for name, val in data.items():
        key = normalize_name(str(name))
        if not key or not isinstance(val, dict):
            continue
        entry = result.setdefault(key, {})
        if any(isinstance(v, int) for v in val.values()):
            # Old flat format — migrate to the "hangman" game key.
            slot = entry.setdefault("hangman", {"player": 0, "hangman": 0})
            slot["player"] += val.get("player", 0) if isinstance(val.get("player"), int) else 0
            slot["hangman"] += val.get("hangman", 0) if isinstance(val.get("hangman"), int) else 0
        else:
            for game_key, game_scores in val.items():
                if isinstance(game_scores, dict):
                    slot = entry.setdefault(game_key, {"player": 0, "hangman": 0})
                    slot["player"] += game_scores.get("player", 0)
                    slot["hangman"] += game_scores.get("hangman", 0)
    return result


def save_scores():
    """Write the in-memory SCORES map to disk (best effort)."""
    try:
        with open(SCORES_FILE, "w", encoding="utf-8") as f:
            json.dump(SCORES, f, indent=2)
    except OSError:
        pass


SCORES = load_scores()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def active_score(session, game_key):
    """The per-game score record this session writes to.

    Named players use SCORES[name][game_key]; guests use their session dict.
    """
    name = session["name"]
    if name:
        return SCORES.setdefault(name, {}).setdefault(
            game_key, {"player": 0, "hangman": 0}
        )
    return session["guest_score"].setdefault(
        game_key, {"player": 0, "hangman": 0}
    )


def total_score(session):
    """Sum of player/hangman points across all games for this session."""
    name = session["name"]
    games = SCORES.get(name, {}) if name else session["guest_score"]
    totals = {"player": 0, "hangman": 0}
    for gs in games.values():
        if isinstance(gs, dict):
            totals["player"] += gs.get("player", 0)
            totals["hangman"] += gs.get("hangman", 0)
    return totals


def apply_score(session, ip=None):
    """Award Hangman points exactly once per completed game."""
    game = session["game"]
    if game["scored"]:
        return
    state = game_state(game)
    if not state["over"]:
        return
    score = active_score(session, "hangman")
    if state["won"]:
        score["player"] += level_points(game["level"])
        log_event(ip, session["name"], "hangman", "win")
    else:
        score["hangman"] += 1
        log_event(ip, session["name"], "hangman", "loss")
    game["scored"] = True
    if session["name"]:
        save_scores()


def ttt_apply_score(session, ip=None):
    """Award TTT points exactly once per completed game."""
    game = session["ttt_game"]
    if game["scored"] or not game["over"]:
        return
    score = active_score(session, "tictactoe")
    if game["winner"] == "X":
        score["player"] += 1
        log_event(ip, session["name"], "tictactoe", "win")
    elif game["winner"] == "O":
        score["hangman"] += 1
        log_event(ip, session["name"], "tictactoe", "loss")
    else:
        log_event(ip, session["name"], "tictactoe", "draw")
    game["scored"] = True
    if session["name"]:
        save_scores()


def rps_apply_score(session, ip=None):
    """Award RPS points exactly once per completed game."""
    game = session["rps_game"]
    if game["scored"] or not game["over"]:
        return
    score = active_score(session, "rps")
    if game["result"] == "win":
        score["player"] += 1
        log_event(ip, session["name"], "rps", "win")
    elif game["result"] == "loss":
        score["hangman"] += 1
        log_event(ip, session["name"], "rps", "loss")
    else:
        log_event(ip, session["name"], "rps", "draw")
    game["scored"] = True
    if session["name"]:
        save_scores()


def rps_build_payload(session, ip=None):
    """Score any finished RPS game and build the full client payload."""
    if "rps_game" not in session:
        session["rps_game"] = rps_new_game()
    rps_apply_score(session, ip)
    return {
        **rps_game_state(session["rps_game"]),
        "name": session["name"],
        "score": active_score(session, "rps"),
        "total_score": total_score(session),
        "names": sorted(SCORES.keys()),
    }


def cf_apply_score(session, ip=None):
    """Award Connect Four points exactly once per completed game."""
    game = session["cf_game"]
    if game["scored"] or not game["over"]:
        return
    score = active_score(session, "connectfour")
    if game["winner"] == "P":
        score["player"] += 1
        log_event(ip, session["name"], "connectfour", "win")
    elif game["winner"] == "C":
        score["hangman"] += 1
        log_event(ip, session["name"], "connectfour", "loss")
    else:
        log_event(ip, session["name"], "connectfour", "draw")
    game["scored"] = True
    if session["name"]:
        save_scores()


def cf_build_payload(session, ip=None):
    """Score any finished Connect Four game and build the full client payload."""
    if "cf_game" not in session:
        session["cf_game"] = cf_new_game()
    cf_apply_score(session, ip)
    return {
        **cf_game_state(session["cf_game"]),
        "name": session["name"],
        "score": active_score(session, "connectfour"),
        "total_score": total_score(session),
        "names": sorted(SCORES.keys()),
    }


def build_payload(session, ip=None):
    """Score any finished Hangman game and build the full client payload."""
    apply_score(session, ip)
    return {
        **game_state(session["game"]),
        "name": session["name"],
        "score": active_score(session, "hangman"),
        "total_score": total_score(session),
        "names": sorted(SCORES.keys()),
    }


def ttt_build_payload(session, ip=None):
    """Score any finished TTT game and build the full client payload."""
    if "ttt_game" not in session:
        session["ttt_game"] = new_ttt_game()
    ttt_apply_score(session, ip)
    return {
        **ttt_state(session["ttt_game"]),
        "name": session["name"],
        "score": active_score(session, "tictactoe"),
        "total_score": total_score(session),
        "names": sorted(SCORES.keys()),
    }


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def new_session():
    """Create a fresh session with all games and guest defaults."""
    return {
        "game": new_game(),
        "ttt_game": new_ttt_game(),
        "rps_game": rps_new_game(),
        "cf_game": cf_new_game(),
        "name": None,
        "guest_score": {},  # {game_key: {"player": N, "hangman": N}}
    }


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class HangmanHandler(BaseHTTPRequestHandler):
    server_version = "PopPopsGames/1.0"

    def get_client_ip(self):
        """Return the real client IP (checks X-Forwarded-For set by nginx)."""
        xff = self.headers.get("X-Forwarded-For", "").strip()
        if xff:
            return xff.split(",")[0].strip()
        return self.client_address[0]

    def get_session_id(self):
        raw = self.headers.get("Cookie")
        if raw:
            jar = cookies.SimpleCookie(raw)
            if "sid" in jar:
                return jar["sid"].value, False
        return uuid.uuid4().hex, True

    def get_session(self):
        sid, is_new = self.get_session_id()
        if sid not in SESSIONS:
            SESSIONS[sid] = new_session()
        return sid, SESSIONS[sid], is_new

    def send_json(self, payload, sid=None, set_cookie=False):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if set_cookie and sid:
            jar = cookies.SimpleCookie()
            jar["sid"] = sid
            jar["sid"]["path"] = "/"
            jar["sid"]["httponly"] = True
            self.send_header("Set-Cookie", jar["sid"].OutputString())
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, path):
        """Serve a file from the static/ directory.

        /            → static/index.html  (launcher)
        /hangman     → 301 → /hangman/
        /hangman/    → static/hangman/index.html
        /tictactoe   → 301 → /tictactoe/
        /tictactoe/  → static/tictactoe/index.html

        The 301 redirects ensure the browser's base URL includes the trailing
        slash so relative asset paths (style.css, script.js) resolve correctly.
        """
        if path in ("/hangman", "/tictactoe", "/rps", "/connectfour"):
            self.send_response(301)
            self.send_header("Location", path + "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if path in ("/", ""):
            rel = "index.html"
        elif path in ("/hangman/", "/tictactoe/", "/rps/", "/connectfour/"):
            rel = path.lstrip("/") + "index.html"
        else:
            rel = path.lstrip("/")

        full = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            self.send_error(404, "Not found")
            return

        ctype = CONTENT_TYPES.get(os.path.splitext(full)[1], "application/octet-stream")
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        ip = self.get_client_ip()
        if self.path in ("/", ""):
            sid, session, is_new = self.get_session()
            log_event(ip, session["name"], "launcher", "visit")
            self.send_static(self.path)
        elif self.path == "/state":
            sid, session, is_new = self.get_session()
            self.send_json(build_payload(session, ip), sid=sid, set_cookie=is_new)
        elif self.path == "/ttt/state":
            sid, session, is_new = self.get_session()
            self.send_json(ttt_build_payload(session, ip), sid=sid, set_cookie=is_new)
        elif self.path == "/rps/state":
            sid, session, is_new = self.get_session()
            self.send_json(rps_build_payload(session, ip), sid=sid, set_cookie=is_new)
        elif self.path == "/connectfour/state":
            sid, session, is_new = self.get_session()
            self.send_json(cf_build_payload(session, ip), sid=sid, set_cookie=is_new)
        elif self.path in ("/hangman/", "/tictactoe/", "/rps/", "/connectfour/"):
            sid, session, is_new = self.get_session()
            game_name = self.path.strip("/")
            log_event(ip, session["name"], game_name, "visit")
            self.send_static(self.path)
        else:
            self.send_static(self.path)

    def do_POST(self):
        if self.path == "/guess":
            self.handle_guess()
        elif self.path == "/new":
            self.handle_new()
        elif self.path == "/name":
            self.handle_name()
        elif self.path == "/ttt/move":
            self.handle_ttt_move()
        elif self.path == "/ttt/new":
            self.handle_ttt_new()
        elif self.path == "/rps/play":
            self.handle_rps_play()
        elif self.path == "/rps/new":
            self.handle_rps_new()
        elif self.path == "/connectfour/drop":
            self.handle_cf_drop()
        elif self.path == "/connectfour/new":
            self.handle_cf_new()
        else:
            self.send_error(404, "Not found")

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8")) or {}
        except (ValueError, UnicodeDecodeError):
            return {}

    def handle_guess(self):
        sid, session, is_new = self.get_session()
        ip = self.get_client_ip()
        game = session["game"]
        data = self.read_json_body()
        letter = str(data.get("letter", "")).strip().upper()

        state = game_state(game)
        valid = (
            not state["over"]
            and len(letter) == 1
            and letter in string.ascii_uppercase
        )
        if valid and letter not in game["guessed"]:
            if not game.get("start_logged"):
                log_event(ip, session["name"], "hangman", f"start:{game['level']}")
                game["start_logged"] = True
            game["guessed"].append(letter)
            if letter not in game["word"]:
                game["wrong"] += 1

        self.send_json(build_payload(session, ip), sid=sid, set_cookie=is_new)

    def handle_new(self):
        sid, session, is_new = self.get_session()
        ip = self.get_client_ip()
        data = self.read_json_body()
        level = str(data.get("level", "")).strip().lower() or session["game"]["level"]
        session["game"] = new_game(level)
        session["game"]["start_logged"] = True
        log_event(ip, session["name"], "hangman", f"start:{level}")
        self.send_json(build_payload(session, ip), sid=sid, set_cookie=is_new)

    def handle_name(self):
        sid, session, is_new = self.get_session()
        ip = self.get_client_ip()
        data = self.read_json_body()
        name = normalize_name(str(data.get("name", "")))
        session["name"] = name or None
        if name and name not in SCORES:
            SCORES[name] = {}
            save_scores()
        log_event(ip, session["name"], "session", "name_set")
        self.send_json(build_payload(session, ip), sid=sid, set_cookie=is_new)

    def handle_ttt_new(self):
        sid, session, is_new = self.get_session()
        ip = self.get_client_ip()
        session["ttt_game"] = new_ttt_game()
        session["ttt_game"]["start_logged"] = True
        log_event(ip, session["name"], "tictactoe", "start")
        self.send_json(ttt_build_payload(session, ip), sid=sid, set_cookie=is_new)

    def handle_ttt_move(self):
        sid, session, is_new = self.get_session()
        ip = self.get_client_ip()
        if "ttt_game" not in session:
            session["ttt_game"] = new_ttt_game()
        game = session["ttt_game"]
        data = self.read_json_body()
        cell = data.get("cell")

        if (not game["over"]
                and isinstance(cell, int)
                and 0 <= cell <= 8
                and game["board"][cell] is None):
            if not game.get("start_logged"):
                log_event(ip, session["name"], "tictactoe", "start")
                game["start_logged"] = True
            game["board"][cell] = "X"
            winner = ttt_check_winner(game["board"])
            if winner:
                game["winner"] = winner
                game["over"] = True
            else:
                ai = ttt_best_move(game["board"])
                if ai is not None:
                    game["board"][ai] = "O"
                    winner = ttt_check_winner(game["board"])
                    if winner:
                        game["winner"] = winner
                        game["over"] = True

        self.send_json(ttt_build_payload(session, ip), sid=sid, set_cookie=is_new)

    def handle_rps_new(self):
        sid, session, is_new = self.get_session()
        ip = self.get_client_ip()
        session["rps_game"] = rps_new_game()
        session["rps_game"]["start_logged"] = True
        log_event(ip, session["name"], "rps", "start")
        self.send_json(rps_build_payload(session, ip), sid=sid, set_cookie=is_new)

    def handle_rps_play(self):
        sid, session, is_new = self.get_session()
        ip = self.get_client_ip()
        if "rps_game" not in session:
            session["rps_game"] = rps_new_game()
        data = self.read_json_body()
        choice = str(data.get("choice", "")).strip().lower()
        if not session["rps_game"].get("start_logged"):
            log_event(ip, session["name"], "rps", "start")
            session["rps_game"]["start_logged"] = True
        rps_play(session["rps_game"], choice)
        self.send_json(rps_build_payload(session, ip), sid=sid, set_cookie=is_new)

    def handle_cf_new(self):
        sid, session, is_new = self.get_session()
        ip = self.get_client_ip()
        data = self.read_json_body()
        level = str(data.get("level", "")).strip().lower() or session["cf_game"]["level"]
        session["cf_game"] = cf_new_game(level)
        session["cf_game"]["start_logged"] = True
        log_event(ip, session["name"], "connectfour", f"start:{level}")
        self.send_json(cf_build_payload(session, ip), sid=sid, set_cookie=is_new)

    def handle_cf_drop(self):
        sid, session, is_new = self.get_session()
        ip = self.get_client_ip()
        if "cf_game" not in session:
            session["cf_game"] = cf_new_game()
        data = self.read_json_body()
        col = data.get("col")
        if isinstance(col, int) and 0 <= col < 7:
            if not session["cf_game"].get("start_logged"):
                log_event(ip, session["name"], "connectfour", f"start:{session['cf_game']['level']}")
                session["cf_game"]["start_logged"] = True
            cf_drop(session["cf_game"], col)
        self.send_json(cf_build_payload(session, ip), sid=sid, set_cookie=is_new)

    def log_message(self, fmt, *args):
        print("[PopPopsGames] " + (fmt % args))


def main():
    srv = ThreadingHTTPServer((HOST, PORT), HangmanHandler)
    log_event("server", "-", "server", "restart")
    print(f"Pop Pop's Games running at http://localhost:{PORT}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        srv.server_close()


if __name__ == "__main__":
    main()
