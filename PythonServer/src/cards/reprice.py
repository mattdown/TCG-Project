"""Repricing a set in place: the same cards and abilities, new costs or stats from new group prices.

The metagame loop (docs/roadmap.md, step 3) moves group prices (costing.GROUP_SCALE) many times;
regenerating the set each time would change every card, so the loop couldn't tell a price's effect
from a new draw. Instead each card moves by the change in its own price, the way the generator
turns a price into a card:
- an action's cost moves by the change in half its price, rounded as the generator rounds it;
- a unit's stats move by the change in its price in stat points, keeping its power-to-health
  shape; its cost moves only when its stats would fall below 1/1 (cost up, 2 stat points a mana)
  or rise past the stat cap (cost down).
Everything else (keywords, the neutral tax, rounding the generator did) carries over, because only
the difference is applied. A set records the scales it was priced with (`notes["group_scale"]`);
sets from before that was recorded were priced with today's GROUP_SCALE.
"""
from dataclasses import dataclass, replace

from src.cards.costing import GROUP_SCALE, price, price_group, round_points
from src.cards.schema import Card, CardSet
from src.cards.vanilla import MAX_STATS, MIN_STATS_VALUE

MAX_COST = 10
MIN_ACTION_COST = 1  # the generator rejects actions worth under 1 mana; repricing keeps them at 1


@dataclass
class Change:
    card: str  # card id
    group: str
    old: tuple[int, int, int]  # cost, power, health
    new: tuple[int, int, int]


def scales_of(card_set: CardSet) -> dict[str, float]:
    return dict(card_set.notes.get("group_scale", GROUP_SCALE))


def _shape(power: int, health: int, total: int) -> tuple[int, int]:
    """`total` stat points split in about the ratio of power to health, at least 1 and at most the cap each."""
    p = round(total * power / (power + health))
    p = min(max(p, 1, total - MAX_STATS["health"]), MAX_STATS["power"], total - 1)
    return p, total - p


def reprice_card(card: Card, old: dict[str, float], new: dict[str, float]) -> Card:
    if not card.abilities:
        return card
    ability = card.abilities[0]
    before, after = price(ability, card.type, old), price(ability, card.type, new)
    if card.type == "action":
        cost = card.cost + round_points(after / 2) - round_points(before / 2)
        return replace(card, cost=min(max(cost, MIN_ACTION_COST), MAX_COST))
    cost = card.cost
    total = card.power + card.health - (round_points(after) - round_points(before))
    while total < MIN_STATS_VALUE and cost < MAX_COST:  # can't pay for it: costs more
        cost, total = cost + 1, total + 2
    while total > sum(MAX_STATS.values()) and cost > 0:  # more stats than a unit can hold: costs less
        cost, total = cost - 1, total - 2
    total = min(max(total, MIN_STATS_VALUE), sum(MAX_STATS.values()))
    power, health = _shape(card.power, card.health, total)
    return replace(card, cost=cost, power=power, health=health)


def reprice(card_set: CardSet, scales: dict[str, float], name: str | None = None) -> tuple[CardSet, list[Change]]:
    """The set with each ability card moved by the change in its price from the set's own scales to
    GROUP_SCALE updated with `scales`, and the cards that changed."""
    old = scales_of(card_set)
    new = old | scales
    cards, changes = [], []
    for card in card_set.cards:
        moved = reprice_card(card, old, new)
        cards.append(moved)
        if moved != card:
            changes.append(Change(card.id, price_group(card.abilities[0], card.type),
                                  (card.cost, card.power, card.health), (moved.cost, moved.power, moved.health)))
    notes = card_set.notes | {"group_scale": new, "repriced_from": card_set.name}
    return CardSet(name or card_set.name, cards, notes), changes
