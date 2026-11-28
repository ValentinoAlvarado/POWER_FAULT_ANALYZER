from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest

from power_fault_analyzer.interfaces.desktop import release_updates

_REQUIRED = (
    "PFA-Windows-x64.zip",
    "SHA256SUMS.txt",
    "Update-PFA-Portable.ps1",
)


class _Response(io.BytesIO):
    def __init__(self, payload: bytes, *, headers: dict[str, str] | None = None):
        super().__init__(payload)
        self.headers = headers or {}


def _release_payload(tag: str = "v0.1.0b2", *, include_all_assets: bool = True) -> dict:
    names = _REQUIRED if include_all_assets else _REQUIRED[:-1]
    return {
        "tag_name": tag,
        "name": f"POWER_FAULT_ANALYZER {tag}",
        "draft": False,
        "prerelease": True,
        "published_at": "2026-11-28T00:00:00Z",
        "html_url": f"https://github.com/ValentinoAlvarado/POWER_FAULT_ANALYZER/releases/tag/{tag}",
        "body": "Update notes",
        "assets": [
            {
                "id": 1000 + index,
                "name": name,
                "browser_download_url": f"https://github.com/ValentinoAlvarado/POWER_FAULT_ANALYZER/releases/download/{tag}/{name}",
            }
            for index, name in enumerate(names)
        ],
    }


def test_discover_latest_complete_release_including_prereleases():
    payload = [
        _release_payload("v0.1.0b2"),
        _release_payload("v0.1.0b3"),
        _release_payload("v0.2.0b1"),
        _release_payload("v9.0.0", include_all_assets=False),
        {
            **_release_payload("v8.0.0"),
            "assets": [
                {
                    **asset,
                    "browser_download_url": asset["browser_download_url"].replace(
                        "https://github.com/ValentinoAlvarado/POWER_FAULT_ANALYZER",
                        "https://updates.example.test",
                    ),
                }
                for asset in _release_payload("v8.0.0")["assets"]
            ],
        },
        {**_release_payload("v10.0.0"), "draft": True},
    ]

    def opener(_request, timeout):
        assert timeout == 8.0
        return _Response(json.dumps(payload).encode("utf-8"))

    release = release_updates.discover_latest_release("0.1.0b1", opener=opener)

    assert release is not None
    assert release.tag_name == "v0.2.0b1"
    assert release.version == "0.2.0b1"
    assert set(release.asset_urls) == set(_REQUIRED)
    assert set(release.asset_api_urls) == set(_REQUIRED)
    assert release.asset_api_urls["SHA256SUMS.txt"].endswith("/releases/assets/1001")


def test_discover_latest_release_returns_none_when_current_is_current():
    payload = [_release_payload("v0.1.0b2")]

    def opener(_request, timeout):
        return _Response(json.dumps(payload).encode("utf-8"))

    assert release_updates.discover_latest_release("0.1.0b2", opener=opener) is None
    assert release_updates.discover_latest_release("0.1.0b3", opener=opener) is None


def test_discover_latest_release_rejects_invalid_installed_version():
    with pytest.raises(ValueError, match="Installed PFA version is invalid"):
        release_updates.discover_latest_release("not-a-version", opener=lambda *_args, **_kwargs: _Response(b"[]"))


def test_load_installation_build_info_requires_matching_portable_metadata(tmp_path: Path):
    (tmp_path / "BUILD-INFO.json").write_text(
        json.dumps(
            {
                "product": "POWER_FAULT_ANALYZER",
                "version": "0.1.0b1",
                "architecture": "x64",
                "git_commit": "a" * 40,
            }
        ),
        encoding="utf-8",
    )

    metadata = release_updates.load_installation_build_info(tmp_path)

    assert metadata == {
        "version": "0.1.0b1",
        "git_commit": "a" * 40,
        "architecture": "x64",
    }


def test_load_installation_build_info_rejects_wrong_product(tmp_path: Path):
    (tmp_path / "BUILD-INFO.json").write_text(
        json.dumps(
            {
                "product": "OTHER",
                "version": "0.1.0b1",
                "architecture": "x64",
                "git_commit": "a" * 40,
            }
        ),
        encoding="utf-8",
    )

    assert release_updates.load_installation_build_info(tmp_path) is None



@pytest.mark.parametrize(
    "payload",
    [
        "[]",
        "null",
        "{not-json",
        json.dumps(
            {
                "product": "POWER_FAULT_ANALYZER",
                "version": "not-a-version",
                "architecture": "x64",
                "git_commit": "a" * 40,
            }
        ),
    ],
)
def test_load_installation_build_info_ignores_invalid_metadata(
    tmp_path: Path, payload: str
):
    (tmp_path / "BUILD-INFO.json").write_text(payload, encoding="utf-8")

    assert release_updates.load_installation_build_info(tmp_path) is None


def test_download_update_bundle_verifies_archive_and_updater_hashes(tmp_path: Path):
    archive_bytes = b"portable update archive bytes"
    updater_bytes = b"Write-Host 'verified updater'"
    checksum_bytes = (
        f"{hashlib.sha256(archive_bytes).hexdigest()}  PFA-Windows-x64.zip\n"
        f"{hashlib.sha256(updater_bytes).hexdigest()}  Update-PFA-Portable.ps1\n"
    ).encode("ascii")
    contents = {
        "https://example.test/SHA256SUMS.txt": checksum_bytes,
        "https://example.test/Update-PFA-Portable.ps1": updater_bytes,
        "https://example.test/PFA-Windows-x64.zip": archive_bytes,
    }
    progress: list[int] = []

    def opener(request, timeout):
        assert timeout == 60.0
        return _Response(contents[request.full_url])

    release = release_updates.ReleaseUpdate(
        tag_name="v0.1.0b2",
        version="0.1.0b2",
        name="PFA update",
        html_url="https://github.com/example/release",
        published_at="2026-11-28T00:00:00Z",
        body="",
        asset_urls={
            name: f"https://example.test/{name}"
            for name in _REQUIRED
        },
    )

    bundle = release_updates.download_update_bundle(
        release,
        destination=tmp_path / "download",
        opener=opener,
        progress=progress.append,
    )

    assert bundle.archive.read_bytes() == archive_bytes
    assert bundle.updater_script.read_bytes() == updater_bytes
    assert bundle.checksum_manifest.read_bytes() == checksum_bytes
    assert progress[-1] == 100


