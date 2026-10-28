"""Ability subgraphs: how the network reads what a card does (docs/technical-plan.md section 5).

Every ability of a visible card becomes a few `ability` nodes: its decision graph (entry,
choose, effect, if, may, choose one, end) or, for a static ability, an entry plus one node per
modifier. Each node's features say what the step is (op, amounts, stat, keyword, duration,
target, the fields of its filter); none of them name a card, so unseen cards read the same way.

Edges, as index pairs local to one observation:
  part_of   node → its card (every node, so the card embedding hears all of its ability)
  next      control flow inside the graph (next step, branches, static modifiers)
  uses      a choose node → every step that refers to the name it binds ("it")
  matches   a node with a filter → every visible card the filter matches now (computed by
            the engine, so it follows the real rules: zones, Elusive, …)
  bound_to  a choose node → the cards already chosen for it, while the ability resolves

The fixed part (features, next, uses) is built once per card definition; the rest per state.
"""
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from src.cards.abilities import TRIGGERS
from src.cards.schema import Card
from src.game.decision_graph import compiled
from src.game.state import Frame
from src.game.terms import KEYWORDS

NODE_KINDS = ("entry", "choose", "effect", "if", "may", "choose_one", "end", "modifier")
ABILITY_KINDS = ("triggered", "on_resolve", "static")
CONDITIONS = ("count", "behind_on_health", "defeated", "in_play", "turn",
              "attacking", "defending", "damaged")
OPS = ("deal_damage", "remove_damage", "defeat", "return_to_hand", "freeze", "modify_stat", "grant_keyword",
       "draw", "discard", "heal_hero", "damage_hero", "gain_crystal", "discard_card")
DURATIONS = ("this_turn", "until_your_next_turn", "while_this_in_play", "permanent")
TARGETS = ("this", "you", "opponent", "ref", "all")
OWNERS = ("you", "opponent", "any")

FEATURES = (
    [f"kind:{k}" for k in NODE_KINDS] + [f"ability:{k}" for k in ABILITY_KINDS]
    + [f"event:{e}" for e in TRIGGERS] + [f"cond:{c}" for c in CONDITIONS] + ["at_least"]
    + [f"op:{o}" for o in OPS] + ["amount", "amount_all", "amount_per", "amount_cap"]
    + ["stat:power", "stat:health", "delta"] + [f"keyword:{k}" for k in KEYWORDS] + ["keyword_value"]
    + [f"duration:{d}" for d in DURATIONS] + [f"target:{t}" for t in TARGETS]
    + [f"owner:{o}" for o in OWNERS]
    + ["filter:damaged", "filter:cost_max", "filter:trait", "filter:not_this",
       "filter:hand", "count", "chooser:opponent", "options", "cost_reduction", "subject:this", "subject:all",
       "resolving"]
    # Added later go at the end: checkpoints from before feature names were saved rely on it (registry.py).
    + ["op:buff", "buff_power", "buff_health"]
    + ["op:summon", "token_power", "token_health"]
)
INDEX = {name: i for i, name in enumerate(FEATURES)}
NODE_DIM = len(FEATURES)


@dataclass(frozen=True)
class CardAbilityGraph:
    """The fixed part of one card definition's ability subgraph."""
    features: np.ndarray  # [n, NODE_DIM]
    next: np.ndarray  # [2, E] local node indices
    uses: np.ndarray  # [2, E]
    filters: tuple[tuple[int, dict], ...]  # (node, filter) for the matches edges
    names: dict  # (ability index, bound name) → node, for bound_to edges
    nodes: dict  # (ability index, compiled node index) → node, for the decision being resolved


def _set(vec: np.ndarray, name: str, value: float = 1.0):
    vec[INDEX[name]] = value


def _filter(vec: np.ndarray, f: dict):
    _set(vec, f"owner:{f.get('owner', 'any')}")
    _set(vec, "filter:damaged", float(bool(f.get("damaged"))))
    if "cost_max" in f:
        _set(vec, "filter:cost_max", f["cost_max"] / 10)
    _set(vec, "filter:trait", float("trait" in f))
    _set(vec, "filter:not_this", float(bool(f.get("not_this"))))
    _set(vec, "filter:hand", float(f.get("zone") == "hand"))


