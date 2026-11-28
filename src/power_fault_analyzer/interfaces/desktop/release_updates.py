"""Discover and apply public portable Windows updates from GitHub Releases.

The desktop application only queries public release metadata.  Installation assets
are downloaded only after the user accepts an update, and every executable update
input is checked against the release's SHA-256 manifest before PowerShell is started.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

DEFAULT_REPOSITORY = "ValentinoAlvarado/POWER_FAULT_ANALYZER"
_REQUIRED_ASSETS = (
    "PFA-Windows-x64.zip",
    "SHA256SUMS.txt",
    "Update-PFA-Portable.ps1",
)
_DOWNLOAD_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ReleaseUpdate:
    """A published GitHub release containing a complete portable update bundle."""

    tag_name: str
    version: str
    name: str
    html_url: str
    published_at: str
    body: str
    asset_urls: dict[str, str]


@dataclass(frozen=True, slots=True)
class DownloadedUpdateBundle:
    """Verified local files required by the portable PowerShell updater."""

    directory: Path
    archive: Path
    checksum_manifest: Path
    updater_script: Path


def load_installation_build_info(
    install_directory: str | Path | None = None,
) -> dict[str, str] | None:
    """Read BUILD-INFO.json from a frozen portable build.

    Development checkouts intentionally return None: they have no isolated
    installation directory and must not offer to replace the user's source tree.
    """
    if install_directory is None:
        if not getattr(sys, "frozen", False):
            return None
        install_directory = Path(sys.executable).resolve().parent

    build_info_path = Path(install_directory) / "BUILD-INFO.json"
    try:
        metadata = json.loads(build_info_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(metadata, dict):
        return None

    version_value = metadata.get("version")
    try:
        if not isinstance(version_value, str) or not version_value.strip():
            return None
        Version(version_value.strip().removeprefix("v"))
    except InvalidVersion:
        return None

    if (
        metadata.get("product") != "POWER_FAULT_ANALYZER"
        or metadata.get("architecture") != "x64"
        or not isinstance(metadata.get("version"), str)
        or not isinstance(metadata.get("git_commit"), str)
        or not metadata["version"].strip()
        or not metadata["git_commit"].strip()
    ):
        return None
    return {
        "version": metadata["version"].strip(),
        "git_commit": metadata["git_commit"].strip(),
        "architecture": "x64",
    }


def _release_from_payload(
    payload: dict,
    *,
    repository: str = DEFAULT_REPOSITORY,
) -> ReleaseUpdate | None:
    if payload.get("draft"):
        return None

    tag_name = str(payload.get("tag_name", "")).strip()
    try:
        version = Version(tag_name.removeprefix("v"))
    except InvalidVersion:
        return None

    trusted_asset_prefix = f"/{repository}/releases/download/"
    assets: dict[str, str] = {}
    for asset in payload.get("assets", ()):
        name = str(asset.get("name", ""))
        url = str(asset.get("browser_download_url", ""))
        try:
            parsed_url = urlsplit(url)
        except ValueError:
            continue
        is_trusted_github_asset = (
            parsed_url.scheme == "https"
            and parsed_url.hostname == "github.com"
            and parsed_url.path.startswith(trusted_asset_prefix)
        )
        if name in _REQUIRED_ASSETS and is_trusted_github_asset:
            assets[name] = url
    if any(name not in assets for name in _REQUIRED_ASSETS):
        return None

    return ReleaseUpdate(
        tag_name=tag_name,
        version=str(version),
        name=str(payload.get("name") or tag_name),
        html_url=str(payload.get("html_url") or ""),
        published_at=str(payload.get("published_at") or ""),
        body=str(payload.get("body") or ""),
        asset_urls=assets,
    )


def discover_latest_release(
    current_version: str,
    *,
    repository: str = DEFAULT_REPOSITORY,
    timeout: float = 8.0,
    opener: Callable | None = None,
) -> ReleaseUpdate | None:
    """Return the newest compatible published release when it is newer.

    Prereleases are considered because PFA's published build channel currently
    uses beta versions. Drafts and incomplete releases are ignored. GitHub Actions
    workflow artifacts are deliberately excluded: only published Releases count.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Repository must use owner/name format.")
    try:
        installed_version = Version(current_version.removeprefix("v"))
    except InvalidVersion as exc:
        raise ValueError(f"Installed PFA version is invalid: {current_version!r}") from exc

    request = Request(
        f"https://api.github.com/repos/{repository}/releases?per_page=30",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "POWER-FAULT-ANALYZER-update-check",
        },
    )
    open_url = opener or urlopen
    with open_url(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    candidates = [
        release
        for item in payload
        if (release := _release_from_payload(item, repository=repository)) is not None
    ]
    if not candidates:
        return None
    latest = max(candidates, key=lambda item: Version(item.version))
    if Version(latest.version) <= installed_version:
        return None
    return latest


def _expected_hashes(checksum_manifest: Path) -> dict[str, str]:
    expected: dict[str, str] = {}
    for line in checksum_manifest.read_text(encoding="ascii").splitlines():
        match = re.match(r"^\s*([a-fA-F0-9]{64})\s+\*?(.+?)\s*$", line)
        if match:
            expected[Path(match.group(2)).name] = match.group(1).lower()
    return expected


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_DOWNLOAD_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_asset(
    url: str,
    destination: Path,
    *,
    timeout: float,
    opener: Callable,
    progress: Callable[[int], None] | None,
    asset_index: int,
    asset_count: int,
) -> None:
    request = Request(
        url,
        headers={"User-Agent": "POWER-FAULT-ANALYZER-update", "Accept": "application/octet-stream"},
    )
    with opener(request, timeout=timeout) as response, destination.open("wb") as output:
        raw_length = getattr(response, "headers", {}).get("Content-Length")
        total_length = int(raw_length) if raw_length and raw_length.isdigit() else 0
        downloaded = 0
        while chunk := response.read(_DOWNLOAD_CHUNK_SIZE):
            output.write(chunk)
            downloaded += len(chunk)
            if progress:
                fraction = downloaded / total_length if total_length else 0.0
                percent = int(((asset_index + min(fraction, 1.0)) / asset_count) * 100)
                progress(min(percent, 99))


def download_update_bundle(
    release: ReleaseUpdate,
    *,
    destination: str | Path | None = None,
    timeout: float = 60.0,
    opener: Callable | None = None,
    progress: Callable[[int], None] | None = None,
) -> DownloadedUpdateBundle:
    """Download the release ZIP, checksum manifest and updater; verify both scripts.

    The PowerShell updater repeats the ZIP check immediately before touching the
    installed application. The desktop client also verifies the updater script
    itself, because it is executable code downloaded from the release.
    """
    open_url = opener or urlopen
    owns_directory = destination is None
    directory = (
        Path(tempfile.mkdtemp(prefix="PFA-update-"))
        if owns_directory
        else Path(destination)
    )
    directory.mkdir(parents=True, exist_ok=True)

    archive = directory / "PFA-Windows-x64.zip"
    checksum = directory / "SHA256SUMS.txt"
    updater = directory / "Update-PFA-Portable.ps1"
    targets = (
        ("SHA256SUMS.txt", checksum),
        ("Update-PFA-Portable.ps1", updater),
        ("PFA-Windows-x64.zip", archive),
    )

    try:
        for index, (name, target) in enumerate(targets):
            url = release.asset_urls.get(name)
            if not url:
                raise ValueError(f"Release is missing required asset URL: {name}")
            _download_asset(
                url,
                target,
                timeout=timeout,
                opener=open_url,
                progress=progress,
                asset_index=index,
                asset_count=len(targets),
            )

        expected = _expected_hashes(checksum)
        for name, path in (
            ("PFA-Windows-x64.zip", archive),
            ("Update-PFA-Portable.ps1", updater),
        ):
            expected_hash = expected.get(name)
            if not expected_hash:
                raise ValueError(f"SHA256SUMS.txt has no entry for {name}.")
            actual_hash = _sha256(path)
            if actual_hash != expected_hash:
                raise ValueError(f"SHA-256 mismatch for {name}; update was not started.")

        if progress:
            progress(100)
        return DownloadedUpdateBundle(
            directory=directory,
            archive=archive,
            checksum_manifest=checksum,
            updater_script=updater,
        )
    except Exception:
        if owns_directory:
            shutil.rmtree(directory, ignore_errors=True)
        raise
