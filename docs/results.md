# Results

What has been measured, with dates, so the numbers live in one place. The generator's own numbers
(funnel, rejection reasons, pricing steps) are in [ability-generation.md](ability-generation.md);
the design is in [technical-plan.md](technical-plan.md) and open work in [roadmap.md](roadmap.md).
Add new measurements here when they land.

Win rates are the first-named agent's, over paired games (each deck pair played twice with the
seats swapped) unless noted. Over 400 games one standard error is about ±2.4 points; over 100
games it's about ±4–5, so single 100-game evals can't separate checkpoints.

## Card sets used for evaluation

| Set | What it is |
|---|---|
| `set_1000` | The training set (seed 0) |
| `set_200` | The first 200 cards of `set_1000` (same seed), so **not** unseen by models trained on `set_1000` |
| `heldout_200` | 200 cards from seed 7: never trained on. The fair test of unseen cards |
| `armor_heavy` | 276 cards from seed 8 with plenty of Armor, which the agent used to play badly |
| `set_1000_g2`, `heldout_200_g2`, `armor_heavy_g2` | The same seeds and recipes with P2's first grammar batch (2026-11-17): new triggers, counts, "played this turn", random targets. Regenerated 2026-11-18 with measured trigger use rates (`armor_heavy_g2` has 220 cards; 228 before); numbers dated 2026-11-17 and v7g2's are on the first version |
| `keywords_200`, `vanilla_200`, `coverage` | Older and special-purpose sets |

Before 2026-11-15 the docs and blog part 1 called `set_200` "unseen". It isn't: v4's "69% on
unseen cards" was on cards it trained on. On truly held-out cards v4 scores 61.8%.

## The agent over time

| Model | Date | Training | vs heuristic | Notes |
|---|---|---|---|---|
| first model | 2026-10-15 | 100 iterations, rules v1, vanilla cards | 95.5% | The v1 heuristic was weak |
| keywords | 2026-10-18 | rules v1, `keywords_200` | 91.8% | |
| `tcgnet_v2` | 2026-10-21 | rules v2, from scratch | best 65% (100 games) | Plateaued at 55–65% |
| `tcgnet_abilities` | 2026-10-22 | 150 iterations, `set_1000`, reads abilities | 61% on `set_200` | The ability-blind model 52%; 55–58% head to head against it |
| `tcgnet_league` | 2026-10-22 | 400 iterations, league, mixed sets | 64% on `set_200` (400 games) | The "best" checkpoint was a lucky 100-game eval |
| `tcgnet_v3` | 2026-10-23 | 200 iterations from league, summons and buffs | 62.5% on `set_200` | |
| `tcgnet_v4` | 2026-10-23 | 120-iteration fine-tune on repriced sets | 68.8% `set_200`, 61.8% held-out, 60.0% Armor-heavy (400 games) | First measured as 74.8% over 100 games |
| `tcgnet_v5_control` | 2026-11-15 | 120-iteration fine-tune from v4 | 68.2% / 65.2% / 59.5% | Control for P1a |
| `tcgnet_v5_outcomes` | 2026-11-15 | same, with action-outcome features | 70.0% / 68.0% / 59.5% | |
| **`tcgnet_v6b`** | 2026-11-16 | 3,000 iterations from scratch, outcome features, about a day | **81.5% / 79.0% / 74.0%** | The server's AI since 2026-11-16; with search since 2026-11-17 |

### v6b against the earlier models (2026-11-16, 400 games each, seed 0)

| | `set_200` | `heldout_200` | `armor_heavy` |
|---|---|---|---|
| v6b vs heuristic | 81.5% | 79.0% | 74.0% |
| v6b vs v4 | 68.0% | 71.5% | 65.0% |
| v6b vs v5_outcomes | 65.0% | 64.8% | 65.8% |
| v6b vs `v6b_best` | 50.2% | 49.5% | 55.0% |

The biggest gain is on held-out cards, so the longer run generalises rather than memorises. The
"best" checkpoint (picked on one 100-game eval) was no better than the final one. Logs:
`PythonServer/data/eval_v6b_<set>.log` (not in git).

### Search within a turn (P1b, 2026-11-17, 400 games each, seed 0)

