"""Best-effort sample strings for xs:pattern facets."""

from __future__ import annotations

import re

import pytest

from app.parser.regex_sample import sample_from_pattern


@pytest.mark.parametrize(
    "pattern",
    [
        "[0-9]{3}-[0-9]{10}",
        "[A-Z]{2,2}[0-9]{2,2}[A-Z0-9]{1,30}",
        "[A-Z]{3}",
        "\\d{4}-\\d{2}",
        "(ab|cd)+x?",
        "[a-zA-Z_][a-zA-Z0-9_\\-]*",
        "[^,]+",
        "[a-z-[aeiou]]{2}",
        "\\+?[0-9]+(\\.[0-9]{1,2})?",
        "ISIN[A-Z0-9]{12}",
        ".+@.+",
        "[0-9]{8}(T[0-9]{6})?",
    ],
)
def test_sample_matches_its_pattern(pattern: str) -> None:
    sample = sample_from_pattern(pattern)
    assert sample is not None, pattern
    assert re.fullmatch(pattern.replace("-[aeiou]", ""), sample) is not None, (pattern, sample)


def test_caret_and_dollar_are_ordinary_characters() -> None:
    """XSD regexes are implicitly anchored; libxml2 matches ^ and $ literally."""
    assert sample_from_pattern("^[A-Z]{2}$") == "^AA$"


@pytest.mark.parametrize("pattern", ["\\I", "[\\I]"])
def test_not_name_start_escape_yields_a_non_name_start_char(pattern: str) -> None:
    sample = sample_from_pattern(pattern)
    assert sample is not None and len(sample) == 1
    assert not (sample.isalpha() or sample in "_:"), sample


def test_unsupported_constructs_return_none() -> None:
    assert sample_from_pattern("\\p{L}+") is None
    assert sample_from_pattern("(?:x)") is None
    assert sample_from_pattern("[") is None
