# TCG-Project

Using graph neural networks and self-play to design a novel, balanced set of cards for a
trading card game. The rules engine and ML training live in Python; Unity handles the
playable client and rendering.

See [docs/technical-plan.md](docs/technical-plan.md) for the design of the rules engine,
state graph and model. All game terms (VP, energy, units, duels…) are placeholders.

## Repository layout

```
PythonServer/          Game engine, agents and training (Python, managed with uv)
  src/cards/           card schema and the vanilla card generator
  src/game/            rules engine, random deck builder, placeholder terms
  src/graph/           state → graph (HeteroData) for the network
  src/model/           policy-value GNN
  src/agents/          random, heuristic and neural agents; match runner
  src/training/        PPO self-play
  src/server/          game session behind the Unity server
  scripts/             entry points (below)
  cardsets/            generated card sets (JSON, one card per line)
  models/              trained checkpoints (gitignored)
  tests/               pytest suite
docs/                  technical plan and draw.io diagrams
TCGClient/             Unity 6 client (6000.3.10f1)
```

## Python setup

Requires [uv](https://docs.astral.sh/uv/). Run every command from `PythonServer/`:

```
cd PythonServer
uv sync
```

| Command | What it does |
|---|---|
| `uv run python -m scripts.generate_cards` | Writes the 200-card vanilla set to `cardsets/vanilla_200.json` (`--count`, `--seed`) |
| `uv run python -m scripts.train` | PPO self-play on random decks; writes `models/tcgnet.pt` and `models/tcgnet_best.pt`. Every `PPOConfig` field is a flag, e.g. `--iterations 200 --games-per-iteration 32` |
| `uv run python -m scripts.benchmark` | Round-robin win rates: random, heuristic and (if trained) neural agents |
| `uv run python -m scripts.server` | ZeroMQ server for the Unity client on `tcp://*:5555` |
| `uv run pytest` | Runs the tests |

## Current rules (vanilla units only)

Two players, 60-card decks of one or two aspects, 7-card opening hand with one mulligan.
Each turn: ready your cards, draw (the first player skips their first draw), then any
number of actions:

- **Add energy:** once per turn, put an energy-source card from hand into your energy zone.
- **Play** a unit by exhausting energy equal to its cost. It is *fresh* until your next turn.
- **Score:** exhaust a ready, non-fresh unit to gain its score in VP.
- **Duel:** exhaust a ready, non-fresh unit to fight an *exhausted* opposing unit. Both deal
  damage equal to their power; a unit is defeated when its damage reaches its health.
  Damage stays between turns.

The first player to 20 VP wins; drawing from an empty deck loses; turn 100 is a draw.

## Unity client protocol

The server speaks JSON over a ZeroMQ REQ/REP socket. Request types: `card_set`,
`new_game`, `state`, `act`, `ai_move`, `ai_turn`; see
[session.py](PythonServer/src/server/session.py) for the fields. The state is always from
the human player's point of view: the AI's hand and both decks are hidden.
