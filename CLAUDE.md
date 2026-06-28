# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Run

```bash
python PopPopsGames.py
```

`HOST = "0.0.0.0"`, so it serves on http://localhost:8000 **and** the machine's
LAN IP (for playing from a phone on the same network). Stop with `Ctrl+C`. There
is no build step and no dependencies (standard library only).

Tests live in [test_hangman.py](test_hangman.py) (stdlib `unittest`, no deps):

```bash
python -m unittest test_hangman          # all
python -m unittest test_hangman.TestScoring -v   # one group, verbose
```

Three groups: `TestGameLogic` (pure helpers), `TestScoring` (scoring +
persistence), `TestHangmanApi` (end-to-end HTTP on an ephemeral port, one cookie
jar per simulated browser). Tests do `import PopPopsGames as server` and redirect
`server.SCORES_FILE` to a temp file, so the real `scores.json` is never touched.
They run in ~1s; if you ever see them crawl, that's the `localhost`→IPv6 stall —
they bind `127.0.0.1` to avoid it.

On Windows, LAN access also needs an inbound firewall rule for TCP 8000 (one was
added under the name "Hangman 8000", scoped to the local subnet). Connecting from
the same machine works without it; only other devices are blocked otherwise.

### Development workflow

- **Static changes** (`static/*.html|css|js`) are served from disk per request —
  just hard-refresh the browser (Ctrl+F5 / pull-to-refresh on mobile). No restart.
- **Python changes** (`PopPopsGames.py`, `hangman.py`, `tictactoe.py`, `words.py`)
  require restarting the process.
- Exercise the API with PowerShell, keeping the `sid` cookie across calls:
  `Invoke-RestMethod http://localhost:8000/state -SessionVariable S` then reuse
  `-WebSession $S`. Forcing a deterministic win is easy — medium = "programmer",
  expert = "psychologist"; guess its unique letters.

## Deployment

The app is live in production on a DigitalOcean droplet.

| Thing | Value |
|---|---|
| Production URLs | `https://mccontek.com`, `https://www.mccontek.com`, `https://games.mccontek.com` |
| Server IP | `164.92.65.37` |
| GitHub repo | `https://github.com/gitarest/PopPopsGames` (private) |
| Server user | `poppop` (runs the app), `root` (SSH/admin) |
| App directory | `/home/poppop/PopPopsGames` |
| Service name | `poppopsgames` (systemd) |

### Deploying changes

Use the `/deploy` skill — it commits, pushes to GitHub, and restarts the server:
```
/deploy
```

To deploy manually:
```bash
git add -A && git commit -m "description"
git push origin master
ssh root@164.92.65.37 "cd /home/poppop/PopPopsGames && git pull && systemctl restart poppopsgames"
```

### SSH access
```bash
ssh root@164.92.65.37
```
No password needed — SSH key is installed. Key lives at `~/.ssh/id_ed25519`.

### Server management
```bash
systemctl status poppopsgames    # check if running
systemctl restart poppopsgames   # restart after manual changes
journalctl -u poppopsgames -f    # tail logs
```

### scores.json on the server
The live `scores.json` is at `/home/poppop/PopPopsGames/scores.json`. It is **not** in git.
To back it up locally:
```bash
scp root@164.92.65.37:/home/poppop/PopPopsGames/scores.json ./scores_backup.json
```
Never `git push` a local `scores.json` to the server — it would wipe the grandkids' scores.

### HTTPS certificate
Issued by Let's Encrypt via certbot. Covers all three domains. Auto-renews — no action needed.
Config is at `/etc/nginx/sites-enabled/poppopsgames` on the server.

## Architecture

Pop Pop's Games is a browser-based multi-game platform. The Python side is a pure
stdlib HTTP server; the browser side is static HTML/CSS/JS that talks to it over a
JSON API. **All game logic lives server-side** — the client only renders state it
receives and never decides win/loss or correctness.

### Python files

- [PopPopsGames.py](PopPopsGames.py) — Main entry point. `ThreadingHTTPServer` +
  `HangmanHandler`. Owns HTTP routing, sessions, scoring, and persistence. Imports
  game logic from `hangman.py` and `tictactoe.py`; re-exports their symbols so
  tests can do `import PopPopsGames as server` and access everything through one
  namespace.
- [hangman.py](hangman.py) — Hangman game logic only: `new_game()`, `game_state()`,
  `level_points()`, `MAX_WRONG`. No HTTP, no scoring.
- [tictactoe.py](tictactoe.py) — TTT game logic and minimax AI: `new_game()`,
  `game_state()`, `check_winner()`, `best_move()`, `TTT_LINES`. No HTTP, no scoring.
- [words.py](words.py) — Aggregates the per-level modules into `WORDS_BY_LEVEL` and
  defines `LEVELS` (UI order) and `DEFAULT_LEVEL`. Each level's words live in
  `words_<level>.py` (`WORDS` list, lowercase; uppercased at game creation).

