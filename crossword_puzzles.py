"""Hand-authored crossword puzzles for the Kids Crossword game.

Each puzzle lists only its words (answer, clue, start position, direction) —
the server derives blocked cells and clue numbering from these placements.
Every puzzle here is built from a validated safe "block": one across word
crossed by short down words at non-adjacent columns, so crossing words never
create accidental extra letter-runs in the grid. The easy puzzles stack two
such blocks with a fully-blocked buffer row between them (no shared cells
between the two halves), which doubles the clue count without risking any
accidental adjacency between the halves.
"""

PUZZLES_BY_LEVEL = {
    "easy": [
        {
            "size": 7,
            "words": [
                {"answer": "APPLE", "clue": "A round fruit that keeps the doctor away",   "row": 0, "col": 0, "dir": "across"},
                {"answer": "ANT",   "clue": "A tiny bug that lives in a colony",           "row": 0, "col": 0, "dir": "down"},
                {"answer": "EGG",   "clue": "Comes from a chicken, cracked for breakfast", "row": 0, "col": 4, "dir": "down"},
                {"answer": "SHEEP", "clue": "A fluffy farm animal that says baa",          "row": 4, "col": 0, "dir": "across"},
                {"answer": "SUN",   "clue": "It shines in the sky during the day",         "row": 4, "col": 0, "dir": "down"},
                {"answer": "PIG",   "clue": "A pink farm animal that says oink",           "row": 4, "col": 4, "dir": "down"},
            ],
        },
        {
            "size": 7,
            "words": [
                {"answer": "HORSE", "clue": "An animal you can ride — it says neigh",              "row": 0, "col": 0, "dir": "across"},
                {"answer": "HEN",   "clue": "A girl chicken that lays eggs",                        "row": 0, "col": 0, "dir": "down"},
                {"answer": "EGG",   "clue": "Comes from a chicken, cracked for breakfast",          "row": 0, "col": 4, "dir": "down"},
                {"answer": "TIGER", "clue": "A big wild cat with orange and black stripes",         "row": 4, "col": 0, "dir": "across"},
                {"answer": "TOY",   "clue": "Something fun to play with",                           "row": 4, "col": 0, "dir": "down"},
                {"answer": "RUG",   "clue": "A soft covering on the floor",                         "row": 4, "col": 4, "dir": "down"},
            ],
        },
        {
            "size": 7,
            "words": [
                {"answer": "MOUSE", "clue": "A small furry animal that likes cheese",              "row": 0, "col": 0, "dir": "across"},
                {"answer": "MOM",   "clue": "Your mother",                                          "row": 0, "col": 0, "dir": "down"},
                {"answer": "EAR",   "clue": "You use it to hear",                                    "row": 0, "col": 4, "dir": "down"},
                {"answer": "ZEBRA", "clue": "A black and white striped animal from Africa",         "row": 4, "col": 0, "dir": "across"},
                {"answer": "ZOO",   "clue": "A place where you can see lions, tigers, and more",    "row": 4, "col": 0, "dir": "down"},
                {"answer": "ANT",   "clue": "A tiny bug that lives in a colony",                    "row": 4, "col": 4, "dir": "down"},
            ],
        },
    ],
    "medium": [
        {
            "size": 6,
            "words": [
                {"answer": "RABBIT", "clue": "A hopping animal with long ears",             "row": 2, "col": 0, "dir": "across"},
                {"answer": "RED",    "clue": "The color of a fire truck",                    "row": 2, "col": 0, "dir": "down"},
                {"answer": "BUS",    "clue": "A big yellow vehicle that takes kids to school", "row": 2, "col": 2, "dir": "down"},
                {"answer": "TREE",   "clue": "It has leaves, branches, and roots",            "row": 2, "col": 5, "dir": "down"},
            ],
        },
        {
            "size": 6,
            "words": [
                {"answer": "SPIDER", "clue": "A bug with eight legs that spins webs", "row": 2, "col": 0, "dir": "across"},
                {"answer": "SUN",    "clue": "It shines in the sky during the day",   "row": 2, "col": 0, "dir": "down"},
                {"answer": "ICE",    "clue": "Frozen water",                          "row": 2, "col": 2, "dir": "down"},
                {"answer": "RUG",    "clue": "A soft covering on the floor",          "row": 2, "col": 5, "dir": "down"},
            ],
        },
        {
            "size": 6,
            "words": [
                {"answer": "MONKEY", "clue": "A playful animal that loves bananas and swings from trees", "row": 2, "col": 0, "dir": "across"},
                {"answer": "MOM",    "clue": "Your mother",                              "row": 2, "col": 0, "dir": "down"},
                {"answer": "NET",    "clue": "Used to catch butterflies or fish",        "row": 2, "col": 2, "dir": "down"},
                {"answer": "YAK",    "clue": "A big shaggy animal from the mountains",   "row": 2, "col": 5, "dir": "down"},
            ],
        },
    ],
    "hard": [
        {
            "size": 7,
            "words": [
                {"answer": "DOLPHIN", "clue": "A smart, friendly animal that lives in the ocean and jumps out of the water", "row": 3, "col": 0, "dir": "across"},
                {"answer": "DOG", "clue": "A loyal pet that says woof",                        "row": 3, "col": 0, "dir": "down"},
                {"answer": "LEG", "clue": "You use it to walk and run",                        "row": 3, "col": 2, "dir": "down"},
                {"answer": "HAT", "clue": "You wear it on your head",                          "row": 3, "col": 4, "dir": "down"},
                {"answer": "NUT", "clue": "A hard-shelled snack, like an acorn or walnut",     "row": 3, "col": 6, "dir": "down"},
            ],
        },
        {
            "size": 7,
            "words": [
                {"answer": "PENGUIN", "clue": "A black and white bird that can't fly but loves to swim", "row": 3, "col": 0, "dir": "across"},
                {"answer": "PIG",  "clue": "A pink farm animal that says oink",                       "row": 3, "col": 0, "dir": "down"},
                {"answer": "GOAT", "clue": "A farm animal that likes to climb and eat almost anything", "row": 3, "col": 3, "dir": "down"},
                {"answer": "NUT",  "clue": "A hard-shelled snack, like an acorn or walnut",           "row": 3, "col": 6, "dir": "down"},
            ],
        },
        {
            "size": 7,
            "words": [
                {"answer": "GIRAFFE", "clue": "The tallest animal in the world, with a very long neck", "row": 3, "col": 0, "dir": "across"},
                {"answer": "GOAT", "clue": "A farm animal that likes to climb and eat almost anything", "row": 3, "col": 0, "dir": "down"},
                {"answer": "ANT",  "clue": "A tiny bug that lives in a colony",                        "row": 3, "col": 3, "dir": "down"},
                {"answer": "EGG",  "clue": "Comes from a chicken, cracked for breakfast",              "row": 3, "col": 6, "dir": "down"},
            ],
        },
    ],
}

LEVELS = ["easy", "medium", "hard"]
DEFAULT_LEVEL = "easy"