def test_download_update_bundle_rejects_modified_updater_script(tmp_path: Path):
    archive_bytes = b"portable update archive bytes"
    checksum_bytes = (
        f"{hashlib.sha256(archive_bytes).hexdigest()}  PFA-Windows-x64.zip\n"
        f"{'0' * 64}  Update-PFA-Portable.ps1\n"
    ).encode("ascii")
    contents = {
        "https://example.test/SHA256SUMS.txt": checksum_bytes,
        "https://example.test/Update-PFA-Portable.ps1": b"modified updater",
        "https://example.test/PFA-Windows-x64.zip": archive_bytes,
    }

    def opener(request, timeout):
        return _Response(contents[request.full_url])

    release = release_updates.ReleaseUpdate(
        tag_name="v0.1.0b2",
        version="0.1.0b2",
        name="PFA update",
        html_url="https://github.com/example/release",
        published_at="2026-11-28T00:00:00Z",
        body="",
        asset_urls={
            name: f"https://example.test/{name}"
            for name in _REQUIRED
        },
    )

    with pytest.raises(ValueError, match="SHA-256 mismatch for Update-PFA-Portable.ps1"):
        release_updates.download_update_bundle(release, destination=tmp_path / "download", opener=opener)


def test_download_update_bundle_falls_back_when_github_asset_api_returns_empty_body(
    tmp_path: Path,
):
    archive_bytes = b"portable update archive bytes"
    updater_bytes = b"Write-Host 'verified updater'"
    checksum_bytes = (
        f"{hashlib.sha256(archive_bytes).hexdigest()}  PFA-Windows-x64.zip\n"
        f"{hashlib.sha256(updater_bytes).hexdigest()}  Update-PFA-Portable.ps1\n"
    ).encode("ascii")
    browser_urls = {
        "SHA256SUMS.txt": "https://github.com/example/release/SHA256SUMS.txt",
        "Update-PFA-Portable.ps1": "https://github.com/example/release/Update-PFA-Portable.ps1",
        "PFA-Windows-x64.zip": "https://github.com/example/release/PFA-Windows-x64.zip",
    }
    api_urls = {
        name: f"https://api.github.com/repos/example/repo/releases/assets/{index}"
        for index, name in enumerate(_REQUIRED, start=1)
    }
    contents = {
        browser_urls["SHA256SUMS.txt"]: checksum_bytes,
        browser_urls["Update-PFA-Portable.ps1"]: updater_bytes,
        browser_urls["PFA-Windows-x64.zip"]: archive_bytes,
        api_urls["SHA256SUMS.txt"]: b"",
        api_urls["Update-PFA-Portable.ps1"]: updater_bytes,
        api_urls["PFA-Windows-x64.zip"]: archive_bytes,
    }
    requests: list[str] = []

    def opener(request, timeout):
        requests.append(request.full_url)
        payload = contents[request.full_url]
        return _Response(payload, headers={"Content-Length": str(len(payload))})

    release = release_updates.ReleaseUpdate(
        tag_name="v0.1.0b3",
        version="0.1.0b3",
        name="PFA update",
        html_url="https://github.com/example/release",
        published_at="2026-11-28T00:00:00Z",
        body="",
        asset_urls=browser_urls,
        asset_api_urls=api_urls,
    )

    bundle = release_updates.download_update_bundle(
        release,
        destination=tmp_path / "download",
        opener=opener,
    )

    assert bundle.checksum_manifest.read_bytes() == checksum_bytes
    assert bundle.updater_script.read_bytes() == updater_bytes
    assert bundle.archive.read_bytes() == archive_bytes
    assert requests[:2] == [
        api_urls["SHA256SUMS.txt"],
        browser_urls["SHA256SUMS.txt"],
    ]


def test_download_update_bundle_rejects_empty_or_truncated_asset(tmp_path: Path):
    release = release_updates.ReleaseUpdate(
        tag_name="v0.1.0b3",
        version="0.1.0b3",
        name="PFA update",
        html_url="https://github.com/example/release",
        published_at="2026-11-28T00:00:00Z",
        body="",
        asset_urls={name: f"https://example.test/{name}" for name in _REQUIRED},
    )

    def empty_opener(_request, timeout):
        return _Response(b"")

    with pytest.raises(OSError, match="non-empty GitHub release asset"):
        release_updates.download_update_bundle(
            release,
            destination=tmp_path / "empty-download",
            opener=empty_opener,
        )
    assert not (tmp_path / "empty-download" / "SHA256SUMS.txt").exists()

    def truncated_opener(_request, timeout):
        return _Response(b"short", headers={"Content-Length": "100"})

    with pytest.raises(OSError, match="truncated release asset"):
        release_updates._download_asset(
            "https://example.test/truncated",
            tmp_path / "truncated.bin",
            timeout=1.0,
            opener=truncated_opener,
            progress=None,
            asset_index=0,
            asset_count=1,
        )
    assert not (tmp_path / "truncated.bin").exists()
