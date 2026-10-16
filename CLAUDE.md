# TCG-Project

Goal: generate a complete, balanced ~3000-card set for an **original** trading card game from
scratch. The rules are written by hand; agents trained through self-play judge the cards.

1. **Part a:** rules engine and state graph.
2. **Part b:** self-play agent.
3. **Part c:** card set generation.

The rules follow Lorcana's broad structure, but the card pool is entirely synthetic: never use
real cards, names or text from any existing game. Read [docs/technical-plan.md](docs/technical-plan.md)
for the design.

## Status and planning

The project dashboard is an Obsidian note: `~/Documents/Workspace/01-Projects/TCG Project/Overview.md`.
It has the status, next steps, open decisions, known limitations and a done log. Keep it up to
date when work lands: tick items, add dated entries to "Done", and record decisions.

Decisions already made (don't re-open without a reason):
- **Cards:** fully synthetic cards; all game terms are placeholders.
- **Model:** PyTorch, with the heterogeneous GNN (`--arch gnn`) as the default model. The
  entity transformer (`--arch transformer`) is kept for accelerators.
- **TPUs:** no TPU / JAX work until profiling shows the model is the bottleneck.
- **Client:** the Unity client is a thin view. The Python server owns all rules and state.

## Layout

```
PythonServer/   Python 3.12, managed with uv. Run everything from here.
  src/cards/    card schema (pure data), vanilla card generator
  src/game/     rules engine, decks, terms.py (every player-facing name)
  src/graph/    encode.py (state → NumPy) → builder.py (PyG) / dense.py (padded tensors)
  src/model/    gnn.py, transformer.py, registry.py (create / save / load by arch)
  src/agents/   random, heuristic, neural agents; match runner
  src/training/ PPO self-play
  src/server/   GameSession: JSON requests → engine (used by scripts/server.py)
  scripts/      generate_cards, train, benchmark, server (run as `python -m scripts.<name>`)
  cardsets/     generated card sets (JSON, one card per line)
  models/       trained checkpoints (gitignored); models/tcgnet.pt is the server's AI
  tests/        pytest
TCGClient/      Unity 6000.3.10f1, URP 2D template
docs/           technical plan, client protocol and design, draw.io diagrams (+ PNG exports)
```

## Commands (from `PythonServer/`)

```
uv sync
uv run pytest
uv run python -m scripts.generate_cards
uv run python -m scripts.train [--arch gnn --iterations 100 --device mps]
uv run python -m scripts.benchmark [--models a.pt b.pt]
uv run python -m scripts.server            # tcp://*:5555 for the Unity client
```

Training prints are buffered when piped. Use `PYTHONUNBUFFERED=1` to watch a log. The
`torch.jit.script` FutureWarning comes from PyG and is harmless.

## Conventions

- **Cards are data.** A new card must never need new code. The network never sees a card ID,
  only what the card is, so it handles unseen and generated cards.
- **Player-facing names** go through `src/game/terms.py`, so the game can be renamed in one place.
- **Hidden information.** Observations and the server's state are always from one player's
  point of view. Never leak the opponent's hand or deck order.
- **Engine changes** come with tests in `tests/test_engine.py`. Use the helpers in
  `tests/helpers.py` to set up positions.
- **Code style.** Match the surrounding code: dataclasses, type hints, short docstrings that
  say why, and few inline comments.
- **Diagrams.** Edit `docs/architecture.drawio` in draw.io, then re-export the PNGs:
  `drawio -x -f png -s 1.25 -p 1 -o docs/architecture_overview.png docs/architecture.drawio`
  (`-p 2` → `architecture_state_graph.png`).
- **Git.** Commit only when asked.

## Unity client

- **Protocol:** [docs/client-protocol.md](docs/client-protocol.md) has every request with
  real example responses, the state fields and the client flow. The server code is
  `PythonServer/src/server/session.py`.
- **Design:** [docs/client-design.md](docs/client-design.md) has the agreed look (colours,
  fonts, layout, the card and its states) and the interaction model (drag targets driven by
  `legal_actions`, tap to inspect). It links the mockup canvas; read the canvas with the
  Artifact tool when you need exact markup.
- **Reference implementation:** the PyTenTen project (`~/Documents/PyTenTen/PyTenTenClient`)
  already solves the plumbing.
  - `Assets/Scripts/NetworkClient.cs`: NetMQ REQ socket on a background thread, with a queue.
  - `Assets/Scripts/UnityMainThreadDispatcher.cs`: hands responses back to the main thread.
  - NetMQ and its dependencies come from NuGetForUnity: see that project's
    `Packages/manifest.json`, `Assets/packages.config` and `Assets/NuGet.config`.
  - JSON uses Newtonsoft.Json. Animation uses DOTween (free).
- **Known protocol gap:** action records don't include results (damage dealt, units
  defeated). The client has to compare states to animate them; extend the server if that
  gets awkward.
