"""Word lists for the Hangman game, grouped by difficulty.

Each difficulty lives in its own module (``words_easy``, ``words_medium``,
``words_hard``, ``words_expert``). Edit those lists to change the words for a
level. This module just gathers them into ``WORDS_BY_LEVEL`` for the server.
"""

from words_easy import WORDS as EASY
from words_medium import WORDS as MEDIUM
from words_hard import WORDS as HARD
from words_expert import WORDS as EXPERT

# Difficulty levels in increasing order. LEVELS also defines what the UI shows.
LEVELS = ["easy", "medium", "hard", "expert"]

WORDS_BY_LEVEL = {
    "easy": EASY,
    "medium": MEDIUM,
    "hard": HARD,
    "expert": EXPERT,
}

# Level used when none is specified (e.g. the first game of a session). The
# client remembers each player's last-used level and restores it on load.
DEFAULT_LEVEL = "easy"
