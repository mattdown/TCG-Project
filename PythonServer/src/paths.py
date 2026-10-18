from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARDSET_PATH = ROOT / "cardsets" / "keywords_200.json"
MODEL_PATH = ROOT / "models" / "tcgnet.pt"