def _condition(vec: np.ndarray, cond: dict | None) -> dict | None:
    """Sets the condition's features; returns the filter it counts, if any."""
    if not cond:
        return None
    key = cond["this_is"] if "this_is" in cond else next(k for k in cond if k in CONDITIONS)
    _set(vec, f"cond:{key}")
    if "count" in cond:
        _set(vec, "at_least", cond["at_least"] / 3)
        return cond["count"]
    return None


def _amount(vec: np.ndarray, amount) -> dict | None:
    """Sets the amount's features; returns the filter a scaling amount counts, if any."""
    if amount == "all":
        _set(vec, "amount_all")
    elif isinstance(amount, int):
        _set(vec, "amount", amount / 5)
    elif isinstance(amount, dict) and "per" in amount:
        _set(vec, "amount_per")
        _set(vec, "amount", amount.get("k", 1) / 5)
        _set(vec, "amount_cap", amount["cap"] / 5)
        return amount["per"]
    return None


def _effect(vec: np.ndarray, step: dict) -> list[dict]:
    filters = []
    _set(vec, f"op:{step['effect']}")
    if (per := _amount(vec, step.get("amount"))) is not None:
        filters.append(per)
    if "stat" in step:
        _set(vec, f"stat:{step['stat']}")
        _set(vec, "delta", step["delta"] / 3)
    if step["effect"] == "summon":  # the amount is how many; a token keyword uses the keyword features
        token = step["token"]
        _set(vec, "token_power", token["power"] / 5)
        _set(vec, "token_health", token["health"] / 5)
        for keyword, value in token.get("keywords", {}).items():
            _set(vec, f"keyword:{keyword}")
            _set(vec, "keyword_value", value / 3)
    if step["effect"] == "buff":
        _set(vec, "buff_power", step["power"] / 3)
        _set(vec, "buff_health", step["health"] / 3)
        _set(vec, "duration:permanent")
    if "keyword" in step:
        _set(vec, f"keyword:{step['keyword']}")
        _set(vec, "keyword_value", step.get("value", 1) / 3)
    if step.get("duration") in DURATIONS:
        _set(vec, f"duration:{step['duration']}")
    target = step["target"]
    kind = target if isinstance(target, str) else next(iter(target))
    _set(vec, f"target:{kind}")
    if kind == "all":
        _filter(vec, target["all"])
        filters.append(target["all"])
    return filters


@lru_cache(maxsize=None)
def card_ability_graph(card: Card) -> CardAbilityGraph:
    rows, nxt, uses, filters, names, nodes = [], [], [], [], {}, {}

    def node(kind: str, ability_kind: str) -> tuple[int, np.ndarray]:
        vec = np.zeros(NODE_DIM, dtype=np.float32)
        _set(vec, f"kind:{kind}")
        _set(vec, f"ability:{ability_kind}")
        rows.append(vec)
        return len(rows) - 1, vec

    for a, ability in enumerate(compiled(card)):
        tree = ability.tree
        base = len(rows)
        refs = []  # (local node, name it refers to)
        for j, n in enumerate(ability.nodes):
            i, vec = node(n.kind, ability.kind)
            nodes[(a, j)] = i
            if n.kind == "entry":
                if "trigger" in tree:
                    _set(vec, f"event:{tree['trigger']['event']}")
                    if "filter" in tree["trigger"]:
                        filters.append((i, tree["trigger"]["filter"]))
                if (counted := _condition(vec, tree.get("condition"))) is not None:
                    filters.append((i, counted))
            elif n.kind == "choose":
                _filter(vec, n.data["filter"])
                _set(vec, "count", n.data.get("count", 1) / 2)
                _set(vec, "chooser:opponent", float(n.data.get("chooser", "you") != "you"))
                filters.append((i, n.data["filter"]))
                names[(a, n.name)] = i
            elif n.kind == "effect":
                filters += [(i, f) for f in _effect(vec, n.data)]
                if isinstance(n.data["target"], dict) and "ref" in n.data["target"]:
                    refs.append((i, n.data["target"]["ref"]))
            elif n.kind == "if":
                if (counted := _condition(vec, n.data)) is not None:
                    filters.append((i, counted))
                for key in ("defeated", "in_play"):
                    if key in n.data:
                        refs.append((i, n.data[key]))
            elif n.kind == "choose_one":
                _set(vec, "options", len(n.branches) / 3)
            for k in ([n.next] if n.next is not None else []) + list(n.branches):
                nxt.append((i, base + k))
        for i, name in refs:
            if (a, name) in names:
                uses.append((names[(a, name)], i))
        if ability.kind == "static":
            entry = base
            for m in tree["modifiers"]:
                i, vec = node("modifier", "static")
                nxt.append((entry, i))
                if "cost_reduction" in m:
                    _set(vec, "cost_reduction", m["cost_reduction"])
                    filters.append((i, {**m["filter"], "zone": "hand", "type": "any"}))
                    continue
                subject = m["subject"]
                _set(vec, "subject:this" if subject == "this" else "subject:all")
                if subject != "this":
                    _filter(vec, subject["all"])
                    filters.append((i, subject["all"]))
                if "keyword" in m:
                    _set(vec, f"keyword:{m['keyword']}")
                    _set(vec, "keyword_value", m.get("value", 1) / 3)
                else:
                    _set(vec, f"stat:{m['stat']}")
                    if (per := _amount(vec, m["amount"])) is not None:
                        filters.append((i, per))
                    elif isinstance(m["amount"], int):
                        _set(vec, "delta", m["amount"] / 3)

    def pairs(edges):
        return np.array(edges, dtype=np.int64).reshape(-1, 2).T.copy()

    features = np.stack(rows) if rows else np.zeros((0, NODE_DIM), dtype=np.float32)
    return CardAbilityGraph(features, pairs(nxt), pairs(uses), tuple(filters), names, nodes)