`SearchAgent` (beam 4, top-k 4, depth 12) around v6b, no retraining. Win rates are v6b+search's.
"Fair" guesses the opponent's hidden cards from the set; the first version ("leaky") re-dealt their
real remaining cards, so it knew their deck list (not their hand).

| | `set_200` | `heldout_200` | `armor_heavy` |
|---|---|---|---|
| v6b vs heuristic (same run) | 81.2% | 80.5% | 74.8% |
| v6b+search vs heuristic, fair | 87.5% | 89.5% | 83.8% |
| v6b+search vs v6b, fair | 59.5% | 65.8% | 63.5% |
| v6b+search vs heuristic, leaky | 88.0% | 89.2% | 84.8% |
| v6b+search vs v6b, leaky | 62.5% | 65.0% | 64.2% |

Search adds 7–9 points against the heuristic, most on held-out and Armor-heavy cards, and wins
about 63% head to head; games end about a turn sooner. Knowing the deck list made no difference
beyond noise, so the gain is from searching the turn. It costs about 90 ms a decision (about 25
positions scored each). Logs: `PythonServer/data/eval_search_fair_<set>.log` (and
`eval_search_<set>.log` for the leaky run).

### Search width (2026-11-17, v6b+search vs plain v6b, 400 games per set, seed 0)

| Beam × top-k | `heldout_200` | `armor_heavy` | Mean | Positions a decision | ms a decision |
|---|---|---|---|---|---|
| 1 × 1 | 44.0% | 43.0% | 43.5% | 5 | 55 |
| 2 × 2 | 54.7% | 60.5% | 57.6% | 11 | 70 |
| 4 × 2 | 56.0% | 58.8% | 57.4% | 17 | 80 |
| 2 × 4 | 60.0% | 60.0% | 60.0% | 15 | 74 |
| **4 × 4** | **64.0%** | **63.7%** | **63.9%** | **26** | **90** |
| 4 × 8 | 62.3% | 62.0% | 62.1% | 32 | 100 |
| 8 × 4 | 62.5% | 65.0% | 63.7% | 41 | 115 |
| 8 × 8 | 65.2% | 66.0% | 65.6% | 58 | 140 |

