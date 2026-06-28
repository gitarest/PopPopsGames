# Pop Pop's Games

A browser-based multi-game platform written in pure Python — **no third-party
dependencies**, just the standard library.

## Run

```bash
python PopPopsGames.py
```

Then open <http://localhost:8000> in your browser. Stop the server with `Ctrl+C`.

The server listens on all interfaces, so you can also play from another device
(e.g. a phone) on the same network at `http://<your-computer-ip>:8000`. On
Windows you may need to allow inbound TCP port 8000 through the firewall first.

## Games

- **Hangman** — guess the hidden word before the drawing completes. Four difficulty levels.
- **Tic-Tac-Toe** — play against an unbeatable minimax AI.
- **Rock Paper Scissors** — pick your throw; the computer picks randomly.

## Scores

Every game tracks **You vs Computer**. Named scores are saved to `scores.json`
and reload when you enter the same name again (even after a restart). Guest
scores last only for the session. The launcher shows your combined total across
all games.

Tap your name in the scoreboard to set it. The editor opens a dropdown of known
players — click one, type a new name, or leave it blank to play as Guest.

## Project layout

```
PopPopsGames.py      # HTTP server: routing, sessions, scoring, persistence
hangman.py           # Hangman game logic
tictactoe.py         # Tic-Tac-Toe game logic + minimax AI
rps.py               # Rock Paper Scissors game logic
words.py             # aggregates per-level word lists into WORDS_BY_LEVEL
words_easy.py        # \
words_medium.py      #  } one word list per difficulty
words_hard.py        #  /
words_expert.py      # /
static/
  index.html         # launcher (game selection + total score)
  style.css          # launcher styles
  launcher.js        # launcher JS
  hangman/           # Hangman page (index.html, style.css, script.js)
  tictactoe/         # Tic-Tac-Toe page
  rps/               # Rock Paper Scissors page
test_hangman.py      # unittest suite (logic, scoring, end-to-end HTTP)
scores.json          # saved player scores (created at runtime; gitignored)
```

## Customizing

- **Words:** edit the `WORDS` list in the per-level file (`words_easy.py`, etc.).
  To add or rename a level, update `LEVELS` and `WORDS_BY_LEVEL` in `words.py`.
- **Default difficulty:** change `DEFAULT_LEVEL` in `words.py`.
- **Hangman wrong-guess limit:** change `MAX_WRONG` in `hangman.py` (the SVG
  drawing has 6 parts, so values other than 6 won't reveal a full figure).
- **Port / host:** change `HOST` and `PORT` at the top of `PopPopsGames.py`.

## Tests

No third-party dependencies — just the standard library's `unittest`:

```bash
python -m unittest test_hangman
```

Covers game logic, scoring, and the HTTP API end to end for all three games.
Uses a temporary score file so your real `scores.json` is never touched.

## Notes

- In-progress games are kept in memory per browser session cookie, so an
  unfinished game resets when the server restarts. Named scores survive restarts;
  Guest scores do not.
- `ThreadingHTTPServer` handles multiple players or browser tabs simultaneously,
  each with their own independent game state.
