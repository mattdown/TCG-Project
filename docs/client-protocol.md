# Client protocol

How the Unity client talks to the Python game server. The server is the single source of
truth: the client renders the state it's given, shows the legal actions, and sends back the
index of the one the player picks. It never applies rules itself.

- Start the server from `PythonServer/`: `uv run python -m scripts.server` (port 5555;
  `--port`, `--cards`, `--model` to override).
- Transport: ZeroMQ **REQ/REP** on `tcp://localhost:5555`. Each request is one JSON string,
  and each gets exactly one JSON string back. REQ sockets must strictly alternate send /
  receive.
- Implementation: [src/server/session.py](../PythonServer/src/server/session.py). Every
  example below was captured from a real game with seed 7 on `keywords_200`.
- **Protocol v2 (2026-10-21)** follows rules v2 (Hearthstone-style, docs/technical-plan.md
  section 2): heroes with health, mana crystals, attacks on units or the hero. v1's energy,
  VP, scoring and duels are gone.
- All game terms (hero, mana, unit, attack, aspect…) are placeholders. Show the `text`
  fields to players rather than building strings from the raw values where possible.

## Status and checking cards

Client milestones 1–3 were built for protocol v1: the board, playing a full game, and
abilities (card text, action cards, the choice prompt, ability feedback, the dev
scenario panel). **Milestone 4 (2026-10-21) moved the client to protocol v2**, as listed below.
The protocol below is complete for everything the server does today.

Milestone 4, rules v2 (done):
- **Heroes:** a portrait for each player with `health` out of `hero_health` (30), in place of
  the VP bars. The enemy hero is a drop target for `attack_hero`.
- **Mana:** crystals (`mana` full of `crystals`, up to `max_mana` = 10) in place of the energy
  zone. There's no energy zone and no "add energy" action any more.
- **Attacks:** drag a unit onto an enemy unit (`attack`) or the enemy hero (`attack_hero`).
  Any enemy unit can be attacked. A unit that has attacked this turn is
  `attacked` (show it dimmed, as before); `can_attack` says whether it can still attack.
- **The Spare Spore:** the second player's one-off +1 mana, a button while `spare_spore` is true.
- **Card:** no score crowns and no energy-source rim. Cards have a `subtitle`: show it under
  the name in the name banner, smaller and in italics ("Porcini Baker" / "Up Before Dawn").
  Action cards have event names ("Ember Volley") and an empty subtitle. The card lab's card
  (`Blog/card_kit.html`) shows one way to lay it out.
- **Unit states:** `frozen` (can't attack until the end of its owner's next turn: show ice), `hidden` (Elusive and
  hasn't attacked yet: enemies can't target it).

**Next for the client (milestone 5, small):**
- **Neutral cards:** `aspects` can be empty (`[]`). Draw them in the neutral grey `#8A93AD`
  instead of an aspect colour; don't index `aspects[0]` without checking.
