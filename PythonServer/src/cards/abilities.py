"""Ability trees: sampling, validation and card text (first version).

Abilities use the authoring form from docs/technical-plan.md section 3: plain dicts and lists.

    ability = {"kind": "triggered", "trigger": {...}, "condition": None, "steps": [...]}
            | {"kind": "activated", "cost": [...], "steps": [...]}
            | {"kind": "on_resolve", "steps": [...]}
            | {"kind": "static", "condition": None, "modifiers": [...]}
    step    = {"choose": {"count": 1, "filter": F}, "as": "it"}
            | {"effect": op, "target": T, "amount": A, ...}
            | {"if": C, "then": [...]}
            | {"may": [...], "if_you_do": [...]}
            | {"choose_one": [[...], [...]]}
    target  = "this" | "you" | "opponent" | {"ref": name} | {"all": F}
    amount  = int | "all" | {"per": F, "k": 1, "cap": 4}
    filter  = {"owner": "you" | "opponent" | "any", "trait"?, "damaged"?, "exhausted"?, "cost_max"?, "not_this"?}

The sampler builds trees that satisfy the constraints by construction; validate() checks
them independently, so it can also vet trees written by hand or by another generator.
The sampling weights are hand-tuned placeholders, and the cost model will set cards' cost
and stats later.
"""
import random

from src.cards.theme import JOBS

TRAITS = JOBS  # traits are jobs (docs/theme.md)
HELPS, HURTS = "helps", "hurts"
MAX_STEPS, MAX_DEPTH, MAX_CHOICES = 4, 2, 2

# op: (target kind, polarity, amount range or None)
EFFECTS = {
    "deal_damage": ("unit", HURTS, (1, 5)),
    "remove_damage": ("unit", HELPS, (1, 5)),
    "defeat": ("unit", HURTS, None),
    "return_to_hand": ("unit", HURTS, None),
    "exhaust": ("unit", HURTS, None),
    "ready": ("unit", HELPS, None),
    "cant_ready": ("unit", HURTS, None),
    "modify_stat": ("unit", None, (1, 3)),  # polarity follows the sign
    "grant_keyword": ("unit", HELPS, None),
    "draw": ("player", HELPS, (1, 3)),
    "discard": ("player", HURTS, (1, 2)),
    "gain_vp": ("player", HELPS, (1, 3)),
    "lose_vp": ("player", HURTS, (1, 2)),
    "add_energy": ("player", HELPS, None),
}
EFFECT_WEIGHTS = {"deal_damage": 10, "remove_damage": 3, "defeat": 2, "return_to_hand": 3, "exhaust": 4, "ready": 3,
                  "cant_ready": 3, "modify_stat": 8, "grant_keyword": 4, "draw": 8, "discard": 3, "gain_vp": 6,
                  "lose_vp": 3, "add_energy": 2}
GRANTABLE_KEYWORDS = ("Guard", "Elusive", "Charge", "Duelist +1", "Duelist +2", "Armor +1")
TRIGGERS = {"on_play": 10, "on_score": 4, "on_attack": 3, "on_defeated": 3, "start_of_turn": 3, "end_of_turn": 2,
            "another_played": 2, "opposing_defeated": 2}
SITUATIONS = ("attacking", "defending", "exhausted", "damaged")
RESTRICTING = {"cost_max", "damaged", "exhausted"}  # filter fields that limit how strong a defeat target can be


def polarity(step: dict) -> str:
    _, pol, _ = EFFECTS[step["effect"]]
    if pol is None:
        return HELPS if step["delta"] > 0 else HURTS
    return pol


# ------------------------------------------------------------------ sampling


