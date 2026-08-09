import json
from pathlib import Path

import pytest

from app.cineprompt import assemble

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "cineprompt_golden.json").read_text(encoding="utf-8"))


def test_fixture_corpus_is_complete():
    assert len(GOLDEN) == 240


@pytest.mark.parametrize("case", GOLDEN, ids=range(len(GOLDEN)))
def test_matches_oracle(case):
    assert assemble.build_text(case["fields"]) == case["expected"]


def test_empty_state_yields_empty_string():
    assert assemble.build_text({}) == ""


def test_nl_join():
    assert assemble.nl_join(["a"]) == "a"
    assert assemble.nl_join(["a", "b"]) == "a and b"
    assert assemble.nl_join(["a", "b", "c"]) == "a, b and c"
