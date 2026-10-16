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
    net.load_state_dict(checkpoint["state_dict"])
    net.eval()
    return net