@dataclass
class AbilityNodes:
    """The ability nodes of one observation, with edges in local indices."""
    features: np.ndarray  # [M, NODE_DIM]
    card: np.ndarray  # [M]: the card node each ability node belongs to
    next: np.ndarray  # [2, E] node → node
    uses: np.ndarray  # [2, E] node → node
    matches: np.ndarray  # [2, E] node → card
    bound_to: np.ndarray  # [2, E] node → card
    by_frame_node: dict  # (card uid, ability index, compiled node index) → node


def ability_nodes(game, card_uids: list[int]) -> AbilityNodes:
    """Ability nodes for the visible cards, in order. Matches only ever point at visible cards."""
    node_of = {uid: i for i, uid in enumerate(card_uids)}
    feats, cards, nxt, uses, matches, bound, by_frame_node = [], [], [], [], [], [], {}
    offset = 0
    resolving = None
    if game.state.pending and isinstance(game.state.pending[-1], Frame):
        top = game.state.pending[-1]
        resolving = (top.source, top.ability, top.node)
    for c_index, uid in enumerate(card_uids):
        c = game.card(uid)
        g = card_ability_graph(c.card)
        n = len(g.features)
        if n == 0:
            continue
        f = g.features
        for (a, j), local in g.nodes.items():
            by_frame_node[(uid, a, j)] = offset + local
            if resolving == (uid, a, j):
                f = f.copy()
                f[local, INDEX["resolving"]] = 1.0
        feats.append(f)
        cards.append(np.full(n, c_index, dtype=np.int64))
        nxt.append(g.next + offset)
        uses.append(g.uses + offset)
        for local, flt in g.filters:
            for target in game.candidates(flt, c.owner, uid):
                if target in node_of:
                    matches.append((offset + local, node_of[target]))
        for frame in game.state.pending:
            if isinstance(frame, Frame) and frame.source == uid:
                for name, chosen in frame.bindings.items():
                    local = g.names.get((frame.ability, name))
                    if local is not None:
                        bound.extend((offset + local, node_of[t]) for t in chosen if t in node_of)
        offset += n

    def cat(parts, rows=2):
        return np.concatenate(parts, axis=1) if parts else np.zeros((rows, 0), dtype=np.int64)

    def pairs(edges):
        return np.array(edges, dtype=np.int64).reshape(-1, 2).T.copy()

    return AbilityNodes(
        features=np.concatenate(feats) if feats else np.zeros((0, NODE_DIM), dtype=np.float32),
        card=np.concatenate(cards) if cards else np.zeros(0, dtype=np.int64),
        next=cat(nxt), uses=cat(uses), matches=pairs(matches), bound_to=pairs(bound),
        by_frame_node=by_frame_node)
