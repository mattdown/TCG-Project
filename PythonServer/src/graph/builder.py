"""Converts encoded observations to PyG HeteroData for the GNN.

Nodes:
  card    every visible card (see encode.py)
  player  you (index 0) and the opponent (index 1)
  global  one node: turn, phase
  action  each legal option. Not part of message passing: it only stores which card nodes
          the option refers to, so the policy head can score it after message passing.
"""
import numpy as np
import torch
from torch_geometric.data import HeteroData

from src.graph.encode import EncodedObs

NODE_TYPES = ("card", "player", "global")
EDGE_TYPES = (
    ("card", "belongs_to", "player"),
    ("player", "has_card", "card"),
    ("card", "faces", "card"),  # between every unit in play and every opposing unit
    ("player", "opposes", "player"),
    ("player", "in", "global"),
    ("global", "has", "player"),
)


def _edges(src: np.ndarray, dst: np.ndarray) -> torch.Tensor:
    return torch.from_numpy(np.stack([src, dst]).astype(np.int64)).view(2, -1)


def to_hetero_data(obs: EncodedObs) -> HeteroData:
    cards = np.arange(obs.num_cards)
    mine = np.flatnonzero(obs.card_in_play & (obs.card_owner == 0))
    theirs = np.flatnonzero(obs.card_in_play & (obs.card_owner == 1))
    face_src, face_dst = np.repeat(mine, len(theirs)), np.tile(theirs, len(mine))

    data = HeteroData()
    data["card"].x_static = torch.from_numpy(obs.card_static)
    data["card"].x_dynamic = torch.from_numpy(obs.card_dynamic)
    data["card"].num_nodes = obs.num_cards
    data["player"].x = torch.from_numpy(obs.player)
    data["global"].x = torch.from_numpy(obs.global_).view(1, -1)

    data["card", "belongs_to", "player"].edge_index = _edges(cards, obs.card_owner)
    data["player", "has_card", "card"].edge_index = _edges(obs.card_owner, cards)
    data["card", "faces", "card"].edge_index = _edges(np.concatenate([face_src, face_dst]),
                                                      np.concatenate([face_dst, face_src]))
    data["player", "opposes", "player"].edge_index = _edges(np.array([0, 1]), np.array([1, 0]))
    data["player", "in", "global"].edge_index = _edges(np.array([0, 1]), np.array([0, 0]))
    data["global", "has", "player"].edge_index = _edges(np.array([0, 0]), np.array([0, 1]))

    data["action"].type = torch.from_numpy(obs.action_type)
    data["action"].actor = torch.from_numpy(obs.action_actor)
    data["action"].target = torch.from_numpy(obs.action_target)
    data["action"].num_nodes = obs.num_actions
    return data


def collate_hetero(observations: list[EncodedObs]) -> HeteroData:
    """Builds the batched graph in one go, instead of one HeteroData per observation.

    Produces the same fields as Batch.from_data_list([to_hetero_data(o) for o in observations])
    that the GNN uses (features, edge_index_dict, card.ptr, action.batch), much faster.
    """
    B = len(observations)
    n_cards = np.array([o.num_cards for o in observations])
    n_actions = np.array([o.num_actions for o in observations])
    card_ptr = np.concatenate([[0], np.cumsum(n_cards)])
    owner = np.concatenate([o.card_owner for o in observations])
    in_play = np.concatenate([o.card_in_play for o in observations])
    card_graph = np.repeat(np.arange(B), n_cards)
    card_player = 2 * card_graph + owner  # global index of each card's owner node
    cards = np.arange(len(owner))

    face_src, face_dst = [], []
    for start, end in zip(card_ptr[:-1], card_ptr[1:]):
        mine = start + np.flatnonzero(in_play[start:end] & (owner[start:end] == 0))
        theirs = start + np.flatnonzero(in_play[start:end] & (owner[start:end] == 1))
        face_src.append(np.repeat(mine, len(theirs)))
        face_dst.append(np.tile(theirs, len(mine)))
    face_src, face_dst = np.concatenate(face_src).astype(np.int64), np.concatenate(face_dst).astype(np.int64)

    graphs = np.arange(B)
    players = np.arange(2 * B)

    data = HeteroData()
    data["card"].x_static = torch.from_numpy(np.concatenate([o.card_static for o in observations]))
    data["card"].x_dynamic = torch.from_numpy(np.concatenate([o.card_dynamic for o in observations]))
    data["card"].num_nodes = int(card_ptr[-1])
    data["card"].ptr = torch.from_numpy(card_ptr.astype(np.int64))
    data["player"].x = torch.from_numpy(np.concatenate([o.player for o in observations]))
    data["global"].x = torch.from_numpy(np.stack([o.global_ for o in observations]))

    data["card", "belongs_to", "player"].edge_index = _edges(cards, card_player)
    data["player", "has_card", "card"].edge_index = _edges(card_player, cards)
    data["card", "faces", "card"].edge_index = _edges(np.concatenate([face_src, face_dst]),
                                                      np.concatenate([face_dst, face_src]))
    data["player", "opposes", "player"].edge_index = _edges(players, players ^ 1)
    data["player", "in", "global"].edge_index = _edges(players, players // 2)
    data["global", "has", "player"].edge_index = _edges(players // 2, players)

    data["action"].type = torch.from_numpy(np.concatenate([o.action_type for o in observations]))
    # The GNN adds card.ptr itself, so actor / target stay local to each graph.
    data["action"].actor = torch.from_numpy(np.concatenate([o.action_actor for o in observations]))
    data["action"].target = torch.from_numpy(np.concatenate([o.action_target for o in observations]))
    data["action"].batch = torch.from_numpy(np.repeat(graphs, n_actions).astype(np.int64))
    data["action"].num_nodes = int(n_actions.sum())
    return data