Each mean is 800 games (one standard error about ±1.7). The gain levels off at 4 × 4: 8 × 8 is
within noise of it at more than twice the positions, so 4 × 4 stays the default. Considering more
moves (top-k) helps more than keeping more lines (beam). The narrowest search, 1 × 1 (at each step,
the policy's favourite move or ending the turn), *loses* to the plain policy, which suggests
the value head is worse than the policy at choosing when to stop unless it also sees alternatives. Times are per
decision of the whole game, with 8 runs sharing the CPU on one thread each, so they're higher than
alone. Log: `PythonServer/data/search_sweep.jsonl`.

### Tactical puzzles: lethal (2026-11-17)

Positions from 200 v6b-vs-v6b games per set where the player to move has a sure win this turn
(`scripts/puzzles.py`; see the technical plan, section 8). The score is how often each agent takes
it. "Face": attacking the hero with everything is enough; "tactical": it takes more.

| | `heldout_200` face (144) | tactical (90) | `armor_heavy` face (189) | tactical (44) |
|---|---|---|---|---|
| heuristic | 72.9% | 40.0% | 58.2% | 47.7% |
| v6b | 89.6% | 77.8% | 89.4% | 65.9% |
| v6b+search | 93.8% | 88.9% | 94.7% | 81.8% |

- v6b misses about 1 in 10 face lethals. In almost every miss it attacks enemy units first and runs
  out of attackers: it trades when going face wins. The heuristic misses more for the same reason
  (it makes favourable trades before attacking the hero).
- Search fixes about half the misses, most on tactical puzzles (+11 and +16 points).
- About 7% of turns (256 of 3,617 and 244 of 3,943) were too big to search within 20,000
  positions, so the hardest positions are under-represented. The puzzles come from v6b's own games,
  so they're the lethals v6b's play leads to.

Puzzles: `PythonServer/data/puzzles_<set>.jsonl`, logs `puzzles_<set>.log` (not in git).

### Training on puzzles (2026-11-17)

Two 150-iteration fine-tunes from v6b on `set_1000` (seed 2): a control, and the same run with 64
puzzle episodes per iteration on top of the 64 games (776 lethal puzzles from 600 v6b games on
`set_1000`; one turn from the puzzle position, +1 for a win, otherwise minus the opponent's value
at their first decision). Scored on the held-out puzzles above (face / tactical, no search):

| | `heldout_200` | `armor_heavy` |
|---|---|---|
| v6b | 89.6% / 77.8% | 89.4% / 65.9% |
| control | 93.8% / 72.2% | 96.8% / 72.7% |
| puzzles | 86.8% / 70.0% | 87.8% / 52.3% |
| control+search | 96.5% / 87.8% | 97.4% / 84.1% |
| puzzles+search | 94.4% / 85.6% | 94.2% / 81.8% |

400 paired games (`heldout_200` / `armor_heavy`): the heuristic scores 19.5% / 25.2% against v6b,
18.0% / 25.0% against the control and 23.2% / 25.8% against the puzzle model. Head to head, v6b vs
the control 50.0% / 51.0%, v6b vs the puzzle model 48.0% / 47.8%, the control vs the puzzle model
46.0% / 46.2%.

- **Puzzle training made lethal worse,** not better, and its in-training solve rate didn't rise
  (65% over the first 10 iterations, 61% over the last 10). A likely reason: a missed lethal is
  scored by the value of the position left behind, which is usually already winning, so taking
  lethal is barely better than playing on.
- **More self-play alone helped:** the control takes 94–97% of face lethals, up from 89%.
- The puzzle model wins head to head (about 54%, just outside the noise) but does slightly worse
  against the heuristic, so it isn't clearly stronger. Neither fine-tune replaces v6b yet.

Logs: `PythonServer/data/train_v7_{control,puzzles}.log`, `puzzles_v7_*.log`, `bench_v7.log`.

### v6b on P2's grammar (2026-11-17, 400 paired games, seed 0)

v6b against the heuristic on the `_g2` sets, whose new triggers, counts, memory and random
targets it has never seen (their features load with zero weights): 73.2% on `heldout_200_g2` and
69.8% on `armor_heavy_g2`, against 80.5% and 74.8% on the old sets. So it still plays, but loses
6–7 points on the richer cards: a fine-tune on `set_1000_g2` is the next step.

### v7g2: v6b fine-tuned on `set_1000_g2` (2026-11-18, 400 paired games, seed 0)

300 iterations from v6b on `set_1000_g2` (seed 2, 4 workers, about 65 minutes). Win rate against
the heuristic:

| Model | `heldout_200_g2` | `armor_heavy_g2` |
|---|---|---|
| v6b | 73.2% | 69.8% |
| v7g2 (final) | 76.5% | 73.8% |
| v7g2_best (iteration 50) | 76.8% | 75.0% |

- **It wins back about half the drop** (3–5 points of the 6–7), each gain just above the noise.
- **Head to head it isn't clearly stronger:** v6b scores 51.0% and 49.0% against the two v7g2
  checkpoints on `heldout_200_g2`, 47.5% against both on `armor_heavy_g2`; final against best is
  49.2% and 47.8%. All within the noise.
- The 100-game evals were flat from iteration 50 on (73–80%), so most of the gain came early:
  the zero-weight features for the new constructs learn quickly, then it plateaus as v6b did.

Logs: `PythonServer/data/train_v7g2.log`, `bench_v7g2.log`.

### Fire rates on P2's grammar (2026-11-18, v7g2, `set_1000_g2`, 800 games)

`experiments.py fire`: hits per card played, relative to an un-narrowed "when played" unit (1.20
hits a play), next to `costing.TRIGGER_USES`. Narrowed rows are relative to narrowed "when played"
(0.88).

| Trigger | Measured | Narrowed | In `TRIGGER_USES` |
|---|---|---|---|
| ally_defeated | 0.87 (103 played) | 0.43 | 1.0 (guess) |
| damaged | 0.43 | 0.31 | 0.8 (guess) |
| action_played | 0.51 | 0.48 | 0.6 (guess) |
| token_summoned | 0.32 | 0.28 | 0.5 (guess) |
| on_defeated | 0.77 | 0.53 | 0.85 |
| on_attack | 0.79 | 0.49 | 1.2 |
| on_attack_hero | 0.43 | 0.24 | 0.7 |
| start_of_turn | 0.64 | 0.63 | 1.1 |
| end_of_turn | 1.31 | 1.65 | 2.0 |
| opposing_defeated | 1.26 | 0.70 | 1.0 |
| another_played | — | 0.24 | 0.8 |

- All four guesses were too high, `damaged` and `token_summoned` most (about 0.5× and 0.6×).
- The 2026-10-22 rates (league model, `set_200`) are mostly too high now as well: attacks, start
  and end of turn are about 0.6–0.65× of the table; only `opposing_defeated` is higher.
- Narrowing costs less than `NARROW_FACTOR` (0.5) assumes for most triggers: narrowed "when
  played" is 0.73× un-narrowed.

`costing.TRIGGER_USES` now uses all of the un-narrowed rates (`another_played` 0.24 / 0.73 =
0.33), and the `_g2` sets were regenerated with them; `NARROW_FACTOR` stays 0.5.

Log: `PythonServer/data/fire_v7g2.log`.

### v6b and v7g2 on the repriced `_g2` sets (2026-11-18, 400 paired games, seed 0)

Against the heuristic (in brackets: on the first `_g2` sets):

| Model | `heldout_200_g2` | `armor_heavy_g2` |
|---|---|---|
| v6b | 78.2% (73.2%) | 73.2% (69.8%) |
| v7g2 (final) | 79.5% (76.5%) | 69.5% (73.8%) |
| v7g2_best (iteration 50) | 79.8% (76.8%) | 75.2% (75.0%) |

Head to head, v6b scores 50.7% against v7g2 and 52.5% against v7g2_best on `heldout_200_g2`, and
56.2% and 47.0% on `armor_heavy_g2`; v7g2 against v7g2_best: 53.2% and 47.8%.

- **The repriced cards suit the agents:** v6b gains 3–5 points against the heuristic.
- **The fine-tune's lead is gone:** v7g2_best is level with v6b, and the final v7g2 loses to it
  on `armor_heavy_g2` (56.2%, about 2.5 standard errors). No model clearly beats v6b on the new
  sets, so there's nothing a re-fine-tune for the new prices would recover.

Log: `PythonServer/data/bench_v7g2_repriced.log`.

## Deck search

### MAP-Elites on `set_1000_g2` (2026-11-18, heuristic agent)

`scripts.map_elites`: 20,000 evaluations, a 10 × 10 map over average cost and the share of damage
dealt to the enemy hero (sliding boundaries every 100 evaluations), fitness the average
hero-health difference against a field of random decks in both seats. The heuristic plays both
sides. Every run filled all 100 cells.

How well the elites do against a fresh field (16 other random decks, other seeds), where random
decks average −1.3:

| Run | Games | Time (8 workers) | Elites on the search field | On a fresh field | Correlation |
|---|---|---|---|---|---|
| 8 field decks, the same game seeds for every deck | 320,000 | 376 s | +27.7 | +18.2 | −0.09 |
| 8 field decks, new seeds each evaluation | 320,000 | 403 s | +26.4 | +18.8 | 0.24 |
| 16 field decks, new seeds each evaluation (default) | 640,000 | 689 s | +27.6 | **+22.0** | 0.38 |

- **The elites are far stronger than random decks**, but overfit the field: a bigger field helps
  most; fixed seeds let the search fit the deals. Search scores are also a maximum over noisy
  evaluations, so they overstate the elites.
- **v6b agrees they're strong:** re-scored with v6b playing both sides, the elites average +23.6.
  But neither agent's order of the elites matches the other's (correlation 0.06): they're all
  close, and the differences between elites are mostly noise.
- **One core of underpriced cards:** 246 cards appear in any elite, but about a dozen are in 85–99
  of the 100, mostly cheap removal and draw: 1-mana actions that deal 5–7 damage to a unit or
  draw 3–4 cards, and 2-mana units that deal 3–5 damage to a random enemy unit. None are the
  deliberately mis-costed cards (those are only in the vanilla and keyword sets); the rough costing
  prices them too low.
- **The map is narrow:** across the elites the hero-damage share is only 0.36–0.51 and the average
  cost 2.4–3.9, since every elite plays the same core.
- **Speed:** about 850–930 games a second with the heuristic (8 workers); the GNN 6.9 (8 workers,
  not batched), so it can re-score an archive (3,200 games in 8 minutes) but not search.

Archives: `PythonServer/data/elites/` (`set_1000_g2_before_groups.json` is the 16-deck run).

### Group prices re-measured with v6b (2026-11-18, `set_1000_g2`)

`experiments.py effects`: decks with 10 cards of a group against the same decks with them refunded
(units) or swapped for vanilla units (actions), v6b on both sides, 300 games per point. The real
deck's win rate at each scale of the price of the time:

| Group | Cards | 0.5 | 1.0 | 1.5 | 2.5 | Fair |
|---|---|---|---|---|---|---|
| unit, deal_damage | 124 | 76.7% | 64.0% | 56.3% | 48.0% | 2.26 |
| unit, discard | 16 | 77.3% | 66.7% | 63.7% | 44.7% | 2.22 |
| unit, return_to_hand | 9 | 71.0% | 60.0% | 54.7% | 43.0% | 1.90 |
| action, deal_damage | 111 | 84.7% | 64.0% | 50.0% | 38.7% | 1.50 |
| action, summon | 66 | 68.0% | 34.7% | 26.3% | 31.3% | 0.77 |
| action, draw | 30 | 62.3% | 31.0% | 25.0% | 14.7% | 0.70 |
| action, buff | 16 | 53.3% | 39.0% | 29.0% | 23.0% | 0.62 |
| unit, damage_hero | 27 | 50.0% | 38.0% | 38.0% | 27.7% | 0.50 |
| unit, buff | 27 | 57.7% | 49.7% | 48.7% | 44.0% | 0.98 |
| unit, draw / summon / gain_crystal / heal_hero | 48 / 54 / 14 / 47 | 63–68% | 56–67% | 55–65% | 55–62% | — |
| unit, grant_keyword / modify_stat / remove_damage / statics | 11–32 | 44–53%, flat | | | | — |

- **Removal was priced for a weak agent:** damage is worth 1.5× (actions) to 2.3× (units) the
  price measured with v3. `GROUP_SCALE` now multiplies each crossing group's scale by its fair
  value, and the `_g2` and coverage sets were regenerated.
- **Action draw disagrees:** in average decks it loses to vanilla units (fair 0.7), but the elites
  use it twice as often as random decks. It keeps its price: the first group where average decks
  and the best decks point opposite ways.
- **Units whose abilities are nearly free** (draw, summon, gain_crystal, heal_hero: group scales
  0.15–0.35) still win 55–68% even at 2.5×: their prices are too small to move a unit's stats.

Log: `PythonServer/data/effects_v6b_g2.log`.

**MAP-Elites again on the repriced set** (same settings, 20,000 evaluations, 1,060 s): elites +26.0
on the search field, +19.4 on the fresh one (random decks −2.0; correlation 0.31). How much more
the elites use each group than random decks do, before and after:

| Group | Before | After |
|---|---|---|
| unit, deal_damage | 2.0× | 1.25× |
| action, deal_damage | 2.0× | 1.64× |
| action, draw | 2.0× | 1.36× |
| unit, heal_hero | 0.87× | **2.31×** |
| action, summon | 0.17× | 1.27× |
| unit, summon | 0.22× | 1.14× |
| unit, draw | 0.14× | 0.96× |

- **The core broke up:** 307 cards appear in some elite (246 before), and 6 are in 80 or more of
  the 100 (12 before). The map widened a little (hero-damage share 0.38–0.56, action share
  0.15–0.48).
- **Removal still leads, less:** the most shared card is a 1-mana action that deals 6 damage split
  at random among enemy units (95 elites); random targets and split damage may be too cheap.
- **New outliers:** units that heal your hero (2.3×; their group scale is 0.3, and they won 55–63%
  at every price in the effects test), and 1-mana "choose one" actions.

Archive: `PythonServer/data/elites/set_1000_g2_after_groups.json`; log `rerun_after_groups.log`.

### Random targets, "choose one" and floor-priced units (2026-11-18, v6b, `set_1000_g2`)

The effects test on feature groups (`--groups`; random targets include split damage), at 0.5–8×
the price of the time:

| Group | Cards | 0.5 | 1 | 2 | 4 | 8 | Fair |
|---|---|---|---|---|---|---|---|
| action, random target | 49 | 82.7% | 55.3% | 32.0% | 29.7% | 44.0% | 1.23 |
| unit, random target | 59 | 63.0% | 54.3% | 43.0% | 36.0% | 28.3% | 1.38 |
| action, choose one | 81 | 83.7% | 45.0% | 22.7% | 29.3% | 47.0% | 0.94 |
| unit, choose one | 62 | 77.0% | 68.7% | 62.7% | 48.3% | 38.7% | 3.77 |
| unit, heal_hero | 38 | 56.3% | 56.7% | 56.0% | 39.7% | 36.3% | 2.73 |
| unit, draw | 61 | 70.7% | 71.0% | 56.3% | 48.0% | 34.7% | 3.52 |
| unit, summon | 48 | 73.3% | 69.3% | 63.3% | 48.7% | 31.0% | 3.82 |
| unit, gain_crystal | 13 | 65.0% | 65.0% | 60.7% | 40.0% | 33.0% | 3.03 |

- `RANDOM_TARGET` 0.65 → 0.85 (about 1.3× for both card types).
- The floor groups take their crossings (unit draw 1.23, summon 0.57, heal_hero 0.82,
  gain_crystal 0.91). 48 of the 62 unit "choose one" cards are in those groups, so "choose one"
  got no factor of its own; actions measured 0.94.
- Actions at 8× win more again: their cost goes past what the deck can play, a quirk of the test.

Log: `PythonServer/data/effects_v6b_g2_features.log`. The `_g2` and coverage sets were regenerated.

**MAP-Elites on these prices** (20,000 evaluations, 626 s): elites +26.4 on the search field and
+23.6 on the fresh one (random decks +0.1; correlation 0.20), so they generalise better than
before, but the over-used groups moved rather than went away:

| Group | First run | After group scales | After this |
|---|---|---|---|
| action, deal_damage | 2.0× | 1.64× | **2.52×** |
| action, buff | 1.17× | 0.29× | 2.08× |
| unit, keywords | 1.07× | 0.91× | 1.42× |
| unit, heal_hero | 0.87× | 2.31× | 1.35× |
| action, draw | 2.0× | 1.36× | 1.14× |
| unit, deal_damage | 2.0× | 1.25× | 0.38× |
| unit, draw | 0.14× | 0.96× | 0.40× |
| unit, summon | 0.22× | 1.14× | 0.42× |

253 cards appear in some elite, 11 in 80 or more. The elites are control decks: 2-mana actions
that deal 5–6 damage to a unit, Guard units and hero healing.

- **Average-deck prices and the best decks keep disagreeing.** Each re-measure moved the
  over-use somewhere else: `action, deal_damage` was measured fair at 1.5× its old price and
  still leads, and unit damage went from over-used to under-used. Removal is worth more in a
  deck built around it (Guard bodies, healing) than in an average deck, which is what the effects
  test measures. Fixing that is P3's job (pricing from the decks that are good), not more
  average-deck measurements.
- The search agent is the heuristic, which trades readily; control may suit it more than it
  would v6b.

Archive: `PythonServer/data/elites/set_1000_g2.json`; log `rerun_after_features.log`.

### MAP-Elites on the class set, `set_1000_c` (2026-11-18, heuristic agent)

**Cost and hero-damage axes, one shared map** (20,000 evaluations): Bog took all 100 cells. Its
top 10% of decks averaged +24.2 against the field, the other classes +11 to +16. The measures
already split the classes as their styles predict: Meadow and Glow dealt the most damage to the
hero in the shortest games (hero share 0.49 / 0.47, 14.7 / 15.4 turns), Bog the least in the
longest (0.38, 18.3 turns, the most actions).

**The ring map, one shared map** (30,000 evaluations, 960,000 games in 895 s): all 96 cells filled
(mean elite +25.0), but by two classes. Ember took the half of the ring from fortress/control
round through spells to aggro (51 elites, mean angle 289°), Moss the half from aggro/swarm to
fortress (42 elites, 109°); Bog kept 2 cells, Glow 1, Meadow and Frost none.

- Each class's elites sit on its side of the ring (Ember near spells/aggro, Moss near
  swarm/growth), so the angle does track play style.
