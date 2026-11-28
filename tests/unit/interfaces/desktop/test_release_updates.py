from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest

from power_fault_analyzer.interfaces.desktop.release_updates import (
    ReleaseUpdate,
    discover_latest_release,
    download_update_bundle,
    load_installation_build_info,
)


_REQUIRED = (
    "PFA-Windows-x64.zip",
    "SHA256SUMS.txt",
    "Update-PFA-Portable.ps1",
)


class _Response(io.BytesIO):
    def __init__(self, payload: bytes):
        super().__init__(payload)
        self.headers = {}


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
                "name": name,
                "browser_download_url": f"https://github.com/example/releases/download/{tag}/{name}",
            }
            for name in names
        ],
    }


def test_discover_latest_complete_release_including_prereleases():
    payload = [
        _release_payload("v0.1.0b2"),
        _release_payload("v0.1.0b3"),
        _release_payload("v0.2.0b1"),
        _release_payload("v9.0.0", include_all_assets=False),
        {**_release_payload("v10.0.0"), "draft": True},
    ]

    def opener(_request, timeout):
        assert timeout == 8.0
        return _Response(json.dumps(payload).encode("utf-8"))

    release = discover_latest_release("0.1.0b1", opener=opener)

    assert release is not None
    assert release.tag_name == "v0.2.0b1"
    assert release.version == "0.2.0b1"
    assert set(release.asset_urls) == set(_REQUIRED)


def test_discover_latest_release_returns_none_when_current_is_current():
    payload = [_release_payload("v0.1.0b2")]

    def opener(_request, timeout):
        return _Response(json.dumps(payload).encode("utf-8"))

    assert discover_latest_release("0.1.0b2", opener=opener) is None
    assert discover_latest_release("0.1.0b3", opener=opener) is None


def test_discover_latest_release_rejects_invalid_installed_version():
    with pytest.raises(ValueError, match="Installed PFA version is invalid"):
        discover_latest_release("not-a-version", opener=lambda *_args, **_kwargs: _Response(b"[]"))


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

    metadata = load_installation_build_info(tmp_path)

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

    assert load_installation_build_info(tmp_path) is None


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

    release = ReleaseUpdate(
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

    bundle = download_update_bundle(
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

    release = ReleaseUpdate(
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
        download_update_bundle(release, destination=tmp_path / "download", opener=opener)
