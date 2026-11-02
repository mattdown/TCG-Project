"""The state graph as the human player's network would see it, for the client's GNN overlay.

Nodes and edges are the ones the GNN reads (src/graph/builder.py), from the human's point of
view, so nothing hidden appears. Reverse edges are left out: each forward edge stands for both
directions. Every node carries a short vector per layer: its GNN embedding averaged down to
VECTOR_DIM numbers, or its raw input features when there's no GNN to run.

Also what the two heads read. The policy head scores each legal action from its type and the
final embeddings of its actor and target cards, the ability node being decided (context), the
first node of a chosen option, and the global node. The value head reads the global node and
both player nodes. Actions are only sent for the human's own decisions: the AI's would need its
observation, which includes its hand.

node_view goes deeper for one node: its named input features, the stages that turn them
into an embedding, and at each layer the messages it takes in along each edge type, with the
attention it gives each neighbour. layer_view goes deeper again, into one layer for one node:
every step of GATv2 per edge type and head, then the sum, ReLU, residual and LayerNorm.
"""
import numpy as np
import torch
import torch.nn.functional as F

from src.game.engine import Game, describe_action
from src.graph.abilities import FEATURES
from src.graph.builder import ABILITY_EDGES
from src.graph.encode import CARD_DYNAMIC_FEATURES, CARD_STATIC_FEATURES, GLOBAL_FEATURES, PLAYER_FEATURES, observe

VECTOR_DIM = 4
DETAIL_DIM = 16  # numbers per vector in node_view
# Reverse edge types → the forward type the overlay draws (faces and opposes go both ways already).
SHOWN_AS = {"has_card": "belongs_to", "has": "in",
            **{reverse[1]: forward[1] for forward, reverse in ABILITY_EDGES.values()}}
READ_BY = {"card": ["policy: actor", "policy: target"], "ability": ["policy: context", "policy: option"],
           "global": ["policy: global", "value: global"]}
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

    probabilities, value = [None] * e.num_actions, None
    if net is not None and getattr(net, "arch", None) == "gnn":
        batch = net.collate([e])
        with torch.no_grad():
            states = net.node_states(batch)
            logits, _, values = net(batch)
        layers = [{t: x[t].cpu().numpy() for t in ("card", "player", "global", "ability")} for x in states]
        source = "gnn"
        if e.num_actions:
            probabilities = [round(float(p), 4) for p in logits.softmax(-1)]
        value = round(float(values[0]), 4)
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

    def card_node(i) -> int | None:
        return int(i) if i >= 0 else None

    def ability_node(i) -> int | None:
        return ability_id + int(i) if i >= 0 else None

    actions = [{"index": i, "type": a.to_dict()["type"], "text": describe_action(game, a),
                "actor": card_node(e.action_actor[i]), "target": card_node(e.action_target[i]),
                "context": ability_node(e.action_context[i]), "option": ability_node(e.action_option[i]),
                "global": global_id, "probability": probabilities[i]}
               for i, a in enumerate(obs.actions)]

    return {"embedding": source, "layers": len(layers), "dim": VECTOR_DIM, "nodes": nodes,
            "edges": [{"type": t, "src": s, "dst": d} for t, s, d in edges],
            "actions": actions, "value": {"estimate": value, "nodes": [global_id, player_id, player_id + 1]}}


def _locate(e, node: int) -> tuple[str, int, dict]:
    """A graph_view node id → (node type, index within its type, each type's first id)."""
    n_cards = e.num_cards
    first = {"card": 0, "player": n_cards, "global": n_cards + 2, "ability": n_cards + 3}
    if not 0 <= node < n_cards + 3 + e.num_nodes:
        raise ValueError(f"no node {node}")
    node_type = ("card" if node < n_cards else "player" if node < n_cards + 2
                 else "global" if node == n_cards + 2 else "ability")
    return node_type, node - first[node_type], first


