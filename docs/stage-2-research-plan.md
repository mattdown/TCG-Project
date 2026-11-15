# Stage 2 research plan: balancing against the best decks

Stage 1 showed the system works: an agent that reads cards it has never seen, a generator
whose prices can be measured in play, and a loop where better prices made skill matter more
(the trained agent went from 62% to about 70% against the heuristic agent on unseen cards once actions
and abilities were priced from measurements, `ability-generation.md` log, 2026-10-23).

Stage 2 is the research problem: pricing cards so that **no deck is broken**, not just so that
the average card is fair.

## 1. Why stage 1's method isn't enough

Every measurement so far prices a card by its **average value across random decks**: the
deck tests, the price scales and the per-effect calibration (`scripts/experiments.py`).

Real balance is about the **best decks a card can be in**. Players find them, and the
metagame forms around them. A card that is fair in 99% of decks and twice as strong in one
combination defines the format. The current method misses it twice over:

- **Random decks almost never assemble a synergy.** A specific two-card combination in a
  1,000-card pool shows up in a tiny share of games.
- **Averaging hides it when it does.** A 1% tail barely moves a mean.
- **A synergy only shows if the agent can play it.** Combos need setup and sequencing, so a
  weaker agent undervalues exactly the cards that are dangerous in skilled hands. Prices are
  already skill-dependent: v4 got more out of unit abilities than v3 did on the same cards.

So the question changes from "what is this card worth on average?" to "what is the most this
card can be worth, in the decks a strong player would build?"

## 2. What "balanced" means: targets we can measure

Stage 2 needs targets that are numbers, so methods can be compared:

| Target | Measure |
|---|---|
| **No dominant deck** | The best deck found wins at most X% (e.g. 60%) against the field of strong decks |
| **A diverse metagame** | Many decks in the equilibrium mixture (below), from different jobs and card types |
| **Most cards playable** | Share of cards that appear in at least one strong deck |
| **No must-play card** | No card appears in more than Y% of strong decks |
| **Fair on average** | Stage 1's tests stay near 50% (a regression check, not the goal) |
| **Skill matters** | A stronger agent beats a weaker one by a clear margin on balanced sets |

## 3. Building blocks we already have

- **Engine:** fast, deterministic, hidden information handled, fuzz-tested.
- **Agent:** reads ability trees as graphs, so it handles any generated card;
  `tcgnet_v4` beats the heuristic agent 69% on unseen cards (275–125 over 400 games).
- **Generator:** controls where synergy can come from (jobs, triggers such as "whenever you
  play another Baker", summons, buffs, "for each" counts), with derivation traces.
- **Measurement harness:** `scripts/experiments.py` with paired seats, parallel workers, and
  re-priced copies of cards. Throughput on this Mac is roughly 5–10 games a second with the
  neural agent across 10 processes; the heuristic agent is much faster.

The main constraint is compute: every method below spends games, and search over decks spends
a lot of them.

## 4. Approaches

### A. Deck search

Search deck space for the strongest decks, with the agent playing them. Candidates:
- **Evolutionary search:** mutate decks (swap cards), keep the winners against a field.
- **Quality-diversity (MAP-Elites):** keep the best deck in each niche (e.g. by main job,
  curve, share of actions), so the search maps the space of *different* strong decks instead
  of converging on one.

A card's value is then measured in the decks that are good. Cost: thousands of games per
generation, so it needs a cheap evaluator (D).

**MAP-Elites in detail** (following Fontaine et al. 2019, section 8):
- **Fitness:** the hero health difference summed over a deck's games against a fixed field, not
  the win rate, so the margin counts and the signal is smoother.
- **Behaviour descriptors:** the paper's are deck statistics known before any game (mean and
  variance of cost). Keep mean cost for comparison, and add at least one measured from play
  (share of damage to the hero rather than units, game length, board width), so the archive
  maps play-styles, not mana curves.
- **Sliding boundaries:** cell edges at percentiles of the decks seen so far, recomputed every
  100 evaluations, because decks bunch up and an even grid wastes most cells.
