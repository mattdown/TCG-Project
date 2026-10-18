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
  example below was captured from a real game with seed 7.
- All game terms (VP, energy, unit, score, duel, aspect…) are placeholders. Show the `text`
  fields to players rather than building strings from the raw values where possible.

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
      "energy_source": true, "cost": 5, "power": 3, "health": 3, "score": 2, "traits": ["Scholar"],
      "keywords": {"elusive": true}},
     …200 cards…]}
```

| Field | Meaning |
|---|---|
| `id` | card definition ID, referenced by `card_id` in the state |
| `type` | `"unit"` or `"action"` (played from hand, its ability resolves, then it goes to the discard pile; no stats) |
| `aspects` | one of `aspect_1` … `aspect_6`: Ember, Bog, Moss, Meadow, Glow, Frost ([theme.md](theme.md)) |
| `energy_source` | can be added to the energy zone |
| `cost`, `power`, `health`, `score` | stats; `score` is the VP gained when the unit scores |
| `traits` | the unit's job, e.g. `["Scholar"]` |
| `keywords` | `{"guard": true, "duelist": 2}`: flags are `true`, Duelist and Armor carry a number. Show them as `Guard.`, `Duelist +2.` (see the keyword rules below) |
| `abilities` | ability trees (the grammar in [technical-plan.md](technical-plan.md) section 3); the client doesn't need to read them |
| `ability_text` | one line of card text per ability, e.g. `"When you play this unit, draw a card."`: show these in the text box |

**Keyword rules** (the server already applies them; the client only shows them):

| Keyword | Rule |
|---|---|
| Guard | can be dueled even while ready, and opponents must duel a Guard unit if they can |
| Elusive | only Elusive units can duel it |
| Charge | can duel the turn it's played (it still can't score that turn) |
| Duelist +N | +N power when it starts a duel |
| Armor +N | takes N less damage in a duel, never below 0 |

Legal duel actions and their previews already account for all of these.

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
  "scenario": {"hand": ["C1-004"], "play": ["C1-007", {"id": "C1-010", "exhausted": true, "damage": 1}],
               "opponent_play": ["C1-002"], "opponent_hand": [], "energy": 5, "opponent_energy": 0}
  ```

  Units placed in play can act straight away, and energy is ready. Every key is optional. An
  unknown card ID is an error.

**Checking cards with the coverage set.** `uv run python -m scripts.generate_cards --kind coverage`
writes a small set that uses every building block of the ability grammar at least twice
(`cardsets/coverage_37.json`), plus a checklist next to it (`coverage_37.md`). Start the server
with `--cards cardsets/coverage_37.json`, then use scenarios to try each card.

### `state`: the current state

```json
→ {"type": "state"}
← {"status": "ok", "state": {…}}
```

### `act`: the human chooses an action

Only valid when `state.decision_player == state.human_seat`. `action_index` is the `index`
of one of `state.legal_actions`.

```json
→ {"type": "act", "action_index": 8}
← {"status": "ok",
   "action": {"type": "duel", "card": 4, "target": 104, "player": 0, "text": "Duel: Tidal Trickster → Tidal Vagabond",
              "result": {"damage": [{"uid": 4, "amount": 1}, {"uid": 104, "amount": 1}], "defeated": [4, 104],
                         "vp": [], "energy_spent": [], "exhausted": [4], "readied": [],
                         "moves": [{"uid": 4, "card_id": "V1-010", "player": 0, "from": "play", "to": "discard"},
                                   {"uid": 104, "card_id": "V1-059", "player": 1, "from": "play", "to": "discard"}]}},
   "state": {…}}
```