class AbilitySampler:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def _w(self, options: dict):
        return self.rng.choices(list(options), list(options.values()))[0]

    def _small(self, lo: int, hi: int) -> int:
        """A number in [lo, hi], weighted towards the low end."""
        values = list(range(lo, hi + 1))
        return self.rng.choices(values, [1 / (i + 1) for i in range(len(values))])[0]

    def ability(self, card_type: str = "unit") -> dict:
        if card_type == "action":
            kind = "on_resolve"
        else:
            kind = self._w({"triggered": 5, "activated": 2, "static": 3})
        self.card_type = card_type
        self.names = []  # (name, side) of choices made so far
        if kind == "static":
            return {"kind": "static", **self._static()}
        ability = {"kind": kind}
        if kind == "triggered":
            ability["trigger"] = self._trigger()
            ability["condition"] = self._condition() if self.rng.random() < 0.2 else None
        elif kind == "activated":
            ability["cost"] = self._cost()
        ability["steps"] = self._steps(ability)
        return ability

    def _trigger(self) -> dict:
        event = self._w(TRIGGERS)
        trigger = {"event": event}
        if event == "another_played":
            trigger["filter"] = {"owner": "you", "trait": self.rng.choice(TRAITS), "not_this": True}
        return trigger

    def _cost(self) -> list:
        # ⟳ is always part of the cost, so an activated ability can't run away: it's used at most once
        # per turn unless something readies the unit (and readied units can't use ⟳ that turn).
        cost = [{"exhaust_this": True}]
        extra = self._w({"none": 4, "pay": 4, "exhaust_another": 1, "discard": 1})
        if extra == "pay":
            cost.append({"pay": self._small(1, 3)})
        elif extra != "none":
            cost.append({extra: 1})
        return cost

    def _condition(self) -> dict:
        kind = self._w({"count": 3, "behind": 1})
        if kind == "count":
            return {"count": {"owner": "you", "trait": self.rng.choice(TRAITS), "not_this": True},
                    "at_least": self.rng.choice((2, 3))}
        return {"behind_on_vp": True}

    def _filter(self, owner: str, extra_chance: float = 0.35) -> dict:
        f = {"owner": owner}
        if owner == "you" and self.card_type == "unit":
            f["not_this"] = True
        if self.rng.random() < extra_chance:
            extra = self._w({"damaged": 2, "exhausted": 2, "cost_max": 2, "trait": 2})
            if extra == "cost_max":
                f["cost_max"] = self.rng.choice((2, 3, 4))
            elif extra == "trait":
                f["trait"] = self.rng.choice(TRAITS)
            else:
                f[extra] = True
        return f

    def _steps(self, ability: dict) -> list:
        # Activated abilities put every cost before the colon, so they never use "you may … if you do".
        may = 0 if ability["kind"] == "activated" else 3
        pattern = self._w({"single": 7, "double": 3, "follow_up": 3, "may": may, "choose_one": 2})
        if pattern == "single":
            return self._effect(ability)
        if pattern == "double":
            first = self._effect(ability)
            return first + self._effect(ability, player_only=True, exclude=first[-1]["effect"])
        if pattern == "follow_up":
            steps = self._effect(ability, op="deal_damage", choose=True)
            name = self.names[-1][0]
            return steps + [{"if": {"defeated": name}, "then": self._effect(ability, player_only=True, helps_only=True)}]
        if pattern == "may":
            cost = self._self_cost()
            self.names = [n for n in self.names if n[0] != "that"]  # the reward doesn't target what was paid
            same_resource = "gain_vp" if cost[-1]["effect"] == "lose_vp" else None  # "lose 1, gain 2" is just "gain 1"
            reward = self._effect(ability, helps_only=True, strong=True, exclude=same_resource)
            return [{"may": cost, "if_you_do": reward}]
        first = self._effect(ability, player_only=True)
        return [{"choose_one": [first, self._effect(ability)]}]

    def _self_cost(self) -> list:
        kind = self._w({"discard": 3, "exhaust_own": 2, "damage_own": 1, "lose_vp": 1})
        if kind == "discard":
            return [{"effect": "discard", "target": "you", "amount": 1, "chosen": True}]
        if kind == "lose_vp":
            return [{"effect": "lose_vp", "target": "you", "amount": 1}]
        self.names.append(("that", "you"))
        choose = {"choose": {"count": 1, "filter": self._filter("you", extra_chance=0)}, "as": "that"}
        if kind == "exhaust_own":
            choose["choose"]["filter"]["exhausted"] = False
            return [choose, {"effect": "exhaust", "target": {"ref": "that"}}]
        return [choose, {"effect": "deal_damage", "target": {"ref": "that"}, "amount": self.rng.choice((1, 2))}]

    def _effect(self, ability: dict, op: str | None = None, player_only=False, helps_only=False, choose=False,
                strong=False, exclude: str | None = None) -> list:
        options = {o: w for o, w in EFFECT_WEIGHTS.items()
                   if (not player_only or EFFECTS[o][0] == "player") and (not helps_only or EFFECTS[o][1] != HURTS)
                   and o != exclude}
        op = op or self._w(options)
        kind, pol, rng_ = EFFECTS[op]
        step = {"effect": op}
        if op == "modify_stat":
            stat = self._w({"power": 6, "health": 3, "score": 1})
            sign = 1 if helps_only or self.rng.random() < 0.7 else -1
            if sign < 0:
                stat = "power"
            step.update(stat=stat, delta=sign * self._small(1, 3 if strong else 2), duration="this_turn")
            pol = HELPS if sign > 0 else HURTS
        elif op == "grant_keyword":
            step.update(keyword=self.rng.choice(GRANTABLE_KEYWORDS), duration="this_turn")
        elif op == "cant_ready":
            step["duration"] = "until_their_next_turn"
        elif op == "ready":
            step["no_score_or_activate"] = True  # stops ready loops (see validate)
        elif op == "discard":
            step["random"] = True

        if rng_ and op != "modify_stat":
            lo, hi = rng_
            step["amount"] = self._small(lo + (1 if strong else 0), hi)
            if op == "remove_damage" and self.rng.random() < 0.3:
                step["amount"] = "all"
            elif op in ("deal_damage", "draw", "gain_vp") and self.rng.random() < 0.15:
                step["amount"] = {"per": {"owner": self.rng.choice(("you", "any")), "trait": self.rng.choice(TRAITS)},
                                  "k": 1, "cap": self.rng.choice((3, 4, 5))}

        side = "you" if pol == HELPS else "opponent"
        if kind == "player":
            step["target"] = side
            return [step]

        # Unit effects: reuse an earlier choice, make a new one, hit everything matching, or this card.
        earlier = [name for name, s in self.names if s == side]
        can_use_this = (side == "you" and ability.get("kind") in ("triggered", "static")
                        and ability.get("trigger", {}).get("event") != "on_defeated" and op != "ready")
        choose = choose or op == "defeat"  # defeat always goes through a restricted choice
        if earlier and not choose and self.rng.random() < 0.6:
            step["target"] = {"ref": earlier[-1]}
            return [step]
        how = "choose" if choose else self._w({"choose": 6, "all": 2, "this": 2 if can_use_this else 0})
        if how == "this":
            step["target"] = "this"
            return [step]
        if how == "all":
            step["target"] = {"all": self._filter(side)}
            if isinstance(step.get("amount"), int) and op == "deal_damage":
                step["amount"] = min(step["amount"], 2)  # area damage stays small
            return [step]
        name = "it" if not any(n == "it" for n, _ in self.names) else "other"
        self.names.append((name, side))
        f = self._filter(side, extra_chance=1.0 if op == "defeat" else 0.35)
        if op == "defeat" and "trait" in f:
            del f["trait"]  # a trait alone doesn't limit how strong the target is
            f["cost_max"] = self.rng.choice((2, 3))
        choose_step = {"choose": {"count": 1, "filter": f}, "as": name}
        step["target"] = {"ref": name}
        return [choose_step, step]

    def _static(self) -> dict:
        kind = self._w({"self_situational": 4, "lord": 3, "self_keyword": 2, "discount": 1, "debuff": 1})
        trait = self.rng.choice(TRAITS)
        if kind == "self_situational":
            amount = (self._small(1, 2) if self.rng.random() < 0.5 else
                      {"per": {"owner": self.rng.choice(("you", "any")), "trait": trait}, "k": 1,
                       "cap": self.rng.choice((3, 4))})
            stat = "power" if self.rng.random() < 0.8 else "health"
            situation = "attacking" if stat == "power" else "defending"
            return {"condition": {"this_is": situation},
                    "modifiers": [{"subject": "this", "stat": stat, "amount": amount}]}
        if kind == "lord":
            return {"condition": None, "modifiers": [{"subject": {"all": {"owner": "you", "trait": trait, "not_this": True}},
                                                      "stat": self.rng.choice(("power", "health")), "amount": 1}]}
        if kind == "self_keyword":
            condition = self.rng.choice(({"this_is": "damaged"},
                                         {"count": {"owner": "you", "trait": trait, "not_this": True}, "at_least": 2}))
            return {"condition": condition,
                    "modifiers": [{"subject": "this", "keyword": self.rng.choice(GRANTABLE_KEYWORDS)}]}
        if kind == "discount":
            return {"condition": None, "modifiers": [{"cost_reduction": 1, "filter": {"owner": "you", "trait": trait}}]}
        return {"condition": None, "modifiers": [{"subject": {"all": {"owner": "opponent", "damaged": True}},
                                                  "stat": "power", "amount": -1}]}


