"""Best-effort sample strings for xs:pattern facets."""

from __future__ import annotations

import re

import pytest
from lxml import etree

from app.parser.regex_sample import sample_from_pattern, samples_from_pattern


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


@pytest.mark.parametrize(
    "pattern",
    ["\\p{IsGreek}+", "\\p{IsCyrillic}{3}", "\\p{Nl}", "\\p{Sc}\\p{Mn}", "\\P{IsGreek}\\P{M}"],
)
def test_unicode_blocks_and_categories_are_sampled(pattern: str) -> None:
    """Checked against libxml2, which is what validates the sample in the end."""
    sample = sample_from_pattern(pattern)
    assert sample
    schema = etree.XMLSchema(
        etree.fromstring(
            '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="v">'
            '<xs:simpleType><xs:restriction base="xs:string">'
            f'<xs:pattern value="{pattern}"/></xs:restriction></xs:simpleType>'
            "</xs:element></xs:schema>"
        )
    )
    root = etree.Element("v")
    root.text = sample
    assert schema.validate(root), sample


def test_unsupported_constructs_return_none() -> None:
    assert sample_from_pattern("\\p{IsNoSuchBlock}+") is None
    assert sample_from_pattern("(?:x)") is None
    assert sample_from_pattern("[") is None


@pytest.mark.parametrize(
    ("pattern", "python"),
    [
        ("\\p{Lu}{3}\\p{Nd}{2}", "[A-Z]{3}[0-9]{2}"),
        ("[\\p{L}\\p{N}_]+", "[A-Za-z0-9_]+"),
        ("\\P{L}\\p{Ll}", "[^A-Za-z][a-z]"),
        ("\\p{IsBasicLatin}{2}", "[A-Za-z0-9]{2}"),
    ],
)
def test_common_unicode_categories_are_sampled(pattern: str, python: str) -> None:
    sample = sample_from_pattern(pattern)
    assert sample is not None and re.fullmatch(python, sample), (pattern, sample)


def test_several_samples_cover_branches_lengths_and_class_members() -> None:
    samples = list(samples_from_pattern("A|BBBBB"))
    assert samples == ["A", "BBBBB"]
    # Class members are walked through first, then the plain first-member form.
    assert list(samples_from_pattern("[A-Z]{2}[0-9]{2}"))[:2] == ["AB23", "AA00"]
    # The shortest match of an optional part comes first, the empty one last.
    assert list(samples_from_pattern("[a-z]*"))[0] == "a"
    assert list(samples_from_pattern("[a-z]*"))[-1] == ""
    stretched = list(samples_from_pattern("x+", min_length=5))
    assert "xxxxx" in stretched


@pytest.mark.parametrize(
    "pattern", ["[0-9]{3}-[0-9]{10}", "(ab|cd)+x?", "[a-z-[aeiou]]{2,4}", "\\d{1,3}(\\.\\d+)?"]
)
def test_every_sample_matches(pattern: str) -> None:
    samples = list(samples_from_pattern(pattern, min_length=3))
    assert samples
    for sample in samples:
        assert re.fullmatch(pattern.replace("-[aeiou]", ""), sample) is not None, (pattern, sample)


def test_unsupported_pattern_yields_no_samples() -> None:
    assert list(samples_from_pattern("\\p{IsGothic}+")) == []


def test_nested_repetition_cannot_run_away() -> None:
    """(a+b+c+)+ stretched to a large minLength multiplies into gigabytes."""
    samples = list(samples_from_pattern("(a+b+c+)+", min_length=200_000))
    assert samples and all(len(sample) <= 200_000 for sample in samples)
    assert sample_from_pattern("(a+b+c+)+", stretch=200_000) is None
    # A plain long repetition is still fine.
    assert sample_from_pattern("a+", stretch=50_000) == "a" * 50_000


def test_one_quantifier_is_lengthened_to_hit_an_exact_length() -> None:
    """TAF TSI ConsignmentNumber: \\d*[1-9]\\d* with length 6."""
    samples = list(samples_from_pattern("\\d*[1-9]\\d*", min_length=6))
    assert any(len(sample) == 6 for sample in samples[:4])