### Adding a new game

1. Create `mygame.py` with pure game logic (`new_game`, `game_state`, etc.).
2. In `PopPopsGames.py`: import from `mygame`, add `mygame_apply_score()`,
   `mygame_build_payload()`, new session key in `new_session()`, and new
   `GET /mygame/state` + `POST /mygame/*` routes in `do_GET`/`do_POST`.
3. Add `static/mygame/index.html`, `style.css`, `script.js`.
4. Add a card to `static/index.html` pointing to `/mygame`.
5. The 301 redirect pattern in `send_static()` handles `/mygame` → `/mygame/`
   automatically — just add the path to the redirect check.

### Sessions and scoring

`SESSIONS = {session_id: session_dict}` keyed by a `sid` cookie minted on first
request. A session holds one game dict per game (`game`, `ttt_game`), `name`
(None = guest), and `guest_score` (a dict keyed by game key).

Scoring is Player vs Computer: a win adds points to `player`, a loss adds 1 to
`hangman` (the computer slot). `apply_score()` / `ttt_apply_score()` award points
exactly once per game via the game's `scored` flag. `active_score(session, game_key)`
routes points: **named** players write to the persistent `SCORES` map
(`{name: {game_key: {"player": N, "hangman": N}}}`), saved to `scores.json` via
`save_scores()`; **guests** write to `session["guest_score"]`. Named totals survive
restarts; guest totals do not.

`total_score(session)` sums across all games and is returned in every payload so
the launcher can show a combined tally.

Old flat `scores.json` format (`{name: {"player": N, "hangman": N}}`) is
auto-migrated to the per-game format on load by `load_scores()`.

### JSON API

**Hangman**
- `GET /state` — current Hangman game view + score.
- `POST /guess` `{"letter": "A"}` — single-letter guess.
- `POST /new` `{"level": "easy"}` — fresh word; level optional.
- `POST /name` `{"name": "Alice"}` — set player name; blank → guest.

**Tic-Tac-Toe**
- `GET /ttt/state` — current TTT game view + score.
- `POST /ttt/move` `{"cell": 4}` — player (X) move; server immediately plays O.
- `POST /ttt/new` — reset the TTT board.

**Shared** — every JSON response (from `build_payload()` / `ttt_build_payload()`)
includes `name`, `score` (game-specific), `total_score` (all games), and `names`
(all saved players, sorted — drives the name autocomplete).

Any other `GET` falls through to `send_static()`, which serves from `static/`
(path-traversal guarded) and issues 301 redirects for bare game paths (`/hangman`
→ `/hangman/`) so relative asset paths resolve correctly.

### Static files

```
static/
  index.html      launcher (game selection + total score)
  style.css       launcher styles
  launcher.js     launcher JS (fetches /state for name/score)
  logo.png        "Pop Pops Games" carnival image used as header + home button
  hangman/
    index.html
    style.css
    script.js
  tictactoe/
    index.html
    style.css
    script.js
```

The game pages show the logo as a small clickable image at the bottom that links
back to `/`. When adding a new game, copy the pattern from an existing game page.

### Client-side state

The browser keeps two bits of UI state the server doesn't:
- **Remembered difficulty** (`localStorage["hangman.level"]`) — survives server
  restarts (sessions are in-memory). Per-device.
- **Name editor** — a button that opens an inline combobox with the known player
  list and a "Guest" option. Uses `mousedown` (fires before `blur`) for list
  selection so the dropdown doesn't close before the click registers.

## Conventions / gotchas

- `MAX_WRONG = 6` (in `hangman.py`) is coupled to the 6-part SVG drawing.
  Changing it without adding/removing `.part` SVG elements breaks the figure.
- The client/server contract is the `game_state()` dict shape. When adding a
  field, update both `game_state()` in the game module **and** `render()` in the
  corresponding `static/<game>/script.js`.
- **`scores.json` is live player data** — don't delete or overwrite it casually.
  To edit by hand, **stop the server first**: it holds `SCORES` in memory and
  rewrites the whole file on every named game completion. Default difficulty is
  `easy` (`DEFAULT_LEVEL` in `words.py`).
- TTT AI is unbeatable (perfect minimax). The best a player can do is draw.
- `ttt_check_winner` / `ttt_best_move` names used in the HTTP handler come from
  the aliased imports in `PopPopsGames.py` (`from tictactoe import check_winner as
  ttt_check_winner`). Keep those aliases in sync if renaming functions in
  `tictactoe.py`.
- `static/script.js.tmp.*` files are editor temp artifacts; ignore them.
- After renaming the folder (to "Pop Pops Games"), reopen VS Code to the new path.
  The folder must be closed in all programs before `Rename-Item` will succeed.
