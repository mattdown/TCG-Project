# TCG-Project

Using graph neural networks and self-play to design a novel, balanced set of cards for a
trading card game. The rules engine and ML training live in Python; Unity handles the
playable client and rendering.

See [docs/technical-plan.md](docs/technical-plan.md) for the design of the rules engine,
state graph and model. All game terms (VP, energy, units, duels…) are placeholders.

## Repository layout

```
PythonServer/          Game engine, agents and training (Python, managed with uv)
  src/cards/           card schema, card generators, ability sampler / validator / text
  src/game/            rules engine, random deck builder, placeholder terms
  src/graph/           state → NumPy arrays (encode.py), then PyG graphs (builder.py)
                       or padded dense tensors (dense.py)
  src/model/           policy-value networks: heterogeneous GNN and entity transformer
  src/agents/          random, heuristic and neural agents; match runner
  src/training/        PPO self-play
  src/server/          game session behind the Unity server
  scripts/             entry points (below)
  cardsets/            generated card sets (JSON, one card per line)
  models/              trained checkpoints (gitignored)
  tests/               pytest suite
docs/                  technical plan, client protocol, draw.io diagrams
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
| `uv run python -m scripts.generate_cards` | Writes a 200-card set: units with keywords to `cardsets/keywords_200.json` (the default set), or `--kind vanilla` for stats only (`--count`, `--seed`) |
| `uv run python -m scripts.sample_abilities` | Prints abilities sampled from the grammar as card text (not playable yet) |
| `uv run python -m scripts.train` | PPO self-play on random decks; writes `models/tcgnet.pt` and `models/tcgnet_best.pt`. Every `PPOConfig` field is a flag, e.g. `--arch transformer --iterations 200 --device mps` |
| `uv run python -m scripts.benchmark` | Round-robin win rates: random, heuristic and neural agents (`--models a.pt b.pt` to compare checkpoints) |
| `uv run python -m scripts.server` | ZeroMQ server for the Unity client on `tcp://*:5555` |
| `uv run pytest` | Runs the tests |

## Current rules

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

Keywords:

- **Guard:** can be dueled even while ready, and opponents must duel a Guard unit if they can.
- **Elusive:** only Elusive units can duel it.
- **Charge:** can duel the turn it's played (but can't score that turn).
- **Duelist +N:** +N power when it starts a duel.
- **Armor +N:** takes N less damage in a duel.

**Abilities** follow the grammar in [docs/technical-plan.md](docs/technical-plan.md)
section 3: triggered (when played, scores, attacks, is defeated, start or end of turn, …),
activated (⟳, once per turn), on-resolve (action cards) and static. The engine compiles each
ability to a decision graph and resolves it on a stack; choices inside abilities (choose a
target, "you may", "choose one") are ordinary decisions. The default card set has no abilities
yet; the tests and the fuzz test (`FUZZ_GAMES=2000 uv run pytest tests/test_fuzz.py`) use
generated ones.

## Unity client protocol

The server speaks JSON over a ZeroMQ REQ/REP socket. Request types: `card_set`,
`new_game`, `state`, `act`, `ai_move`, `ai_turn`. See
[docs/client-protocol.md](docs/client-protocol.md) for example responses, the state fields
and the client flow. The state is always from the human player's point of view: the AI's
hand and both decks are hidden.
