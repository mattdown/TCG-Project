"""Compiles ability trees (authoring form) into decision graphs the engine walks.

A decision graph is a flat tuple of nodes; node 0 is the entry. Every node says what happens
next, so resolution state is just (current node, chosen values): plain data that can be
cloned, saved or sent to the client mid-ability.

  entry       start; a triggered ability's condition is checked here
  choose      a player picks card(s) matching a filter, bound to a name   (decision)
  effect      changes the game
  if          branches[0] if the condition holds, else branches[1]
  may         yes → branches[0] (cost, then the "if you do" steps); no → branches[1]   (decision)
  choose_one  one branch per option                                       (decision)
  end         done

Costs that need a choice are desugared into choose + effect steps: an activated ability's
"exhaust another of your ready units" and "discard a card", and a chosen discard.
Static abilities aren't flows: they compile to an entry node only and are applied whenever
the engine calculates stats or keywords.
"""
from dataclasses import dataclass
from functools import lru_cache

from src.cards.schema import Card

DECISION_NODES = ("choose", "may", "choose_one")


@dataclass(frozen=True)
class Node:
    kind: str
    data: dict | None = None
    next: int | None = None
    branches: tuple[int, ...] = ()
    name: str | None = None  # for choose: the name the chosen cards are bound to


@dataclass(frozen=True)
class CompiledAbility:
    kind: str  # triggered | activated | on_resolve | static
    tree: dict
    nodes: tuple[Node, ...]


def _hand_card(name: str) -> dict:
    return {"choose": {"count": 1, "filter": {"owner": "you", "zone": "hand", "type": "any"}}, "as": name}


def _desugar(steps: list) -> list:
    """Turns a chosen discard into an explicit choice of which card to discard."""
    out = []
    for i, step in enumerate(steps):
        if step.get("effect") == "discard" and step.get("chosen") and step["target"] == "you":
            for j in range(step.get("amount", 1)):
                name = f"_discard{i}_{j}"
                out += [_hand_card(name), {"effect": "discard_card", "target": {"ref": name}}]
        elif "if" in step:
            out.append({**step, "then": _desugar(step["then"]), "else": _desugar(step.get("else", []))})
        elif "may" in step:
            out.append({**step, "may": _desugar(step["may"]), "if_you_do": _desugar(step.get("if_you_do", []))})
        elif "choose_one" in step:
            out.append({**step, "choose_one": [_desugar(b) for b in step["choose_one"]]})
        else:
            out.append(step)
    return out


def _cost_steps(cost: list) -> list:
    steps = []
    for c in cost:
        if "exhaust_another" in c:
            steps += [{"choose": {"count": 1, "filter": {"owner": "you", "exhausted": False, "not_this": True}},
                       "as": "_cost_unit"},
                      {"effect": "exhaust", "target": {"ref": "_cost_unit"}}]
        if "discard" in c:
            steps += [_hand_card("_cost_card"), {"effect": "discard_card", "target": {"ref": "_cost_card"}}]
    return steps


def compile_ability(tree: dict) -> CompiledAbility:
    nodes: list[dict] = [{"kind": "entry"}]

    def add(kind, **fields) -> int:
        nodes.append({"kind": kind, **fields})
        return len(nodes) - 1

    def sequence(steps: list, cont: int) -> int:
        first = cont
        for step in reversed(steps):
            first = one(step, first)
        return first

    def one(step: dict, cont: int) -> int:
        if "choose" in step:
            return add("choose", data=step["choose"], name=step["as"], next=cont)
        if "effect" in step:
            return add("effect", data=step, next=cont)
        if "if" in step:
            branches = (sequence(step["then"], cont), sequence(step.get("else", []), cont))
            return add("if", data=step["if"], branches=branches)
        if "may" in step:
            yes = sequence(step["may"] + step.get("if_you_do", []), cont)
            return add("may", data={"cost": step["may"]}, branches=(yes, cont))
        if "choose_one" in step:
            return add("choose_one", data={"options": step["choose_one"]},
                       branches=tuple(sequence(b, cont) for b in step["choose_one"]))
        raise ValueError(f"unknown step {step}")

    if tree["kind"] != "static":
        end = add("end")
        steps = _cost_steps(tree.get("cost", [])) + _desugar(tree["steps"])
        nodes[0]["next"] = sequence(steps, end)
    frozen = tuple(Node(n["kind"], n.get("data"), n.get("next"), tuple(n.get("branches", ())), n.get("name"))
                   for n in nodes)
    return CompiledAbility(tree["kind"], tree, frozen)


@lru_cache(maxsize=None)
def compiled(card: Card) -> tuple[CompiledAbility, ...]:
    """The card's abilities as decision graphs, compiled once per card definition."""
    return tuple(compile_ability(a) for a in card.abilities)
