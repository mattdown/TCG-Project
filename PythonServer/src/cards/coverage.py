"""Coverage-guided card generation: a small set that uses every building block of the grammar.

No example cards are involved. The generator samples many candidate cards from the grammar,
lists the building blocks each one uses (triggers, effects, conditions, decisions, durations,
statics, amounts, targets, costs, keywords, card types), then picks cards greedily until
every block it ever saw is used at least `per_feature` times. The result is for checking the
engine and the client, not for balance.
"""
import math
import random
from collections import Counter

from src.cards.abilities import AbilitySampler, render
from src.cards.costing import ability_value
from src.cards.schema import Card, CardSet
from src.cards.theme import JOBS, SPECIES
from src.cards.vanilla import (ARCHETYPES, ARCHETYPE_KEYWORDS, KEYWORD_RANGE, _allocate, keyword_value,
                               stat_budget)
from src.game.terms import ASPECTS, KEYWORDS, keyword_text

FILTER_FIELDS = ("trait", "damaged", "exhausted", "cost_max", "not_this")


def _filter_features(f: dict, out: set):
    for field in FILTER_FIELDS:
        if field in f:
            out.add(f"filter: {field}")
    out.add(f"filter owner: {f.get('owner', 'any')}")


def _target_features(target, out: set):
    if target in ("you", "opponent"):
        out.add(f"target: {target}")
    elif target == "this":
        out.add("target: this card")
    elif "ref" in target:
        out.add("target: an earlier choice")
    elif "all" in target:
        out.add("target: all(…)")
        _filter_features(target["all"], out)


def _amount_features(amount, out: set):
    if isinstance(amount, dict):
        out.add("amount: per count, capped")
        _filter_features(amount["per"], out)
    elif amount == "all":
        out.add("amount: all")


def _condition_features(cond: dict, out: set):
    if not cond:
        return
    kind = next(iter(cond))
    out.add(f"condition: {kind}" + (f" {cond[kind]}" if kind == "this_is" else ""))
    if "count" in cond:
        _filter_features(cond["count"], out)


def _steps_features(steps: list, out: set):
    for step in steps:
        if "choose" in step:
            out.add("decision: choose")
            _filter_features(step["choose"]["filter"], out)
        elif "effect" in step:
            out.add(f"effect: {step['effect']}")
            _target_features(step["target"], out)
            _amount_features(step.get("amount"), out)
            if "duration" in step:
                out.add(f"duration: {step['duration']}")
            if step["effect"] == "modify_stat":
                out.add(f"stat change: {step['stat']} {'+' if step['delta'] > 0 else '−'}")
        elif "if" in step:
            out.add("step: if")
            _condition_features(step["if"], out)
            _steps_features(step["then"], out)
        elif "may" in step:
            out.add("decision: may")
            _steps_features(step["may"], out)
            _steps_features(step["if_you_do"], out)
        elif "choose_one" in step:
            out.add("decision: choose one")
            for branch in step["choose_one"]:
                _steps_features(branch, out)


def card_features(card: Card) -> set[str]:
    """The building blocks a card uses."""
    out = {f"card type: {card.type}"}
    for name, _ in card.keywords:
        out.add(f"keyword: {name}")
    for ability in card.abilities:
        out.add(f"ability: {ability['kind']}")
        _condition_features(ability.get("condition"), out)
        if ability["kind"] == "triggered":
            out.add(f"trigger: {ability['trigger']['event']}")
            if "filter" in ability["trigger"]:
                _filter_features(ability["trigger"]["filter"], out)
        if ability["kind"] == "activated":
            for cost in ability["cost"]:
                out.update(f"cost: {k}" for k in cost)
        if ability["kind"] == "static":
            for m in ability["modifiers"]:
                if "cost_reduction" in m:
                    out.add("static: cost reduction")
                    continue
                out.add(f"static: {'keyword' if 'keyword' in m else m['stat']} for "
                        f"{'this card' if m['subject'] == 'this' else 'all(…)'}")
                if "amount" in m:
                    _amount_features(m["amount"], out)
        else:
            _steps_features(ability["steps"], out)
    return out


