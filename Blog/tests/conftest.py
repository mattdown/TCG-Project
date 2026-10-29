"""Blog code sits next to these tests, and imports PythonServer itself (card_lab.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