- **Which agent:** the GNN is the judge, but at 5–10 games a second the paper's budget (about
  2 million games) would take days. Build and tune the loop with the heuristic agent, then
  either batch the GNN's inference across games or search with the heuristic and re-score
  only the archive with the GNN (about 400 elites × 200 games). Where the two agents disagree
  about a deck is a result in itself.
- **Bias:** the map depends on the agent. One fixed policy may play extreme decks badly, so
  the map shows the agent's weak spots as well as the decks'. Check elites with a second agent.
- **Later:** CMA-ME emitters instead of random card swaps once the search runs over continuous
  parameters (G below).

### B. The metagame as a game

Treat deck choice as a game between players and solve it:
- **Double oracle / PSRO:** keep a population of decks, compute the equilibrium mixture of
  the matchup table, add the best response to that mixture (found with A), repeat.
- The equilibrium gives the balance targets directly: how many decks it uses, whether one
  dominates, which cards appear in it.

### C. Worst-case pricing per card (red-team decks)

For each card, search for the deck that gets the most out of it, then raise its price until
even that deck isn't dominant. This is minimax pricing instead of averaging, and it is the
direct answer to the "1% of decks" problem. Doing it for every card is expensive, so it
should run on cards flagged by D or E.

### D. Deck-level surrogate model (synergy-aware cost)

Predict a deck's strength from its cards: card embeddings (the agent's card encoder) combined
with attention, trained on game results and matchups from A–C.
- **Synergy becomes measurable:** the deck's predicted value minus the sum of its cards' values.
- **It's the cheap evaluator** deck search needs, with real games only to check the best candidates.
- **It generalises the cost model:** a card's price is no longer one number but a function of
  the deck around it, and the price that matters is its value in the best decks.

### E. Targeted exploration from the generator

The generator knows which cards reference each other: a job trigger and that job's units,
"for each unit" and summons, buffs and wide boards. A graph of these references can point A
and C at likely combinations, instead of waiting to find them by chance.

### F. A stronger player

Synergies only matter if the agent can play them. Candidates:
- **Search at play time:** determinized MCTS or IS-MCTS (guess the hidden cards, search each
  guess) with the value head at the leaves. A turn's order of plays and attacks is the main
  planning problem, and the engine is deterministic within a turn, so even shallow search
  should help.
- **Longer training on more varied decks**, including decks from A, so the agent learns to play
  strong archetypes, not just random piles. Probably on a cloud GPU.
- **Search in training (expert iteration):** use the same shallow search while training, so the
  policy learns to imitate moves the search found and the value head learns from their
  outcomes (AlphaZero-style), instead of PPO alone. Play-time search makes one agent stronger;
  search in training makes the network itself stronger, which helps every measurement that runs
  the raw network. Train on A's elite decks, so A and F feed each other: deck search finds real
  archetypes, and a stronger agent makes deck search's verdicts trustworthy.

### G. Class identity: generation vectors

**Decided (2026-11-15): classes are designed**, top-down, with the emergent routes in H left for
later (and for the blog as what could come next). Balancing pulls classes together, so tuning
needs a term that keeps them apart.

Aspects become classes by changing what the generator makes, not what cards cost:
- **A shared base grammar plus a sparse offset per class** on the sampler's log-weights, keyed by
  the choice labels the sampler already has (`t.weighted("Effect", …)` in `src/cards/abilities.py`).
  Neutral cards use the base. **Hard zeros** (things a class never does) give more identity than
  soft tilts.
- **Themes:** bundles of offsets that go together (go-wide: make tokens, scale with unit count,
  buff all). Each card samples a theme first. Independent per-choice weights can't express
  choices that go together, and synergy lives in exactly those pairs.
- **More than abilities:** stat ratios, keyword frequency and the cost curve are part of the
  vector. **The cost model stays the same for every class**, so a style can't just mean cheaper.
- **Set-level checks:** quotas (or over-generate and select) so each class hits its targets, and
  enough enablers for every payoff. Measure the distribution that comes out (the derivation
  traces), not the input weights: the validator's rejections skew it.

### H. A play-style space

Three spaces and two maps: **generation (G) → card statistics (C) → play-style (S)**.
- **G → C** needs no play: generate a set and count. **C → S** needs self-play, so learn a
  surrogate on decks (one set gives thousands of decks).
