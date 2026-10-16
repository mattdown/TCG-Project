"""Entity-transformer policy-value network: the dense alternative to the GNN.

Every token (global, both players, every visible card) attends to every other token. The
graph isn't thrown away: each pair of tokens has a relation (belongs_to, faces, …, or none)
and each relation adds a learned bias per attention head. Everything is dense matrix
multiplies on fixed shapes, which suits GPUs, TPUs and compilers, and ports to JAX directly.

Card encoder, action slots and heads are the same as in the GNN.
"""
import torch
import torch.nn.functional as F
from torch import nn

from src.game.actions import ActionType
from src.graph.dense import GLOBAL_TOKEN, NUM_FIXED_TOKENS, RELATIONS, DenseBatch, collate_dense
from src.graph.encode import CARD_DYNAMIC_DIM, CARD_STATIC_DIM, GLOBAL_DIM, PLAYER_DIM, EncodedObs
from src.model.common import mlp


class RelationalAttentionLayer(nn.Module):
    """Pre-norm transformer layer whose attention logits get a per-head bias for each relation."""

    def __init__(self, hidden: int, heads: int, ff_mult: int = 4):
        super().__init__()
        self.heads = heads
        self.norm1 = nn.LayerNorm(hidden)
        self.qkv = nn.Linear(hidden, 3 * hidden)
        self.out = nn.Linear(hidden, hidden)
        self.relation_bias = nn.Embedding(len(RELATIONS), heads)
        self.norm2 = nn.LayerNorm(hidden)
        self.ff = nn.Sequential(nn.Linear(hidden, ff_mult * hidden), nn.GELU(), nn.Linear(ff_mult * hidden, hidden))

    def forward(self, x: torch.Tensor, relation: torch.Tensor, key_mask: torch.Tensor) -> torch.Tensor:
        B, T, H = x.shape
        q, k, v = self.qkv(self.norm1(x)).view(B, T, 3, self.heads, H // self.heads).permute(2, 0, 3, 1, 4)
        bias = self.relation_bias(relation).permute(0, 3, 1, 2)  # [B, heads, T, T]
        bias = bias.masked_fill(~key_mask[:, None, None, :], float("-inf"))
        attn = F.scaled_dot_product_attention(q, k, v, attn_mask=bias)
        x = x + self.out(attn.transpose(1, 2).reshape(B, T, H))
        return x + self.ff(self.norm2(x))


class EntityTransformerNet(nn.Module):
    arch = "transformer"

    def __init__(self, hidden: int = 128, num_layers: int = 4, heads: int = 4):
        super().__init__()
        self.hparams = {"hidden": hidden, "num_layers": num_layers, "heads": heads}
        self.card_encoder = mlp(CARD_STATIC_DIM, hidden, hidden)
        self.card_in = nn.Linear(hidden + CARD_DYNAMIC_DIM, hidden)
        self.player_in = nn.Linear(PLAYER_DIM, hidden)
        self.global_in = nn.Linear(GLOBAL_DIM, hidden)
        self.layers = nn.ModuleList(RelationalAttentionLayer(hidden, heads) for _ in range(num_layers))
        self.final_norm = nn.LayerNorm(hidden)
        self.action_type_emb = nn.Embedding(len(ActionType), hidden)
        self.empty_slot = nn.Parameter(torch.zeros(2, hidden))
        self.policy_head = mlp(4 * hidden, hidden, 1)
        self.value_head = mlp(3 * hidden, hidden, 1)

    @staticmethod
    def collate(observations: list[EncodedObs]) -> DenseBatch:
        return collate_dense(observations)

    def forward(self, batch: DenseBatch) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        cards = self.card_in(torch.cat([self.card_encoder(batch.card_static), batch.card_dynamic], dim=-1))
        x = torch.cat([self.global_in(batch.global_)[:, None], self.player_in(batch.player), cards], dim=1)
        fixed = batch.card_mask.new_ones(batch.card_mask.size(0), NUM_FIXED_TOKENS)
        key_mask = torch.cat([fixed, batch.card_mask], dim=1)
        for layer in self.layers:
            x = layer(x, batch.relation, key_mask)
        x = self.final_norm(x)

        g, card_h = x[:, GLOBAL_TOKEN], x[:, NUM_FIXED_TOKENS:]
        slots = [self._slot(card_h, batch.action_actor, 0), self._slot(card_h, batch.action_target, 1)]
        A = batch.action_type.size(1)
        action_in = torch.cat([self.action_type_emb(batch.action_type), *slots, g[:, None].expand(-1, A, -1)], dim=-1)
        logits = self.policy_head(action_in).squeeze(-1)  # [B, A]

        value = torch.tanh(self.value_head(torch.cat([g, x[:, 1], x[:, 2]], dim=-1))).squeeze(-1)
        decision = torch.arange(logits.size(0), device=logits.device)[:, None].expand(-1, A)
        return logits[batch.action_mask], decision[batch.action_mask], value

    def _slot(self, card_h: torch.Tensor, idx: torch.Tensor, slot: int) -> torch.Tensor:
        used = idx >= 0
        gathered = torch.gather(card_h, 1, idx.clamp(min=0)[..., None].expand(-1, -1, card_h.size(-1)))
        return torch.where(used[..., None], gathered, self.empty_slot[slot])
