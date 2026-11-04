"""GNN visualiser: how the network reads the board, animated for the blog (part 1: one node's inputs).

    uv run --project PythonServer python Blog/gnn_visualiser.py                 # Blog/build/gnn_visualiser.html, opened
    uv run --project PythonServer --with playwright python Blog/gnn_visualiser.py --render   # also the .mp4s

It also writes the three parts as their own pages for the blog, gnn_visualiser_1.html to _3.html
(the inputs, up to the neighbours fanning out; one layer; the heads), each with its own timeline.

Run from the repository root; it uses PythonServer's environment. The art comes from Blog/art
(card_generation_visualiser.py --refresh-art makes it).

A small position from set_200 (two units a side, hands left out) is turned into the state graph
the GNN reads (src/graph/encode.py, the edges as src/server/graph_view.py sends them to the client's
overlay). The page shows the board, lays the graph over it, zooms into one card's node, turns the
card into its 24 input features in two steps (read them off the card, then scale them) as a
greyscale column like the client's EmbeddingGlyph, embeds them with the trained model (--model:
the card encoder, then the projection to the hidden size; src/model/gnn.py), and then brings in the
node's neighbours, edge type by edge type.

Part 2 is one GNN layer for that node, like the schematic in the client's layer inspector: the
neighbours fan out round it, and for one edge type and one attention head it shows W_l and W_r,
LeakyReLU and the dot product with a that score each neighbour, the softmax, the weighted sum, the
heads joined, every edge type's message added, then ReLU, the residual and LayerNorm; then the four
layers and how far each reaches. The numbers are src/server/graph_view.layer_view's, in full.

Part 3 is the two heads (GNNNet.forward): the policy head joins six 128-number slots per legal action
(its type's embedding, actor, target, context, option, the game node; unused slots get a learned
empty vector) and scores the 768 numbers with an MLP, then a softmax over the actions; the value
head joins the game node and both player nodes and turns the 384 numbers into a value from -1 to 1. Everything is a function of the time t, so it can be scrubbed and rendered
frame by frame like the card generation visualiser.
"""
import argparse
import webbrowser
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from card_generation_visualiser import SET_SIZE, bake, describe, render  # next to this file; it puts PythonServer on the path
from src.cards.abilities import render as card_text  # noqa: E402
from src.cards.art import art_key  # noqa: E402
from src.cards.schema import load_card_set  # noqa: E402
from src.game.actions import Action, ActionType  # noqa: E402
from src.game.engine import Game  # noqa: E402
from src.game.state import CardInstance, Zone  # noqa: E402
from src.game.terms import ASPECT_NAMES, KEYWORD_NAMES, KEYWORDS, keyword_text  # noqa: E402
from src.graph.encode import (CARD_DYNAMIC_DIM, CARD_DYNAMIC_FEATURES, CARD_STATIC_DIM,  # noqa: E402
                              CARD_STATIC_FEATURES, KEYWORD_SCALE, observe)
from src.model.registry import load_model  # noqa: E402
from src.server.graph_view import ability_label, graph_view, layer_view  # noqa: E402

WALK_TARGET = 2  # the action worked through: the focus card attacking this card (Porcini Baker)

TEMPLATE = Path(__file__).with_name("gnn_visualiser.html")
GAME = "a trading card game agent's graph neural network"
PAGES = {  # by part: each page's title and summary (None is all three in one page)
    None: ("GNN visualiser", f"How {GAME} reads the board and picks a move: the board as a state graph, one "
           "GATv2 message-passing layer step by step, and the policy and value heads."),
    1: ("GNN visualiser 1: the board as a graph", f"Part 1 of how {GAME} reads the board: the game becomes a "
        "graph with a node for each card, player and the game, plus a small graph for each card's ability. One "
        "card's features are scaled to 0-1 and embedded, then joined to its neighbours by typed edges."),
    2: ("GNN visualiser 2: one GATv2 layer", f"Part 2 of how {GAME} reads the board: one GATv2 message-passing "
        "layer, step by step. Two learned matrices, LeakyReLU and a dot product score each neighbour, softmax "
        "turns the scores into attention, and the weighted messages from every edge type are added, followed by "
        "ReLU, a residual connection and LayerNorm."),
    3: ("GNN visualiser 3: the policy and value heads", f"Part 3 of how {GAME} picks a move: the policy head "
        "describes every legal move the same way from the nodes it involves and scores it with an MLP, whatever "
        "the cards, and the value head judges who is winning."),
}
OUT = Path(__file__).parent / "build"
CARD_SET = Path(__file__).parents[1] / "PythonServer" / "cardsets" / f"set_{SET_SIZE}.json"
MODEL = Path(__file__).parents[1] / "PythonServer" / "models" / "tcgnet.pt"  # the server's AI

