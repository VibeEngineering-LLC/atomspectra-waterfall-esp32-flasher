from __future__ import annotations

import hashlib
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NamedTuple, Callable

import requests

CACHE_BASE = Path(os.environ.get("LOCALAPPDATA", "~/.cache")) / "atomspectra-flasher" / "cache"
GITHUB_API = "https://api.github.com/repos/{owner_repo}/releases/latest"
TIMEOUT = 30


class FirmwareAsset(NamedTuple):
    name: str
    url: str
    size: int
    sha256: str


class FirmwareRelease(NamedTuple):
    tag: str
    assets: tuple[FirmwareAsset, ...]
    body: str


class NetworkError(Exception):
    pass

class ReleaseNotFoundError(Exception):
    pass


def _parse_sha_from_body(body: str, filename: str) -> str | None:
    # Ищет строку вида "SHA256: <filename> <hash>"
    for line in body.splitlines():
        if line.startswith("SHA256:"):
            parts = line.strip().split()
            if len(parts) >= 3 and parts[1] == filename:
                return parts[2]
    return None


def fetch_latest_release(owner_repo: str) -> FirmwareRelease:
    url = GITHUB_API.format(owner_repo=owner_repo)
    try:
        response = requests.get(url, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise NetworkError(f"Network error while fetching release: {e}")

    if response.status_code == 404:
        raise ReleaseNotFoundError(f"Release not found for {owner_repo}")
    elif response.status_code == 403:
        raise NetworkError("Rate limit exceeded or access forbidden")
    elif not response.ok:
        raise NetworkError(f"HTTP error: {response.status_code} - {response.reason}")

    data = response.json()
    tag = data["tag_name"]
    body = data.get("body", "")

    assets = []
    for asset in data.get("assets", []):
        name = asset["name"]
        url = asset["browser_download_url"]
        size = asset["size"]
        sha256 = _parse_sha_from_body(body, name)
        assets.append(FirmwareAsset(name, url, size, sha256))

    return FirmwareRelease(tag, tuple(assets), body)


def get_cached_or_download(
    owner_repo: str,
    tag: str,
    asset: FirmwareAsset,
    progress_cb: Callable[[int, int], None] | None = None
) -> Path:
    cache_dir = CACHE_BASE / owner_repo.replace("/", "_") / tag
    cache_dir.mkdir(parents=True, exist_ok=True)
    bin_path = cache_dir / asset.name

    if bin_path.exists():
        # Проверяем SHA
        if _verify_sha(bin_path, asset.sha256):
            return bin_path
        else:
            # Удаляем старый файл
            bin_path.unlink()

    # Скачиваем
    tmp_path = bin_path.with_suffix(".tmp")
    try:
        _download(asset.url, tmp_path, asset.size, progress_cb)
        if not _verify_sha(tmp_path, asset.sha256):
            raise ValueError("SHA256 verification failed")
        shutil.move(tmp_path, bin_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    return bin_path


def _download(url: str, dest: Path, size: int, progress_cb: Callable[[int, int], None] | None) -> None:
    chunk_size = 65536
    downloaded = 0

    with requests.get(url, stream=True, timeout=TIMEOUT) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, size)


def _verify_sha(path: Path, expected: str) -> bool:
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest() == expected.lower()


def clear_cache(owner_repo: str | None = None):
    if owner_repo is None:
        # Очистить весь кэш
        shutil.rmtree(CACHE_BASE, ignore_errors=True)
    else:
        cache_dir = CACHE_BASE / owner_repo.replace("/", "_")
        shutil.rmtree(cache_dir, ignore_errors=True)