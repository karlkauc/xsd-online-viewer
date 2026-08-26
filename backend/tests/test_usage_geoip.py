from __future__ import annotations

import io
import tarfile
from pathlib import Path

import httpx
import pytest

from app.usage.geoip import EDITION, GeoIp, download_database


def _tarball(payload: bytes = b"fake-mmdb") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(f"{EDITION}_20260825/{EDITION}.mmdb")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def test_download_extracts_mmdb(tmp_path: Path) -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, content=_tarball())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dest = tmp_path / "geo" / f"{EDITION}.mmdb"
    assert download_database("KEY", dest, client=client) == dest
    assert dest.read_bytes() == b"fake-mmdb"
    assert seen["params"] == {"edition_id": EDITION, "license_key": "KEY", "suffix": "tar.gz"}


def test_download_http_error(tmp_path: Path) -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    with pytest.raises(httpx.HTTPStatusError):
        download_database("BAD", tmp_path / "x.mmdb", client=client)


def test_missing_file_and_no_key_is_inert(tmp_path: Path) -> None:
    geo = GeoIp(str(tmp_path / "missing.mmdb"), "")
    geo.start()
    assert geo.ready is False
    assert geo.country("8.8.8.8") is None
    geo.close()


def test_unreadable_file_is_inert(tmp_path: Path) -> None:
    path = tmp_path / "bad.mmdb"
    path.write_bytes(b"not a database")
    geo = GeoIp(str(path), "")
    geo.start()
    assert geo.ready is False and geo.country("8.8.8.8") is None


def test_country_lookup_with_stub_reader() -> None:
    class Country:
        iso_code = "AT"

    class Result:
        country = Country()

    class Reader:
        def country(self, ip: str) -> Result:
            if ip.startswith("10."):
                raise ValueError("private")
            return Result()

        def close(self) -> None:
            pass

    geo = GeoIp("/nonexistent", "")
    geo._reader = Reader()
    assert geo.country("1.2.3.4") == "AT"
    assert geo.country("10.0.0.1") is None
    assert geo.country(None) is None
    geo.close()
    assert geo.ready is False