- **S** starts from readable descriptors (game length, share of damage to the hero, board width,
  hand size, mana efficiency, how often units trade), measured against a fixed field. Later, a
  learned space from the GNN's state embeddings averaged over a deck's games, with the readable
  descriptors as labelled directions in it.
- **G → S:** nudge each generation weight and measure the change in style; an SVD of that
  Jacobian shows the few generation directions that move play-style at all.
  **S → G:** optimise toward a target style (CMA-ES on the surrogate, checked with real games),
  preferring sparse vectors, since many vectors give the same style.

**Letting styles emerge** instead of naming them up front (future work; for now classes are designed, G):
- **Synergy graph:** for each card pair, how much more often decks with both win than decks
  with either alone. Community detection gives archetypes; fit a class vector to each,
  regenerate, replay and recluster (like EM). This is "identity from clustering" made concrete.
- **Metagame check (B):** archetypes are real if they survive in the equilibrium mixture.
- **Learned descriptors** (AURORA-style) in MAP-Elites, or **co-evolving K classes** with a
  penalty for being too close.
- Styles that show up with only one agent are the agent's, not the cards'.

## 5. A first experiment with ground truth: planted synergies

Before trusting any method, test it on synergies we put there on purpose:
1. Take a balanced-on-average set and **plant** a few deliberately broken combinations: two
   fair-looking cards that together are far too strong (e.g. "your Bakers get +2/+2" plus
   cheap Baker summons), and a few deliberately overpriced cards as controls.
2. Ask each method to find them. Can random-deck averaging see them (expected: no)? Does
   deck search find the combination? Does the surrogate flag it as synergy? Does red-teaming
   price it correctly?
3. Measure how many games each method needs to find each planted combination.

This gives stage 2 what the ±1 mis-costed vanilla cards gave stage 1: a known answer to check
methods against. It's also a clear story for the blog.

## 6. Proposed order

| Milestone | Work | Done when |
|---|---|---|
| **M0** | Planted-synergy benchmark (section 5); metrics from section 2 as code | Random-deck averaging is shown to miss the planted combos |
| **M1** | Deck search (A): evolutionary first, then MAP-Elites, starting by adapting Fontaine et al. 2019 to our engine (heuristic agent, health-difference fitness, sliding boundaries, one play-measured descriptor). Measure games a second for both agents, batched and not, first | It finds the planted combos within a known budget of games |
| **M2** | Deck-level surrogate (D), trained on M1's games | It predicts held-out matchups well and flags planted synergies |
| **M3** | Metagame loop (B) using M1 for best responses and M2 to screen | An equilibrium over decks with diversity numbers |
| **M4** | Worst-case pricing (C) on flagged cards, then re-generate | The section 2 targets hold on a fresh set |
| **M5** | Stronger player (F) and scale to 3,000 cards | Targets still hold with a stronger agent; cloud runs |

F can start alongside any milestone: a stronger player makes every other measurement more
trustworthy. Search in training fits best once M1 has elite decks to train on.

Class identity (G and H) runs alongside M0–M1, since it only changes the generator: per-class
vectors with themes and set-level checks first, then MAP-Elites over decks from a class-weighted
set to see whether the classes land in different regions of the map. That is the first real
test of the idea. The emergent route (synergy graph, then fitted class vectors) needs M1's games.

## 7. Open questions

- **Where does the price live?** One cost per card, or a base cost plus learned deck-dependent
  corrections? Printed cards have one cost, so worst-case pricing has to collapse to one number.
- **Which field?** Balance against what: the equilibrium mixture, a fixed set of archetypes, or
  every deck found so far?
- **Skill dependence:** prices measured with agent N can be wrong for agent N+1. Re-measure
  after every agent improvement, or price for a fixed reference agent?
- **Aspects as classes:** turning on one aspect per deck (`ONE_ASPECT`) shrinks deck space a lot
  and is how real games contain synergy. When should it come in: before deck search, or after
  the class vectors (G) exist?
- **Compute:** how much of this fits on the Mac, and what goes to a cloud GPU (training) or many
  CPUs (games)?
