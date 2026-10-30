"""Which image a card uses: named after what the card looks like, never its ID.

The key is the card's name, subtitle and habitat ("porcini-baker--up-before-dawn--meadow"), so a
regenerated set reuses every image whose card it still has. Keys are file names in the client
(Assets/Resources/CardArt/<key>.jpg, made by TCGClient/Tools/card_art), so they must stay stable:
the habitat words are fixed here, not taken from terms.py, so renaming an aspect doesn't lose art.
"""
import re

HABITAT_WORDS = {"aspect_1": "ember", "aspect_2": "bog", "aspect_3": "moss", "aspect_4": "meadow",
                 "aspect_5": "glow", "aspect_6": "frost"}


def art_key(name: str, subtitle: str, aspects) -> str:
    habitat = HABITAT_WORDS[aspects[0]] if aspects else "neutral"
    return "--".join(re.sub(r"[^a-z0-9]+", "-", p.lower()).strip("-") for p in (name, subtitle, habitat) if p)