- **Hero aspect:** each player has an `aspect` (the deck's). Tint or frame the hero portrait
  with it.
- **Vanilla and keyword-only units** have no `ability_text`: show flavour, or just the
  keywords, in the text box.

**Checking cards by hand.**
1. Generate the coverage set: from `PythonServer/`, run `uv run python -m scripts.generate_cards --kind coverage`.
   It writes `cardsets/coverage.json`: a small set that uses every building block of the
   ability grammar at least twice, about a quarter of it action cards. It also writes the
   checklist [`cardsets/coverage.md`](../PythonServer/cardsets/coverage.md) next to it.
2. Run the server on it: `uv run python -m scripts.server --cards cardsets/coverage.json`.
3. Use the checklist. It lists every card with its text, then every building block (e.g.
   `decision: may`, `trigger: on_attack`) with the cards that use it. Start a `scenario` with the
   card and whatever it needs: enemy units to target, units of the jobs it mentions, mana,
   hero health. Card IDs change whenever the set is regenerated, so always take them from the
   current checklist.
4. Anything that doesn't match its text is a server bug: note the card and the scenario.

## Responses and errors

Every response has `"status": "ok"` or `"status": "error"`. Errors carry a `msg` and change
nothing on the server, so the client can show the message and carry on:

```json
{"status": "error", "msg": "it is not the AI's decision"}
{"status": "error", "msg": "action_index 999 out of range (0..6)"}
{"status": "error", "msg": "no game in progress: send new_game first"}
{"status": "error", "msg": "no trained model found: train one or choose another opponent"}
```

## Requests

### `card_set`: all card definitions

Fetch once at startup. The state only refers to cards by `card_id`, so the client looks up
stats and names here.

```json
→ {"type": "card_set"}
← {"status": "ok", "name": "keywords_200", "cards": [
     {"id": "K1-004", "name": "Puffball Scholar", "type": "unit", "aspects": ["aspect_4"],
      "cost": 1, "power": 2, "health": 1, "traits": ["Scholar"], "keywords": {}, "subtitle": "",
      "abilities": [], "ability_text": []},
     …200 cards…]}
```

| Field | Meaning |
|---|---|
| `id` | card definition ID, referenced by `card_id` in the state |
| `name`, `subtitle` | units: `"Porcini Baker"` and `"Up Before Dawn"`, the version of the character (show it under the name, smaller); action cards: an event name such as `"Ember Volley"` and an empty `subtitle`. Sets made before subtitles existed have `""` everywhere |
| `type` | `"unit"` or `"action"` (played from hand, its ability resolves, then it goes to the discard pile; no stats) |
| `aspects` | `[]` for a **neutral** card (any deck can use it; show it in grey, `#8A93AD`), or one of `aspect_1` … `aspect_6`: Ember, Bog, Moss, Meadow, Glow, Frost ([theme.md](theme.md)) |
| `cost`, `power`, `health` | mana cost and stats (actions have 0 power and health) |
| `traits` | the unit's job, e.g. `["Scholar"]` |
| `keywords` | `{"guard": true, "duelist": 2}`: flags are `true`, Duelist and Armor carry a number. Show them as `Guard.`, `Duelist +2.` (see the keyword rules below) |
| `abilities` | ability trees (the grammar in [technical-plan.md](technical-plan.md) section 3); the client doesn't need to read them |
| `ability_text` | one line of card text per ability, e.g. `"When you play this unit, draw a card."`: show these in the text box |
| `token` | `true` for a **token**: a unit an ability summons (`"Summon two 1/1 Sporelings."`), never in a deck. Tokens come after the set's cards, with ids like `"token:Sporeling-1/1"`, so a summoned unit's `card_id` is found like any other. They cost 0, are neutral, and may have a job and a keyword |

The response also has `keywords`: each keyword's player-facing name, whether it carries a
number, and its reminder text, for inspect panels (`N` is the number):
`"keywords": {"duelist": {"name": "Duelist", "numbered": true, "rule": "+N power while attacking."}, …}`.

It also has `aspects`: each habitat's player-facing name and a one-line description, keyed
like the cards' `aspects` field, plus `neutral` for cards with no aspect (an empty `aspects`
list). The client's help screen shows them; colours stay in the client.
`"aspects": {"aspect_1": {"name": "Ember", "description": "Burnt-woodland toadstools: fire and ash."}, …, "neutral": {"name": "Neutral", "description": "No habitat: any deck can use it."}}`.

**Keyword rules** (the server already applies them; the client only shows them):

