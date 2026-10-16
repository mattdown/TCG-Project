"""Pieces shared by every policy-value network.

A network has a `collate(list[EncodedObs])` method that builds its own batch type, and a
forward pass returning (action logits [A], decision index of each action [A], values [B]).
The logits are flat across the batch, in observation order, so training code never needs to
know which model it is using.
"""
import torch
from torch import nn
from torch_geometric.utils import scatter


def mlp(in_dim: int, hidden: int, out_dim: int) -> nn.Sequential:
    return nn.Sequential(nn.Linear(in_dim, hidden), nn.ReLU(), nn.Linear(hidden, out_dim))


def segment_log_softmax(logits: torch.Tensor, index: torch.Tensor) -> torch.Tensor:
    """Log-softmax over the actions of each decision separately."""
    max_per = scatter(logits, index, reduce="max")
    shifted = logits - max_per[index]
    log_norm = scatter(shifted.exp(), index, reduce="sum").log()
    return shifted - log_norm[index]


def segment_entropy(log_probs: torch.Tensor, index: torch.Tensor) -> torch.Tensor:
    return -scatter(log_probs.exp() * log_probs, index, reduce="sum")


def segment_ptr(index: torch.Tensor, num_decisions: int) -> torch.Tensor:
    """Offsets of each decision's first action in the flat logits: [num_decisions + 1]."""
    counts = torch.bincount(index, minlength=num_decisions)
    return torch.cat([counts.new_zeros(1), counts.cumsum(0)])