# The position, by card number in set_200: the first of yours is the card the camera follows.
YOURS, THEIRS = (132, 24), (2, 12)  # Fly-agaric Lamplighter and Honey Chef; Porcini Baker and Lion's-mane Baker
DAMAGE = {132: 2}  # so its state features aren't all zero
HEALTH, CRYSTALS, TURN = (22, 17), 5, 9

# How each input feature is read off the card (src/graph/encode.py), in the encoder's order.
STATE_NAMES = {"in_hand": "In hand", "in_play": "In play", "mine": "Yours", "attacked": "Has attacked",
               "fresh": "Played this turn", "damage": "Damage", "health_left": "Health left",
               "mulligan_marked": "Marked to swap", "hidden": "Hidden", "frozen": "Frozen"}
CARD_PART = {"cost": "cost", "power": "power", "health": "health", "damage": "health", "health_left": "health",
             **{k: "text" for k in KEYWORD_SCALE}, **{a: "art" for a in ASPECT_NAMES}}


def position() -> tuple[Game, dict[int, int]]:
    """The game, and card number → uid for the cards in play."""
    cards = load_card_set(CARD_SET).cards
    game = Game(cards[:30], cards[30:60], seed=0, first_player=0)
    game.step(Action(ActionType.KEEP_HAND))
    game.step(Action(ActionType.KEEP_HAND))
    s = game.state
    s.turn = TURN
    for p, health in zip(s.players, HEALTH):
        p.deck.extend(p.hand)  # no hands: the animation is about the board
        for uid in p.hand:
            s.cards[uid].zone = Zone.DECK
        p.hand.clear()
        p.health, p.crystals, p.mana = health, CRYSTALS, CRYSTALS
    uids = {}
    for player, numbers in ((0, YOURS), (1, THEIRS)):
        for n in numbers:
            uid = len(s.cards)
            s.cards.append(CardInstance(uid, cards[n - 1], player, Zone.PLAY, damage=DAMAGE.get(n, 0)))
            s.players[player].play.append(uid)
            uids[n] = uid
    return game, uids


def card_view(game: Game, uid: int) -> dict:
    """What painted_card.html needs to draw a card in play."""
    c = game.card(uid)
    card = c.card
    ability = card.abilities[0] if card.abilities else None
    return {"name": card.name, "subtitle": card.subtitle, "type": card.type, "cost": card.cost, "power": card.power,
            "health": card.health - c.damage, "damaged": c.damage > 0, "traits": list(card.traits),
            "keywords": [keyword_text(k, v) for k, v in card.keywords], "art": True,
            "text": card_text(ability, card.type) if ability else "", "kind": ability["kind"] if ability else "",
            "art_key": art_key(card.name, card.subtitle, card.aspects)}


