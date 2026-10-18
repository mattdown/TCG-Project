"""Player-facing names for game terms.

Every term is a placeholder until the game has a name and theme. Code uses the internal
keys; anything shown to a player (action text, the Unity client) goes through TERMS.
"""

TERMS = {
    "vp": "VP",
    "energy": "energy",
    "unit": "unit",
    "score": "score",
    "duel": "duel",
    "exhausted": "exhausted",
    "fresh": "fresh",
    "aspect": "aspect",
}

ASPECTS = ("aspect_1", "aspect_2", "aspect_3", "aspect_4", "aspect_5", "aspect_6")
ASPECT_NAMES = {"aspect_1": "Ember", "aspect_2": "Bog", "aspect_3": "Moss", "aspect_4": "Meadow",
                "aspect_5": "Glow", "aspect_6": "Frost"}  # see docs/theme.md

# Keyword → whether it carries a number ("Duelist +2") or is just present ("Guard").
KEYWORDS = {"guard": False, "elusive": False, "charge": False, "duelist": True, "armor": True}
KEYWORD_NAMES = {"guard": "Guard", "elusive": "Elusive", "charge": "Charge", "duelist": "Duelist", "armor": "Armor"}
# Reminder text for each keyword, shown when a card is inspected. N is the keyword's number.
KEYWORD_RULES = {
    "guard": "Can be dueled even while ready, and opponents must duel a Guard unit if they can.",
    "elusive": "Only Elusive units can duel it.",
    "charge": "Can duel the turn it's played (it still can't score that turn).",
    "duelist": "+N power when it starts a duel.",
    "armor": "Takes N less damage in a duel, never below 0.",
}


def keyword_text(name: str, value: int) -> str:
    """'Guard', 'Duelist +2'."""
    return f"{KEYWORD_NAMES[name]} +{value}" if KEYWORDS[name] else KEYWORD_NAMES[name]