- The elites' fitness is within a couple of points everywhere (+24.6 to +25.5 by class), so the
  takeover is a founder effect more than a strength gap: a mutation can't change a deck's class,
  so the classes that did well among the first random decks colonise the map and the others
  never get cells to improve in. A shared map can't compare classes; an archive per class can.

Archives: `PythonServer/data/elites/set_1000_c_shared.json` (cost and hero share),
`set_1000_c_ring_shared.json` (ring).

**The ring map, an archive per class** (`--per-class`, 30,000 evaluations, 1,149 s): 556 of 576
cells (96%); every class reaches every sector (with its neutrals). Each class's top 10 elites:

| Class | Own styles | Top-10 mean | Their mean angle | Its best sectors |
|---|---|---|---|---|
| Moss | growth, fortress (120–180°) | +23.2 | 117° | growth +25.4, fortress +25.1 |
| Frost | fortress, control (180–240°) | +23.0 | 288° | control +24.8, spells/aggro +23.8 |
| Glow | aggro, swarm (0–60°) | +22.5 | 63° | aggro/swarm +23.7, swarm +23.6 |
| Bog | control, spells (240–300°) | +21.8 | 272° | fort/control +22.8, spells/aggro +22.7 |
| Meadow | swarm, growth (60–120°) | +21.0 | 69° | aggro/swarm +22.5, swarm +21.8 |
| Ember | spells, aggro (300–360°) | +20.0 | **206°** | fort/control +20.6, growth/fort +20.5 |

