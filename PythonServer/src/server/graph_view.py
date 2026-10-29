"""The state graph as the human player's network would see it, for the client's GNN overlay.

Nodes and edges are the ones the GNN reads (src/graph/builder.py), from the human's point of
view, so nothing hidden appears. Reverse edges are left out: each forward edge stands for both
directions. Every node carries a short vector per layer: its GNN embedding averaged down to
VECTOR_DIM numbers, or its raw input features when there's no GNN to run.
"""
import numpy as np
import torch

from src.game.engine import Game
from src.graph.abilities import FEATURES
from src.graph.encode import observe

VECTOR_DIM = 16
# Feature prefixes that name what an ability node does, after its kind.
LABEL_PREFIXES = ("op:", "event:", "cond:")


def squash(v: np.ndarray, dim: int = VECTOR_DIM) -> list[float]:
    """Averages v down to dim numbers (zero-padded to a multiple of dim), rounded for JSON."""
    padded = np.zeros(-(-len(v) // dim) * dim, dtype=np.float32)
    padded[:len(v)] = v
    return [round(float(x), 3) for x in padded.reshape(dim, -1).mean(axis=1)]


def ability_label(features: np.ndarray) -> tuple[str, str]:
    """(kind, label) of an ability node from its features: "effect", "effect: deal_damage"."""
    names = [FEATURES[i] for i in np.flatnonzero(features)]
    kind = next(n.split(":", 1)[1] for n in names if n.startswith("kind:"))
    detail = [n.split(":", 1)[1] for n in names if n.startswith(LABEL_PREFIXES)]
    return kind, f"{kind}: {', '.join(detail)}" if detail else kind


def graph_view(game: Game, player: int, net=None) -> dict:
    obs = observe(game, player)
    e = obs.encoded
    n_cards, n_nodes = e.num_cards, e.num_nodes
    player_id, global_id, ability_id = n_cards, n_cards + 2, n_cards + 3

    if net is not None and getattr(net, "arch", None) == "gnn":
        with torch.no_grad():
            states = net.node_states(net.collate([e]))
        layers = [{t: x[t].cpu().numpy() for t in ("card", "player", "global", "ability")} for x in states]
        source = "gnn"
    else:
        layers = [{"card": np.concatenate([e.card_static, e.card_dynamic], axis=1), "player": e.player,
                   "global": e.global_[None], "ability": e.node_features}]
        source = "features"

    def vectors(node_type: str, i: int) -> list[list[float]]:
        return [squash(layer[node_type][i]) for layer in layers]

    nodes = []
    for i, uid in enumerate(obs.card_uids):
        c = game.card(uid)
        nodes.append({"id": i, "type": "card", "uid": uid, "card_id": c.card.id, "owner": int(e.card_owner[i]),
                      "zone": c.zone.name.lower(), "vectors": vectors("card", i)})
    for p in range(2):  # 0: the observing player, 1: the opponent
        nodes.append({"id": player_id + p, "type": "player", "owner": p, "vectors": vectors("player", p)})
    nodes.append({"id": global_id, "type": "global", "vectors": vectors("global", 0)})
    for i in range(n_nodes):
        kind, label = ability_label(e.node_features[i])
        nodes.append({"id": ability_id + i, "type": "ability", "card": int(e.node_card[i]), "kind": kind,
                      "label": label, "resolving": bool(e.node_features[i, FEATURES.index("resolving")]),
                      "vectors": vectors("ability", i)})

    edges = [("belongs_to", i, player_id + int(e.card_owner[i])) for i in range(n_cards)]
    mine = np.flatnonzero(e.card_in_play & (e.card_owner == 0))
    theirs = np.flatnonzero(e.card_in_play & (e.card_owner == 1))
    edges += [("faces", int(a), int(b)) for a in mine for b in theirs]
    edges += [("opposes", player_id, player_id + 1), ("in", player_id, global_id), ("in", player_id + 1, global_id)]
    edges += [("part_of", ability_id + i, int(c)) for i, c in enumerate(e.node_card)]
    for name, field, to_card in (("next", e.node_next, False), ("uses", e.node_uses, False),
                                 ("matches", e.node_matches, True), ("bound_to", e.node_bound, True)):
        edges += [(name, ability_id + int(s), int(d) if to_card else ability_id + int(d)) for s, d in field.T]

    return {"embedding": source, "layers": len(layers), "dim": VECTOR_DIM, "nodes": nodes,
            "edges": [{"type": t, "src": s, "dst": d} for t, s, d in edges]}