def features(game: Game, uid: int, values: np.ndarray) -> list[dict]:
    """The card node's 24 inputs: each feature's name, what it is on the card, the rule that scales it and the
    number the network gets (from observe, so it is exactly what the network reads)."""
    c = game.card(uid)
    card = c.card
    raw = {"cost": card.cost, "power": card.power, "health": card.health, "damage": c.damage,
           "health_left": card.health - c.damage}
    rows = []
    for name, value in zip((*CARD_STATIC_FEATURES, *CARD_DYNAMIC_FEATURES), values):
        group = "card" if name in CARD_STATIC_FEATURES else "state"
        if name in raw:
            label = name.replace("_", " ").capitalize() if name != "health_left" else "Health left"
            shown, rule = str(raw[name]), "÷ 10"
        elif name in KEYWORD_SCALE:
            label, n = KEYWORD_NAMES[name], card.keyword(name)
            if KEYWORDS[name]:  # numbered keywords
                shown, rule = f"+{n}" if n else "none", f"÷ {KEYWORD_SCALE[name]}"
            else:
                shown, rule = "yes" if n else "no", "1 if yes"
        elif name in ASPECT_NAMES:
            label, shown, rule = ASPECT_NAMES[name], "yes" if name in card.aspects else "no", "1 if yes"
        else:
            label, shown, rule = STATE_NAMES[name], "yes" if value else "no", "1 if yes"
        rows.append({"name": name, "label": label, "group": group, "raw": shown, "rule": rule,
                     "value": round(float(value), 3), "part": CARD_PART.get(name, "card")})
    return rows


def embedding(net, e, i: int) -> dict:
    """How the card node's input becomes its embedding (GNN.node_states): the static features through the
    card encoder, the dynamic ones joined on, and a linear projection to the hidden size."""
    if getattr(net, "arch", None) != "gnn":
        raise SystemExit("the GNN visualiser needs a GNN model (--model)")
    batch = net.collate([e])
    with torch.no_grad():
        encoded = net.card_encoder(batch["card"].x_static)[i]
        projected = net.node_states(batch)[0]["card"][i]
    vector = lambda t: [round(float(v), 3) for v in t]
    return {"static": CARD_STATIC_DIM, "dynamic": CARD_DYNAMIC_DIM, "hidden": net.hparams["hidden"],
            "encoded": vector(encoded), "projected": vector(projected)}


def layers(net, game: Game, e, i: int, edges: list[dict]) -> dict:
    """Layer 1 for the focus node step by step, its vector after every layer, and how many edges away
    each node is (what the layers can reach)."""
    batch = net.collate([e])
    with torch.no_grad():
        states = [x["card"][i] for x in net.node_states(batch)]
    near = {}
    for edge in edges:  # the layers pass messages both ways along every edge
        near.setdefault(edge["src"], set()).add(edge["dst"])
        near.setdefault(edge["dst"], set()).add(edge["src"])
    hops, frontier, depth = {i: 0}, {i}, 0
    while frontier:
        depth += 1
        frontier = {b for a in frontier for b in near.get(a, ()) if b not in hops}
        hops |= dict.fromkeys(frontier, depth)
    return {"detail": layer_view(game, 0, i, 1, net, detail=net.hparams["hidden"]),
            "states": [[round(float(v), 3) for v in x] for x in states], "hops": hops}