`action` is the action record, with its `result` (see [Results](#results-and-previews)).

### `ai_move`: the AI makes one decision

Only valid when it's the AI's decision. Call it repeatedly to animate the AI's turn one step
at a time.

```json
→ {"type": "ai_move"}
← {"status": "ok", "action": {"type": "end_turn", "card": null, "target": null, "player": 1, "text": "End turn",
     "result": {"damage": [], "defeated": [], "vp": [], "energy_spent": [], "exhausted": [], "readied": [37],
                "moves": [{"uid": 53, "card_id": "V1-098", "player": 0, "from": "deck", "to": "hand"}]}},
   "state": {…}}
```

Ending the AI's turn starts yours: it readies your exhausted cards and you draw.

### `ai_turn`: the AI decides until it's the human's decision or the game ends

The quick option when no step-by-step animation is needed.

```json
→ {"type": "ai_turn"}
← {"status": "ok", "actions": [
     {"type": "add_energy", "card": 108, "target": null, "player": 1, "text": "Add Quiet Piper as energy"},
     {"type": "duel", "card": 78, "target": 11, "player": 1, "text": "Duel: Humble Squire → Quiet Weaver"},
     {"type": "score", "card": 99, "target": null, "player": 1, "text": "Score with Ashen Gardener"},
     {"type": "play", "card": 79, "target": null, "player": 1, "text": "Play Bright Warden"},
     {"type": "end_turn", "card": null, "target": null, "player": 1, "text": "End turn"}],
   "state": {…}}
```

(Each record also has its `result`; left out here.)

## The state

Always from the human's point of view: the AI's hand and both decks' contents are never
sent. A mid-game example (turn 7, the human's turn; most of the hand trimmed):

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
    {"vp": 1, "energy_ready": 3, "energy_total": 3, "deck_count": 50, "hand_count": 4,
     "hand": [{"uid": 12, "card_id": "V1-022", "exhausted": false, "fresh": false, "damage": 0}, …],
     "play": [{"uid": 5, "card_id": "V1-100", "exhausted": false, "fresh": false, "damage": 0}],
     "discard": [ …2 cards… ],
     "mulligan_marked": []},
    {"vp": 2, "energy_ready": 0, "energy_total": 3, "deck_count": 50, "hand_count": 4,
     "hand": null,
     "play": [{"uid": 99, "card_id": "V1-034", "exhausted": true, "fresh": false, "damage": 0},
              {"uid": 79, "card_id": "V1-143", "exhausted": false, "fresh": true, "damage": 0}],
     "discard": [ …1 card… ],
     "mulligan_marked": null}
  ],
  "legal_actions": [
    {"index": 0, "type": "add_energy", "card": 12, "target": null, "text": "Add Golden Scholar as energy"},
    {"index": 1, "type": "add_energy", "card": 39, "target": null, "text": "Add Rusty Scholar as energy"},
    {"index": 2, "type": "play", "card": 39, "target": null, "text": "Play Rusty Scholar"},
    {"index": 3, "type": "add_energy", "card": 47, "target": null, "text": "Add Rusty Lantern as energy"},
    {"index": 4, "type": "score", "card": 5, "target": null, "text": "Score with Velvet Rider"},
    {"index": 5, "type": "duel", "card": 5, "target": 99, "text": "Duel: Velvet Rider → Ashen Gardener"},
    {"index": 6, "type": "end_turn", "card": null, "target": null, "text": "End turn"}
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
| `vp` | victory points; 20 wins |
| `energy_ready` / `energy_total` | ready energy / cards in the energy zone |
| `hand` | the human's hand, or `null` for the AI (use `hand_count`) |
| `play` | units in play, in the order they were played |
| `mulligan_marked` | uids the human has marked to put back during the mulligan |
| `vp_to_win` | VP needed to win (20) |
| `legal_actions` | empty unless it's the human's decision |
| `pending` | `null`, or the ability waiting for a choice: `source` (uid), `card_id`, `kind` (`choose`, `may`, `choose_one`), `chooser` (seat), `ability_text`. Show it as a prompt ("Oyster Fisher: choose a unit") with the legal actions as the answers |

**Card instances** (`hand`, `play`, `discard`): `uid` identifies this physical card for the
whole game, so use it to track a card's GameObject as it moves between zones. `card_id`
points into the card set. `exhausted` (turned sideways), `fresh` (played this turn, can't
act), `damage` (current damage; defeated at `damage >= health`).

**Actions**: `card` is the uid of the acting or played card, `target` the uid of the duel
target or chosen card, `option` the ability or option index. Action types:

| Type | Meaning | `card` | `target` |
|---|---|---|---|
| `mulligan` | mark a hand card to put back | hand card | — |
| `keep_hand` | finish the mulligan (marked cards are replaced) | — | — |
| `add_energy` | put an energy-source card from hand into the energy zone (once per turn) | hand card | — |
| `play` | play a unit, exhausting energy equal to its cost | hand card | — |
| `score` | exhaust a ready, non-fresh unit to gain its score in VP | unit | — |
| `duel` | exhaust a ready, non-fresh unit to fight an exhausted opposing unit | unit | opposing unit |
| `end_turn` | pass the turn | — | — |
| `activate` | use a ⟳ ability: exhausts the unit and pays its other costs; `option` = which of the card's abilities | unit | — |
| `choose_target` | while an ability resolves: pick a card for it | the ability's source | the chosen card |
| `accept` / `decline` | answer a "you may …" | the ability's source | — |
| `choose_option` | pick one option of a "choose one"; `option` = which, `text` describes it | the ability's source | — |

While `pending` is set, the legal actions are only the answers to that choice. Abilities
can also ask the AI's seat to choose: the client then calls `ai_move` as usual.

## Results and previews

The server reports every change an action makes, so the client never works one out itself.
The engine records them while it applies the rules (`StepResult` in `src/game/engine.py`).

- **`result`** on every action record (`act`, `ai_move`, `ai_turn`): what the action did.
- **`preview`** on legal `play`, `score` and `duel` actions: the same shape, from trying the
  action on a copy of the game, up to the first choice an ability asks for. Use it while
  dragging ("Drop to score · +2 VP", "Defeated"). Only moves of cards that were in play (and the
  played card itself) are kept, so a preview never reveals what an ability would draw. It's
  `null` for other actions.

```json
"preview": {"damage": [{"uid": 4, "amount": 1}, {"uid": 104, "amount": 1}], "defeated": [4, 104],
            "vp": [], "energy_spent": [], "exhausted": [4], "readied": [],
            "moves": [{"uid": 4, "card_id": "V1-010", "player": 0, "from": "play", "to": "discard"},
                      {"uid": 104, "card_id": "V1-059", "player": 1, "from": "play", "to": "discard"}]}
```

| Field | Meaning |
|---|---|
| `damage` | damage dealt to each unit (uid, amount) |
| `defeated` | uids of units defeated (they also move from `play` to `discard`) |
| `vp` | VP gained per player |
| `energy_spent` | ready energy exhausted per player to pay a cost |
| `exhausted` | units exhausted by acting (scoring, dueling) |
| `readied` | cards readied at the start of a turn (units and energy) or by an ability |
| `moves` | cards moved between zones, in order: `uid`, `card_id`, `player` (owner), `from`, `to`; zones are `deck`, `hand`, `play`, `energy`, `discard` |
| `abilities` | uids of the cards whose abilities started resolving, in order (to highlight the card as its ability happens) |

**Hidden moves.** The AI's draws and mulligan put-backs keep only who and where:
`{"uid": null, "card_id": null, "player": 1, "from": "deck", "to": "hand"}`. Every other move
names the card: your own cards, and anything going into or out of play, energy or discard.

Examples, from the game above (seed 7):

```json
play:   "preview": {…, "energy_spent": [{"player": 0, "amount": 1}],
                    "moves": [{"uid": 4, "card_id": "V1-010", "player": 0, "from": "hand", "to": "play"}]}
score:  "preview": {…, "vp": [{"player": 0, "amount": 1}], "exhausted": [4]}
your end_turn: "result": {…, "moves": [{"uid": null, "card_id": null, "player": 1, "from": "deck", "to": "hand"}]}
```

## Client flow

```
startup:   card_set → cache card definitions by id
new game:  new_game → render state
loop:
  if state.game_over:                       show the winner, offer a new game
  elif decision_player == human_seat:       show legal_actions; on a choice → act(index)
  else:                                     ai_move (animate each step) or ai_turn
  animate the action's result, then render the returned state
```

- **Mulligan:** both players mulligan before turn 1, the first player first. The human picks
  `mulligan` actions (each marks one card, shown in `mulligan_marked`) and then `keep_hand`.
  The AI's mulligan happens through `ai_move` / `ai_turn` like any other AI decision.
- **One request at a time:** REQ/REP can't have two requests in flight. Run the socket on a
  background thread with a queue, and hand responses back to Unity's main thread
  (PyTenTen's client does exactly this).
