"""Quality tests for generated abilities (docs/ability-generation.md).

validate() in abilities.py says whether an ability is legal. These tests say whether it is
worth generating. Each one looks only at the shape of the tree, never at particular effects,
so they keep working as the grammar grows. They are a cheap first filter: self-play
measurements and the learned cost model take over later.
"""
import json

MAX_COMPLEXITY = 4
ACTION_COMPLEXITY = 2  # extra nodes for actions: an action is only its ability
MAX_NARROWING = 1
RESTRICTIONS = ("damaged", "cost_max", "trait")


def complexity(ability: dict) -> int:
    """Nodes in the tree: each step (choice, effect, if, may, choose one), the condition and
    each static modifier."""
    def steps(seq: list) -> int:
        total = 0
        for step in seq:
            total += 1
            for key in ("then", "else", "may", "if_you_do"):
                total += steps(step.get(key, []))
            for branch in step.get("choose_one", []):
                total += steps(branch)
        return total

    total = 1 if ability.get("condition") else 0
    if ability["kind"] == "static":
        return total + len(ability["modifiers"])
    return total + steps(ability["steps"])


def narrowing(ability: dict) -> int:
    """Things that must line up before the ability does anything: a condition, and each
    restriction (damaged, cost, job) on a filter that picks cards. Each roughly halves how often
    an ability hits in self-play (`scripts/experiments.py fire`). Filters inside a condition or
    a "for each" count aren't counted again: they don't stop the ability, only size it."""
    def walk(node, key=None) -> int:
        if key in ("condition", "per", "if"):
            return 0
        if isinstance(node, list):
            return sum(walk(n) for n in node)
        if not isinstance(node, dict):
            return 0
        total = sum(1 for r in RESTRICTIONS if node.get(r)) if "owner" in node else 0
        return total + sum(walk(v, k) for k, v in node.items())

    return (1 if ability.get("condition") else 0) + walk(ability)


def _touches(step: dict) -> set[str]:
    """The cards a step acts on or asks about, by name ("this" for the card itself)."""
    if "effect" in step:
        target = step["target"]
        if target == "this":
            return {"this"}
        if isinstance(target, dict) and "ref" in target:
            return {target["ref"]}
    if "if" in step and "defeated" in step["if"]:
        return {step["if"]["defeated"]}
    return set()


def disconnected_steps(seq: list) -> list[str]:
    """Every step after the first must act on a card an earlier step acted on, so an ability
    is one idea rather than unrelated effects side by side. Choices only name a card, so
    they don't count as steps here. "You may … if you do" and choose one connect their parts
    by construction; the parts are checked on their own."""
    problems, seen, first = [], set(), True
    for step in seq:
        if "choose" in step:
            continue
        touched = _touches(step)
        if not first and not touched & seen:
            label = step.get("effect") or next(k for k in ("if", "may", "choose_one") if k in step)
            problems.append(f"'{label}' isn't connected to the steps before it")
        seen |= touched
        first = False
        for key in ("then", "else", "may", "if_you_do"):
            problems += disconnected_steps(step.get(key, []))
        for branch in step.get("choose_one", []):
            problems += disconnected_steps(branch)
    return problems


def _numbers(tree) -> list[int]:
    if isinstance(tree, bool):
        return []
    if isinstance(tree, int):
        return [abs(tree)]
    if isinstance(tree, dict):
        return [n for key in sorted(tree) for n in _numbers(tree[key])]
    if isinstance(tree, list):
        return [n for item in tree for n in _numbers(item)]
    return []


def skeleton(tree, abstract_traits: bool = False) -> str:
    """The tree with every number replaced by '#' (and optionally every job by 'JOB'): two
    abilities with the same skeleton differ only in their numbers."""
    def strip(t, key=None):
        if isinstance(t, bool):
            return t
        if isinstance(t, int):
            return "#"
        if abstract_traits and key == "trait":
            return "JOB"
        if isinstance(t, dict):
            return {k: strip(v, k) for k, v in t.items()}
        if isinstance(t, list):
            return [strip(v) for v in t]
        return t
    return json.dumps(strip(tree), sort_keys=True)


def dominated_options(ability: dict) -> list[str]:
    """In a choose one, an option that has the same shape as another and is no bigger in any
    number is never worth picking ("draw 2 cards or draw a card"). Every number in the grammar is
    better bigger for the side that chooses it (more damage, more cards, a higher cost limit),
    so this needs no knowledge of particular effects. Options of different shapes need a value
    model to compare: the learned cost model, or how often the trained agent picks each one."""
    problems = []

    def walk(seq):
        for step in seq:
            for key in ("then", "else", "may", "if_you_do"):
                walk(step.get(key, []))
            branches = step.get("choose_one", [])
            for branch in branches:
                walk(branch)
            for i, a in enumerate(branches):
                for j, b in enumerate(branches):
                    if i < j and skeleton(a) == skeleton(b):
                        na, nb = _numbers(a), _numbers(b)
                        if all(x >= y for x, y in zip(na, nb)) or all(y >= x for x, y in zip(na, nb)):
                            problems.append(f"choose one: option {j + 1 if na >= nb else i + 1} "
                                            f"is never better than option {i + 1 if na >= nb else j + 1}")

    walk(ability.get("steps", []))
    return problems


def quality_problems(ability: dict, max_complexity: int = MAX_COMPLEXITY) -> list[str]:
    """Problems that make an ability not worth generating; empty means it passes."""
    problems = []
    size = complexity(ability)
    if size > max_complexity:
        problems.append(f"too complex: {size} nodes (budget {max_complexity})")
    if (n := narrowing(ability)) > MAX_NARROWING:
        problems.append(f"too narrow: {n} conditions or restrictions (budget {MAX_NARROWING})")
    problems += disconnected_steps(ability.get("steps", []))
    problems += dominated_options(ability)
    return problems