class _CandidateMaker:
    def __init__(self, rng: random.Random, jobs: tuple[str, ...]):
        self.rng = rng
        self.sampler = AbilitySampler(rng, traits=jobs)

    def card(self, index: int) -> Card:
        rng = self.rng
        card_type = "action" if rng.random() < 0.25 else "unit"
        ability = self.sampler.ability(card_type)
        value = ability_value(ability)
        aspect = (ASPECTS[index % len(ASPECTS)],)
        energy_source = rng.random() < 0.8
        if card_type == "action":
            cost = max(0, math.ceil(value / 2))
            return Card(f"cand-{index}", "", "action", aspect, energy_source, cost, 0, 0, 0, abilities=(ability,))

        archetype = rng.choice(list(ARCHETYPES))
        keywords = {}
        if rng.random() < 0.35:
            options = {k: w for k, w in ARCHETYPE_KEYWORDS[archetype].items() if w}
            name = rng.choices(list(options), list(options.values()))[0]
            lo, hi = KEYWORD_RANGE.get(name, (1, 1))
            keywords[name] = rng.randint(lo, hi)
        spend = math.ceil(value) + keyword_value(keywords)
        cost = rng.randint(1, 5)
        while stat_budget(cost, energy_source) - spend < 2 and cost < 9:  # leave at least 1 power, 1 health
            cost += 1
        stats = _allocate(rng, max(2, stat_budget(cost, energy_source) - spend), ARCHETYPES[archetype])
        return Card(f"cand-{index}", "", "unit", aspect, energy_source, cost, **stats,
                    keywords=tuple(sorted(keywords.items())), abilities=(ability,))


def generate_coverage_set(seed: int = 0, per_feature: int = 2, candidates: int = 4000, max_cards: int = 60,
                          jobs: int = 6, prefix: str = "C1") -> CardSet:
    """Abilities only refer to `jobs` jobs, and the units are spread across the same jobs, so
    every condition and filter can actually be met in a game."""
    rng = random.Random(seed)
    job_list = tuple(rng.sample(JOBS, jobs))
    maker = _CandidateMaker(rng, job_list)
    pool = [maker.card(i) for i in range(candidates)]
    features = [card_features(c) for c in pool]
    reachable = set().union(*features)
    counts = Counter()
    chosen = []
    while len(chosen) < max_cards:
        def gain(i):
            return sum(1 for f in features[i] if counts[f] < per_feature)

        # New coverage per building block on the card: prefers simpler cards, which are easier to check by hand.
        best = max((i for i in range(len(pool)) if i not in chosen), key=lambda i: gain(i) / len(features[i]) ** 0.5)
        if gain(best) == 0:
            break
        chosen.append(best)
        counts.update(features[best])

    species = rng.sample(SPECIES, len(SPECIES))
    # Jobs take turns, and each job steps through the species list, so every name is unique.
    names = [(f"{species[(n // jobs) % len(species)]} {job_list[n % jobs]}", job_list[n % jobs])
             for n in range(len(chosen))]
    cards, covered_by = [], {}
    for n, i in enumerate(chosen):
        c = pool[i]
        name, job = names[n]
        card = Card(f"{prefix}-{n + 1:03d}", name, c.type, (ASPECTS[n % len(ASPECTS)],), c.energy_source, c.cost,
                    c.power, c.health, c.score, traits=(job,) if c.type == "unit" else (), keywords=c.keywords,
                    abilities=c.abilities)
        cards.append(card)
        covered_by[card.id] = sorted(features[i])
    notes = {
        "generator": "coverage",
        "seed": seed,
        "per_feature": per_feature,
        "features": {f: [cid for cid, fs in covered_by.items() if f in fs] for f in sorted(reachable)},
        "jobs": list(job_list),
        "costing": "rough ability values from src/cards/costing.py",
    }
    return CardSet(f"coverage_{len(cards)}", cards, notes)


def coverage_report(card_set: CardSet) -> str:
    """A Markdown checklist: every card with its text, then every building block with the cards that use it."""
    lines = [f"# {card_set.name}: checklist", "",
             f"Generated from the grammar (seed {card_set.notes['seed']}), so every building block appears "
             f"at least {card_set.notes['per_feature']} times. Costs are rough (src/cards/costing.py).", "",
             "## Cards", ""]
    for c in card_set.cards:
        stats = "action" if c.type == "action" else f"{c.power} power · {c.health} health · {c.score} score"
        keywords = ", ".join(keyword_text(k, v) for k, v in c.keywords)
        lines.append(f"- [ ] **{c.id} {c.name}** (cost {c.cost}, {stats}{', ' + keywords if keywords else ''})")
        for ability in c.abilities:
            lines.append(f"  - {render(ability, c.type)}")
    lines += ["", "## Building blocks", "", "| Building block | Cards |", "|---|---|"]
    for feature, cards in card_set.notes["features"].items():
        lines.append(f"| {feature} | {', '.join(cards)} |")
    return "\n".join(lines) + "\n"
