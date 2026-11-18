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
