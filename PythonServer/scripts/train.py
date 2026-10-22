"""PPO self-play training with a league. Writes models/tcgnet.pt (latest) and models/tcgnet_best.pt.

--cards takes one or more card sets: each game picks one, and evaluation uses the first."""
import argparse
from dataclasses import fields
from pathlib import Path

from src.cards.schema import load_card_set
from src.paths import CARDSET_PATH, MODEL_PATH
from src.training.ppo import PPOConfig, train


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards", type=Path, nargs="+", default=[CARDSET_PATH])
    parser.add_argument("--out", type=Path, default=MODEL_PATH)
    for f in fields(PPOConfig):
        parser.add_argument(f"--{f.name.replace('_', '-')}", type=type(f.default), default=f.default)
    args = parser.parse_args()

    cfg = PPOConfig(**{f.name: getattr(args, f.name) for f in fields(PPOConfig)})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    print(cfg)
    train(cfg, [load_card_set(path) for path in args.cards], args.out)


if __name__ == "__main__":
    main()