- **Changing the generator vs re-pricing:** when a combination is broken, raise a price, change
  the card, or stop the generator making that pattern (a new general test)?

## 8. Related work to check

From memory, to verify before relying on it:
- Deck building by evolutionary search for Hearthstone (several papers around 2016–2019).
- "Evolving the Hearthstone meta": balancing by simulating a metagame (around 2019).
- Quality-diversity: Mouret & Clune, MAP-Elites (2015); Zhang, Fontaine et al., deep
  surrogate assisted MAP-Elites (2022); Grillotti & Cully, AURORA, learned behaviour descriptors (2022).
- Play-style: Holmgård et al., procedural personas (around 2014–15); Lin et al., playstyle
  metrics (2021, and ICLR 2024).
- Directions in a generator's latent space: InterFaceGAN and GANSpace (2020); Mario levels from a
  GAN's latent space (Volz et al. 2018; Fontaine et al. 2021).
- Summerville & Mateas, Mystical Tutor (2016): card text generation, no play in the loop.
- As far as we know, generating the whole card pool conditioned on a play-style space measured
  by self-play is new. Do a proper literature search before claiming it.
- PSRO (policy-space response oracles, 2017) and double-oracle methods for population-based
  game solving.
- Legends of Code and Magic: a research card game with competitions on drafting and playing.

Read in full:
- **Fontaine et al., "Mapping Hearthstone Deck Spaces through MAP-Elites with Sliding
  Boundaries"** (GECCO 2019, arXiv 1904.10656). SabberStone simulator; basic and classic cards
  (171 per class); a genome is a 30-card deck, mutated by replacing k random cards (k geometric,
  k = 1 half the time), no crossover. Fitness is the hero health difference summed over 200
  games against a field. Descriptors: the mean and variance of the deck's costs. Hunter,
  paladin and warlock, each played by scripted aggro and control agents. 10,000 evaluations per
  run on a 500-node cluster, the grid growing from 2×2 to 20×20. Aggro does best at low mean
  cost, control across a range; a nerf-and-buff experiment changed how often cards appear in
  elites, mostly as expected. Stated limitation: the results depend on the scripted agent.
- **Fontaine et al., CMA-ME** (GECCO 2020, arXiv 1912.02400). CMA-ES "emitters" inside MAP-Elites,
  rewarded for improving the archive. Its Hearthstone domain evolves the 109 weights of a small
  state-scoring network (descriptors: mean hand size and number of turns), and roughly doubles
  MAP-Elites' QD-score.
- **AI Playtesting** (<https://aiplaytesting.github.io/>), a 14-week project: an AI playtester for
  Slay the Spire, with 32 reimplemented cards and fixed 12–13 card decks against one scripted
  boss. The rules run in Python with Unity as a front end (the same split as ours), plus a
  designer app to build decks, train the agent with one click and chart playtest statistics.
  The agent is Deep Q-learning on a hand-made state vector with one output per card, so new
  cards mean retraining; action masking took it from a few percent to about 60%, and to 87–90%
  on two test decks a human always wins. Balancing is a designer reading the statistics.
  Useful for us:
  - **Decks with a known answer** to judge the agent: the same idea as our planted synergies.
  - **The agent missed the designers' combo** (playing Flex before attacks): a concrete case of
    section 4F, where an agent that can't execute a synergy undervalues its cards.
  - **The differences** are the point of this project: an agent that reads cards it has never
    seen (generated cards), two-player self-play instead of a scripted boss, and a closed loop
    that re-prices and regenerates cards instead of handing a designer a chart.

## 9. Blog part 2

The frame: **average-case balance versus worst-case balance.** Stage 1 is the average case,
and it worked (the hand-written cost table was off by about 2×, and self-play proved it).
Then the planted-synergy experiment shows why that isn't enough, and the rest of the post is
the search for the decks that break a set. A MAP-Elites explainer (`Blog/map_elites_visualiser.py`)
introduces the deck search, and classes with their own play-styles are the natural bridge to part 3.
Close on how classes could emerge instead of being designed (H): archetypes found in self-play,
then encoded as class vectors.
