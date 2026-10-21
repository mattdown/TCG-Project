"""Heuristic generators for units without abilities.

generate_vanilla_set makes stats-only units; generate_keyword_set adds keywords and themed
names (mushroom species + job, see docs/theme.md). Each card gets a stat budget from its cost
and spends it on keywords first, then on power and health:

    value  = power + health + keyword values
    budget = 2 * cost + 1  (a 1-mana 1/2, a 3-mana 3/4: Hearthstone players' rule of thumb)

A share of cards are deliberately costed one point above or below budget. The deltas are
recorded in the card set's notes (never seen by the engine or the network), so a later cost
model can be checked on whether it finds them.
"""
import random

from src.cards.schema import Card, CardSet
from src.cards.theme import JOBS, SPECIES
from src.game.terms import ASPECTS, KEYWORDS

COST_WEIGHTS = {1: 10, 2: 16, 3: 18, 4: 16, 5: 13, 6: 10, 7: 8, 8: 5, 9: 3, 10: 2}
MAX_STATS = {"power": 12, "health": 12}
MIN_STATS_VALUE = 1 + 1  # 1 power, 1 health

# Relative weights for spending the budget on (power, health).
ARCHETYPES = {
    "balanced": {"power": 1.0, "health": 1.0},
    "attacker": {"power": 2.0, "health": 1.0},
    "defender": {"power": 1.0, "health": 2.0},
}

ADJECTIVES = [
    "Brave", "Silent", "Ashen", "Golden", "Hollow", "Restless", "Gentle", "Iron", "Wild", "Hidden",
    "Clever", "Weary", "Bright", "Crooked", "Distant", "Eager", "Frozen", "Gilded", "Humble", "Lucky",
    "Mossy", "Nimble", "Proud", "Quiet", "Rusty", "Stormy", "Tidal", "Velvet", "Wandering", "Young",
]
NOUNS = [
    "Scout", "Keeper", "Tinker", "Ranger", "Herald", "Warden", "Sailor", "Scholar", "Smith", "Piper",
    "Rider", "Hermit", "Sentinel", "Courier", "Duelist", "Gardener", "Lantern", "Navigator", "Oracle", "Pilgrim",
    "Rogue", "Squire", "Trickster", "Vagabond", "Weaver", "Alchemist", "Bard", "Captain", "Drifter", "Fox",
]


def stat_budget(cost: int) -> int:
    return 2 * cost + 1


def stat_value(power: int, health: int) -> int:
    return power + health


def _allocate(rng: random.Random, budget: int, weights: dict[str, float]) -> dict[str, int]:
    stats = {"power": 1, "health": 1}
    remaining = budget - stat_value(**stats)
    while remaining > 0:
        options = [s for s in stats if stats[s] < MAX_STATS[s]]
        if not options:
            break
        stat = rng.choices(options, [weights[s] for s in options])[0]
        stats[stat] += 1
        remaining -= 1
    return stats


def _unique_names(rng: random.Random, n: int) -> list[str]:
    names = [f"{a} {b}" for a in ADJECTIVES for b in NOUNS]
    if n > len(names):
        raise ValueError(f"only {len(names)} unique names available")
    return rng.sample(names, n)


def generate_vanilla_set(n: int = 200, seed: int = 0, mis_cost_rate: float = 0.3) -> CardSet:
    rng = random.Random(seed)
    names = _unique_names(rng, n)
    cards, deltas, archetypes = [], {}, {}
    for i in range(n):
        cost = rng.choices(list(COST_WEIGHTS), list(COST_WEIGHTS.values()))[0]
        delta = rng.choice((-1, 1)) if rng.random() < mis_cost_rate else 0
        archetype = rng.choice(list(ARCHETYPES))
        stats = _allocate(rng, stat_budget(cost) + delta, ARCHETYPES[archetype])
        card = Card(
            id=f"V1-{i + 1:03d}",
            name=names[i],
            type="unit",
            aspects=(ASPECTS[i % len(ASPECTS)],),
            cost=cost,
            **stats,
        )
        cards.append(card)
        # The real delta can differ from the intended one when a stat hits its cap.
        deltas[card.id] = stat_value(**stats) - stat_budget(cost)
        archetypes[card.id] = archetype
    notes = {
        "generator": "vanilla",
        "seed": seed,
        "budget": "value = power + health; budget = 2 * cost + 1",
        "budget_delta": deltas,
        "archetype": archetypes,
    }
    return CardSet(f"vanilla_{n}", cards, notes)


