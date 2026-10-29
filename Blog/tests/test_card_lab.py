"""The card lab's data: what its pages and the card generation visualiser are built from."""
from card_lab import one, run
from src.cards.abilities import render


def test_card_lab_data():
    data = run(seed=3, count=30, jobs=6, action_share=0.25, vanilla_share=0.1, keyword_share=0.3, variety=2)
    assert len(data["kept"]) == 30
    for a in data["attempts"]:
        assert a["checks"][0]["test"] == ("grammar" if a["tree"] else "card")
        assert (a["card"] is None) == (a["stopped_at"] in ("grammar", "quality", "card"))
    kept = [data["attempts"][i] for i in data["kept"]]
    assert all(a["card"]["traits"][0] in data["job_list"] for a in kept if a["card"]["type"] == "unit")
    assert {a["kind"] for a in kept} >= {"vanilla", "keywords", "on_resolve"}
    assert all(a["card"]["aspect"] is None for a in kept if a["kind"] in ("vanilla", "keywords"))
    ability = next(a for a in kept if a["tree"])
    assert render(ability["tree"], ability["card_type"])


def test_explorer_data():
    data = one(seed=12, jobs=6, action_share=0.25, vanilla_share=0.0, keyword_share=0.0, variety=1)
    kept = data["kept"]
    assert kept["stopped_at"] is None and kept["card"] is not None
    assert 0 < kept["ability_p"] <= 1 and kept["ability_decisions"] >= 1
    assert all(a["stopped_at"] and "trace" in a for a in data["others"])


def test_visualiser_pool_starts_on_the_chosen_card():
    from card_generation_visualiser import pool_data
    cards = pool_data(112, 3)["cards"]
    assert [c["seed"] for c in cards][0] == 112 and len({c["seed"] for c in cards}) == 4
    assert all("trace" in c["kept"] and "others" not in c for c in cards)