def heads(net, game: Game, e, uids: dict[int, int], card_uids: list[int]) -> dict:
    """What the policy and value heads read and make (GNNNet.forward, done step by step so each part can
    be shown): the slots of every legal action, the policy MLP's hidden layer for the walked-through
    action, every action's score and probability, and the value head's inputs, hidden layer and output."""
    batch = net.collate([e])
    view = graph_view(game, 0, net)
    vector = lambda t: [round(float(v), 3) for v in t]
    with torch.no_grad():
        x = net.node_states(batch)[-1]
        logits, _, value = net(batch)
        first, last = net.policy_head[0], net.policy_head[2]  # Linear, ReLU, Linear
        first_id = {"ability": e.num_cards + 3, "global": e.num_cards + 2, "player": e.num_cards, "card": 0}

        def final(node: int) -> torch.Tensor:  # a graph_view node id → its vector after the last layer
            t = next(t for t, i in first_id.items() if node >= i)
            return x[t][node - first_id[t]]

        actions = []
        for a, logit in zip(view["actions"], logits):
            slots = [net.action_type_emb.weight[int(e.action_type[a["index"]])]]
            for k, key in enumerate(("actor", "target", "context", "option")):
                slots.append(final(a[key]) if a[key] is not None else net.empty_slot[k])
            slots.append(x["global"][0])
            joined = torch.cat(slots)
            hidden = F.relu(first(joined))
            assert abs(float(last(hidden)) - float(logit)) < 1e-4  # the same as the forward pass
            actions.append({"text": a["text"], "type": a["type"], "actor": a["actor"], "target": a["target"],
                            "context": a["context"], "option": a["option"], "global": a["global"],
                            "logit": round(float(logit), 3), "probability": round(float(logits.softmax(-1)[a["index"]]), 4),
                            "slots": [vector(v) for v in slots], "hidden": vector(hidden)})
        v_in = torch.cat([x["global"][0], x["player"][0], x["player"][1]])
        v_hidden = F.relu(net.value_head[0](v_in))
        raw = net.value_head[2](v_hidden)
        assert abs(float(torch.tanh(raw)) - float(value[0])) < 1e-4
    actor, target = card_uids.index(uids[YOURS[0]]), card_uids.index(uids[WALK_TARGET])
    walk = next(i for i, a in enumerate(actions) if a["actor"] == actor and a["target"] == target)
    return {"actions": actions, "walk": walk,
            "value": {"nodes": view["value"]["nodes"], "inputs": [vector(x["global"][0]), vector(x["player"][0]),
                      vector(x["player"][1])], "hidden": vector(v_hidden), "raw": round(float(raw), 3),
                      "value": round(float(value[0]), 3)}}


def graph_data(model: Path = MODEL) -> dict:
    game, uids = position()
    obs = observe(game, 0)
    e = obs.encoded
    view = graph_view(game, 0)
    inputs = {"card": np.concatenate([e.card_static, e.card_dynamic], axis=1), "player": e.player,
              "global": e.global_[None], "ability": e.node_features}
    first = {"card": 0, "player": e.num_cards, "global": e.num_cards + 2, "ability": e.num_cards + 3}

    nodes = []
    for n in view["nodes"]:
        t = n["type"]
        vector = inputs[t][n["id"] - first[t]]
        node = {"id": n["id"], "type": t, "vector": [round(float(v), 3) for v in vector]}
        if t == "card":
            node |= {"owner": n["owner"], "slot": game.state.players[n["owner"]].play.index(n["uid"]),
                     "card": card_view(game, n["uid"])}
            node["label"] = node["card"]["name"]
        elif t == "player":
            node |= {"owner": n["owner"], "label": "You" if n["owner"] == 0 else "Opponent"}
        elif t == "global":
            node["label"] = "The game"
        else:
            kind, label = ability_label(vector)
            node |= {"card": n["card"], "kind": kind, "label": label.replace("_", " ")}
        nodes.append(node)

    focus = obs.card_uids.index(uids[YOURS[0]])
    return {"nodes": nodes, "edges": view["edges"], "focus": focus,
            "features": features(game, uids[YOURS[0]], inputs["card"][focus]),
            "embedding": embedding(net := load_model(model), e, focus),
            "layers": layers(net, game, e, focus, view["edges"]),
            "heads": heads(net, game, e, uids, obs.card_uids),
            "heroes": [{"owner": p, "name": "You" if p == 0 else "Opponent", "health": HEALTH[p]} for p in (0, 1)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", type=Path, default=MODEL, help="the GNN whose embedding is shown")
    parser.add_argument("--out", type=Path, default=OUT / "gnn_visualiser.html")
    parser.add_argument("--render", action="store_true", help="also render the video next to the page (needs playwright)")
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    data = graph_data(args.model)
    keys = {n["card"]["art_key"] for n in data["nodes"] if n["type"] == "card"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pages = {args.out: data} | {args.out.with_stem(f"{args.out.stem}_{n}"): data | {"part": n} for n in (1, 2, 3)}
    for out, part in pages.items():
        out.write_text(describe(bake(TEMPLATE, part, keys), *PAGES[part.get("part")]))
        print(f"Wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
    if args.render:
        for out in pages:
            render(out, out.with_suffix(".mp4"), args.fps)
    elif not args.no_browser:
        webbrowser.open(args.out.resolve().as_uri())


if __name__ == "__main__":
    main()
