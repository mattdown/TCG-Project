# Client design

The look and the interaction model for the Unity client. The mockups are a design canvas:
<https://claude.ai/artifact/X7BvrK2fMP9huCZ6DdqsKt> (private to the owner; open it with the
Artifact tool or ask for a share). The **Art style** page has the board, the inspect screen and
the card style sheet. The **UX flows** page has one frame per gesture. The protocol the client
talks is in [client-protocol.md](client-protocol.md).

Everything named here (aspects, keywords, card names) is a placeholder, like the rest of the game.

> **Rules v2 (2026-10-21).** The game moved to Hearthstone-style rules
> ([technical-plan.md](technical-plan.md) section 2), and the look below still shows v1 in
> places. Client milestone 4 (built 2026-10-21) changed:
> - **VP bars → hero portraits** with health out of 30. The enemy hero is an attack target.
> - **Energy gems and the energy zone → mana crystals:** full / total, up to 10, refilled each
>   turn. No "add as energy" drop zone, no energy-source rim on the cost gem.
> - **No score crowns** on cards, and no score drop zone.
> - **The Spare Spore:** a small button for the second player's one-off +1 mana.
> - **Units only attack:** drag an arrow from a unit to any enemy unit or the enemy hero. A unit that has attacked is dimmed (no "Zz" since 2026-10-22); a frozen one shows ice; a
>   hidden (Elusive) one can't be targeted by enemies.
> - **Subtitles** under card names.
>
> As built: each hero keeps its v1 corner (the enemy's top left, yours bottom left) with a
> heart and a health bar in place of the VP bar; the enemy hero's whole panel is the
> `attack_hero` drop target, ringed red while an arrow is out and showing "22 → 19" under the
> finger. Mana crystals are painted stones (`Art/Sprites/mana_full.png` / `mana_empty.png`) in a
> row with a "4/6" count, over a soft dark glow that widens with the row; the ones a play would
> spend get a gold disc behind them. The Spare Spore is a purple button left of
> the turn pill, labelled with the action's text. Frozen units show ice and a ❄ over the art;
> hidden ones a lilac veil. Unit names leave the banner's right end to the power and health
> badges.

## Look

Reference: Clash Royale. Vibrant colours, chunky display type, thick dark outlines, buttons with
a darker lip along the bottom edge, white numbers with a dark outline.

| Token | Value |
|---|---|
| Outline / darkest navy | `#0E1733` |
| Panel navy | `#16203D` (cards), `#1E2C55` (UI background) |
| Light panel (card text box) | `#E9EEF8` |
| Energy (cost gem, energy bar) | `#E24BD6`; spent / empty `#3A2558` |
| Power | `#F08A24` |
| Health | `#E8364F` |
| Score crowns, primary button | `#FFC93C`, lip `#D98A10` |
| Stat above printed value | `#7CFF7C` |
| Stat below printed value | `#FF8A96` |
| Glows | playable `#81FF00`, selected `#FFE14D`, target `#FF4D5E` |
| Field | checkerboard `#5E9C57` / `#5A9753`, 44 px squares, darkening to navy at the top and bottom edges |

Aspect colours, one per `aspect_N`: Ember `#F0533A`, Bog `#2F86E8`, Moss `#43B04F`,
Meadow `#F5B52E`, Glow `#9152E0`, Frost `#22BCC9`. Card art uses the aspect colour as a radial glow.
The aspect names and the rest of the theme are in [theme.md](theme.md).

Fonts: Lilita One for numbers, names and buttons; Nunito (700–900) for body text.

## Layout

Landscape only, designed at 1280×720 (16:9). Wider phones get extra space at the sides.

| Area | Where |
|---|---|
| Opponent bar | top strip: avatar, name, deck and hand counts, VP bar (left); energy gems (right); card backs peek in at top centre |
| Opponent units | one centred row near the top |
| Arena | the painted forest clearing (`Art/Sprites/game_background.jpeg`), scaled to cover the screen with its centre line on the divider between the unit rows (`View/BackgroundFit.cs`) |
| Your units | one centred row below the divider |
| Your VP | bottom left: avatar, deck count, VP bar |
| Your energy, END TURN | bottom right: energy gems with a ready/total count, turn number, END TURN button |
| Hand | fanned along the bottom centre, partly off-screen |

## The card

One card design is used everywhere: 150×210 at 100% in hand, 86% on the field, about 2× when
inspected. Every card on the field shows its full text.

- **Frame:** painted art (`Art/Sprites/card_frame.png`; action cards use `card_frame_action.png`,
  which has no power orb or health shield). The card art shows through the oval window. The
  builder places every part in the frame art's own pixels (`ClientAssetBuilder.FrameBox`).
- **Cost:** on the frame's pink gem, top left.
- **Name:** on the wooden banner under the art; the subtitle goes on the small tab below it.
- **Text box:** the parchment, in dark brown. Keywords are bold and end with a full stop (`Guard.`); triggers are bold and end with a colon (`On play:`). Text is centred and auto-sizes (10 down to 5 pt) so the box never resizes. Vanilla cards show flavour text in italics.
- **Traits:** a small navy tag on the bottom edge, its rim in the aspect colour.
- **Power:** on the gold orb, bottom left.
- **Health:** on the red shield, bottom right, showing health *left* (damage lowers the number).

States:

| State | Shown as |
|---|---|
| Attacked (this turn) | art dimmed; the card is **not** tilted, and the text stays readable |
| Damaged | health number in red |
| Buffed / debuffed | stat number in green / red |
| Selected | lifted 10 px, gold glow |
| Target | red glow |
| Playable (in hand), or can still attack (your units) | green glow |
| END TURN with nothing else left to do | the button pulses with a gold glow |

## Interaction

Two gestures, matching Hearthstone:

- **Hand cards follow the finger** and drop onto a zone.
- **Units on the field stay put**; you drag an **arrow** from them to a target.

While dragging, every valid drop shows a flat rounded rectangle: faint for the other options,
bright in its action colour under the finger, with a label. Highlights come from the state's
`legal_actions`, so a zone only lights up if a matching action exists, and a drop sends
`act(index)` for that action.

| Gesture | Drop on | Action | Highlight |
|---|---|---|---|
| Drag a hand card | your side of the field | `play` | green zone, "Drop to play · N mana"; a light slot shows where it lands; the crystals it will spend are outlined |
| Drag an arrow from a unit | an enemy unit | `attack` | valid targets get red rings, others dim; the hovered one shows the result ("Defeated", "Takes 2") |
| Drag an arrow from a unit | the enemy hero | `attack_hero` | the portrait gets a red ring; the health previews the loss ("−3") |
| Tap any card | — | inspect | the card at ~2× with an explanation box per keyword; hand cards also get a PLAY button, greyed out when not legal |

Rules behind the highlights (from `src/game/engine.py`): any enemy unit can be attacked, but
while the enemy has a Guard unit, attacks must go to one; hidden Elusive units can't be
attacked; a unit can attack once per turn, not on the turn it's played (unless it has Charge);
a card can be played if its cost is at most your mana and, for a unit, you have fewer than 7
in play. The client doesn't need any of this: the legal actions already say it.

Drag previews come from each legal action's server-side `preview`
([client-protocol.md](client-protocol.md)), so the client never computes a result itself.

## Built without a design (simple placeholders, same style)

- **Mulligan:** the hand large over a dimmed board; tap cards to put back (they dim with a
  PUT BACK badge; tap again to keep one), then KEEP HAND. Picking is local: KEEP sends the
  whole choice at once (a `mulligan` act per card, then `keep_hand`).
- **Game over:** result, final VP for both players, NEW GAME.
- **The opponent's turn:** one `ai_move` every 0.6 s. A played card flies in from their hand, an
  added energy flies to their gems as a card back, a duel shows the arrow for half a second, a
  score pulses the unit. Damage ("-2"), defeats, VP gains and card moves come from each action
  record's `result`.

- **Abilities** (milestone 3):
  - *Card text:* keywords first (`Guard.`, a granted one in green), then one paragraph per
    ability line. The lead-in is bold: a trigger up to its first comma
    (`When you play this unit,`). Choose-one
    options go on their own lines. Long text ends in "…" on the card; the inspect panel has it all.
  - *Action cards:* no power, health or crowns. Played by dragging onto the field; the card
    shows large in the middle while it resolves, then fades to the discard pile.
  - *Stats:* current values from the server, green above the printed value, red below.
  - *Choices:* a banner across the divider with the source card's name and the ability text.
    Cards that can be chosen get a gold ring and are tapped; Yes / No and choose-one options are
    buttons. The AI's choices show the banner too ("heuristic is choosing"), a little longer.
  - *Inspect:* a box per keyword with the server's reminder text, the full card text, and chips
    for attacked, fresh, damage, frozen and hidden.
  - *Feedback:* the cards in `result.abilities` pulse gold in order; healing, stat changes,
    granted keywords and VP lost float up from the card.
  - *Dev panel:* the DEV button, bottom left, starts a `scenario` from text such as
    `hand: C1-004; opponent_play: C1-018, C1-036 attacked; energy: 2; seed: 1`.
  - *GNN overlay:* the GNN button, next to DEV, darkens the board and draws the server's `graph`
    over it: card nodes on their cards with each card's ability graph unfolded below, player
    nodes on the heroes, the global node by the turn counter. Each node is a disc coloured by
    node type, with its embedding inside as a greyscale column (4 cells, light positive, dark
    negative, so the node colours stand out); edges
    are coloured by type, tapping a type in the legend hides it, and hovering a node lights its
    edges. A panel in the top right lists the legal actions by the
    network's probability (top 10), and the value, with the legend below it; hovering a row (tap to keep it) fades the other nodes
    and draws a line from each node the head reads, coloured by its slot in the head's input
    (policy: actor, target, context, option, global; value: global, you, opponent). It refreshes after every state while open
    (`Board/GraphOverlay.cs`).

## Help screen

Mockup: the canvas's UX flows page, artboard "6 · Help: how to read a card". A blue **?** button
(44 px, top right; the enemy's mana sits to its left) opens it over the dimmed board; the red ✕
or a tap outside closes it. Built in `Board/HelpView.cs`; the button in `ClientAssetBuilder`.

- **How to read a card:** the real card prefab at 2×, showing a unit from the loaded set (one with
  a keyword, ability text and a subtitle if there is one). Gold callouts with leader lines: Cost,
  Class colour, Name, Rules text on the left; Attack, Health, Job on the right. Their targets are
  worked out from the card's own parts (`CardView.CostGem`, `FrameEdge`, `NameText`, `BodyText`,
  `PowerIcon`, `HealthIcon`, `TraitTag`), so they follow layout changes. Attack's label sits above
  the heart with its line running down to the sword's blade, so it isn't read as the health.
  Three notes under the card: green / red numbers, no attacking on the turn a unit is played
  (unless Charge), Frozen units skip their next attack.
- **Keywords:** a box per keyword from `card_set`'s `keywords` (numbered ones as "Duelist +N").
- **Classes:** the six habitats and Neutral, with names and one-line descriptions from
  `card_set`'s `aspects`; the colours are the client's (Neutral is `#8A93AD`).

## Not designed yet
- Phone sizes: board text is ~9 px at 86%, readable on tablets and desktop but small on phones.