- **Most classes win in their own styles:** Moss, Glow, Bog and Meadow's best decks sit in or next
  to their sectors, and Frost's best is control.
- **Ember doesn't:** its best decks are on the far side of the ring, using its burn as removal
  behind neutral Guard units, and it's the weakest class. Its aggro plan isn't paying off (the
  heuristic may play aggro badly, or Ember's hero damage is too weak for its price).
- **Class balance:** the top-10 means span 3.2 points (Moss +23.2 to Ember +20.0); by mean elite
  over all cells Meadow is lowest (+14.5, the others +17.7 to +19.9).

Archive: `set_1000_c_per_class.json`.

## Training findings

- **The eval curve flattens, slowly rising.** v6b's 100-game evals averaged a score (held-out and
  Armor-heavy) of about 72 for the first 800 iterations, then 75–77 to the end. Entropy fell
  slowly (0.57 → 0.53), KL stayed near 0.02 with early stopping after 2–3 epochs.
- **Action-outcome features (P1a, 2026-11-15).** As a 120-iteration fine-tune from v4 they gave
  small gains that weren't significant (Armor-heavy 61.8% vs 59.5% for the control, head to head
  49–53%), and the new input's weights barely grew. Trained from scratch for longer (v6b) the agent
  is much stronger, but that run changed length, starting point and features at once, so it
  doesn't isolate the features.
