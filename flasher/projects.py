from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class FlashSegment:
    offset: int
    path: Path


@dataclass(frozen=True)
class Project:
    key: str
    title: str
    chip: str
    flash_mode: str
    flash_freq: str
    flash_size: str
    before: str
    after: str
    stub: bool
    segments: tuple[FlashSegment, ...]
    next_steps: str = ""

    # Новые поля
    github_repo: str = ""
    factory_asset_name: str = "firmware.factory.bin"
    segments_from_factory: bool = False

    def resolve(self, bin_path: Path) -> tuple[FlashSegment, ...]:
        if self.segments_from_factory:
            return (FlashSegment(0x0, bin_path),)
        else:
            return self.segments


# Реестр проектов
PROJECT_REGISTRY = {
    "atomspectra-waterfall-esp32": Project(
        key="atomspectra-waterfall-esp32",
        title="AtomSpectra (водопад ESP32-S3)",
        chip="esp32s3",
        flash_mode="dio",
        flash_freq="80m",
        flash_size="detect",
        before="default_reset",
        after="hard_reset",
        stub=True,
        segments=(),  # Будет заменён в resolve
        github_repo="VibeEngineering-LLC/atomspectra-waterfall-esp32",
        factory_asset_name="firmware.factory.bin",
        segments_from_factory=True,
    ),
    "atomfast-gateway": Project(
        key="atomfast-gateway",
        title="AtomFast BLE Gateway (ESP32)",
        chip="esp32",
        flash_mode="dio",
        flash_freq="40m",
        flash_size="detect",
        before="default_reset",
        after="hard_reset",
        stub=True,
        segments=(),  # Будет заменён в resolve
        github_repo="VibeEngineering-LLC/atomfast-esp32",
        factory_asset_name="firmware.factory.bin",
        segments_from_factory=True,
    ),
    "radex-gateway": Project(
        key="radex-gateway",
        title="Radex BLE Gateway (ESP32-S3)",
        chip="esp32s3",
        flash_mode="dio",
        flash_freq="80m",
        flash_size="detect",
        before="default_reset",
        after="hard_reset",
        stub=True,
        segments=(),  # Будет заменён в resolve
        github_repo="VibeEngineering-LLC/radex-esp32",
        factory_asset_name="firmware.factory.bin",
        segments_from_factory=True,
    ),
    "radon-gateway": Project(
        key="radon-gateway",
        title="RadonEye BLE Gateway (ESP32)",
        chip="esp32",
        flash_mode="dio",
        flash_freq="40m",
        flash_size="detect",
        before="default_reset",
        after="hard_reset",
        stub=True,
        segments=(),  # Будет заменён в resolve
        github_repo="VibeEngineering-LLC/radoneye-esp32",
        factory_asset_name="firmware.factory.bin",
        segments_from_factory=True,
    ),
}


def all_projects() -> list[Project]:
    return list(PROJECT_REGISTRY.values())