# ------------------------------------------------------------------ validation


def validate(ability: dict, card_type: str = "unit") -> list[str]:
    """Returns a list of problems; empty means the tree satisfies every constraint."""
    problems = []
    if ability["kind"] == "static":
        for m in ability["modifiers"]:
            amount = m.get("amount")
            if isinstance(amount, dict) and "cap" not in amount:
                problems.append("scaling amount without a cap")
            if m.get("subject") == "this" and card_type != "unit":
                problems.append("'this' modifier on a card that isn't in play")
        return problems
    if card_type == "action" and ability["kind"] != "on_resolve":
        problems.append("action cards only have on-resolve abilities")
    if ability["kind"] == "activated":
        if not any(c.get("exhaust_this") for c in ability["cost"]):
            problems.append("activated abilities must cost ⟳ (exhaust this card)")
        if any("may" in step for step in ability["steps"]):
            problems.append("activated abilities put their costs before the colon, not in 'you may'")
    choices = 0

    def walk(steps, scope, depth, cost_context):
        nonlocal choices
        if depth > MAX_DEPTH:
            problems.append("nested too deeply")
        if len(steps) > MAX_STEPS:
            problems.append("too many steps")
        scope = dict(scope)
        for step in steps:
            if "choose" in step:
                choices += 1
                scope[step["as"]] = step["choose"]["filter"]
            elif "effect" in step:
                check_effect(step, scope, cost_context)
            elif "if" in step:
                ref = step["if"].get("defeated")
                if ref is not None and ref not in scope:
                    problems.append(f"condition refers to unknown {ref!r}")
                walk(step["then"], scope, depth + 1, cost_context)
            elif "may" in step:
                walk(step["may"], scope, depth + 1, True)
                inner = dict(scope)
                for s in step["may"]:
                    if "choose" in s:
                        inner[s["as"]] = s["choose"]["filter"]
                walk(step["if_you_do"], inner, depth + 1, cost_context)
            elif "choose_one" in step:
                for branch in step["choose_one"]:
                    walk(branch, scope, depth + 1, cost_context)

    def check_effect(step, scope, cost_context):
        op = step["effect"]
        kind, _, rng_ = EFFECTS[op]
        target = step["target"]
        if op == "ready" and not step.get("no_score_or_activate"):
            problems.append("readied units must be barred from scoring and ⟳ that turn")
        if isinstance(target, dict) and "ref" in target:
            if target["ref"] not in scope:
                problems.append(f"{op} refers to {target['ref']!r} before it is chosen")
                return
            side, target_kind = scope[target["ref"]]["owner"], "unit"
            if op == "defeat" and not RESTRICTING & set(scope[target["ref"]]):
                problems.append("defeat needs a restricted target (low cost, damaged or exhausted)")
        elif isinstance(target, dict) and "all" in target:
            side, target_kind = target["all"]["owner"], "unit"
            if op == "defeat":
                problems.append("defeat can't target all(…)")
        elif target == "this":
            side, target_kind = "you", "unit"
            if card_type != "unit":
                problems.append("'this' target on a card that isn't in play")
        else:
            side, target_kind = target, "player"
        if target_kind != kind:
            problems.append(f"{op} needs a {kind} target")
        wanted = "you" if polarity(step) == HELPS else "opponent"
        if side != wanted and not cost_context:
            problems.append(f"{op} {polarity(step)} its target but targets {side}")
        amount = step.get("amount")
        if isinstance(amount, int) and rng_ and not rng_[0] <= amount <= rng_[1]:
            problems.append(f"{op} amount {amount} outside {rng_}")
        if isinstance(amount, dict) and "cap" not in amount:
            problems.append("scaling amount without a cap")

    walk(ability["steps"], {}, 0, False)
    if choices > MAX_CHOICES:
        problems.append("too many choices")
    return problems