- **Best-checkpoint selection.** Twice (the league run and v6b) the "best" checkpoint from a
  single 100-game eval was no better than the last one. Training evals now use the same deals
  every time (`PPOConfig.eval_seed`); pick checkpoints with a 400-game benchmark.
- **Deck luck doesn't cap the win rate (2026-11-16).** v6b vs the heuristic with the same deck on
  both sides (mirror decks): 83.5% / 79.2% / 74.2%, almost the same as with different decks. So
  training on mirror decks (`PPOConfig.mirror_share`) isn't worth it; it stays at 0.
- **Aspects were ignored (2026-11-16).** Hiding the aspect features changed nothing beyond noise
  (vs heuristic 82.5% / 78.5% / 73.0%; head to head 47–50%), so the per-card aspect features were
  dropped. Old checkpoints load with those columns removed, with identical outputs.
- **Free hero attacks (2026-10-29).** v4 sometimes ended the turn instead of making a free hero
  attack (1–2% of the spots where both were legal; `v4_best` 6.7%), mostly early with 1-power
  units: a ±1 reward at the end of the game hides 1 damage on turn 3. Not re-checked on v6b yet.

## Card pricing (stage 1, 2026-10-22 to 10-23)

Decks played against altered copies of themselves, 800 games per comparison
(`scripts/experiments.py`); full steps in the ability-generation log.

