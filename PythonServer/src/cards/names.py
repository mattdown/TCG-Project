"""Card names from what a card does (docs/theme.md, "Card names").

Units are a species + job with a subtitle picked from the ability ("Porcini Baker – Up Before
Dawn"), so the same character can come back with different abilities. Actions get an event
name instead: an aspect word plus a noun for their main effect ("Ember Volley"). Every full
name in a set is unique. Names are theme only: no rule or network input depends on them.
"""
from src.cards.theme import (ACTION_NOUNS, ACTION_WORDS, SUBTITLES_BY_EFFECT, SUBTITLES_BY_KEYWORD,
                             SUBTITLES_BY_STATIC, SUBTITLES_BY_TRIGGER, SUBTITLES_GENERIC)
from src.cards.trace import Tracer


def main_effect(ability: dict) -> str | None:
    """The effect an ability is about: the reward of a "you may", the first option of a choose one."""
    def first(steps):
        for step in steps:
            if "effect" in step:
                return step["effect"]
            for key in ("if_you_do", "then"):
                if key in step:
                    return first(step[key])
            if "choose_one" in step:
                return first(step["choose_one"][0])
        return None
    return first(ability.get("steps", []))


def static_kind(ability: dict) -> str:
    m = ability["modifiers"][0]
    if "cost_reduction" in m:
        return "discount"
    if m["subject"] == "this":
        return "self_keyword" if "keyword" in m else "self_situational"
    return "lord" if m["subject"]["all"]["owner"] == "you" else "debuff"


class Namer:
    """Picks names that no kept card has yet. Call reserve() for each card that is kept, so
    draws that are thrown away don't use names up."""

    def __init__(self, trace: Tracer):
        self.trace = trace
        self.used: set[str] = set()

    def reserve(self, card) -> None:
        self.used.add(full_name(card))

    def subtitle(self, name: str, ability: dict | None, keywords: dict | None = None) -> str:
        """A subtitle that makes `name` unique in the set. Units without an ability are named
        after their keyword, if they have one."""
        t = self.trace
        banks = []
        if ability is None:
            for keyword in sorted(keywords or {}):
                banks.append((f"its keyword ({keyword})", SUBTITLES_BY_KEYWORD[keyword]))
        elif ability["kind"] == "static":
            banks.append(("what the static does", SUBTITLES_BY_STATIC[static_kind(ability)]))
        else:
            effect = ("its main effect", SUBTITLES_BY_EFFECT.get(main_effect(ability), ()))
            if ability["kind"] == "triggered":
                trigger = ("its trigger", SUBTITLES_BY_TRIGGER[ability["trigger"]["event"]])
                first = t.choice("Name after", ["its trigger", "its main effect"])
                banks += [trigger, effect] if first == "its trigger" else [effect, trigger]
            else:
                banks.append(effect)
        banks.append(("generic", SUBTITLES_GENERIC))
        for why, bank in banks:
            options = [s for s in bank if f"{name} – {s}" not in self.used]
            if options:
                subtitle = t.choice("Subtitle", options, f"from {why}")
                break
        else:
            n = 2
            while f"{name} – {SUBTITLES_GENERIC[0]} {n}" in self.used:
                n += 1
            subtitle = f"{SUBTITLES_GENERIC[0]} {n}"
        return subtitle

    def action(self, aspect: str | None, ability: dict) -> str:
        """An event name: a word from the card's aspect (any aspect for a neutral card) and a noun
        for its main effect."""
        nouns = ACTION_NOUNS[main_effect(ability)]
        every = [f"{w} {n}" for words in ACTION_WORDS.values() for w in words for n in nouns]
        own = [f"{w} {n}" for w in ACTION_WORDS[aspect] for n in nouns] if aspect else every
        name = None
        for options, note in ((own, "an aspect word + a noun for the main effect"), (every, "this aspect's names are used up")):
            options = [o for o in options if o not in self.used]
            if options:
                name = self.trace.choice("Action name", options, note)
                break
        if name is None:
            n = 2
            while f"{own[0]} {n}" in self.used:
                n += 1
            name = f"{own[0]} {n}"
        return name


def full_name(card) -> str:
    return f"{card.name} – {card.subtitle}" if card.subtitle else card.name