# ------------------------------------------------------------------ card text


def _a(word: str) -> str:
    return ("an " if word[0].lower() in "aeiou" else "a ") + word


def _cap(text: str) -> str:
    return text[0].upper() + text[1:]


def _low(text: str) -> str:
    return text if text.split(" ", 1)[0] in TRAITS else text[0].lower() + text[1:]


def _adjectives(f: dict) -> str:
    words = []
    if f.get("not_this"):
        words.append("other")
    if f.get("damaged"):
        words.append("damaged")
    if f.get("exhausted") is True:
        words.append("exhausted")
    elif f.get("exhausted") is False:
        words.append("ready")
    if f.get("trait"):
        words.append(f["trait"])
    return " ".join(words)


def _suffix(f: dict) -> str:
    return f" with cost {f['cost_max']} or less" if "cost_max" in f else ""


def _all_phrase(f: dict) -> str:
    adj = _adjectives(f)
    noun = f"{adj} units".strip() if adj else "units"
    if f["owner"] == "opponent":
        return f"all {adj + ' ' if adj else ''}opposing units{_suffix(f)}"
    if f["owner"] == "you":
        return f"your {noun}{_suffix(f)}"
    return f"all {noun}{_suffix(f)}"


def _count_phrase(f: dict) -> str:
    adj = _adjectives(f)
    if f["owner"] == "you":
        return f"each of your {adj + ' ' if adj else ''}units"
    if f["owner"] == "opponent":
        return f"each opposing {adj + ' ' if adj else ''}unit"
    return f"each {adj + ' ' if adj else ''}unit in play"


