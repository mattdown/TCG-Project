"""The card lab's data: what its pages and the card generation visualiser are built from."""
from pathlib import Path

from card_lab import run
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



def test_card_lab_default_batch_has_art():
    """The default seed is the saved set's, so the lab opens on cards with painted art, and an export bakes it in."""
    from card_lab import ART, DEFAULTS, PAGE, art_keys, bake
    data = run(**DEFAULTS | {"count": 5})
    keys = {data["attempts"][i]["card"]["art"] for i in data["kept"]}
    assert all((ART / "cards" / f"{k}.webp").exists() for k in keys)
    html = bake(PAGE, data, art_keys(data))
    assert "<!--" + "CARD_ART-->" not in html and all(f'"{k}": "data:image/webp' in html for k in keys)

def test_visualiser_shows_the_set_with_art():
    """The visualiser's cards are the saved set's, so each one has the art painted for it."""
    from card_generation_visualiser import ART, SET_SIZE, pool_data
    from src.cards.schema import load_card_set
    saved = load_card_set(Path(__file__).parents[2] / "PythonServer" / "cardsets" / f"set_{SET_SIZE}.json").cards
    cards = pool_data(5)["cards"]
    assert [c["number"] for c in cards] == [1, 2, 3, 4, 5]
    assert [c["kept"]["card"]["name"] for c in cards] == [c.name for c in saved[:5]]
    assert all("trace" in c["kept"] and (ART / "cards" / f"{c['art']}.webp").exists() for c in cards)


def test_gnn_visualiser_reads_the_encoder():
    """The focus card's features are the encoder's own numbers, and it has neighbours of each edge type shown."""
    import pytest
    from gnn_visualiser import MODEL, graph_data
    if not MODEL.exists():
        pytest.skip("needs the trained model (models/ is gitignored)")
    data = graph_data()
    assert len(data["embedding"]["encoded"]) == len(data["embedding"]["projected"]) == data["embedding"]["hidden"]
    focus = data["nodes"][data["focus"]]
    assert focus["type"] == "card" and [f["value"] for f in data["features"]] == focus["vector"]
    assert all(r["value"] in (0.0, 1.0) for r in data["features"] if r["rule"] == "1 if yes")
    types = {e["type"] for e in data["edges"] if data["focus"] in (e["src"], e["dst"])}
    assert types == {"belongs_to", "faces", "part_of", "matches"}
