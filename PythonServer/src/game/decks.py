"""Random legal decks, used for self-play so the agent sees as much of the card space as possible.

Each deck focuses on FOCUS_JOBS jobs: FOCUS_SHARE of its units come from them, so abilities
about your own jobs ("your Bakers get +1 power") have something to work with. Cards without a
job (actions) are drawn as often as without a focus.

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
FOCUS_JOBS = 2  # 0 for no focus
FOCUS_SHARE = 0.7  # of a deck's units with a job


def random_deck(card_set: CardSet, rng: random.Random, deck_size: int = DECK_SIZE,
                max_copies: int = MAX_COPIES, one_aspect: bool = ONE_ASPECT, focus_jobs: int = FOCUS_JOBS,
                focus_share: float = FOCUS_SHARE) -> list[Card]:
    """Cards drawn with a mild preference for cheap ones: from one aspect plus neutral cards
    when `one_aspect` (every card if the set is too small), otherwise from the whole set, and
    with `focus_share` of the units from `focus_jobs` jobs."""
    pool = list(card_set.cards)
    if one_aspect:
        aspect = rng.choice(ASPECTS)
        pool = [c for c in card_set.cards if c.aspects in ((), (aspect,))]
    if len(pool) * max_copies < deck_size:  # a small set (e.g. a coverage set): use every aspect
        pool = list(card_set.cards)
    if len(pool) * max_copies < deck_size:
        raise ValueError(f"not enough cards for a {deck_size}-card deck")
    weights = [1 / (c.cost ** 0.5 + 1) for c in pool]
    if focus_jobs:
        weights = _focus(pool, weights, rng, focus_jobs, focus_share)
    copies = Counter()
    deck = []
    while len(deck) < deck_size:
        card = rng.choices(pool, weights)[0]
        if copies[card.id] < max_copies:
            copies[card.id] += 1
            deck.append(card)
    return deck


def _focus(pool: list[Card], weights: list[float], rng: random.Random, jobs: int, share: float) -> list[float]:
    """Re-weights units so `share` of the unit weight is on `jobs` jobs, picked in proportion to
    how many units have them. The total unit weight stays the same, so cards without a job keep
    their share of the deck."""
    counts = Counter(c.traits[0] for c in pool if c.traits)
    if len(counts) <= jobs:
        return weights
    focus = set()
    while len(focus) < jobs:
        focus.add(rng.choices(list(counts), list(counts.values()))[0])
    on = sum(w for c, w in zip(pool, weights) if c.traits and c.traits[0] in focus)
    off = sum(w for c, w in zip(pool, weights) if c.traits and c.traits[0] not in focus)
    total = on + off
    return [w if not c.traits else w * (share * total / on if c.traits[0] in focus else (1 - share) * total / off)
            for c, w in zip(pool, weights)]
