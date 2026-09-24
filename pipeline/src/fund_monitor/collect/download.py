import logging
import os
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


def download_file(url: str, destination: Path, timeout_seconds: float = 300.0) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    with httpx.stream("GET", url, timeout=timeout_seconds, follow_redirects=True) as response:
        response.raise_for_status()
        with partial.open("wb") as file:
            for chunk in response.iter_bytes():
                file.write(chunk)
    partial.replace(destination)
    logger.info("downloaded %s (%d bytes) to %s", url, destination.stat().st_size, destination)
    return destination


def remote_signature(url: str) -> tuple[int | None, float | None]:
    response = httpx.head(url, timeout=60.0, follow_redirects=True)
    response.raise_for_status()
    length = response.headers.get("content-length")
    modified = response.headers.get("last-modified")
    return (
        int(length) if length else None,
        parsedate_to_datetime(modified).timestamp() if modified else None,
    )


def is_current(destination: Path, length: int | None, modified: float | None) -> bool:
    if length is None or modified is None or not destination.exists():
        return False
    stat = destination.stat()
    return stat.st_size == length and stat.st_mtime == modified


def download_if_changed(url: str, destination: Path) -> bool:
    length, modified = remote_signature(url)
    if is_current(destination, length, modified):
        logger.info("unchanged since last download: %s", destination.name)
        return False
    download_file(url, destination)
    if modified is not None:
        os.utime(destination, (modified, modified))
    return True
