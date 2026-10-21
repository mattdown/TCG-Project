"""Converts encoded observations to padded, fixed-shape tensors for the entity transformer.

Each state becomes one sequence of tokens: [global, you, opponent, card 0, card 1, …, ability
node 0, ability node 1, …].
Instead of an edge list, a relation matrix gives the graph edge (if any) between every pair
of tokens; the transformer turns it into a learned attention bias. Everything is dense, so
it suits GPUs, TPUs and compilers alike.

Card, ability node and action counts are padded up to a small set of bucket sizes, so a compiler (XLA,
torch.compile) only ever sees a handful of shapes.
"""
from dataclasses import dataclass, fields

import numpy as np
import torch

from src.graph.abilities import NODE_DIM
from src.graph.builder import ABILITY_EDGES, _ability_pairs
from src.graph.encode import CARD_DYNAMIC_DIM, CARD_STATIC_DIM, GLOBAL_DIM, PLAYER_DIM, EncodedObs

# rel[dst, src]: the edge from token src to token dst. Matches the GNN's edge types.
RELATIONS = ("none", "self", "belongs_to", "has_card", "faces", "opposes", "in", "has",
             *(et[1] for pair in ABILITY_EDGES.values() for et in pair))
REL = {name: i for i, name in enumerate(RELATIONS)}
NUM_FIXED_TOKENS = 3  # global, you, opponent
GLOBAL_TOKEN, PLAYER_TOKENS = 0, (1, 2)


def bucket(n: int, minimum: int = 8) -> int:
    """Rounds up to the next power of two (at least `minimum`)."""
    return max(minimum, 1 << max(n - 1, 0).bit_length())


@dataclass
class DenseBatch:
    card_static: torch.Tensor  # [B, N, CARD_STATIC_DIM]
    card_dynamic: torch.Tensor  # [B, N, CARD_DYNAMIC_DIM]
    card_mask: torch.Tensor  # [B, N] bool, False for padding
    node_features: torch.Tensor  # [B, K, NODE_DIM] ability nodes
    node_mask: torch.Tensor  # [B, K] bool
    player: torch.Tensor  # [B, 2, PLAYER_DIM]
    global_: torch.Tensor  # [B, GLOBAL_DIM]
    relation: torch.Tensor  # [B, T, T] long, T = 3 + N + K
    action_type: torch.Tensor  # [B, A]
    action_actor: torch.Tensor  # [B, A], -1 for no actor or padding
    action_target: torch.Tensor  # [B, A]
    action_context: torch.Tensor  # [B, A] ability node index, -1 if none
    action_option: torch.Tensor  # [B, A]
    action_mask: torch.Tensor  # [B, A] bool, False for padding

    def to(self, device) -> "DenseBatch":
        return DenseBatch(**{f.name: getattr(self, f.name).to(device) for f in fields(self)})


def relation_matrix(owner: np.ndarray, in_play: np.ndarray, size: int, obs: EncodedObs | None = None,
                    node_size: int = 0) -> np.ndarray:
    """[3 + size + node_size] square relation ids for one state, with padding left as "none".
    Ability nodes (from obs) come after the `size` card slots."""
    n = len(owner)
    T = NUM_FIXED_TOKENS + size + node_size
    rel = np.zeros((T, T), dtype=np.int64)
    rel[np.arange(T), np.arange(T)] = REL["self"]
    rel[1, 2] = rel[2, 1] = REL["opposes"]
    rel[GLOBAL_TOKEN, PLAYER_TOKENS] = REL["in"]
    rel[PLAYER_TOKENS, GLOBAL_TOKEN] = REL["has"]
    cards = NUM_FIXED_TOKENS + np.arange(n)
    rel[1 + owner, cards] = REL["belongs_to"]
    rel[cards, 1 + owner] = REL["has_card"]
    faces = in_play[:, None] & in_play[None, :] & (owner[:, None] != owner[None, :])
    rel[NUM_FIXED_TOKENS:NUM_FIXED_TOKENS + n, NUM_FIXED_TOKENS:NUM_FIXED_TOKENS + n][faces] = REL["faces"]
    if obs is not None and obs.num_nodes:
        node_base = NUM_FIXED_TOKENS + size
        for field, (forward, reverse) in ABILITY_EDGES.items():
            src, dst = _ability_pairs(obs, field)
            dst_base = node_base if forward[2] == "ability" else NUM_FIXED_TOKENS
            rel[dst_base + dst, node_base + src] = REL[forward[1]]
            rel[node_base + src, dst_base + dst] = REL[reverse[1]]
    return rel


def collate_dense(observations: list[EncodedObs]) -> DenseBatch:
    B = len(observations)
    N = bucket(max(o.num_cards for o in observations))
    K = bucket(max(o.num_nodes for o in observations))
    A = bucket(max(o.num_actions for o in observations))
    card_static = np.zeros((B, N, CARD_STATIC_DIM), dtype=np.float32)
    card_dynamic = np.zeros((B, N, CARD_DYNAMIC_DIM), dtype=np.float32)
    card_mask = np.zeros((B, N), dtype=bool)
    node_features = np.zeros((B, K, NODE_DIM), dtype=np.float32)
    node_mask = np.zeros((B, K), dtype=bool)
    relation = np.zeros((B, NUM_FIXED_TOKENS + N + K, NUM_FIXED_TOKENS + N + K), dtype=np.int64)
    action_type = np.zeros((B, A), dtype=np.int64)
    action_actor = np.full((B, A), -1, dtype=np.int64)
    action_target = np.full((B, A), -1, dtype=np.int64)
    action_context = np.full((B, A), -1, dtype=np.int64)
    action_option = np.full((B, A), -1, dtype=np.int64)
    action_mask = np.zeros((B, A), dtype=bool)
    for b, o in enumerate(observations):
        n, a = o.num_cards, o.num_actions
        card_static[b, :n] = o.card_static
        card_dynamic[b, :n] = o.card_dynamic
        card_mask[b, :n] = True
        node_features[b, :o.num_nodes] = o.node_features
        node_mask[b, :o.num_nodes] = True
        relation[b] = relation_matrix(o.card_owner, o.card_in_play, N, o, K)
        action_type[b, :a] = o.action_type
        action_actor[b, :a] = o.action_actor
        action_target[b, :a] = o.action_target
        action_context[b, :a] = o.action_context
        action_option[b, :a] = o.action_option
        action_mask[b, :a] = True
    return DenseBatch(
        card_static=torch.from_numpy(card_static),
        card_dynamic=torch.from_numpy(card_dynamic),
        card_mask=torch.from_numpy(card_mask),
        node_features=torch.from_numpy(node_features),
        node_mask=torch.from_numpy(node_mask),
        player=torch.from_numpy(np.stack([o.player for o in observations])),
        global_=torch.from_numpy(np.stack([o.global_ for o in observations])),
        relation=torch.from_numpy(relation),
        action_type=torch.from_numpy(action_type),
        action_actor=torch.from_numpy(action_actor),
        action_target=torch.from_numpy(action_target),
        action_context=torch.from_numpy(action_context),
        action_option=torch.from_numpy(action_option),
        action_mask=torch.from_numpy(action_mask),
    )
