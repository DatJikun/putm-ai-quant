"""ingest.ask against the shared cases in tests/fixtures/ask-pack/cases.json.

tests/ask.test.ts runs the same cases against src/lib/ask.ts, so the two
implementations cannot drift apart.
"""

import json
from pathlib import Path

import pytest

from ingest.ask import answer

FIXTURES = Path(__file__).parent / "fixtures"
CASES = json.loads((FIXTURES / "ask-pack" / "cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_answer_matches_shared_case(case):
    pack = FIXTURES / case.get("pack", "ask-pack")
    if "error" in case:
        with pytest.raises((FileNotFoundError, ValueError)) as caught:
            answer(pack, case["tool"], case["args"])
        assert str(caught.value) == case["error"]
    else:
        assert answer(pack, case["tool"], case["args"]) == case["expect"]