def node_view(game: Game, player: int, node: int, net=None) -> dict:
    """One node of graph_view (same ids): what goes into its embedding and how, layer by layer."""
    obs = observe(game, player)
    e = obs.encoded
    node_type, i, first = _locate(e, node)

    def named(name: str, names, values) -> dict:
        return {"name": name, "dim": len(names),
                "features": [{"name": n, "value": round(float(v), 3)} for n, v in zip(names, values) if v != 0]}

    inputs = {
        "card": lambda: [named("static", CARD_STATIC_FEATURES, e.card_static[i]),
                         named("dynamic", CARD_DYNAMIC_FEATURES, e.card_dynamic[i])],
        "player": lambda: [named("features", PLAYER_FEATURES, e.player[i])],
        "global": lambda: [named("features", GLOBAL_FEATURES, e.global_)],
        "ability": lambda: [named("features", FEATURES, e.node_features[i])],
    }[node_type]()
    read_by = READ_BY.get(node_type, ["value: you" if i == 0 else "value: opponent"])
    view = {"id": node, "type": node_type, "embedding": "features", "input": inputs, "stages": [], "layers": [],
            "read_by": read_by, "hidden": None, "heads": None}
    if net is None or getattr(net, "arch", None) != "gnn":
        return view

    batch = net.collate([e])
    messages = []
    with torch.no_grad():
        states = net.node_states(batch, messages)
        encoded = net.card_encoder(batch["card"].x_static) if node_type == "card" else None
    hidden = states[0][node_type].size(-1)

    def vector(t: torch.Tensor) -> list[float]:
        return squash(t.cpu().numpy(), DETAIL_DIM)

    projected = vector(states[0][node_type][i])
    if node_type == "card":
        view["stages"] = [
            {"name": "card encoder", "op": "mlp", "dim": hidden, "vector": vector(encoded[i])},
            {"name": "+ dynamic", "op": "concat", "dim": hidden + len(CARD_DYNAMIC_FEATURES), "vector": None},
            {"name": "projection", "op": "linear", "dim": hidden, "vector": projected}]
    elif node_type == "ability":
        view["stages"] = [{"name": "ability encoder", "op": "mlp", "dim": hidden, "vector": projected}]
    else:
        view["stages"] = [{"name": "projection", "op": "linear", "dim": hidden, "vector": projected}]

    def overlay_id(t: str, local: int) -> int:
        return first[t] + local

    for depth, layer in enumerate(messages, start=1):
        incoming = []
        for (src, rel, dst), (h, edge_index, alpha) in layer.items():
            if dst != node_type:
                continue
            into = (edge_index[1] == i).nonzero().flatten()
            if len(into) == 0:
                continue
            neighbours = sorted(({"node": overlay_id(src, int(edge_index[0, k])), "attention": round(float(alpha[k]), 3)}
                                 for k in into), key=lambda n: -n["attention"])
            incoming.append({"type": rel, "shown_as": SHOWN_AS.get(rel, rel),
                             "message": round(float(h[i].norm()), 3), "neighbours": neighbours})
        view["layers"].append({"dim": hidden, "vector": vector(states[depth][node_type][i]), "incoming": incoming})
    view.update(embedding="gnn", hidden=hidden, heads=net.hparams["heads"])
    return view


def layer_view(game: Game, player: int, node: int, layer: int, net) -> dict:
    """One GNN layer (1-based) for one node, step by step.

    Per edge type r into the node, GATv2 with H heads of C numbers, each head's numbers sent in
    full: each neighbour j's value W_l·x_j and this node's query W_r·x_i; per head a score a·LeakyReLU(W_l·x_j + W_r·x_i),
    softmax over the neighbours to attention; each neighbour's weighted value attention·W_l·x_j and
    their sum per head; the message is those sums, heads joined end to end, plus a bias. The messages of every edge type are added,
    then the layer's output is LayerNorm(x_i + ReLU(sum)). Recomputed here from the model's own
    weights, step by step (the tests check it matches the forward pass).
    """
    if net is None or getattr(net, "arch", None) != "gnn":
        raise ValueError("no GNN model on the server")

    def per_head(t: torch.Tensor) -> list[list[float]]:
        """A [heads, numbers] tensor in full: each head's own numbers, which the popup shows one head at a time."""
        return [[round(float(v), 3) for v in head] for head in t]

    if not 1 <= layer <= len(net.convs):
        raise ValueError(f"no layer {layer}")
    e = observe(game, player).encoded
    node_type, i, first = _locate(e, node)
    batch = net.collate([e])
    with torch.no_grad():
        x = net.node_states(batch)[layer - 1]
        conv, norm = net.convs[layer - 1], net.norms[layer - 1][node_type]
        x_i = x[node_type][i]
        total = torch.zeros_like(x_i)
        edge_types = []
        for (src, rel, dst), gat in conv.convs.items():
            edge_index = batch.edge_index_dict[(src, rel, dst)]
            senders = edge_index[0, edge_index[1] == i] if dst == node_type else edge_index[0, :0]
            if len(senders) == 0:
                continue
            H, C = gat.heads, gat.out_channels
            values = gat.lin_l(x[src][senders]).view(-1, H, C)
            query = gat.lin_r(x_i).view(H, C)
            scores = (F.leaky_relu(values + query, gat.negative_slope) * gat.att).sum(-1)  # [k, H]
            attention = scores.softmax(0)
            weighted = attention.unsqueeze(-1) * values  # [k, H, C]
            heads = weighted.sum(0)
            message = heads.reshape(-1) + gat.bias
            total += message
            neighbours = [{"node": first[src] + int(j), "embedding": squash(x[src][j].numpy(), DETAIL_DIM),
                           "value": per_head(values[k]),
                           "scores": [round(float(v), 3) for v in scores[k]],
                           "attention": [round(float(v), 3) for v in attention[k]],
                           "weighted": per_head(weighted[k])}
                          for k, j in enumerate(senders.tolist())]
            neighbours.sort(key=lambda n: -sum(n["attention"]))
            edge_types.append({"type": rel, "shown_as": SHOWN_AS.get(rel, rel), "source": src,
                               "query": per_head(query), "neighbours": neighbours, "heads": per_head(heads),
                               "bias": round(float(gat.bias.norm()), 3),
                               "message": squash(message.numpy(), DETAIL_DIM),
                               "message_size": round(float(message.norm()), 3)})
        relu = F.relu(total)
        residual = x_i + relu
        output = norm(residual)

    def step(t: torch.Tensor) -> dict:
        return {"vector": squash(t.numpy(), DETAIL_DIM), "size": round(float(t.norm()), 3)}

    gat = next(iter(conv.convs.values()))
    return {"node": node, "type": node_type, "layer": layer, "layers": len(net.convs), "hidden": x_i.numel(),
            "heads": gat.heads, "head_dim": gat.out_channels, "negative_slope": gat.negative_slope,
            "input": step(x_i), "edge_types": edge_types, "sum": step(total), "relu": step(relu),
            "residual": step(residual), "output": step(output)}
