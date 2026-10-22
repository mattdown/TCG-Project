"""A rough value for abilities, in stat-budget points, so cards with abilities can be costed.

This is a hand-written first guess, not data: it's a prior about how much things are worth,
and the learned cost model replaces it later (docs/technical-plan.md section 8). One budget
point is one point of power or health (see vanilla.py).
"""
from src.cards.quality import narrowing
from src.cards.vanilla import KEYWORD_VALUE, keyword_value

# Value of one use of each effect on one target, per point of its amount where it has one.
EFFECT_VALUE = {
    "deal_damage": 1.0, "remove_damage": 0.5, "defeat": 4.0, "return_to_hand": 3.0, "exhaust": 1.5, "freeze": 1.5,
    "draw": 2.0, "discard": 1.5, "heal_hero": 0.5, "damage_hero": 1.0, "gain_crystal": 2.5,
    "grant_keyword": 1.0, "discard_card": 1.0,
}
STAT_VALUE = {"power": 0.5, "health": 0.5}  # per point, for one turn
BUFF_VALUE = 1.0  # per lasting point: a unit's own stats are one point each
ALL_TARGETS = 2.0  # hitting everything that matches, instead of one chosen card
REMOVE_ALL_DAMAGE = 3  # treated as removing this much

# How often an ability gets used per card played, relative to "when played". Measured in self-play
# (`scripts/experiments.py fire`, 2026-10-22, league model): most triggers fire far less often than
# first guessed (start of turn was 2.5, attacking the hero 1.5).
TRIGGER_USES = {"on_play": 1.0, "on_defeated": 0.85, "on_attack_hero": 0.7, "on_attack": 1.2, "start_of_turn": 1.1,
                "end_of_turn": 2.0, "another_played": 0.8, "opposing_defeated": 1.0}
ACTIVATED_USES = 2.0
NARROW_FACTOR = 0.5  # per condition or restriction (quality.narrowing): each about halved the hits measured
IF_FACTOR = 0.5  # "if it was defeated, …"


def _amount(amount) -> float:
    if amount is None:
        return 1
    if amount == "all":
        return REMOVE_ALL_DAMAGE
    if isinstance(amount, int):
        return amount
    if "per" in amount:
        return amount["cap"] / 2  # about half the cap, on average
    return 2  # the stat of an earlier choice


def effect_value(step: dict, card_type: str | None = None) -> float:
    """The step's rough value; with `card_type`, what that card pays for it (see PRICE_SCALE)."""
    op = step["effect"]
    if op == "modify_stat":
        value = STAT_VALUE[step["stat"]] * abs(step["delta"])
    elif op == "buff":
        value = BUFF_VALUE * (step["power"] + step["health"])
    elif op == "summon":  # a body in play, like a unit's own stats and keywords
        token = step["token"]
        value = step["amount"] * (BUFF_VALUE * (token["power"] + token["health"])
                                  + keyword_value(token.get("keywords", {})))
    elif op == "grant_keyword":
        value = KEYWORD_VALUE[step["keyword"]] * step.get("value", 1) * 0.5  # for one turn
    else:
        value = EFFECT_VALUE[op] * _amount(step.get("amount"))
    if isinstance(step["target"], dict) and "all" in step["target"]:
        value *= ALL_TARGETS
    if card_type:
        value *= 1.0 if op in STAT_RATE else PRICE_SCALE[card_type]
    return value


def steps_value(steps: list, card_type: str | None = None) -> float:
    total = 0.0
    for step in steps:
        if "effect" in step:
            total += effect_value(step, card_type)
        elif "if" in step:
            total += IF_FACTOR * steps_value(step["then"], card_type)
        elif "may" in step:
            # What you get, less what you pay; never worth less than nothing, since you can decline.
            total += max(0.0, steps_value(step["if_you_do"], card_type) - steps_value(step["may"], card_type))
        elif "choose_one" in step:
            total += 1.1 * max(steps_value(b, card_type) for b in step["choose_one"])
    return total


def static_value(ability: dict, card_type: str | None = None) -> float:
    total = 0.0
    for m in ability["modifiers"]:
        if "cost_reduction" in m:
            total += 2.0
            continue
        many = m["subject"] != "this"
        if "keyword" in m:
            value = KEYWORD_VALUE[m["keyword"]] * m.get("value", 1)
        else:
            value = STAT_VALUE[m["stat"]] * 2 * abs(_amount(m["amount"]))  # lasting, not one turn
        total += value * (ALL_TARGETS if many else 1)
    return total * NARROW_FACTOR ** narrowing(ability) * (PRICE_SCALE[card_type] if card_type else 1.0)


def ability_value(ability: dict, card_type: str | None = None) -> float:
    """Rough value of one ability in budget points; with `card_type`, its price (see price)."""
    kind = ability["kind"]
    if kind == "static":
        return static_value(ability, card_type)
    value = steps_value(ability["steps"], card_type)
    if kind == "on_resolve":
        value *= NARROW_FACTOR ** narrowing(ability)
    elif kind == "triggered":
        value *= TRIGGER_USES[ability["trigger"]["event"]] * NARROW_FACTOR ** narrowing(ability)
    elif kind == "activated":
        value *= ACTIVATED_USES
        for cost in ability["cost"]:
            value -= 0.5 * cost.get("pay", 0) + (1.0 if "exhaust_another" in cost or "discard" in cost else 0.0)
    return max(value, 0.5)


# What a card pays for its ability, as a share of the rough value above: units pay in stats,
# actions in mana (one mana per two points). Lasting stats (STAT_RATE) pay the full value: the
# share corrects the table's overvalued one-shot effects, and a lasting point is worth what a
# unit's own stat point is. Measured in self-play (`scripts/experiments.py
# scale`, 2026-10-22): a deck tied with a copy whose abilities were swapped for stats (units) or
# whose actions were swapped for vanilla units (actions) at about these shares. The learned cost
# model replaces both.
PRICE_SCALE = {"unit": 0.4, "action": 0.2}
STAT_RATE = ("buff", "summon")


def price(ability: dict, card_type: str) -> float:
    """What a card with this ability pays for it, in budget points."""
    return ability_value(ability, card_type)
