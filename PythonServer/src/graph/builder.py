"""Builds the state graph one player sees at a decision point.

Nodes:
  card    every visible card: your hand, your units, the opponent's units
  player  you (index 0) and the opponent (index 1)
  global  one node: turn, phase
  action  each legal option. Not part of message passing: it only stores which card nodes
          the option refers to, so the policy head can score it after message passing.

The opponent's hand and both decks are hidden, so they only appear as counts on the
player nodes. Card features hold only what a card *is* (no card ID), so the network can
handle cards it has never seen.
"""
from dataclasses import dataclass

import torch
from torch_geometric.data import HeteroData

from src.game.actions import Action
from src.game.engine import Game
from src.game.state import Phase, Zone
from src.game.terms import ASPECTS

NODE_TYPES = ("card", "player", "global")
EDGE_TYPES = (
    ("card", "belongs_to", "player"),
    ("player", "has_card", "card"),
    ("card", "faces", "card"),  # between every unit in play and every opposing unit
    ("player", "opposes", "player"),
    ("player", "in", "global"),
    ("global", "has", "player"),
)
CARD_STATIC_DIM = 5 + len(ASPECTS)
CARD_DYNAMIC_DIM = 8
PLAYER_DIM = 12
GLOBAL_DIM = 4


@dataclass
class Observation:
    data: HeteroData
    actions: list[Action]  # in the same order as the action nodes


def card_static_features(card) -> list[float]:
    """What the card is. The card encoder turns these into the card embedding."""
    return [card.cost / 10, card.power / 10, card.health / 10, card.score / 5, float(card.energy_source),
            *(float(a in card.aspects) for a in ASPECTS)]


def _edges(pairs: list[tuple[int, int]]) -> torch.Tensor:
    if not pairs:
        return torch.zeros((2, 0), dtype=torch.long)
    return torch.tensor(pairs, dtype=torch.long).t().contiguous()


def build_observation(game: Game, player: int) -> Observation:
    s = game.state
    me, opp = s.players[player], s.players[1 - player]

    card_uids = me.hand + me.play + opp.play
    node_of = {uid: i for i, uid in enumerate(card_uids)}
    static, dynamic, belongs = [], [], []
    for i, uid in enumerate(card_uids):
        c = game.card(uid)
        mine = c.owner == player
        static.append(card_static_features(c.card))
        dynamic.append([
            float(c.zone == Zone.HAND), float(c.zone == Zone.PLAY), float(mine), float(c.exhausted),
            float(c.fresh), c.damage / 10, (c.card.health - c.damage) / 10, float(uid in me.mulligan_marked),
        ])
        belongs.append((i, 0 if mine else 1))
    faces = [(node_of[a], node_of[b]) for a in me.play for b in opp.play]
    faces += [(b, a) for a, b in faces]

    def player_features(p: int) -> list[float]:
        ps = s.players[p]
        units = [game.card(u) for u in ps.play]
        return [ps.vp / game.config.vp_to_win, game.ready_energy(p) / 10, len(ps.energy) / 10, len(ps.hand) / 10,
                len(ps.deck) / 60, len(ps.discard) / 60, len(units) / 10, sum(not u.exhausted for u in units) / 10,
                sum(u.card.score for u in units) / 20, float(ps.added_energy_this_turn), float(s.active_player == p),
                float(ps.mulligan_done)]

    data = HeteroData()
    data["card"].x_static = torch.tensor(static, dtype=torch.float).view(-1, CARD_STATIC_DIM)
    data["card"].x_dynamic = torch.tensor(dynamic, dtype=torch.float).view(-1, CARD_DYNAMIC_DIM)
    data["card"].num_nodes = len(card_uids)
    data["player"].x = torch.tensor([player_features(player), player_features(1 - player)], dtype=torch.float)
    data["global"].x = torch.tensor([[s.turn / 50, float(s.phase == Phase.MULLIGAN), float(s.phase == Phase.MAIN),
                                      float(s.decision_player == player)]], dtype=torch.float)

    data["card", "belongs_to", "player"].edge_index = _edges(belongs)
    data["player", "has_card", "card"].edge_index = _edges([(p, c) for c, p in belongs])
    data["card", "faces", "card"].edge_index = _edges(faces)
    data["player", "opposes", "player"].edge_index = _edges([(0, 1), (1, 0)])
    data["player", "in", "global"].edge_index = _edges([(0, 0), (1, 0)])
    data["global", "has", "player"].edge_index = _edges([(0, 0), (0, 1)])

    actions = game.legal_actions() if s.decision_player == player else []
    data["action"].type = torch.tensor([a.type for a in actions], dtype=torch.long)
    data["action"].actor = torch.tensor([node_of.get(a.card, -1) for a in actions], dtype=torch.long)
    data["action"].target = torch.tensor([node_of.get(a.target, -1) for a in actions], dtype=torch.long)
    data["action"].num_nodes = len(actions)
    return Observation(data, actions)
