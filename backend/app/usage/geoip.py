"""Country lookup via MaxMind GeoLite2-Country (optional).

The database is *not* shipped in the image (GeoLite2 EULA). At startup:
  * if ``db_path`` exists, it is opened directly (docker-compose / dev);
  * else if a licence key is configured, the ~6 MB tarball is downloaded in a
    background thread and opened once ready;
  * else lookups return ``None`` and ``country_code`` stays NULL.

Attribution: "This product includes GeoLite2 data created by MaxMind,
available from https://www.maxmind.com."
"""

from __future__ import annotations

import io
import logging
import tarfile
import threading
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DOWNLOAD_URL = "https://download.maxmind.com/app/geoip_download"
EDITION = "GeoLite2-Country"


def download_database(license_key: str, dest: Path, *, client: httpx.Client | None = None) -> Path:
    """Fetch the GeoLite2-Country tarball and extract the .mmdb to ``dest``."""
    params = {"edition_id": EDITION, "license_key": license_key, "suffix": "tar.gz"}
    own_client = client is None
    client = client or httpx.Client(timeout=60.0, follow_redirects=True)
    try:
        response = client.get(DOWNLOAD_URL, params=params)
        response.raise_for_status()
        data = response.content
    finally:
        if own_client:
            client.close()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        member = next((m for m in archive.getmembers() if m.name.endswith(f"{EDITION}.mmdb")), None)
        if member is None:
            raise ValueError(f"{EDITION}.mmdb not found in MaxMind archive")
        extracted = archive.extractfile(member)
        if extracted is None:
            raise ValueError("MaxMind archive member is not a regular file")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(extracted.read())
        tmp.replace(dest)
    return dest


class GeoIp:
    def __init__(self, db_path: str, license_key: str = "") -> None:
        self._path = Path(db_path) if db_path else None
        self._key = license_key.strip()
        self._reader: Any = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @property
    def ready(self) -> bool:
        return self._reader is not None

    def start(self) -> None:
        if self._path is None:
            return
        if self._path.is_file():
            self._open()
            return
        if not self._key:
            logger.info("geoip: no database and no MAXMIND_LICENSE_KEY; country_code stays NULL")
            return
        self._thread = threading.Thread(target=self._download_and_open, name="geoip-download", daemon=True)
        self._thread.start()

    def close(self) -> None:
        with self._lock:
            reader, self._reader = self._reader, None
        if reader is not None:
            reader.close()

    def country(self, ip: str | None) -> str | None:
        reader = self._reader
        if reader is None or not ip:
            return None
        try:
            return reader.country(ip).country.iso_code
        except Exception:  # noqa: BLE001 - AddressNotFound, private IPs, malformed
            return None

    # -- internals ----------------------------------------------------------

    def _download_and_open(self) -> None:
        assert self._path is not None
        try:
            download_database(self._key, self._path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("geoip: download failed; country_code stays NULL: %r", exc)
            return
        self._open()

    def _open(self) -> None:
        try:
            import geoip2.database

            reader = geoip2.database.Reader(str(self._path))
        except Exception as exc:  # noqa: BLE001
            logger.warning("geoip: cannot open %s: %r", self._path, exc)
            return
        with self._lock:
            self._reader = reader
        logger.info("geoip: database ready", extra={"ctx_path": str(self._path)})
