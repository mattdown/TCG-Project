"""Random legal decks, used for self-play so the agent sees as much of the card space as possible."""
import random
from collections import Counter

from src.cards.schema import Card, CardSet
from src.game.terms import ASPECTS

DECK_SIZE = 60
MAX_COPIES = 4


def random_deck(card_set: CardSet, rng: random.Random, deck_size: int = DECK_SIZE,
                max_copies: int = MAX_COPIES) -> list[Card]:
    """One or two aspects, then cards drawn with a mild preference for cheap ones."""
    aspects = set(rng.sample(ASPECTS, 2 if rng.random() < 0.8 else 1))
    pool = [c for c in card_set.cards if set(c.aspects) <= aspects]
    if len(pool) * max_copies < deck_size:
        raise ValueError(f"not enough cards in aspects {sorted(aspects)} for a {deck_size}-card deck")
    weights = [1 / (c.cost ** 0.5 + 1) for c in pool]
    copies = Counter()
    deck = []
    while len(deck) < deck_size:
        card = rng.choices(pool, weights)[0]
        if copies[card.id] < max_copies:
            copies[card.id] += 1
            deck.append(card)
    return deck
