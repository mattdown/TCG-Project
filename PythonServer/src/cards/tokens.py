"""Tokens: units that abilities summon.

A token is described inside the ability that summons it ({"name", "power", "health",
"keywords"?, "trait"?}), so cards stay data. token_card() turns a description into a card with an
id derived from it, so the same description is always the same card: the server sends these
with the card set, and the network sees a token like any other unit.
"""
import json
from functools import lru_cache

from src.cards.schema import Card

TOKEN_PREFIX = "token:"


def token_card(spec: dict) -> Card:
    return _token_card(json.dumps(spec, sort_keys=True))


@lru_cache(maxsize=None)
def _token_card(key: str) -> Card:
    spec = json.loads(key)
    keywords = tuple(sorted(spec.get("keywords", {}).items()))
    trait = spec.get("trait")
    parts = [spec["name"], f"{spec['power']}/{spec['health']}", *(f"{k}{v}" for k, v in keywords), trait or ""]
    return Card(TOKEN_PREFIX + "-".join(p.replace(" ", "_") for p in parts if p), spec["name"], "unit", (), 0,
                spec["power"], spec["health"], traits=(trait,) if trait else (), keywords=keywords)


def is_token(card: Card) -> bool:
    return card.id.startswith(TOKEN_PREFIX)


def tokens_of(card: Card) -> list[Card]:
    """The tokens a card's abilities can summon."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("effect") == "summon":
                found.append(token_card(node["token"]))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(list(card.abilities))
    return found
