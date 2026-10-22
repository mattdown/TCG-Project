"""Creating, saving and loading networks by architecture name."""
import torch

from src.model.gnn import GNNNet
from src.model.transformer import EntityTransformerNet

ARCHITECTURES = {cls.arch: cls for cls in (GNNNet, EntityTransformerNet)}


def create_model(arch: str, **hparams) -> torch.nn.Module:
    if arch not in ARCHITECTURES:
        raise ValueError(f"unknown architecture {arch!r}; choose from {sorted(ARCHITECTURES)}")
    return ARCHITECTURES[arch](**hparams)


def save_model(net: torch.nn.Module, path, extra: dict | None = None):
    torch.save({"arch": net.arch, "hparams": net.hparams, "state_dict": net.state_dict(), **(extra or {})}, path)


def load_model(path, device: str = "cpu") -> torch.nn.Module:
    checkpoint = torch.load(path, map_location=device)
    # Checkpoints from before the transformer existed have no "arch" and are GNNs.
    net = create_model(checkpoint.get("arch", "gnn"), **checkpoint["hparams"]).to(device)
    state = checkpoint["state_dict"]
    # New action types only add rows to the action-type embedding: keep the trained rows.
    rows = net.action_type_emb.weight
    old = state.get("action_type_emb.weight")
    if old is not None and old.shape[0] < rows.shape[0]:
        state["action_type_emb.weight"] = torch.cat([old, rows.detach()[old.shape[0]:].to(old.device)])
    # New ability node features are appended (src/graph/abilities.py): zero weights for them, so
    # an older model ignores them.
    weight = net.ability_in[0].weight
    old = state.get("ability_in.0.weight")
    if old is not None and old.shape[1] < weight.shape[1]:
        state["ability_in.0.weight"] = torch.cat([old, old.new_zeros(old.shape[0], weight.shape[1] - old.shape[1])], 1)
    net.load_state_dict(state)
    net.eval()
    return net
