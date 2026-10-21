"""Random legal decks, used for self-play so the agent sees as much of the card space as possible.

With ONE_ASPECT a deck is one aspect's cards plus neutral cards (no aspect), like a Hearthstone
class. It's off while aspects are only colours (assigned at random, no identity yet): decks
then draw from the whole set. The hero takes the deck's most common aspect either way (Game
infers it)."""
import random
from collections import Counter

from src.cards.schema import Card, CardSet
from src.game.terms import ASPECTS

DECK_SIZE = 30
MAX_COPIES = 2
ONE_ASPECT = False  # turn on once aspects have an identity (docs/technical-plan.md section 2)


def random_deck(card_set: CardSet, rng: random.Random, deck_size: int = DECK_SIZE,
                max_copies: int = MAX_COPIES, one_aspect: bool = ONE_ASPECT) -> list[Card]:
    """Cards drawn with a mild preference for cheap ones: from one aspect plus neutral cards
    when `one_aspect` (every card if the set is too small), otherwise from the whole set."""
    pool = list(card_set.cards)
    if one_aspect:
        aspect = rng.choice(ASPECTS)
        pool = [c for c in card_set.cards if c.aspects in ((), (aspect,))]
    if len(pool) * max_copies < deck_size:  # a small set (e.g. a coverage set): use every aspect
        pool = list(card_set.cards)
    if len(pool) * max_copies < deck_size:
        raise ValueError(f"not enough cards for a {deck_size}-card deck")
    weights = [1 / (c.cost ** 0.5 + 1) for c in pool]
    copies = Counter()
    deck = []
    while len(deck) < deck_size:
        card = rng.choices(pool, weights)[0]
        if copies[card.id] < max_copies:
            copies[card.id] += 1
            deck.append(card)
    return deck
