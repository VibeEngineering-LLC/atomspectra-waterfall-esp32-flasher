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

    # Опциональный шаг: грациозный ребут платы по сети (HTTP) ПЕРЕД
    # аппаратным сбросом esptool — плата успевает дописать/закрыть открытый
    # сегмент водопада. Есть только у прошивки atomspectra-waterfall-esp32
    # (эндпоинты /api/csrf-token + /api/reboot-esp), у ESPHome-шлюзов нет.
    pre_flash_http_reboot: bool = False

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
        pre_flash_http_reboot=True,
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
    # Radex MR107ion (радон) через BLE. Прошивка ESPHome, плата
    # ESP32-S3-DevKitC-1 N16R8 (16 MB флеша, 8 MB PSRAM) - та же, что у
    # водопада AtomSpectra. MAC прибора в бинарник не зашит: плата ищет
    # Radex в эфире сама, поэтому один общий образ годится всем.
    "radex-gateway": Project(
        key="radex-gateway",
        title="Radex BLE Gateway (ESP32-S3 N16R8)",
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
        next_steps="Прошивка не знает ни вашей сети, ни адреса прибора - и то, и другое настраивается после заливки, пересобирать ничего не нужно.\n1. Плата поднимает свою точку доступа 'radex-gw-s3 Fallback' (пароль radexgw123). Подключитесь к ней с телефона или ноутбука.\n2. Откроется страница настройки (если нет - зайдите на http://192.168.4.1). Выберите домашнюю сеть Wi-Fi и введите пароль.\n3. Плата перезагрузится и войдёт в вашу сеть. Web UI - http://radex-gw-s3.local/ (логин и пароль по умолчанию: radex / radex).\n4. Включите Radex MR107ion рядом с платой. Прибор находится в эфире сам - следите за полем 'Найденный прибор Radex' в Web UI. Если приборов несколько, впишите нужный MAC вручную и нажмите 'Применить MAC и перезагрузить'.\nВыгрузка на Народмон выключена и включается только вручную.",
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
    "bdkg05-gateway": Project(
        key="bdkg05-gateway", title="ATOMTEX БДКГ-05 USB Gateway (ESP32-S3)",
        chip="esp32s3", flash_mode="dio", flash_freq="80m", flash_size="detect",
        before="default_reset", after="hard_reset", stub=True, segments=(),
        github_repo="VibeEngineering-LLC/atomtex-esp32",
        factory_asset_name="firmware.factory.bin", segments_from_factory=True,
    ),
}


def all_projects() -> list[Project]:
    return list(PROJECT_REGISTRY.values())