def _chosen_phrase(f: dict) -> str:
    adj = _adjectives({k: v for k, v in f.items() if k != "not_this"})
    unit = f"{adj} unit".strip() if adj else "unit"
    if f["owner"] == "opponent":
        return f"chosen {adj + ' ' if adj else ''}opposing unit{_suffix(f)}"
    other = "another" if f.get("not_this") else "a"
    return f"{other} chosen {unit} of yours{_suffix(f)}"


def _amount_suffix(amount, unit_word: str = "") -> str:
    if isinstance(amount, dict):
        return f" for each {_count_phrase(amount['per']).removeprefix('each ')} (up to {amount['cap']}{unit_word})"
    return ""


class Renderer:
    def __init__(self, card_type: str):
        self.card_type = card_type
        self.chosen = {}  # name → filter
        self.introduced = set()

    def target(self, t) -> tuple[str, bool]:
        """(phrase, plural)"""
        if t == "this":
            return f"this {self.card_type}", False
        if isinstance(t, dict) and "ref" in t:
            name = t["ref"]
            if name in self.introduced:
                return ("that unit" if len(self.introduced) > 1 else "it"), False
            self.introduced.add(name)
            return _chosen_phrase(self.chosen[name]), False
        if isinstance(t, dict) and "all" in t:
            return _all_phrase(t["all"]), True
        raise ValueError(t)

    def effect(self, s: dict) -> str:
        op, amount = s["effect"], s.get("amount")
        if op in ("draw", "discard", "gain_vp", "lose_vp", "add_energy"):
            you = s["target"] == "you"
            n = amount if isinstance(amount, int) else 1
            if op == "draw":
                text = "draw a card" if n == 1 else f"draw {n} cards"
                if isinstance(amount, dict):
                    text = "draw a card" + _amount_suffix(amount)
                return _cap(text) + "." if you else f"Your opponent {text.replace('draw', 'draws')}."
            if op == "discard":
                cards = "a card" if n == 1 else f"{n} cards"
                return f"Discard {cards}." if you else f"Your opponent discards {cards} at random."
            if op == "gain_vp":
                return f"Gain {n if isinstance(amount, int) else 1} VP{_amount_suffix(amount)}."
            if op == "lose_vp":
                return f"Lose {n} VP." if you else f"Your opponent loses {n} VP."
            return "Put the top card of your deck into your energy zone, exhausted."

        t, plural = self.target(s["target"])
        s_ = "" if plural else "s"
        its = "their" if plural else "its"
        if op == "deal_damage":
            n = amount if isinstance(amount, int) else 1
            return f"Deal {n} damage to {t}{_amount_suffix(amount)}."
        if op == "remove_damage":
            return f"Remove {'all' if amount == 'all' else amount} damage from {t}."
        if op == "defeat":
            return f"Defeat {t}."
        if op == "return_to_hand":
            return f"Return {t} to their owners’ hands." if plural else f"Return {t} to its owner’s hand."
        if op == "ready":
            pronoun = "They" if plural else "It"
            return f"Ready {t}. {pronoun} can’t score or use ⟳ abilities this turn."
        if op == "exhaust":
            return f"Exhaust {t}."
        if op == "cant_ready":
            return f"{_cap(t)} can’t ready at the start of {its} next turn."
        if op == "modify_stat":
            sign = "+" if s["delta"] > 0 else "−"
            return f"{_cap(t)} get{s_} {sign}{abs(s['delta'])} {s['stat']} this turn."
        if op == "grant_keyword":
            return f"{_cap(t)} gain{s_} {s['keyword']} this turn."
        raise ValueError(op)

    def steps(self, steps: list) -> str:
        out = []
        for s in steps:
            if "choose" in s:
                self.chosen[s["as"]] = s["choose"]["filter"]
            elif "effect" in s:
                out.append(self.effect(s))
            elif "if" in s:
                out.append(f"If {'it was' if len(self.introduced) == 1 else 'that unit was'} defeated, "
                           f"{_low(self.steps(s['then']))}")
            elif "may" in s:
                cost = self.steps(s["may"]).rstrip(".")
                out.append(f"You may {_low(cost)}. If you do, {_low(self.steps(s['if_you_do']))}")
            elif "choose_one" in s:
                options = [Renderer(self.card_type).steps(b) for b in s["choose_one"]]
                out.append("Choose one: " + " ".join(f"• {o}" for o in options))
        return " ".join(out)


