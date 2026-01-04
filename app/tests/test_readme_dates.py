import re
from pathlib import Path

README_PATH = Path(__file__).resolve().parents[2] / "README.md"


def test_readme_contains_no_iso_dates():
    content = README_PATH.read_text()
    assert not re.search(r"\b\d{4}-\d{2}-\d{2}T", content)
    assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", content)
