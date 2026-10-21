# Theme: mushroom folk with jobs

Every character in the game is a **mushroom with a job**: a fisher, a baker, a knight, a
postman. The tone is quirky, warm and playful. Scuffles on the forest floor are comedic, not
violent. The art aims for a highly rendered 3D animated-film look.

The game's name is still to be decided.

## What the theme changes, and what it doesn't

- **Game terms and keywords stay as they are:** VP, energy, unit, score, duel, exhausted,
  fresh, Guard, Elusive, Charge, Evolve, and so on. Players already know these words from other
  card games. They live in `PythonServer/src/game/terms.py`.
- **Aspects get habitat names** (below). Later they work like Hearthstone classes (your hero
  comes from one habitat, and your deck is that habitat's cards plus neutral cards); for now
  they are only colours.
- **Traits are jobs** (below).
- **Unit names** combine a mushroom species with a job, plus a subtitle. **Action cards** get event names.

## Aspects

Each aspect is a habitat. The internal IDs and colours are unchanged; the colours are the
ones in [client-design.md](client-design.md).

| ID | Aspect | Colour | Habitat and feel |
|---|---|---|---|
| `aspect_1` | **Ember** | `#F0533A` | toadstools from burnt woodland: fiery reds, ash and embers |
| `aspect_2` | **Bog** | `#2F86E8` | damp, puddle-dwelling shrooms: rain, lily pads, reeds |
| `aspect_3` | **Moss** | `#43B04F` | the deep forest floor: moss, ferns, fallen logs |
| `aspect_4` | **Meadow** | `#F5B52E` | sunny field mushrooms: farms, bakeries, wildflowers |
| `aspect_5` | **Glow** | `#9152E0` | bioluminescent night shrooms: fireflies, moonlight, soft glows |
| `aspect_6` | **Frost** | `#22BCC9` | snowcaps of the winter woods: ice, pine needles, frost |

**Neutral cards** have no habitat (shown in grey, `#8A93AD`): any deck can use them. Vanilla and
keyword-only units are neutral. What each habitat is *good at* isn't decided yet: it should come
from clustering the generated cards (docs/technical-plan.md section 2), not from a hand-written
list. For now ability cards get a habitat at random.

## Jobs (traits)

A unit's traits are its jobs. **Jobs aren't tied to particular abilities yet.** That's a
later decision: generation could leave them neutral, or give each job a leaning.

The starting list, open to additions:

| | | | |
|---|---|---|---|
| Fisher | Baker | Knight | Archer |
| Forager | Bard | Postman | Gardener |
| Lamplighter | Burglar | Doctor | Blacksmith |
| Scholar | Miner | Sailor | Chef |
| Firefighter | Beekeeper | Tailor | Explorer |

## Card names

**Units** are a **species + job** (the character) with a **subtitle** (this version of it):
"Porcini Baker – Up Before Dawn". 18 species × 20 jobs is only 360 characters, and a 3000-card
set needs the same character to come back several times with different abilities, as versions
of a character do in other card games.

The subtitle is picked from what the card does. It comes from a phrase bank keyed by:
- the ability's trigger ("Up Before Dawn" for start of turn, "Last Batch" when defeated)
- or its main effect ("Bookworm" for drawing, "Gentle Touch" for healing)
- or, for statics, its kind ("Head of the Guild" for "your other Bakers get +1")

A generic bank ("Apprentice", "Old Timer") is the fallback. Every species + job + subtitle is
unique in a set.

**Action cards** are events, not characters, so they have no species or job. Their name is an
aspect word plus a noun for the main effect: "Ember Volley" (damage), "Frost Forecast" (draw),
"Lichen Rally" (ready). Each aspect has its own words (Ember: Ember, Cinder, Smoulder,
Bonfire; Frost: Frost, Rime, Snowdrift, Icicle; …).

The phrase banks are theme data in `PythonServer/src/cards/theme.py`, and
`src/cards/names.py` picks from them. Names never affect rules or what the network sees. They
can be replaced later by an LLM naming pass that reads the card text. Today's banks give about
100,000 unit names and 1,800 action names.

Species + job pairs, ideally with a pun or alliteration:

- Oyster Fisher
- Inkcap Scholar
- Morel Knight
- Chanterelle Bard
- Puffball Postman
- Truffle Burglar
- Shiitake Chef
- Enoki Lamplighter
- Porcini Baker
- Fly-agaric Firefighter

Species to draw from: fly agaric (toadstool), chanterelle, morel, porcini, oyster, inkcap,
puffball, enoki, shiitake, truffle, button, portobello, chicken-of-the-woods, lion's mane,
turkey tail, honey fungus, bioluminescent ghost fungus, snowcap.

**Species suit aspects:**
- **Glow:** bioluminescent species
- **Ember:** red toadstools
- **Frost:** pale snowcaps

**Evolve fits naturally:** a button mushroom evolves into its grown-up form, e.g.
"Button Fisher" → "Portobello Fisher".

## Art direction

- **Style:** highly rendered 3D animated feature-film look (Disney/Pixar-like):
  - soft subsurface scattering on caps and velvety gills
  - big expressive eyes and stubby little legs
  - warm rim lighting and shallow depth of field
- **Scale:** the world is seen at mushroom height. Clover leaves, dewdrops, acorns and
  fireflies are big. Props are made from found things: twig fishing rods, walnut-shell
  shields, thimble watering cans, leaf letters.
- **Card art:** one character, centred, in a vertical 4:5 frame, over a soft radial glow
  in its aspect's colour that fades to dark navy at the edges. No text in the art: the card
  frame, name and rules text come from the Unity client.
- **Consistency:** generate a multi-character style sheet first, then use it as a
  reference for each card ("in exactly this style").
- **For release:** aim for a recognisable house style rather than imitating a specific
  studio.

### Preview prompts (Gemini)

**Card art: Oyster Fisher (Bog)**
> A charming little oyster mushroom character with a fan-shaped, pale grey-blue cap and big expressive eyes, sitting on a lily pad at the edge of a rain puddle, holding a tiny twig fishing rod with a dewdrop bobber, wearing a miniature yellow rain hat. It looks proudly at a minnow it just caught. Highly rendered 3D animated feature-film style, like a modern Disney/Pixar movie: soft subsurface scattering on the cap, velvety gills, warm rim lighting, shallow depth of field. Centred composition, vertical 4:5 framing, background a soft radial glow in deep teal blue fading to dark navy at the edges. No text, no frame.

**Style sheet: six jobs**
> A character line-up of six cute mushroom characters standing side by side, each a different species with a different job: a red fly-agaric knight with a walnut-shell shield, a golden chanterelle baker holding a tiny loaf, a tall inkcap scholar with round spectacles and a scroll, a puffball postman with a satchel of leaf letters, a glowing blue bioluminescent lamplighter carrying a firefly lantern, and a morel gardener with a thimble watering can. Consistent style across all six: highly rendered 3D animated film look in the style of Disney/Pixar, stubby little legs, expressive faces, soft studio lighting, plain light grey background, full body, front view. No text.

**Key art: a duel on the forest floor**
> Two small teams of mushroom characters facing off across a mossy log on the forest floor at dusk, in a playful standoff. On the left: a fiery red toadstool team with acorn-cap helmets. On the right: a frosty white snowcap team with pine-needle spears. A grumpy little puffball in the middle is about to bonk someone with a twig. Giant clover leaves and dewdrops for scale, bioluminescent mushrooms glowing in the background, fireflies. Highly rendered 3D animated feature-film style like Disney/Pixar, cinematic lighting, warm and cool colour contrast, wide 16:9 composition, playful rather than violent. No text.

**Evolve: before and after (Glow)**
> A two-panel character sheet of the same mushroom character before and after growing. Left: a tiny, shy bioluminescent button mushroom with a faint blue glow, peeking out from moss. Right: the same character fully grown into a tall, confident glowing mushroom wizard with a wide cap that emits soft cyan light and a staff made from a curled fern. Highly rendered 3D animated film style like Disney/Pixar, matching proportions and colours across both panels, dark purple background with a radial violet glow. No text.

## Still to decide

- The game's name.
- Whether jobs lean towards certain abilities, and how strongly.
- The final job and species lists, and how many jobs a set uses. A set probably wants a
  handful of jobs per aspect, so each job has enough cards to build around.
