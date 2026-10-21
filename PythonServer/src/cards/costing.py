"""A rough value for abilities, in stat-budget points, so cards with abilities can be costed.

This is a hand-written first guess, not data: it's a prior about how much things are worth,
and the learned cost model replaces it later (docs/technical-plan.md section 8). One budget
point is one point of power or health (see vanilla.py).
"""
from src.cards.vanilla import KEYWORD_VALUE

# Value of one use of each effect on one target, per point of its amount where it has one.
EFFECT_VALUE = {
    "deal_damage": 1.0, "remove_damage": 0.5, "defeat": 4.0, "return_to_hand": 3.0, "exhaust": 1.5, "freeze": 1.5,
    "draw": 2.0, "discard": 1.5, "heal_hero": 0.5, "damage_hero": 1.0, "gain_crystal": 2.5,
    "grant_keyword": 1.0, "discard_card": 1.0,
}
STAT_VALUE = {"power": 0.5, "health": 0.5}  # per point, for one turn
ALL_TARGETS = 2.0  # hitting everything that matches, instead of one chosen card
REMOVE_ALL_DAMAGE = 3  # treated as removing this much

# How often an ability gets used, roughly.
TRIGGER_USES = {"on_play": 1.0, "on_defeated": 0.7, "on_attack_hero": 1.5, "on_attack": 1.5, "start_of_turn": 2.5,
                "end_of_turn": 2.5, "another_played": 1.5, "opposing_defeated": 1.5}
ACTIVATED_USES = 2.0
CONDITION_FACTOR = 0.6  # an ability that only works sometimes
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


def effect_value(step: dict) -> float:
    op = step["effect"]
    if op == "modify_stat":
        value = STAT_VALUE[step["stat"]] * abs(step["delta"])
    elif op == "grant_keyword":
        value = KEYWORD_VALUE[step["keyword"]] * step.get("value", 1) * 0.5  # for one turn
    else:
        value = EFFECT_VALUE[op] * _amount(step.get("amount"))
    if isinstance(step["target"], dict) and "all" in step["target"]:
        value *= ALL_TARGETS
    return value


def steps_value(steps: list) -> float:
    total = 0.0
    for step in steps:
        if "effect" in step:
            total += effect_value(step)
        elif "if" in step:
            total += IF_FACTOR * steps_value(step["then"])
        elif "may" in step:
            # What you get, less what you pay; never worth less than nothing, since you can decline.
            total += max(0.0, steps_value(step["if_you_do"]) - steps_value(step["may"]))
        elif "choose_one" in step:
            total += 1.1 * max(steps_value(b) for b in step["choose_one"])
    return total


def static_value(ability: dict) -> float:
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
    if ability.get("condition"):
        total *= CONDITION_FACTOR
    return total


def ability_value(ability: dict) -> float:
    """Rough value of one ability in budget points."""
    kind = ability["kind"]
    if kind == "static":
        return static_value(ability)
    value = steps_value(ability["steps"])
    if kind == "triggered":
        value *= TRIGGER_USES[ability["trigger"]["event"]]
        if ability.get("condition"):
            value *= CONDITION_FACTOR
    elif kind == "activated":
        value *= ACTIVATED_USES
        for cost in ability["cost"]:
            value -= 0.5 * cost.get("pay", 0) + (1.0 if "exhaust_another" in cost or "discard" in cost else 0.0)
    return max(value, 0.5)
