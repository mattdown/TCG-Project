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
them independently, so it can also vet trees written by hand or by another generator. The
quality tests in quality.py then drop legal abilities that aren't worth generating.
The sampling weights are hand-tuned placeholders, and the cost model will set cards' cost
and stats later.
"""
import random

from src.cards.quality import quality_problems
from src.cards.trace import Tracer
from src.cards.theme import JOBS
from src.game.terms import KEYWORDS, keyword_text

TRAITS = JOBS  # traits are jobs (docs/theme.md)
HELPS, HURTS = "helps", "hurts"
MAX_STEPS, MAX_DEPTH, MAX_CHOICES = 4, 2, 2

# op: (target kind, polarity, amount range or None)
EFFECTS = {
    "deal_damage": ("unit", HURTS, (1, 5)),
    "remove_damage": ("unit", HELPS, (1, 5)),
    "defeat": ("unit", HURTS, None),
    "return_to_hand": ("unit", HURTS, None),
    "freeze": ("unit", HURTS, None),
    "modify_stat": ("unit", None, (1, 3)),  # polarity follows the sign; a bonus or penalty that ends
    "buff": ("unit", HELPS, None),  # lasting +power / +health ("+2/+2"), until the unit leaves play
    "grant_keyword": ("unit", HELPS, None),
    "draw": ("player", HELPS, (1, 3)),
    "discard": ("player", HURTS, (1, 2)),
    "heal_hero": ("player", HELPS, (2, 5)),
    "damage_hero": ("player", HURTS, (1, 3)),
    "gain_crystal": ("player", HELPS, None),
}
EFFECT_WEIGHTS = {"deal_damage": 10, "remove_damage": 3, "defeat": 2, "return_to_hand": 3, "freeze": 4,
                  "modify_stat": 8, "buff": 6, "grant_keyword": 4, "draw": 8, "discard": 3, "heal_hero": 5, "damage_hero": 5,
                  "gain_crystal": 2}
OWN_JOB = 0.75  # chance a job reference is the unit's own job
GRANTABLE_KEYWORDS = (("guard", 1), ("duelist", 1), ("duelist", 2), ("armor", 1))
# Guard and Armor protect a unit during the opponent's turn, so a grant lasts until the start of
# your next turn; Duelist only matters when you attack, so it lasts this turn. Charge is never
# granted: it only matters on the turn a unit is played. Elusive isn't either: a unit that has
# attacked can't hide again.
GRANT_DURATION = {"guard": "until_your_next_turn", "elusive": "until_your_next_turn",
                  "armor": "until_your_next_turn", "duelist": "this_turn"}
DURATION_TEXT = {"this_turn": "this turn", "until_your_next_turn": "until the start of your next turn"}
TRIGGERS = {"on_play": 10, "on_attack_hero": 3, "on_attack": 3, "on_defeated": 3, "start_of_turn": 3, "end_of_turn": 2,
            "another_played": 2, "opposing_defeated": 2}
SITUATIONS = ("attacking", "defending", "exhausted", "damaged")
RESTRICTING = {"cost_max", "damaged"}  # filter fields that limit how strong a defeat target can be


def polarity(step: dict) -> str:
    _, pol, _ = EFFECTS[step["effect"]]
    if pol is None:
        return HELPS if step["delta"] > 0 else HURTS
    return pol


# ------------------------------------------------------------------ sampling


class AbilitySampler:
    """Every random decision goes through a Tracer, so the path taken through the grammar can be
    shown afterwards (self.trace.root after raw())."""

    def __init__(self, rng: random.Random, traits: tuple[str, ...] = TRAITS):
        self.rng = rng
        self.trace = Tracer(rng)
        self.traits = traits  # the jobs abilities may refer to
        self.own_job = None  # the unit's own job, when it's known before the ability (CardGenerator)

    def ability(self, card_type: str = "unit") -> dict:
        """A random ability that passes validate() and the quality tests (src/cards/quality.py).
        Abilities that fail are resampled."""
        while True:
            ability = self.raw(card_type)
            if not validate(ability, card_type) and not quality_problems(ability):
                return ability

    def raw(self, card_type: str, reset: bool = True) -> dict:
        """One draw from the grammar, before any checks. `reset=False` adds to the current trace."""
        t = self.trace
        if reset:
            t.reset()
        if card_type == "action":
            t.fixed("Ability kind", "on_resolve", "action cards only have on-resolve abilities")
            kind = "on_resolve"
        else:
            kind = t.weighted("Ability kind", {"triggered": 5, "activated": 0, "static": 3},
                              "units only attack: no ⟳ abilities in rules v2")
        self.card_type = card_type
        self.names = []  # (name, side) of choices made so far
        if kind == "static":
            with t.section("static"):
                return {"kind": "static", **self._static()}
        ability = {"kind": kind}
        if kind == "triggered":
            ability["trigger"] = self._trigger()
            has_condition = t.chance("Add a condition?", 0.2)
            with t.section("condition"):
                ability["condition"] = self._condition() if has_condition else None
        elif kind == "activated":
            ability["cost"] = self._cost()
        with t.section("steps"):
            ability["steps"] = self._steps(ability)
        if kind == "triggered" and ability["trigger"]["event"] == "end_of_turn":
            # A "this turn" bonus at the end of your turn would end at once: make it last through
            # the opponent's turn instead.
            for step in _effects_in(ability["steps"]):
                if step["effect"] == "modify_stat":
                    step["duration"] = "until_your_next_turn"
        return ability

    def _trigger(self) -> dict:
        t = self.trace
        with t.section("trigger"):
            event = t.weighted("Trigger", TRIGGERS)
            trigger = {"event": event}
            if event == "another_played":
                trigger["filter"] = {"owner": "you", "trait": self._job("Which job"), "not_this": True}
        return trigger

    def _cost(self) -> list:
        # ⟳ is always part of the cost, so an activated ability can't run away: it's used at most once
        # per turn unless something readies the unit (and readied units can't use ⟳ that turn).
        t = self.trace
        with t.section("cost"):
            t.fixed("Cost", "⟳", "every activated ability exhausts its card, so it can't run away")
            cost = [{"exhaust_this": True}]
            extra = t.weighted("Extra cost", {"none": 4, "pay": 4, "exhaust_another": 1, "discard": 1})
            if extra == "pay":
                cost.append({"pay": t.small("Energy", 1, 3)})
            elif extra != "none":
                cost.append({extra: 1})
        return cost

    def _job(self, label: str) -> str:
        """A job to refer to: usually the unit's own, since decks focus on two jobs and tribes
        reward their own members."""
        t = self.trace
        if self.own_job is None:
            return t.choice(label, self.traits)
        if t.chance(f"{label}: its own ({self.own_job})?", OWN_JOB):
            return self.own_job
        return t.choice(label, [j for j in self.traits if j != self.own_job] or self.traits)

    def _condition(self) -> dict:
        t = self.trace
        kind = t.weighted("Condition", {"count": 3, "behind_on_health": 1})
        if kind == "count":
            return {"count": {"owner": "you", "trait": self._job("Count which job"), "not_this": True},
                    "at_least": t.choice("At least", (2, 3))}
        return {"behind_on_health": True}

    def _filter(self, owner: str, extra_chance: float = 0.35) -> dict:
        t = self.trace
        f = {"owner": owner}
        if owner == "you" and self.card_type == "unit":
            f["not_this"] = True
        if 0 < extra_chance < 1:
            restrict = t.chance("Restrict the target?", extra_chance)
        else:
            restrict = self.rng.random() < extra_chance  # forced either way; drawn so the random stream is unchanged
            if restrict:
                t.fixed("Restrict the target?", "yes", "defeat always needs a restricted target")
        if restrict:
            # A job filter on enemy units rarely has a target: decks focus on two of the jobs.
            extra = t.weighted("Restriction", {"damaged": 2, "cost_max": 2, "trait": 2 if owner != "opponent" else 0},
                               "no enemy jobs: decks focus on two jobs" if owner == "opponent" else "")
            if extra == "cost_max":
                f["cost_max"] = t.choice("Cost at most", (2, 3, 4))
            elif extra == "trait":
                f["trait"] = self._job("Job")
            else:
                f[extra] = True
        return f

    def _steps(self, ability: dict) -> list:
        t = self.trace
        # Activated abilities put every cost before the colon, so they never use "you may … if you do".
        may = 0 if ability["kind"] == "activated" else 3
        pattern = t.weighted("Step pattern", {"single": 7, "double": 3, "follow_up": 3, "may": may, "choose_one": 2},
                             "activated abilities can't use 'you may'" if not may else "")
        if pattern == "single":
            with t.section("effect"):
                return self._effect(ability)
        if pattern == "double":
            with t.section("first effect"):
                first = self._effect(ability)
            with t.section("second effect"):
                return first + self._effect(ability, player_only=True, exclude=first[-1]["effect"])
        if pattern == "follow_up":
            with t.section("effect"):
                steps = self._effect(ability, op="deal_damage", choose=True)
            name = self.names[-1][0]
            with t.section("if it was defeated"):
                return steps + [{"if": {"defeated": name},
                                 "then": self._effect(ability, player_only=True, helps_only=True)}]
        if pattern == "may":
            with t.section("you may (cost)"):
                cost = self._self_cost()
            self.names = [n for n in self.names if n[0] != "that"]  # the reward doesn't target what was paid
            same_resource = "heal_hero" if cost[-1]["effect"] == "damage_hero" else None  # "lose 2, heal 3" is just "heal 1"
            with t.section("if you do (reward)"):
                reward = self._effect(ability, helps_only=True, strong=True, exclude=same_resource)
            return [{"may": cost, "if_you_do": reward}]
        with t.section("option 1"):
            first = self._effect(ability, player_only=True)
        with t.section("option 2"):
            return [{"choose_one": [first, self._effect(ability)]}]

    def _self_cost(self) -> list:
        t = self.trace
        kind = t.weighted("Cost to pay", {"discard": 3, "damage_own": 1, "damage_hero": 2})
        if kind == "discard":
            return [{"effect": "discard", "target": "you", "amount": 1, "chosen": True}]
        if kind == "damage_hero":
            return [{"effect": "damage_hero", "target": "you", "amount": t.choice("Damage", (2, 3))}]
        self.names.append(("that", "you"))
        choose = {"choose": {"count": 1, "filter": self._filter("you", extra_chance=0)}, "as": "that"}
        return [choose, {"effect": "deal_damage", "target": {"ref": "that"}, "amount": t.choice("Damage", (1, 2))}]

    def _effect(self, ability: dict, op: str | None = None, player_only=False, helps_only=False, choose=False,
                strong=False, exclude: str | None = None) -> list:
        t = self.trace
        options = {o: (w if (not player_only or EFFECTS[o][0] == "player") and (not helps_only or EFFECTS[o][1] != HURTS)
                       and o != exclude else 0)
                   for o, w in EFFECT_WEIGHTS.items()}
        why = [w for w, on in (("player effects only", player_only), ("helpful effects only", helps_only),
                               (f"not {exclude} again", exclude)) if on]
        if op:
            t.fixed("Effect", op, "this step pattern always deals damage first")
        else:
            op = t.weighted("Effect", options, "; ".join(why))
        kind, pol, rng_ = EFFECTS[op]
        step = {"effect": op}
        if op == "modify_stat":
            stat = t.weighted("Stat", {"power": 6, "health": 3})
            sign = 1 if helps_only or t.chance("Raise it? (else lower)", 0.7) else -1
            if sign < 0:
                stat = "power"
                t.fixed("Stat", "power", "only power is ever lowered")
            big = strong or self.card_type == "action"
            step.update(stat=stat, delta=sign * t.small("By", 1 + (self.card_type == "action"), 3 if big else 2,
                                                        "an action spends a whole card" if self.card_type == "action" else ""),
                        duration="this_turn")
            pol = HELPS if sign > 0 else HURTS
        elif op == "buff":
            shape = t.weighted("Buff", {"power": 2, "health": 2, "both": 3})
            big = strong or self.card_type == "action"
            n = t.small("By", 1 + (self.card_type == "action"), 3 if big else 2,
                        "an action spends a whole card" if self.card_type == "action" else "")
            step.update(power=n if shape != "health" else 0, health=n if shape != "power" else 0)
        elif op == "grant_keyword":
            keyword, value = t.choice("Keyword", GRANTABLE_KEYWORDS)
            step.update(keyword=keyword, value=value, duration=GRANT_DURATION[keyword])
        elif op == "discard":
            step["random"] = True

        if rng_ and op != "modify_stat":
            lo, hi = rng_
            # An action spends a whole card, so its effects start one higher (as rewards do).
            bump = 1 if strong or self.card_type == "action" else 0
            why = "a reward is at least 2" if strong else "an action spends a whole card" if bump else ""
            step["amount"] = t.small("Amount", min(lo + bump, hi), hi + (self.card_type == "action"), why)
            if op == "remove_damage" and t.chance("Remove all damage instead?", 0.3):
                step["amount"] = "all"
            elif op in ("deal_damage", "draw", "heal_hero") and t.chance("Scale with a count instead?", 0.15):
                step["amount"] = {"per": {"owner": t.choice("Count whose units", ("you", "any")),
                                          "trait": self._job("Count which job")},
                                  "k": 1, "cap": t.choice("Up to", (3, 4, 5))}

        side = "you" if pol == HELPS else "opponent"
        if kind == "player":
            t.fixed("Target", side, "helpful effects target you, harmful ones your opponent")
            step["target"] = side
            return [step]

        # Unit effects: reuse an earlier choice, make a new one, hit everything matching, or this card.
        with t.section("target"):
            earlier = [name for name, s in self.names if s == side]
            can_use_this = (side == "you" and ability.get("kind") in ("triggered", "static")
                            and ability.get("trigger", {}).get("event") != "on_defeated")
            choose = choose or op == "defeat"  # defeat always goes through a restricted choice
            if earlier and not choose and t.chance(f"Reuse '{earlier[-1]}'?", 0.6):
                step["target"] = {"ref": earlier[-1]}
                return [step]
            if choose:
                how = "choose"
                t.fixed("Target", "choose", "defeat always targets a restricted choice" if op == "defeat"
                        else "the follow-up needs a chosen unit")
            else:
                how = t.weighted("Target", {"choose": 6, "all": 2, "this": 2 if can_use_this else 0},
                                 "" if can_use_this else "'this' isn't possible here")
            if how == "this":
                step["target"] = "this"
                return [step]
            if how == "all":
                step["target"] = {"all": self._filter(side)}
                if isinstance(step.get("amount"), int) and op == "deal_damage" and step["amount"] > 2:
                    t.fixed("Amount", 2, "area damage stays small")
                    step["amount"] = 2
                return [step]
            name = "it" if not any(n == "it" for n, _ in self.names) else "other"
            self.names.append((name, side))
            f = self._filter(side, extra_chance=1.0 if op == "defeat" else 0.35)
            if op == "defeat" and "trait" in f:
                del f["trait"]  # a trait alone doesn't limit how strong the target is
                f["cost_max"] = t.choice("Cost at most", (2, 3), "a job alone doesn't limit a defeat target")
        choose_step = {"choose": {"count": 1, "filter": f}, "as": name}
        step["target"] = {"ref": name}
        return [choose_step, step]

    def _static(self) -> dict:
        t = self.trace
        kind = t.weighted("Static kind", {"self_situational": 4, "lord": 3, "self_keyword": 2, "discount": 1, "debuff": 1})
        trait = self._job("Job")
        if kind == "self_situational":
            if t.chance("Fixed amount? (else scale with a count)", 0.5):
                amount = t.small("Amount", 1, 2)
            else:
                amount = {"per": {"owner": t.choice("Count whose units", ("you", "any")), "trait": trait}, "k": 1,
                          "cap": t.choice("Up to", (3, 4))}
            stat = "power" if t.chance("Power? (else health)", 0.8) else "health"
            situation = "attacking" if stat == "power" else "defending"
            t.fixed("While", situation, "power matters when attacking, health when defending")
            return {"condition": {"this_is": situation},
                    "modifiers": [{"subject": "this", "stat": stat, "amount": amount}]}
        if kind == "lord":
            return {"condition": None, "modifiers": [{"subject": {"all": {"owner": "you", "trait": trait, "not_this": True}},
                                                      "stat": t.choice("Stat", ("power", "health")), "amount": 1}]}
        if kind == "self_keyword":
            condition = t.choice("While", ({"this_is": "damaged"},
                                           {"count": {"owner": "you", "trait": trait, "not_this": True}, "at_least": 2}))
            return {"condition": condition,
                    "modifiers": [{"subject": "this", **dict(zip(("keyword", "value"), t.choice("Keyword", GRANTABLE_KEYWORDS)))}]}
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
            if m.get("keyword") == "charge":
                problems.append("Charge can't be granted: it only matters on the turn a unit is played")
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
        if op == "grant_keyword":
            if step["keyword"] in ("charge", "elusive"):
                problems.append(f"{step['keyword']} can't be granted (it only matters before a unit first acts)")
            elif step.get("duration") != GRANT_DURATION[step["keyword"]]:
                problems.append(f"{step['keyword']} must last {DURATION_TEXT[GRANT_DURATION[step['keyword']]]}")
        if isinstance(target, dict) and "ref" in target:
            if target["ref"] not in scope:
                problems.append(f"{op} refers to {target['ref']!r} before it is chosen")
                return
            side, target_kind = scope[target["ref"]]["owner"], "unit"
            if op == "defeat" and not RESTRICTING & set(scope[target["ref"]]):
                problems.append("defeat needs a restricted target (low cost or damaged)")
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
    if ability["kind"] == "triggered" and ability["trigger"]["event"] == "end_of_turn" and any(
            e["effect"] in ("modify_stat", "grant_keyword") and e.get("duration", "this_turn") == "this_turn"
            for e in _effects_in(ability["steps"])):
        problems.append("a 'this turn' effect at the end of your turn ends as soon as it starts")
    if choices > MAX_CHOICES:
        problems.append("too many choices")
    return problems


def _effects_in(steps: list):
    """Every effect step, including ones nested inside if / may / choose one."""
    for step in steps:
        if "effect" in step:
            yield step
        for key in ("then", "else", "may", "if_you_do"):
            yield from _effects_in(step.get(key, []))
        for branch in step.get("choose_one", []):
            yield from _effects_in(branch)


def card_problems(card_type: str, health: int, keywords: dict, abilities) -> list[str]:
    """Problems that depend on the card as well as the ability: abilities that could never matter."""
    problems = []
    for ability in abilities:
        conditions = [ability.get("condition") or {}]
        effects = list(_effects_in(ability.get("steps", [])))
        on_this = [e for e in effects if e["target"] == "this"]
        # A 1-health unit is defeated by its first damage, so it's never "damaged" while in play.
        if card_type == "unit" and health < 2 and (
                any(c.get("this_is") == "damaged" for c in conditions)
                or any(e["effect"] == "remove_damage" for e in on_this)):
            problems.append("only matters once this unit is damaged, but 1 damage defeats it")
        # Keywords without a number don't stack, so giving this unit one it already has does nothing.
        given = [m for m in ability.get("modifiers", []) if m.get("subject") == "this" and "keyword" in m]
        given += [e for e in on_this if e["effect"] == "grant_keyword"]
        if any(not KEYWORDS[g["keyword"]] and keywords.get(g["keyword"]) for g in given):
            problems.append("gives this unit a keyword it already has")
        # A unit is fresh the turn it's played: it can only attack with Charge.
        # It also has no damage yet.
        if ability["kind"] == "triggered" and ability["trigger"]["event"] == "on_play":
            if any(e["effect"] == "remove_damage" for e in on_this):
                problems.append("removes damage from a unit that was just played and has none")
            if any(e["effect"] == "buff" for e in on_this):
                problems.append("a lasting bonus to this unit when it's played is just more stats")
            for e in on_this:
                if e["effect"] == "modify_stat" and e.get("duration", "this_turn") == "this_turn" and (
                        e["stat"] == "power" and not keywords.get("charge")):
                    problems.append(f"+{e['stat']} this turn on a unit that was just played and can't use it")
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


def _opposing(f: dict) -> str:
    """"damaged enemy Chef": the job goes next to the noun, like on your own units."""
    words = [_adjectives({k: v for k, v in f.items() if k not in ("trait", "not_this")}), "enemy", f.get("trait", "")]
    return " ".join(w for w in words if w)


def _suffix(f: dict) -> str:
    return f" with cost {f['cost_max']} or less" if "cost_max" in f else ""


def _all_phrase(f: dict) -> str:
    adj = _adjectives(f)
    noun = f"{adj} units".strip() if adj else "units"
    if f["owner"] == "opponent":
        return f"all {_opposing(f)} units{_suffix(f)}"
    if f["owner"] == "you":
        return f"your {noun}{_suffix(f)}"
    return f"all {noun}{_suffix(f)}"


def _count_phrase(f: dict) -> str:
    adj = _adjectives(f)
    if f["owner"] == "you":
        return f"each of your {adj + ' ' if adj else ''}units"
    if f["owner"] == "opponent":
        return f"each {_opposing(f)} unit"
    return f"each {adj + ' ' if adj else ''}unit in play"


def _chosen_phrase(f: dict) -> str:
    adj = _adjectives({k: v for k, v in f.items() if k != "not_this"})
    unit = f"{adj} unit".strip() if adj else "unit"
    if f["owner"] == "opponent":
        return f"chosen {_opposing(f)} unit{_suffix(f)}"
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
        if op in ("draw", "discard", "heal_hero", "damage_hero", "gain_crystal"):
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
            if op == "heal_hero":
                return f"Heal your hero for {n if isinstance(amount, int) else 1}{_amount_suffix(amount)}."
            if op == "damage_hero":
                return f"Deal {n} damage to {'your' if you else 'the enemy'} hero."
            return "Gain an empty mana crystal."

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
        if op == "freeze":
            return f"Freeze {t}: {'they' if plural else 'it'} can’t attack on {its} next turn."
        if op == "exhaust":
            return f"Exhaust {t}."
        if op == "modify_stat":
            sign = "+" if s["delta"] > 0 else "−"
            duration = DURATION_TEXT[s.get("duration", "this_turn")]
            return f"{_cap(t)} get{s_} {sign}{abs(s['delta'])} {s['stat']} {duration}."
        if op == "buff":
            gains = " and ".join(f"+{s[stat]} {stat}" for stat in ("power", "health") if s[stat])
            return f"{_cap(t)} get{s_} {gains}."
        if op == "grant_keyword":
            duration = DURATION_TEXT[s.get("duration", "this_turn")]
            return f"{_cap(t)} gain{s_} {keyword_text(s['keyword'], s.get('value', 1))} {duration}."
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
    if "behind_on_health" in c:
        return "your hero has less health than the enemy hero"
    return f"this {card_type} is {c['this_is']}"


def _trigger_text(t: dict) -> str:
    return {
        "on_play": "When you play this unit",
        "on_attack_hero": "Whenever this unit attacks the enemy hero",
        "on_attack": "Whenever this unit attacks",
        "on_defeated": "When this unit is defeated",
        "start_of_turn": "At the start of your turn",
        "end_of_turn": "At the end of your turn",
        "another_played": f"Whenever you play another {t.get('filter', {}).get('trait', '')} unit",
        "opposing_defeated": "Whenever an enemy unit is defeated",
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
                text = f"{who} {'has' if s_ else 'have'} {keyword_text(m['keyword'], m.get('value', 1))}."
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
                costs.append(f"{c['pay']} mana")
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