| Test | Before repricing | After step 2 | After step 4 / v4 |
|---|---|---|---|
| Real deck vs abilities removed (same stats) | 57–63% | 68–71% | |
| Real deck vs abilities' points refunded as stats | 20–25% | 44–48% | 55–59% (v4: 58%) |
| Real deck vs actions swapped for vanilla units | 23% | 35–41% | 37% (v4: 50.1%) |

- The rough value table overpriced abilities badly: units' abilities were worth less than one
  stat point on average, and actions lost to a 1-mana vanilla unit even at cost 0.
- Only 53% of played ability cards ever hit anything; each narrowing of a filter about halved the
  hits, and triggers fired 2–3× less often than the table assumed.
- No global price scale fixed it. Measured scales (0.4 units, 0.2 actions), then per-effect
  scales (`costing.GROUP_SCALE`), did.
- How well a card is priced depends on the agent: v4 got more out of unit abilities than v3 on the
  same cards.

## Luck and going first

- **Going first:** with Hearthstone's 4-card opening hand for the second player, the first player
  won 58–59% of mirror games. With 5 cards: 49% (league model) and 54% (heuristic agent)
  (2026-10-22). Not re-measured since the cards were repriced.
- **Deck quality (2026-10-22, before repricing):** in the league model's mirror games one deck won
  all four games (both players, both seats) on 60% of deck pairs; the skill ceiling against an
  equal player looked like ~70%. Since repricing, mirror decks barely change the result (above).

