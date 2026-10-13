# TCG-Project

Using graph neural networks and self-play to design a novel, balanced set of cards for a
trading card game. The rules engine and ML training live in Python; Unity handles the
playable client and rendering.

## Repository layout

```
PythonServer/          Game engine, agents and training (Python, managed with uv)
  src/game/            rules engine and card definitions
  src/agents/          agents that play the game
  src/model/           GNN models
  scripts/             entry points: training, self-play, analysis
  models/              trained model checkpoints
TCGClient/             Unity client
```

## Python setup

Requires [uv](https://docs.astral.sh/uv/). Run commands from `PythonServer/`:

```
cd PythonServer
uv sync
uv run python -m scripts.<script_name>
```

## Unity client

The Unity project lives in `TCGClient/`. Not yet set up.