# Budget points per keyword (per point of value for Duelist and Armor), and value ranges.
KEYWORD_VALUE = {"guard": 1, "elusive": 2, "charge": 1, "duelist": 1, "armor": 2}
KEYWORD_RANGE = {"duelist": (1, 3), "armor": (1, 2)}
# Which keywords suit each archetype.
ARCHETYPE_KEYWORDS = {
    "balanced": {"guard": 1, "elusive": 1, "charge": 1, "duelist": 1, "armor": 1},
    "attacker": {"guard": 0, "elusive": 1, "charge": 3, "duelist": 3, "armor": 0},
    "defender": {"guard": 3, "elusive": 0, "charge": 0, "duelist": 0, "armor": 3},
}


def keyword_value(keywords: dict[str, int]) -> int:
    return sum(KEYWORD_VALUE[k] * v for k, v in keywords.items())


def _themed_names(rng: random.Random, n: int) -> list[tuple[str, str]]:
    """Unique (name, job) pairs, e.g. ("Oyster Fisher", "Fisher")."""
    pairs = [(f"{species} {job}", job) for species in SPECIES for job in JOBS]
    if n > len(pairs):
        raise ValueError(f"only {len(pairs)} unique names available")
    return rng.sample(pairs, n)


def generate_keyword_set(n: int = 200, seed: int = 0, keyword_rate: float = 0.45, mis_cost_rate: float = 0.3,
                         prefix: str = "K1") -> CardSet:
    """Units with stats, sometimes a keyword (rarely two), and themed names and jobs."""
    rng = random.Random(seed)
    names = _themed_names(rng, n)
    cards, deltas, archetypes = [], {}, {}
    for i in range(n):
        cost = rng.choices(list(COST_WEIGHTS), list(COST_WEIGHTS.values()))[0]
        delta = rng.choice((-1, 1)) if rng.random() < mis_cost_rate else 0
        archetype = rng.choice(list(ARCHETYPES))
        budget = stat_budget(cost) + delta

        keywords = {}
        wanted = (1 + (rng.random() < 0.15)) if rng.random() < keyword_rate else 0
        for _ in range(wanted):
            options = {k: w for k, w in ARCHETYPE_KEYWORDS[archetype].items() if w and k not in keywords}
            name = rng.choices(list(options), list(options.values()))[0]
            lo, hi = KEYWORD_RANGE.get(name, (1, 1))
            value = rng.randint(lo, hi)
            # Leave room for 1 power and 1 health.
            if keyword_value(keywords | {name: value}) <= budget - MIN_STATS_VALUE:
                keywords[name] = value

        stats = _allocate(rng, budget - keyword_value(keywords), ARCHETYPES[archetype])
        name, job = names[i]
        card = Card(
            id=f"{prefix}-{i + 1:03d}",
            name=name,
            type="unit",
            aspects=(ASPECTS[i % len(ASPECTS)],),
            cost=cost,
            traits=(job,),
            keywords=tuple(sorted(keywords.items())),
            **stats,
        )
        cards.append(card)
        deltas[card.id] = stat_value(**stats) + keyword_value(keywords) - stat_budget(cost)
        archetypes[card.id] = archetype
    notes = {
        "generator": "keywords",
        "seed": seed,
        "budget": "value = power + health + keyword values; budget = 2 * cost + 1",
        "keyword_value": {k: KEYWORD_VALUE[k] for k in KEYWORDS},
        "budget_delta": deltas,
        "archetype": archetypes,
    }
    return CardSet(f"keywords_{n}", cards, notes)
