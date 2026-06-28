"""Master test runner — runs all game test suites.

Run:
    python -m unittest test_games
    python test_games.py

Add a new game's test module to the `_MODULES` list when a new game is added.
"""

import unittest
import test_hangman
import test_tictactoe
import test_rps
import test_connectfour

_MODULES = (
    test_hangman,
    test_tictactoe,
    test_rps,
    test_connectfour,
)


def load_tests(loader, tests, pattern):
    for module in _MODULES:
        tests.addTests(loader.loadTestsFromModule(module))
    return tests


if __name__ == "__main__":
    unittest.main(verbosity=2)
