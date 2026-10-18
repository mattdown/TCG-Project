# Client design

The look and the interaction model for the Unity client. The mockups are a design canvas:
<https://claude.ai/artifact/X7BvrK2fMP9huCZ6DdqsKt> (private to the owner; open it with the
Artifact tool or ask for a share). The **Art style** page has the board, the inspect screen and
the card style sheet. The **UX flows** page has one frame per gesture. The protocol the client
talks is in [client-protocol.md](client-protocol.md).

Everything named here (aspects, keywords, card names) is a placeholder, like the rest of the game.

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
| Glows | playable `#5BEA5B`, selected `#FFE14D`, target `#FF4D5E` |
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
| Divider | a thin semi-transparent white line across the field |
| Your units | one centred row below the divider |
| Your VP | bottom left: avatar, deck count, VP bar |
| Your energy, END TURN | bottom right: energy gems with a ready/total count, turn number, END TURN button |
| Hand | fanned along the bottom centre, partly off-screen |

## The card

One card design is used everywhere: 150×210 at 100% in hand, 86% on the field, about 2× when
inspected. Every card on the field shows its full text.

- **Cost:** a hexagonal gem, top left. A gold rim means it's an energy source; a dark rim means it isn't.
- **Score:** one crown per VP, top right of the art.
- **Name:** a banner in the aspect colour across the bottom of the art.
- **Text box:** keywords are bold and end with a full stop (`Guard.`); triggers are bold and end with a colon (`On play:`). Text is centred and shrinks in four steps (11.5 → 8.5 px) so the box never resizes. Vanilla cards show flavour text in italics.
- **Traits:** a small navy tag at the bottom centre.
- **Power:** an orange circle with a sword through it, bottom left.
- **Health:** a heart, bottom right, showing health *left* (damage lowers the number).

States:

| State | Shown as |
|---|---|
| Exhausted | art dimmed with "Zz"; the card is **not** tilted, and the text stays readable |
| Damaged | health number in red |
| Buffed / debuffed | stat number in green / red |
| Selected | lifted 10 px, gold glow |
| Target | red glow |
| Playable (in hand) | green glow |

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
| Drag a hand card | your side of the field | `play` | green zone, "Drop to play · N energy"; a light slot shows where it lands; the gems it will spend are outlined |
| Drag a hand card | the energy bar | `add_energy` | pink zone, "Drop to add as energy · once per turn"; a dashed gem slot appears |
| Drag an arrow from a unit | an exhausted opposing unit | `duel` | valid targets get red rings, others dim; the hovered one shows the result ("Defeated", "Takes 2") |
| Drag an arrow from a unit | your VP area | `score` | gold zone, "Drop to score · +N VP"; the VP bar previews the gain |
| Tap any card | — | inspect | the card at ~2× with an explanation box per keyword; hand cards also get PLAY / ADD ENERGY buttons, greyed out when not legal |

Rules behind the highlights (from `src/game/engine.py`): only exhausted opposing units can be
dueled; a unit can duel or score only if it's ready and wasn't played this turn; energy can be
added once per turn and only from energy-source cards; a card can be played if its cost is at
most your ready energy.

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

## Not designed yet
- Phone sizes: board text is ~9 px at 86%, readable on tablets and desktop but small on phones.