## Speed

**An iteration** (64 games of self-play plus a PPO update, one process, M4 Mac):

| Date | Setup | Time | Split |
|---|---|---|---|
| 2026-11-15 | MPS, deepcopy previews | 25.5 s | play 18.0, learn 7.5 |
| 2026-11-15 | CPU, deepcopy previews | 21 s | play 13.4 (previews 7.7, model 4.7), learn 7.6 |
| 2026-11-15 | CPU, hand-written `Game.clone()` | 15 s | play 7.2 (previews 1.3), learn 7.9 |
| 2026-11-16 | CPU, v6b late in training | ~20–25 s | play ~12, learn ~8–13: longer games than the profile's |
| 2026-11-17 | CPU, fine-tuning v6b, one process | ~20 s | play 5.7, learn ~14 |
| 2026-11-17 | CPU, the same with 4 self-play workers (`--workers 4`) | ~16 s | play 2.5, learn ~14 |

**Self-play workers (2026-11-17).** Splitting the 64 games over worker processes: 2 workers 4.6 s,
4 workers 3.1 s, 6 or 8 workers 3.4–3.8 s, against 6.7–7.7 s in one process (v6b on `set_1000`,
30% league games). So about 2.3× at 4, and no better beyond: the M4 has 4 performance cores, and
an iteration waits for its slowest worker. Learning is now about 85% of an iteration, and it's
compute, not overhead: a PPO update (about 6,000 steps, 3 epochs) took 15.5 s with 4 threads,
16.4 s with 2, 18.7–20.4 s with 6–10, 14.6 s on MPS, and the same per step with minibatches of
512, 1,024 or 2,048 (about 1,200 steps a second forward and backward).

The graphs are small, so the GNN is overhead-bound: about 350 µs a position on CPU and 190–250 µs
on MPS, and MPS only wins from batches of 32 up. The model is now about 85% of an iteration.

**Per decision** (2026-10-16, before abilities; 512-decision minibatches):

| Stage | Time |
|---|---|
| Engine step (vanilla rules) | 5 µs |
| Encode state | 16 µs |
| Collate: GNN / transformer | 7 µs / 11 µs |
| GNN forward + backward: CPU / MPS | 155 µs / 101 µs |
| Transformer forward + backward: CPU / MPS | 499 µs / 131 µs |

With abilities, encoding takes about 85 µs a state and a GNN pass about 2.4× as long. The GNN has
about 1M parameters. Deck search with the heuristic agent runs about 215 games a second
(MAP-Elites explainer, 2026-11-15).
