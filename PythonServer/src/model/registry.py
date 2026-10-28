"""Creating, saving and loading networks by architecture name."""
import torch

from src.game.actions import ActionType
from src.graph.abilities import FEATURES
from src.model.gnn import GNNNet
from src.model.transformer import EntityTransformerNet

ARCHITECTURES = {cls.arch: cls for cls in (GNNNet, EntityTransformerNet)}


def _with(names: list[str], removed: dict[str, list[str]]) -> list[str]:
    """names with the removed ones put back, each list right after the name it followed."""
    out = []
    for name in names:
        out += [name, *removed.get(name, [])]
    return out


# Checkpoints saved before feature and action names were stored still had the v1 leftovers:
# activated (⟳) abilities and the exhaust / ready grammar. Features and action types added since
# then were appended, so an older, narrower checkpoint uses a prefix of these lists.
LEGACY_FEATURES = _with(list(FEATURES), {
    "ability:triggered": ["ability:activated"], "cond:defending": ["cond:exhausted"],
    "op:gain_crystal": ["op:exhaust", "op:ready"], "filter:damaged": ["filter:exhausted", "filter:ready"]})
LEGACY_ACTIONS = _with([t.name for t in ActionType], {"SPARE_SPORE": ["ACTIVATE"]})


def create_model(arch: str, **hparams) -> torch.nn.Module:
    if arch not in ARCHITECTURES:
        raise ValueError(f"unknown architecture {arch!r}; choose from {sorted(ARCHITECTURES)}")
    return ARCHITECTURES[arch](**hparams)


def save_model(net: torch.nn.Module, path, extra: dict | None = None):
    torch.save({"arch": net.arch, "hparams": net.hparams, "state_dict": net.state_dict(),
                "ability_features": list(FEATURES), "action_types": [t.name for t in ActionType], **(extra or {})},
               path)


def _by_name(old: torch.Tensor, old_names: list[str], fresh: torch.Tensor, names: list[str], dim: int) -> torch.Tensor:
    """Rearranges old's slices along dim to match names; a name old doesn't have keeps fresh's slice."""
    where = {name: i for i, name in enumerate(old_names[:old.shape[dim]])}
    slices = [old.select(dim, where[n]) if n in where else fresh.select(dim, i).to(old.device)
              for i, n in enumerate(names)]
    return torch.stack(slices, dim)


def load_model(path, device: str = "cpu") -> torch.nn.Module:
    checkpoint = torch.load(path, map_location=device)
    # Checkpoints from before the transformer existed have no "arch" and are GNNs.
    net = create_model(checkpoint.get("arch", "gnn"), **checkpoint["hparams"]).to(device)
    state = checkpoint["state_dict"]
    # New action types get the fresh embedding rows; removed ones are dropped.
    if "action_type_emb.weight" in state:
        state["action_type_emb.weight"] = _by_name(
            state["action_type_emb.weight"], checkpoint.get("action_types", LEGACY_ACTIONS),
            net.action_type_emb.weight.detach(), [t.name for t in ActionType], 0)
    # New ability node features get zero weights, so an older model ignores them; removed ones are dropped.
    if "ability_in.0.weight" in state:
        weight = net.ability_in[0].weight.detach()
        state["ability_in.0.weight"] = _by_name(
            state["ability_in.0.weight"], checkpoint.get("ability_features", LEGACY_FEATURES),
            torch.zeros_like(weight), list(FEATURES), 1)
    net.load_state_dict(state)
    net.eval()
    return net
