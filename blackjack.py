"""Blackjack game logic for Pop Pop's Games — Player vs Dealer, 3-deck shoe."""

import random

SUITS = ("♠", "♥", "♦", "♣")
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
RED_SUITS = {"♥", "♦"}
NUM_DECKS = 3


def _new_deck():
    return [{"rank": r, "suit": s} for _ in range(NUM_DECKS) for s in SUITS for r in RANKS]


def _hand_value(hand):
    value, aces = 0, 0
    for card in hand:
        r = card["rank"]
        if r in ("J", "Q", "K"):
            value += 10
        elif r == "A":
            value += 11
            aces += 1
        else:
            value += int(r)
    while value > 21 and aces:
        value -= 10
        aces -= 1
    return value


def _is_blackjack(hand):
    return len(hand) == 2 and _hand_value(hand) == 21


def _can_deal(deck):
    return len(deck) >= 4


def new_game():
    deck = _new_deck()
    random.shuffle(deck)
    return {
        "deck":          deck,
        "player_hand":   [],
        "dealer_hand":   [],
        "phase":         "deal",   # deal | player | round_over | deck_over
        "player_wins":   0,
        "computer_wins": 0,
        "ties":          0,
        "round_result":  None,
        "over":          False,
        "scored":        False,
        "start_logged":  False,
    }


def deal(game):
    """Deal a new round. Transitions to deck_over if fewer than 4 cards remain."""
    if not _can_deal(game["deck"]):
        game["phase"] = "deck_over"
        game["over"]  = True
        return
    game["player_hand"] = [game["deck"].pop(), game["deck"].pop()]
    game["dealer_hand"] = [game["deck"].pop(), game["deck"].pop()]
    game["round_result"] = None

    player_bj = _is_blackjack(game["player_hand"])
    dealer_bj = _is_blackjack(game["dealer_hand"])
    if player_bj and dealer_bj:
        game["ties"]        += 1
        game["round_result"] = "push_blackjack"
        game["phase"]        = "round_over"
    elif player_bj:
        game["player_wins"] += 1
        game["round_result"] = "player_blackjack"
        game["phase"]        = "round_over"
    elif dealer_bj:
        game["computer_wins"] += 1
        game["round_result"]   = "dealer_blackjack"
        game["phase"]          = "round_over"
    else:
        game["phase"] = "player"


def hit(game):
    if game["phase"] != "player":
        return
    if not game["deck"]:
        stand(game)  # no cards left to draw — forced stand
        return
    game["player_hand"].append(game["deck"].pop())
    val = _hand_value(game["player_hand"])
    if val > 21:
        game["computer_wins"] += 1
        game["round_result"]   = "player_bust"
        game["phase"]          = "round_over"
    elif val == 21:
        stand(game)  # auto-stand — can't improve on 21


def stand(game):
    if game["phase"] != "player":
        return
    while _hand_value(game["dealer_hand"]) < 17 and game["deck"]:
        game["dealer_hand"].append(game["deck"].pop())
    pv = _hand_value(game["player_hand"])
    dv = _hand_value(game["dealer_hand"])
    if dv > 21:
        game["player_wins"] += 1
        game["round_result"] = "dealer_bust"
    elif pv > dv:
        game["player_wins"] += 1
        game["round_result"] = "player_higher"
    elif dv > pv:
        game["computer_wins"] += 1
        game["round_result"]   = "dealer_higher"
    else:
        game["ties"]        += 1
        game["round_result"] = "push"
    game["phase"] = "round_over"


def finalize(game):
    """Mark the deck as over so scoring can run (called when player leaves the page)."""
    if game["over"] or game["scored"]:
        return
    total = game["player_wins"] + game["computer_wins"] + game["ties"]
    if total == 0:
        return  # no hands played — nothing to score
    game["phase"] = "deck_over"
    game["over"]  = True


def game_state(game):
    reveal = game["phase"] != "player"
    if reveal or not game["dealer_hand"]:
        dealer_display = game["dealer_hand"]
        dealer_value   = _hand_value(game["dealer_hand"]) if game["dealer_hand"] else None
    else:
        dealer_display = game["dealer_hand"][:1] + [{"rank": "?", "suit": "?"}]
        dealer_value   = None
    return {
        "player_hand":     game["player_hand"],
        "dealer_hand":     dealer_display,
        "player_value":    _hand_value(game["player_hand"]) if game["player_hand"] else None,
        "dealer_value":    dealer_value,
        "phase":           game["phase"],
        "player_wins":     game["player_wins"],
        "computer_wins":   game["computer_wins"],
        "ties":            game["ties"],
        "round_result":    game["round_result"],
        "cards_remaining": len(game["deck"]),
        "over":            game["over"],
    }
