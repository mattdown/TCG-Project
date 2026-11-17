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
| **`tcgnet_v6b`** | 2026-11-16 | 3,000 iterations from scratch, outcome features, about a day | **81.5% / 79.0% / 74.0%** | The server's AI since 2026-11-16 |

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
