"""Coverage-guided card generation: a small set that uses every building block of the grammar.

No example cards are involved. The generator samples many candidate cards from the grammar,
lists the building blocks each one uses (triggers, effects, conditions, decisions, durations,
statics, amounts, targets, costs, keywords, card types), then picks cards greedily until
every block it ever saw is used at least `per_feature` times. The result is for checking the
engine and the client, not for balance.
"""
import random
from collections import Counter

from src.cards.abilities import render
from src.cards.generate import CardGenerator
from src.cards.names import Namer, full_name
from src.cards.trace import Tracer
from src.cards.schema import Card, CardSet
from src.cards.theme import JOBS, SPECIES
from src.game.terms import ASPECTS, keyword_text

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


def generate_coverage_set(seed: int = 0, per_feature: int = 2, candidates: int = 4000, max_cards: int = 60,
                          jobs: int = 6, action_share: float = 0.25, prefix: str = "C1") -> CardSet:
    """Abilities only refer to `jobs` jobs, and the units are spread across the same jobs, so
    every condition and filter can actually be met in a game. About `action_share` of the cards
    are action cards, and no ability appears twice."""
    rng = random.Random(seed)
    job_list = tuple(rng.sample(JOBS, jobs))
    generator = CardGenerator(rng, job_list, action_share=0.25)
    pool = [generator.good().card for _ in range(candidates)]
    features = [card_features(c) for c in pool]
    reachable = set().union(*features)
    counts = Counter()
    chosen, seen_abilities = [], []

    def gain(i):
        return sum(1 for f in features[i] if counts[f] < per_feature)

    def open_candidates(action: bool | None = None):
        return [i for i in range(len(pool)) if i not in chosen and pool[i].abilities not in seen_abilities
                and (action is None or (pool[i].type == "action") == action)]

    def pick(i):
        chosen.append(i)
        seen_abilities.append(pool[i].abilities)
        counts.update(features[i])

    def actions_wanted() -> bool:
        return sum(pool[i].type == "action" for i in chosen) < action_share * (len(chosen) + 1)

    # New coverage per building block on the card: prefers simpler cards, which are easier to check by hand.
    def score(i):
        return gain(i) / len(features[i]) ** 0.5

    while len(chosen) < max_cards:
        useful = [i for i in open_candidates(actions_wanted()) if gain(i) > 0] or \
                 [i for i in open_candidates() if gain(i) > 0]
        if not useful:
            break
        pick(max(useful, key=score))
    # Coverage done: top up with the simplest action cards until they make up action_share of the set.
    while actions_wanted() and len(chosen) < max_cards and open_candidates(True):
        pick(min(open_candidates(True), key=lambda i: len(features[i])))

    species = rng.sample(SPECIES, len(SPECIES))
    namer = Namer(Tracer(rng))
    cards, covered_by, units = [], {}, 0
    for n, i in enumerate(chosen):
        c = pool[i]
        aspect = ASPECTS[n % len(ASPECTS)]
        if c.type == "unit":
            # Jobs take turns, and each job steps through the species list, so species + job pairs differ.
            job = job_list[units % jobs]
            name, traits = f"{species[(units // jobs) % len(species)]} {job}", (job,)
            subtitle = namer.subtitle(name, c.abilities[0])
            units += 1
        else:
            name, traits, subtitle = namer.action(aspect, c.abilities[0]), (), ""
        card = Card(f"{prefix}-{n + 1:03d}", name, c.type, (aspect,), c.cost, c.power, c.health, traits=traits,
                    keywords=c.keywords, abilities=c.abilities, subtitle=subtitle)
        namer.reserve(card)
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
    return CardSet("coverage", cards, notes)


def card_lines(card_set: CardSet) -> list[str]:
    """A Markdown checklist entry per card: name, cost, stats, keywords and ability text."""
    lines = []
    for c in card_set.cards:
        stats = "action" if c.type == "action" else f"{c.power} power · {c.health} health"
        keywords = ", ".join(keyword_text(k, v) for k, v in c.keywords)
        lines.append(f"- [ ] **{c.id} {full_name(c)}** (cost {c.cost}, {stats}{', ' + keywords if keywords else ''})")
        for ability in c.abilities:
            lines.append(f"  - {render(ability, c.type)}")
    return lines


def coverage_report(card_set: CardSet) -> str:
    """A Markdown checklist: every card with its text, then every building block with the cards that use it."""
    lines = [f"# {card_set.name}: checklist", "",
             f"Generated from the grammar (seed {card_set.notes['seed']}), so every building block appears "
             f"at least {card_set.notes['per_feature']} times. Costs are rough (src/cards/costing.py).", "",
             "## Cards", "", *card_lines(card_set)]
    lines += ["", "## Building blocks", "", "| Building block | Cards |", "|---|---|"]
    for feature, cards in card_set.notes["features"].items():
        lines.append(f"| {feature} | {', '.join(cards)} |")
    return "\n".join(lines) + "\n"


def ability_set_report(card_set: CardSet) -> str:
    notes = card_set.notes
    stopped = ", ".join(f"{k} {v}" for k, v in notes["stopped_at"].items())
    lines = [f"# {card_set.name}: checklist", "",
             f"{len(card_set)} cards with abilities (seed {notes['seed']}, jobs: {', '.join(notes['jobs'])}). "
             f"{notes['draws']} draws from the grammar; stopped at: {stopped}. "
             "Costs are rough (src/cards/costing.py).", "", *card_lines(card_set)]
    return "\n".join(lines) + "\n"
