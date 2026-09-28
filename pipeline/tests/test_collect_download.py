from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx
import pytest

from fund_monitor.collect import download

URL = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_202608.zip"
AUGUST = "Wed, 26 Aug 2026 10:00:00 GMT"
SEPTEMBER = "Tue, 01 Sep 2026 10:00:00 GMT"


class FakeCvm:
    def __init__(self, body: bytes, modified: str | None) -> None:
        self.body = body
        self.modified = modified
        self.downloads = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            headers = {"content-length": str(len(self.body))}
            if self.modified is not None:
                headers["last-modified"] = self.modified
            return httpx.Response(200, headers=headers)
        self.downloads += 1
        return httpx.Response(200, content=self.body)


@pytest.fixture
def cvm(monkeypatch: pytest.MonkeyPatch) -> FakeCvm:
    fake = FakeCvm(b"first version", AUGUST)
    client = httpx.Client(transport=httpx.MockTransport(fake.handle))
    monkeypatch.setattr(httpx, "head", client.head)
    monkeypatch.setattr(httpx, "stream", client.stream)
    return fake


def test_first_download_stamps_last_modified(cvm: FakeCvm, tmp_path: Path) -> None:
    destination = tmp_path / "daily.zip"
    assert download.download_if_changed(URL, destination)
    assert destination.read_bytes() == b"first version"
    assert destination.stat().st_mtime == parsedate_to_datetime(AUGUST).timestamp()
    assert not destination.with_name("daily.zip.part").exists()


def test_unchanged_file_is_not_downloaded_again(cvm: FakeCvm, tmp_path: Path) -> None:
    destination = tmp_path / "daily.zip"
    download.download_if_changed(URL, destination)
    assert not download.download_if_changed(URL, destination)
    assert cvm.downloads == 1


def test_new_last_modified_downloads_again(cvm: FakeCvm, tmp_path: Path) -> None:
    destination = tmp_path / "daily.zip"
    download.download_if_changed(URL, destination)
    cvm.modified = SEPTEMBER
    assert download.download_if_changed(URL, destination)
    assert cvm.downloads == 2
    assert destination.stat().st_mtime == parsedate_to_datetime(SEPTEMBER).timestamp()


def test_new_size_downloads_again(cvm: FakeCvm, tmp_path: Path) -> None:
    destination = tmp_path / "daily.zip"
    download.download_if_changed(URL, destination)
    cvm.body = b"republished, longer version"
    assert download.download_if_changed(URL, destination)
    assert destination.read_bytes() == b"republished, longer version"


def test_missing_last_modified_always_downloads(cvm: FakeCvm, tmp_path: Path) -> None:
    destination = tmp_path / "daily.zip"
    cvm.modified = None
    assert download.download_if_changed(URL, destination)
    assert download.download_if_changed(URL, destination)
    assert cvm.downloads == 2
