# TCG-Project

Goal: generate a complete, balanced ~3000-card set for an **original** trading card game from
scratch. The rules are written by hand; agents trained through self-play judge the cards.

1. **Part a:** rules engine and state graph.
2. **Part b:** self-play agent.
3. **Part c:** card set generation.

The rules follow Hearthstone's broad structure (rules v2: mana, heroes, attacks; the earlier
Lorcana-style v1 is recorded in docs/technical-plan.md section 2b). The card pool is entirely synthetic: never use real cards, names or text from any
existing game. Read [docs/technical-plan.md](docs/technical-plan.md)
for the design.

## Status and planning

The project dashboard is an Obsidian note: `~/Documents/Workspace/01-Projects/TCG Project/Overview.md`.
It has the status, next steps, open decisions, known limitations and a done log. Keep it up to
date when work lands: tick items, add dated entries to "Done", and record decisions.

Decisions already made (don't re-open without a reason):
- **Cards:** fully synthetic cards; all game terms are placeholders.
- **Rules v2:** Hearthstone-style, chosen because more players and readers know it. Heroes
  with 30 health, mana up to 10, units attack units or the hero. Units only attack: no
  activated (⟳) abilities are generated (the engine keeps them for a later mechanic).
- **Blog series:** part 1 setup and card generation, part 2 self-play and balancing, part 3 a
  twist of our own.
- **Model:** PyTorch, with the heterogeneous GNN (`--arch gnn`) as the default model. The
  entity transformer (`--arch transformer`) is kept for accelerators.
- **TPUs:** no TPU / JAX work until profiling shows the model is the bottleneck.
- **Theme:** mushrooms with jobs ([docs/theme.md](docs/theme.md)). Game terms and keywords stay generic;
  aspects are habitats (Ember, Bog, Moss, Meadow, Glow, Frost); traits are jobs, not yet tied to abilities.
- **Client:** the Unity client is a thin view. The Python server owns all rules and state.
- **Ability generation:** generate and test with general tests on the tree's shape, never
  rules about particular cards; one ability per card for now. Keep
  [docs/ability-generation.md](docs/ability-generation.md) up to date (stages, tests,
  numbers, log) whenever the generator changes.
- **Abilities:** authored as trees (the grammar in docs/technical-plan.md section 3), compiled to
  decision graphs that the engine walks and the GNN reads. Static abilities and keywords stay
  declarative.

## Layout

```
PythonServer/   Python 3.12, managed with uv. Run everything from here.
  src/cards/    card schema (pure data), generators (vanilla, keywords, coverage), ability
                sampler / validator / card text, quality tests, the card pipeline
                (generate.py), derivation traces (trace.py), rough costing
  src/game/     rules engine, decks, terms.py (every player-facing name)
  src/graph/    encode.py (state → NumPy) → builder.py (PyG) / dense.py (padded tensors)
  src/model/    gnn.py, transformer.py, registry.py (create / save / load by arch)
  src/agents/   random, heuristic, neural agents; match runner
  src/training/ PPO self-play
  src/server/   GameSession: JSON requests → engine (used by scripts/server.py)
  scripts/      generate_cards, card_lab, train, benchmark, server (run as `python -m scripts.<name>`)
  cardsets/     generated card sets (JSON, one card per line)
  models/       trained checkpoints (gitignored); models/tcgnet.pt is the server's AI
  tests/        pytest
TCGClient/      Unity 6000.3.10f1, URP 2D template
docs/           technical plan, client protocol and design, theme, draw.io diagrams (+ PNGs)
```

## Commands (from `PythonServer/`)

```
uv sync
uv run pytest
uv run python -m scripts.generate_cards     # --kind keywords|vanilla|abilities|coverage, --count N
uv run python -m scripts.card_lab           # card lab web page, /explorer for one card's path (--text, --export)
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
  (`-p 2` → `architecture_state_graph.png`, `-p 3` → `architecture_ability_grammar.png`).
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
- **Client code** (`TCGClient/Assets/Scripts/`): `Net/` (NetMQ REQ socket on a thread +
  main-thread dispatcher), `Protocol/` (JSON models, snake_case like the protocol), `View/`
  (`CardView`, palette, `Ui` building blocks and `UiTheme`, the client's few chrome strings in
  `UiText`), `Board/` (`BoardView` renders a state and animates action results,
  `BoardInteraction` handles drags, drop zones and taps, `Overlays.cs` has inspect, mulligan
  and game over, `GameController` runs the request flow and steps the AI with `ai_move`).
  The human's decisions are commands (`Commands.cs`): each step picks its action from the
  latest `legal_actions`, so a multi-step choice like the mulligan is picked locally and sent
  in one go, and indexes never go stale.
  Ability UI: `View/CardText.cs` builds card text from the server's `keywords` and
  `ability_text`; `Board/AbilityPanels.cs` has the choice banner and the dev scenario panel
  (DEV button); `Board/AutoPlayer.cs` is a dev-only random player for soak tests (add it to the
  Game object in Play mode). Lilita One and Nunito lack ⟳ and →: DejaVu Sans Bold is their
  TMP fallback.
- **No rules in C#.** Drop zones come only from `legal_actions`; drag previews ("+2 VP",
  "Defeated") come from each legal action's `preview`, and animations from each action
  record's `result`; the engine records both as it applies the rules (`StepResult`), so the
  client never works out a result. Animation uses DOTween (free; its TMP tweens are Pro-only, so tween TMP values by hand).
- **Generated assets:** the card prefab, `Scenes/Main.unity`, TMP font assets and sprite import
  settings are built by `Scripts/Editor/ClientAssetBuilder.cs` (menu **TCG > Rebuild Client
  Assets**, or `-executeMethod ClientAssetBuilder.BuildAll` in batch mode). Change layout there,
  not by hand: a rebuild overwrites the prefab and scene. Placeholder sprites come from
  `TCGClient/Tools/make_placeholder_sprites.py` (`uv run --no-project --with pillow python Tools/make_placeholder_sprites.py`).
- **NetMQ shutdown:** `NetMQConfig.Cleanup` can hang in Unity; it runs on the network thread,
  which is abandoned if slow. Never call it on the main thread (it froze the editor).
