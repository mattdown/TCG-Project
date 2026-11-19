"""Random legal decks, used for self-play so the agent sees as much of the card space as possible.

Each deck focuses on FOCUS_JOBS jobs: FOCUS_SHARE of its units come from them, so abilities
about your own jobs ("your Bakers get +1 power") have something to work with. Cards without a
job (actions) are drawn as often as without a focus.

With one_aspect a deck is one aspect's cards plus neutral cards (no aspect), like a Hearthstone
class. By default that's on for sets generated with classes (src/cards/classes.py) and off for
older sets, whose aspects are only colours (assigned at random): their decks draw from the
whole set. The hero takes the deck's most common aspect either way (Game
infers it)."""
import random
from collections import Counter

from src.cards.schema import Card, CardSet
from src.game.terms import ASPECTS

DECK_SIZE = 30
MAX_COPIES = 2
ONE_ASPECT = None  # None: one aspect for sets made with classes, the whole set otherwise
CLASS_SHARE = 0.65  # one-aspect decks: share of the draw weight on the class's own cards (neutrals the rest)
FOCUS_JOBS = 2  # 0 for no focus
FOCUS_SHARE = 0.7  # of a deck's units with a job


def has_classes(card_set: CardSet) -> bool:
    return "classes" in card_set.notes


def class_pool(card_set: CardSet, aspect: str | None) -> list[Card]:
    """What a deck of this class can use: its cards and the neutral ones."""
    return [c for c in card_set.cards if c.aspects in ((), (aspect,))]


def deck_class(deck) -> str | None:
    """A deck's class: its most common aspect (None if it has only neutral cards)."""
    counts = Counter(c.aspects[0] for c in deck if c.aspects)
    return counts.most_common(1)[0][0] if counts else None


def random_deck(card_set: CardSet, rng: random.Random, deck_size: int = DECK_SIZE,
                max_copies: int = MAX_COPIES, one_aspect: bool | None = ONE_ASPECT, focus_jobs: int = FOCUS_JOBS,
                focus_share: float = FOCUS_SHARE, class_share: float = CLASS_SHARE) -> list[Card]:
    """Cards drawn with a mild preference for cheap ones: from one aspect plus neutral cards
    when `one_aspect` (every card if the set is too small), otherwise from the whole set, and
    with `focus_share` of the units from `focus_jobs` jobs. A one-aspect deck puts `class_share`
    of its draw weight on the class's cards: neutrals outnumber a class's cards about 2.5 to 1,
    so drawing them alike gave decks only a third class cards."""
    pool = list(card_set.cards)
    if one_aspect is None:
        one_aspect = has_classes(card_set)
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
    if one_aspect:
        own = sum(w for c, w in zip(pool, weights) if c.aspects)
        neutral = sum(w for c, w in zip(pool, weights) if not c.aspects)
        if own and neutral:
            weights = [w * (class_share / own if c.aspects else (1 - class_share) / neutral)
                       for c, w in zip(pool, weights)]
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