| Keyword | Rule |
|---|---|
| Guard | enemy units must attack a Guard unit if they can (so the hero can't be attacked) |
| Elusive | can't be attacked or chosen by enemy abilities until it attacks |
| Charge | can attack the turn it's played |
| Duelist +N | +N power while attacking |
| Armor +N | takes N less damage from attacks, never below 0 |

Legal attack actions and their previews already account for all of these.

### `new_game`: start a game on random decks

```json
→ {"type": "new_game", "opponent": "neural", "human_seat": 0, "seed": 7}
← {"status": "ok", "opponent": "tcgnet", "state": {…}}
```

- `opponent`: `"neural"` (needs a trained model in `models/tcgnet.pt`), `"heuristic"` or
  `"random"`. Defaults to `"neural"`.
- `human_seat`: 0 or 1 (default 0). Who goes first is random: see `active_player`.
- `seed`: optional, makes decks and shuffles reproducible.
- `opponent` in the response is the AI's name (the model file name for neural agents).
- `scenario`: optional, for checking single cards by hand. The game skips both mulligans and
  starts on the human's first turn with chosen cards (IDs from `card_set`):

  ```json
  "scenario": {"hand": ["C1-004"], "play": ["C1-007", {"id": "C1-010", "attacked": true, "damage": 1}],
               "opponent_play": ["C1-002"], "opponent_hand": [], "mana": 5, "opponent_mana": 0,
               "health": 30, "opponent_health": 12}
  ```

  Units placed in play can attack straight away. `mana` sets the mana crystals, all full.
  Every key is optional. An unknown card ID is an error.

See [Status and checking cards](#status-and-checking-cards) for using scenarios with the coverage set.

### `state`: the current state

```json
→ {"type": "state"}
← {"status": "ok", "state": {…}}
```

### `act`: the human chooses an action

Only valid when `state.decision_player == state.human_seat`. `action_index` is the `index`
of one of `state.legal_actions`.

```json
→ {"type": "act", "action_index": 2}
← {"status": "ok",
   "action": {"type": "attack", "card": 12, "target": 53, "option": null, "player": 0,
              "text": "Attack: Porcini Chef → Enoki Postman",
              "result": {"damage": [{"uid": 12, "amount": 4}, {"uid": 53, "amount": 3}], "defeated": [12, 53],
                         "hero_damage": [], "hero_healed": [], "mana_spent": [], "crystals": [],
                         "attacked": [12],
                         "moves": [{"uid": 12, "card_id": "K1-022", "player": 0, "from": "play", "to": "discard"},
                                   {"uid": 53, "card_id": "K1-133", "player": 1, "from": "play", "to": "discard"}],
                         "abilities": [], "healed": [], "effects": []}},
   "state": {…}}
```

`action` is the action record, with its `result` (see [Results](#results-and-previews)).

### `ai_move`: the AI makes one decision

Only valid when it's the AI's decision. Call it repeatedly to animate the AI's turn one step
at a time.

```json
→ {"type": "ai_move"}
← {"status": "ok", "action": {"type": "end_turn", "card": null, "target": null, "option": null, "player": 1,
     "text": "End turn",
     "result": {"damage": [], "defeated": [], "hero_damage": [], "hero_healed": [], "mana_spent": [], "crystals": [],
                "attacked": [],
                "moves": [{"uid": 3, "card_id": "K1-070", "player": 0, "from": "deck", "to": "hand"}],
                "abilities": [], "healed": [], "effects": []}},
   "state": {…}}
```

Ending the AI's turn starts yours: you gain a mana crystal, they all refill, your units can
attack again and you draw.

### `ai_turn`: the AI decides until it's the human's decision or the game ends

The quick option when no step-by-step animation is needed.

```json
→ {"type": "ai_turn"}
← {"status": "ok", "actions": [
     {"type": "play", "card": 32, "target": null, "option": null, "player": 1, "text": "Play Shiitake Sailor"},
     {"type": "attack", "card": 43, "target": 26, "option": null, "player": 1, "text": "Attack: Porcini Beekeeper → Shiitake Baker"},
     {"type": "attack_hero", "card": 54, "target": null, "option": null, "player": 1, "text": "Attack: Fly-agaric Burglar → the enemy hero"},
     {"type": "attack_hero", "card": 32, "target": null, "option": null, "player": 1, "text": "Attack: Shiitake Sailor → the enemy hero"},
     {"type": "end_turn", "card": null, "target": null, "option": null, "player": 1, "text": "End turn"}],
   "state": {…}}
```

(Each record also has its `result`; left out here.)

### `graph`: the state graph the GNN reads

For the client's GNN overlay. The graph is built from the human's observation (the same one the
network gets), so the AI's hand and both decks never appear. Nodes are `card`, `player`
(`owner` 0 is the human), `global` and `ability` (the steps of each visible card's ability
graph). `id` is the node's index in `nodes`. Edges are the forward ones only (`belongs_to`,
`faces`, `opposes`, `in`, `part_of`, `next`, `uses`, `matches`, `bound_to`); the GNN also
passes messages back along each. `vectors` has one entry per layer (the input projection, then
one after each GNN layer), each the embedding averaged down to `dim` (4) numbers. With no GNN model on
the server, `embedding` is `"features"` and the single vector is the node's raw input features.

`actions` are the human's legal actions (same order and `index` as `legal_actions`; empty when
it's the AI's decision, since its view includes its hand), each with the nodes the policy head
scores it from: `actor` and `target` card nodes, `context` (the ability node being decided) and
`option` (the first node of a chosen option), null when the slot is empty, and always `global`.
`probability` is the network's softmax over the legal actions. `value` is the value head's
estimate for the human in [-1, 1] and the nodes it reads (global and both players). Both numbers
are null without a GNN model.

```json
→ {"type": "graph"}
← {"status": "ok", "graph": {"embedding": "gnn", "layers": 5, "dim": 4,
     "nodes": [
       {"id": 0, "type": "card", "uid": 12, "card_id": "S1-642", "owner": 0, "zone": "hand", "vectors": [[-0.01, 0.019, 0.04, -0.07], …]},
       …
       {"id": 7, "type": "player", "owner": 0, "vectors": […]},
       {"id": 9, "type": "global", "vectors": […]},
       {"id": 10, "type": "ability", "card": 0, "kind": "entry", "label": "entry: on_play", "resolving": false, "vectors": […]},
       {"id": 11, "type": "ability", "card": 0, "kind": "effect", "label": "effect: summon", "resolving": false, "vectors": […]}],
     "edges": [{"type": "belongs_to", "src": 0, "dst": 7}, {"type": "next", "src": 10, "dst": 11}, …],
     "actions": [{"index": 0, "type": "play", "text": "Play Enoki Tailor", "actor": 0, "target": null,
                  "context": null, "option": null, "global": 9, "probability": 0.12}, …],
     "value": {"estimate": -0.05, "nodes": [9, 7, 8]}}}
```

## The state

Always from the human's point of view: the AI's hand and both decks' contents are never
sent. A mid-game example (turn 7, the human's turn; most of the hand and the previews trimmed;
captured before decks became one aspect plus neutral, so a replay of seed 7 now differs):

```json
{
  "turn": 7,
  "phase": "main",
  "active_player": 0,
  "decision_player": 0,
  "human_seat": 0,
  "game_over": false,
  "winner": null,
  "players": [
    {"aspect": "aspect_3", "health": 22, "mana": 4, "crystals": 4, "spare_spore": false, "fatigue": 0, "deck_count": 23, "hand_count": 5,
     "hand": [{"uid": 29, "card_id": "K1-070", "attacked": false, "fresh": false, "damage": 0, "cost": 4,
               "power": 3, "health": 5, "keywords": {"charge": true}, "can_attack": false, "frozen": false,
               "hidden": false}, …],
     "play": [{"uid": 12, "card_id": "K1-022", "attacked": false, "fresh": false, "damage": 0, "cost": 1,
               "power": 1, "health": 1, "keywords": {"duelist": 2}, "can_attack": true, "frozen": false,
               "hidden": false}],
     "discard": [ …1 card… ],
     "mulligan_marked": []},
    {"aspect": "aspect_2", "health": 21, "mana": 0, "crystals": 3, "spare_spore": false, "fatigue": 0, "deck_count": 23, "hand_count": 4,
     "hand": null,
     "play": [{"uid": 53, "card_id": "K1-133", "attacked": true, "fresh": false, "damage": 0, …},
              {"uid": 54, "card_id": "K1-151", "attacked": true, "fresh": false, "damage": 1, …},
              {"uid": 43, "card_id": "K1-173", "attacked": false, "fresh": true, "damage": 0, …}],
     "discard": [],
     "mulligan_marked": null}
  ],
  "hero_health": 30,
  "max_mana": 10,
  "pending": null,
  "legal_actions": [
    {"index": 0, "type": "play", "card": 29, "target": null, "option": null, "text": "Play Snowcap Gardener", "preview": {…}},
    {"index": 1, "type": "play", "card": 26, "target": null, "option": null, "text": "Play Shiitake Baker", "preview": {…}},
    {"index": 2, "type": "attack", "card": 12, "target": 53, "option": null, "text": "Attack: Porcini Chef → Enoki Postman", "preview": {…}},
    {"index": 3, "type": "attack", "card": 12, "target": 54, "option": null, "text": "Attack: Porcini Chef → Fly-agaric Burglar", "preview": {…}},
    {"index": 4, "type": "attack", "card": 12, "target": 43, "option": null, "text": "Attack: Porcini Chef → Porcini Beekeeper", "preview": {…}},
    {"index": 5, "type": "attack_hero", "card": 12, "target": null, "option": null, "text": "Attack: Porcini Chef → the enemy hero", "preview": {…}},
    {"index": 6, "type": "end_turn", "card": null, "target": null, "option": null, "text": "End turn", "preview": null}
  ]
}
```

| Field | Meaning |
|---|---|
| `turn` | counts every player's turn; 0 during the mulligan, 1 is the first player's first turn |
| `phase` | `"mulligan"`, `"main"` or `"game_over"` |
| `active_player` | whose turn it is (during the mulligan: the first player) |
| `decision_player` | who must choose next. If it's `human_seat`, show `legal_actions`; otherwise ask the AI |
| `winner` | seat number, or `null` for a draw (turn 100) when `game_over` is true |
| `players[i]` | indexed by seat, not "you / them": use `human_seat` to tell which is the human |
| `aspect` | the hero's aspect: the deck's most common aspect (`null` if it has only neutral cards). For now aspects are only colours and decks mix them; later a deck will be one aspect plus neutral cards. Use it to tint the hero portrait |
| `health` | the hero's health left; 0 loses |
| `mana` / `crystals` | unspent mana this turn / mana crystals (one more each turn, up to `max_mana`; all refill at the start of your turn) |
| `spare_spore` | the second player's one-off +1 mana is still available |
| `fatigue` | damage the hero took from the last draw from an empty deck (the next one deals 1 more) |
| `hand` | the human's hand, or `null` for the AI (use `hand_count`); at most 10 cards (a card drawn into a full hand is discarded) |
| `play` | units in play, in the order they were played; at most 7 |
| `mulligan_marked` | uids the human has marked to put back during the mulligan |
| `hero_health`, `max_mana` | 30 and 10: a full hero and the most crystals |
| `legal_actions` | empty unless it's the human's decision |
| `pending` | `null`, or the ability waiting for a choice: `source` (uid), `card_id`, `kind` (`choose`, `may`, `choose_one`), `chooser` (seat), `ability_text`. Show it as a prompt ("Oyster Fisher: choose a unit") with the legal actions as the answers |

**Card instances** (`hand`, `play`, `discard`): `uid` identifies this physical card for the
whole game, so use it to track a card's GameObject as it moves between zones. `card_id`
points into the card set. `attacked` (has attacked this turn: show it dimmed),
`fresh` (played this turn: can't attack unless it has Charge), `damage` (current damage;
defeated at `damage >= health`).

They also carry current values, with every ability's changes applied, so the client can show
raised stats in green and lowered ones in red without working anything out:

```json
{"uid": 12, "card_id": "K1-022", "attacked": false, "fresh": false, "damage": 0, "cost": 1,
 "power": 1, "health": 1, "keywords": {"duelist": 2}, "can_attack": true, "frozen": false, "hidden": false}
```

| Field | Meaning |
|---|---|
| `cost` | current cost to play (hand cards include cost reductions) |
| `power`, `health` | current stats; health before damage (units only) |
| `keywords` | current keywords, including granted ones (`{"guard": true}`; units only) |
| `can_attack` | it's its owner's turn and it can attack now (has attack actions in `legal_actions` when it's yours) |
| `frozen` | can't attack on its owner's next turn |
| `hidden` | Elusive and hasn't attacked yet: enemies can't attack it or choose it |

**Actions**: `card` is the uid of the acting or played card, `target` the uid of the attacked
unit or chosen card, `option` the ability or option index. Action types:

| Type | Meaning | `card` | `target` |
|---|---|---|---|
| `mulligan` | mark a hand card to put back | hand card | — |
| `keep_hand` | finish the mulligan (marked cards are replaced) | — | — |
| `play` | play a card, paying its cost in mana | hand card | — |
| `attack` | a unit attacks an enemy unit: both deal their power as damage | unit | enemy unit |
| `attack_hero` | a unit attacks the enemy hero, who takes its power as damage | unit | — |
| `spare_spore` | the second player's one-off +1 mana for this turn | — | — |
| `end_turn` | pass the turn | — | — |
| `choose_target` | while an ability resolves: pick a card for it | the ability's source | the chosen card |
| `accept` / `decline` | answer a "you may …" | the ability's source | — |
| `choose_option` | pick one option of a "choose one"; `option` = which, `text` describes it | the ability's source | — |

While `pending` is set, the legal actions are only the answers to that choice. Abilities
can also ask the AI's seat to choose: the client then calls `ai_move` as usual.

## Results and previews

The server reports every change an action makes, so the client never works one out itself.
The engine records them while it applies the rules (`StepResult` in `src/game/engine.py`).

- **`result`** on every action record (`act`, `ai_move`, `ai_turn`): what the action did.
- **`preview`** on legal `play`, `attack` and `attack_hero` actions: the same shape, from
  trying the action on a copy of the game, up to the first choice an ability asks for. Use it
  while dragging ("−3", "Defeated"). Only moves of cards that were in play (and the
  played card itself) are kept, so a preview never reveals what an ability would draw. It's
  `null` for other actions.

```json
"preview": {"damage": [{"uid": 12, "amount": 4}, {"uid": 53, "amount": 3}], "defeated": [12, 53],
            "hero_damage": [], "hero_healed": [], "mana_spent": [], "crystals": [], "attacked": [12],
            "moves": [{"uid": 12, "card_id": "K1-022", "player": 0, "from": "play", "to": "discard"},
                      {"uid": 53, "card_id": "K1-133", "player": 1, "from": "play", "to": "discard"}],
            "abilities": [], "healed": [], "effects": []}
```

| Field | Meaning |
|---|---|
| `damage` | damage dealt to each unit (uid, amount) |
| `defeated` | uids of units defeated (they also move from `play` to `discard`) |
| `hero_damage` | damage to each player's hero (player, amount): attacks, abilities, fatigue |
| `hero_healed` | health each hero got back (player, amount) |
| `mana_spent` | mana paid per player |
| `crystals` | mana crystals gained from abilities per player (empty: they fill next turn) |
| `attacked` | units that attacked |
| `moves` | cards moved between zones, in order: `uid`, `card_id`, `player` (owner), `from`, `to`; zones are `deck`, `hand`, `play`, `discard` |
| `abilities` | uids of the cards whose abilities started resolving, in order (to highlight the card as its ability happens) |
| `healed` | damage removed from each unit (uid, amount) |
| `summoned` | tokens that entered play: `{"uid", "player", "card_id"}`, in order. They also appear in the player's `play` in the new state (fresh). Animate them appearing next to the card whose ability summoned them; a token that leaves play goes to the discard pile, even when returned to hand |
| `effects` | lasting changes abilities made: `{"uid", "kind", "stat", "keyword", "value", "this_turn", "lasts"}`; `lasts` is `this_turn`, `until_your_next_turn` (e.g. a granted Guard or Armor, which lasts through the opponent's turn), `until_its_next_turn` (freeze), `while_in_play` or `permanent`; `this_turn` is true only for `this_turn`; `kind` is `stat` (e.g. `power` −1), `keyword` (granted) or `freeze` |

**Hidden moves.** The AI's draws and mulligan put-backs keep only who and where:
`{"uid": null, "card_id": null, "player": 1, "from": "deck", "to": "hand"}`. Every other move
names the card: your own cards, and anything going into or out of play or the discard pile
(including a card the AI draws into a full hand, which is discarded face up).

Examples, from the game above (seed 7):

```json
play:        "preview": {…, "mana_spent": [{"player": 0, "amount": 4}],
                         "moves": [{"uid": 29, "card_id": "K1-070", "player": 0, "from": "hand", "to": "play"}]}
attack_hero: "preview": {…, "hero_damage": [{"player": 1, "amount": 3}], "attacked": [12]}
your end_turn: "result": {…, "moves": [{"uid": null, "card_id": null, "player": 1, "from": "deck", "to": "hand"}]}
```

## Client flow

```
startup:   card_set → cache card definitions by id
new game:  new_game → render state
loop:
  if state.game_over:                       show the winner, offer a new game
  elif decision_player == human_seat and state.pending:
                                            show the choice prompt; on an answer → act(index)
  elif decision_player == human_seat:       show legal_actions; on a choice → act(index)
  else:                                     ai_move (animate each step) or ai_turn
  animate the action's result, then render the returned state
```

- **Mulligan:** the first player starts with 3 cards, the second with 5. Both mulligan before
  turn 1, the first player first. The human picks
  `mulligan` actions (each marks one card, shown in `mulligan_marked`) and then `keep_hand`.
  The AI's mulligan happens through `ai_move` / `ai_turn` like any other AI decision.
- **One request at a time:** REQ/REP can't have two requests in flight. Run the socket on a
  background thread with a queue, and hand responses back to Unity's main thread
  (PyTenTen's client does exactly this).
