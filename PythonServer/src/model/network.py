"""Policy-value network over the state graph.

1. Card encoder: static card features → card embedding.
2. Heterogeneous GNN: GATv2 attention per edge type, with residuals and layer norm.
3. Policy head: each legal action is [action type | actor | target | global] embeddings
   concatenated into one vector and scored. Unused slots get a learned "empty" vector.
4. Value head: win probability for the observing player, in [-1, 1].
"""
import torch
import torch.nn.functional as F
from torch import nn
from torch_geometric.data import Batch, HeteroData
from torch_geometric.nn import GATv2Conv, HeteroConv
from torch_geometric.utils import scatter

from src.game.actions import ActionType
from src.graph.builder import CARD_DYNAMIC_DIM, CARD_STATIC_DIM, EDGE_TYPES, GLOBAL_DIM, NODE_TYPES, PLAYER_DIM


def mlp(in_dim: int, hidden: int, out_dim: int) -> nn.Sequential:
    return nn.Sequential(nn.Linear(in_dim, hidden), nn.ReLU(), nn.Linear(hidden, out_dim))


class TCGNet(nn.Module):
    def __init__(self, hidden: int = 128, num_layers: int = 4, heads: int = 4):
        super().__init__()
        self.hparams = {"hidden": hidden, "num_layers": num_layers, "heads": heads}
        self.card_encoder = mlp(CARD_STATIC_DIM, hidden, hidden)
        self.card_in = nn.Linear(hidden + CARD_DYNAMIC_DIM, hidden)
        self.player_in = nn.Linear(PLAYER_DIM, hidden)
        self.global_in = nn.Linear(GLOBAL_DIM, hidden)
        self.convs = nn.ModuleList(
            HeteroConv({et: GATv2Conv(hidden, hidden // heads, heads=heads, add_self_loops=False)
                        for et in EDGE_TYPES}, aggr="sum")
            for _ in range(num_layers))
        self.norms = nn.ModuleList(nn.ModuleDict({nt: nn.LayerNorm(hidden) for nt in NODE_TYPES})
                                   for _ in range(num_layers))
        self.action_type_emb = nn.Embedding(len(ActionType), hidden)
        self.empty_slot = nn.Parameter(torch.zeros(2, hidden))
        self.policy_head = mlp(4 * hidden, hidden, 1)
        self.value_head = mlp(3 * hidden, hidden, 1)

    def forward(self, batch: Batch) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Returns (action logits [A], decision index of each action [A], values [G])."""
        card = batch["card"]
        x = {
            "card": self.card_in(torch.cat([self.card_encoder(card.x_static), card.x_dynamic], dim=-1)),
            "player": self.player_in(batch["player"].x),
            "global": self.global_in(batch["global"].x),
        }
        for conv, norms in zip(self.convs, self.norms):
            out = conv(x, batch.edge_index_dict)
            x = {nt: norms[nt](h + F.relu(out[nt])) if nt in out else h for nt, h in x.items()}

        actions = batch["action"]
        offset = card.ptr[actions.batch]
        slots = [self._slot(x["card"], actions.actor, offset, 0), self._slot(x["card"], actions.target, offset, 1)]
        action_in = torch.cat([self.action_type_emb(actions.type), *slots, x["global"][actions.batch]], dim=-1)
        logits = self.policy_head(action_in).squeeze(-1)

        hidden = x["player"].size(-1)
        players = x["player"].view(-1, 2, hidden)  # the observing player is always node 0
        value = torch.tanh(self.value_head(torch.cat([x["global"], players[:, 0], players[:, 1]], dim=-1)))
        return logits, actions.batch, value.squeeze(-1)

    def _slot(self, h: torch.Tensor, local_idx: torch.Tensor, offset: torch.Tensor, slot: int) -> torch.Tensor:
        used = local_idx >= 0
        if h.size(0) == 0:
            return self.empty_slot[slot].expand(local_idx.size(0), -1)
        gathered = h[torch.where(used, local_idx + offset, 0)]
        return torch.where(used[:, None], gathered, self.empty_slot[slot])


def collate(observations: list[HeteroData]) -> Batch:
    return Batch.from_data_list(observations)


def segment_log_softmax(logits: torch.Tensor, index: torch.Tensor) -> torch.Tensor:
    """Log-softmax over the actions of each decision separately."""
    max_per = scatter(logits, index, reduce="max")
    shifted = logits - max_per[index]
    log_norm = scatter(shifted.exp(), index, reduce="sum").log()
    return shifted - log_norm[index]


def segment_entropy(log_probs: torch.Tensor, index: torch.Tensor) -> torch.Tensor:
    return -scatter(log_probs.exp() * log_probs, index, reduce="sum")


def save_model(net: TCGNet, path, extra: dict | None = None):
    torch.save({"hparams": net.hparams, "state_dict": net.state_dict(), **(extra or {})}, path)


def load_model(path, device: str = "cpu") -> TCGNet:
    checkpoint = torch.load(path, map_location=device)
    net = TCGNet(**checkpoint["hparams"]).to(device)
    net.load_state_dict(checkpoint["state_dict"])
    net.eval()
    return net