def _condition_text(c: dict, card_type: str) -> str:
    if "count" in c:
        f = c["count"]
        return f"you have {c['at_least']} or more {_adjectives(f)} units in play"
    if "behind_on_vp" in c:
        return "you have fewer VP than your opponent"
    return f"this {card_type} is {c['this_is']}"


def _trigger_text(t: dict) -> str:
    return {
        "on_play": "When you play this unit",
        "on_score": "Whenever this unit scores",
        "on_attack": "Whenever this unit attacks in a duel",
        "on_defeated": "When this unit is defeated",
        "start_of_turn": "At the start of your turn",
        "end_of_turn": "At the end of your turn",
        "another_played": f"Whenever you play another {t.get('filter', {}).get('trait', '')} unit",
        "opposing_defeated": "Whenever an opposing unit is defeated",
    }[t["event"]]


def render(ability: dict, card_type: str = "unit") -> str:
    kind = ability["kind"]
    if kind == "static":
        parts = []
        for m in ability["modifiers"]:
            cond = ability.get("condition")
            prefix = f"While {_condition_text(cond, card_type)}, " if cond else ""
            if "cost_reduction" in m:
                parts.append(f"{prefix}{m['filter']['trait']} cards you play cost {m['cost_reduction']} less.")
                continue
            subject = m["subject"]
            if subject == "this":
                who, s_ = ("it" if cond and "this_is" in cond else f"this {card_type}"), "s"
            else:
                who, s_ = _all_phrase(subject["all"]), ""
            if "keyword" in m:
                text = f"{who} {'has' if s_ else 'have'} {m['keyword']}."
            else:
                amount = m["amount"]
                n = amount if isinstance(amount, int) else amount["k"]
                sign = "+" if n > 0 else "−"
                text = f"{who} get{s_} {sign}{abs(n)} {m['stat']}{_amount_suffix(amount, '')}."
                if isinstance(amount, dict):
                    text = text.replace(f"(up to {amount['cap']})", f"(up to {sign}{amount['cap']})")
            parts.append(prefix + (text if prefix else _cap(text)))
        return " ".join(parts)

    body = Renderer(card_type).steps(ability["steps"])
    if kind == "on_resolve":
        return body
    if kind == "activated":
        costs = []
        for c in ability["cost"]:
            if c.get("exhaust_this"):
                costs.append("⟳")
            if "pay" in c:
                costs.append(f"{c['pay']} energy")
            if "discard" in c:
                costs.append("discard a card")
            if "exhaust_another" in c:
                costs.append("exhaust another of your ready units")
        return f"{', '.join(costs)}: {body}"
    lead = _trigger_text(ability["trigger"])
    cond = ability.get("condition")
    if cond:
        lead += f", if {_condition_text(cond, card_type)}"
    return f"{lead}, {_low(body)}"
