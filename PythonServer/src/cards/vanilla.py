"""Heuristic generator for vanilla units: stats only, no keywords or abilities.

Each card gets a stat budget from its cost and spends it on power, health and score:

    value  = power + health + SCORE_VALUE * score
    budget = 2 * cost + 2, +1 if the card is not an energy source

A share of cards are deliberately costed one point above or below budget. The deltas are
recorded in the card set's notes (never seen by the engine or the network), so a later cost
model can be checked on whether it finds them.
"""
import random

from src.cards.schema import Card, CardSet
from src.game.terms import ASPECTS

COST_WEIGHTS = {1: 10, 2: 16, 3: 18, 4: 16, 5: 13, 6: 10, 7: 8, 8: 5, 9: 4}
SCORE_VALUE = 2
NON_ENERGY_BONUS = 1
ENERGY_SOURCE_RATE = 0.8
MAX_STATS = {"power": 10, "health": 10, "score": 4}
STAT_COST = {"power": 1, "health": 1, "score": SCORE_VALUE}

# Relative weights for spending the budget on (power, health, score).
ARCHETYPES = {
    "balanced": {"power": 1.0, "health": 1.0, "score": 1.0},
    "attacker": {"power": 2.0, "health": 1.0, "score": 0.5},
    "defender": {"power": 1.0, "health": 2.0, "score": 0.5},
    "scorer": {"power": 0.6, "health": 0.8, "score": 1.6},
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


def stat_budget(cost: int, energy_source: bool) -> int:
    return 2 * cost + 2 + (0 if energy_source else NON_ENERGY_BONUS)


def stat_value(power: int, health: int, score: int) -> int:
    return power + health + SCORE_VALUE * score


def _allocate(rng: random.Random, budget: int, weights: dict[str, float]) -> dict[str, int]:
    stats = {"power": 1, "health": 1, "score": 0}
    remaining = budget - stat_value(**stats)
    while remaining > 0:
        options = [s for s in stats if STAT_COST[s] <= remaining and stats[s] < MAX_STATS[s]]
        if not options:
            break
        stat = rng.choices(options, [weights[s] for s in options])[0]
        stats[stat] += 1
        remaining -= STAT_COST[stat]
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
        energy_source = rng.random() < ENERGY_SOURCE_RATE
        delta = rng.choice((-1, 1)) if rng.random() < mis_cost_rate else 0
        archetype = rng.choice(list(ARCHETYPES))
        stats = _allocate(rng, stat_budget(cost, energy_source) + delta, ARCHETYPES[archetype])
        card = Card(
            id=f"V1-{i + 1:03d}",
            name=names[i],
            type="unit",
            aspects=(ASPECTS[i % len(ASPECTS)],),
            energy_source=energy_source,
            cost=cost,
            **stats,
        )
        cards.append(card)
        # The real delta can differ from the intended one when a stat hits its cap.
        deltas[card.id] = stat_value(**stats) - stat_budget(cost, energy_source)
        archetypes[card.id] = archetype
    notes = {
        "generator": "vanilla",
        "seed": seed,
        "budget": "value = power + health + 2 * score; budget = 2 * cost + 2, +1 if not an energy source",
        "budget_delta": deltas,
        "archetype": archetypes,
    }
    return CardSet(f"vanilla_{n}", cards, notes)
