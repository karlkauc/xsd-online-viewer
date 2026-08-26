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


@pytest.fixture
def vc_versioning_xsd_bytes() -> bytes:
    return (FIXTURES_DIR / "vc-versioning.xsd").read_bytes()


@pytest.fixture
def assertions_xsd_bytes() -> bytes:
    return (FIXTURES_DIR / "assertions.xsd").read_bytes()


@pytest.fixture
def alternatives_xsd_bytes() -> bytes:
    return (FIXTURES_DIR / "alternatives.xsd").read_bytes()


@pytest.fixture
def open_content_xsd_bytes() -> bytes:
    return (FIXTURES_DIR / "open-content.xsd").read_bytes()


@pytest.fixture
def inheritable_and_all_xsd_bytes() -> bytes:
    return (FIXTURES_DIR / "inheritable-and-all.xsd").read_bytes()


@pytest.fixture
def override_xsd_bytes() -> bytes:
    return (FIXTURES_DIR / "override.xsd").read_bytes()


@pytest.fixture
def override_base_xsd_bytes() -> bytes:
    return (FIXTURES_DIR / "override-base.xsd").read_bytes()


@pytest.fixture
def xmldsig_bytes() -> bytes:
    return (FIXTURES_DIR / "xmldsig-core-schema.xsd").read_bytes()
