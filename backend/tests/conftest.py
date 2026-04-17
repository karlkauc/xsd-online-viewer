"""Pytest fixtures shared across the backend test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def simple_xsd_bytes() -> bytes:
    return (FIXTURES_DIR / "simple.xsd").read_bytes()


@pytest.fixture
def annotated_xsd_bytes() -> bytes:
    return (FIXTURES_DIR / "annotated.xsd").read_bytes()


@pytest.fixture
def library_xsd_bytes() -> bytes:
    return (FIXTURES_DIR / "library.xsd").read_bytes()


@pytest.fixture
def xxe_attack_bytes() -> bytes:
    return (FIXTURES_DIR / "xxe_attack.xsd").read_bytes()


@pytest.fixture
def billion_laughs_bytes() -> bytes:
    return (FIXTURES_DIR / "billion_laughs.xsd").read_bytes()
